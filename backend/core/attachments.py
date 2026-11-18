"""Private file storage, bounded validation and current domain authorization."""

import hashlib
import io
import re
import shlex
import subprocess
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .exceptions import Conflict
from .models import (
    Announcement, Attachment, Case, CaseNotice, CommunityCard, Credential, Event,
    Project, User, WorkItem,
)
from .policy import (
    active_actor, api_narrow, can_manage_case, can_manage_org, can_manage_project,
    can_open_case, can_read_case, can_read_project, can_read_project_detail, can_read_work, can_update_work,
    manager_scope_ids, visible_announcements, visible_cards, visible_credentials,
)
from .services import audit


RESOURCE_MODELS = {
    "project": Project,
    "work": WorkItem,
    "case": Case,
    "case_notice": CaseNotice,
    "announcement": Announcement,
    "community": CommunityCard,
    "event": Event,
    "credential": Credential,
}
OFFICE_TYPES = {
    ".docx": ("word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ("xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".pptx": ("ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
}


def _current_actor(actor):
    """Do not allow an already loaded user object to outlive account revocation."""
    if not active_actor(actor):
        raise PermissionDenied("Etkin kullanıcı oturumu gerekir.")
    current = User.objects.select_related("primary_org").filter(pk=actor.pk, is_active=True).first()
    if current is None:
        raise PermissionDenied("Kullanıcı hesabı etkin değil.")
    for attr in ("_api_client", "_god_mode", "_real_actor"):
        if hasattr(actor, attr):
            setattr(current, attr, getattr(actor, attr))
    return current


def resource_for_actor(actor, resource_type, resource_id, *, write=False, initial=False):
    """Resolve upload ownership from its domain; no grant comes from an upload ID."""
    actor = _current_actor(actor)
    model = RESOURCE_MODELS.get(resource_type)
    try:
        resource_id = uuid.UUID(str(resource_id))
    except (ValueError, TypeError, AttributeError):
        raise NotFound("Kayıt bulunamadı.")
    if not model:
        raise NotFound("Kayıt bulunamadı.")
    obj = model.objects.filter(pk=resource_id).first()
    allowed = False
    if obj is None:
        raise NotFound("Kayıt bulunamadı.")
    if resource_type == "project":
        allowed = can_read_project(actor, obj) and can_read_project_detail(actor, obj)
        if write:
            allowed = allowed and (
                obj.created_by_id == actor.pk and obj.status in ("DRAFT", "REVISION")
                or can_manage_project(actor, obj)
            )
    elif resource_type == "work":
        allowed = can_read_work(actor, obj)
        if obj.context == "PROJECT_TASK":
            allowed = allowed and can_read_project_detail(actor, obj.project)
        if write:
            allowed = allowed and can_update_work(actor, obj)
    elif resource_type == "case":
        allowed = can_read_case(actor, obj)
        if write:
            allowed = allowed and can_manage_case(actor, obj)
            # Opening a delegated case may name a coordinator from another
            # managed unit. The authorized create can claim its own staged
            # files without granting the creator subsequent read access.
            allowed = allowed or bool(
                initial and obj.version == 1 and obj.created_by_id == actor.pk
                and can_open_case(actor, obj.owner_org_id)
                and obj.coordinator.is_active
                and can_manage_org(actor, obj.coordinator.primary_org_id)
            )
    elif resource_type == "case_notice":
        allowed = api_narrow(actor, model.objects.filter(pk=obj.pk)).filter(
            Q(created_by=actor) | Q(owner_org_id__in=manager_scope_ids(actor))
        ).exists()
        if write:
            allowed = allowed and obj.status == "PENDING"
    elif resource_type == "announcement":
        allowed = visible_announcements(actor).filter(pk=obj.pk).exists()
        if write:
            allowed = allowed and obj.status == "DRAFT" and (
                obj.created_by_id == actor.pk or can_manage_org(actor, obj.owner_org_id)
            )
    elif resource_type == "community":
        allowed = visible_cards(actor).filter(pk=obj.pk).exists()
        if write:
            allowed = allowed and obj.status == "DRAFT" and (
                obj.created_by_id == actor.pk or can_manage_org(actor, obj.owner_org_id)
            )
    elif resource_type == "event":
        allowed = api_narrow(actor, model.objects.filter(pk=obj.pk)).filter(
            Q(invitees=actor) | Q(owner_org_id__in=manager_scope_ids(actor))
        ).exists()
        if write:
            allowed = allowed and can_manage_org(actor, obj.owner_org_id)
    elif resource_type == "credential":
        allowed = visible_credentials(actor).filter(pk=obj.pk).exists()
        if write:
            allowed = allowed and (obj.user_id == actor.pk or can_manage_org(actor, obj.user.primary_org_id))
    if not allowed:
        raise NotFound("Kayıt bulunamadı.")
    return obj


def attachment_data(item):
    return {
        "id": str(item.pk), "name": item.name, "size": item.size,
        "content_type": item.content_type, "status": item.status,
        "scan_status": item.scan_status,
        "created_at": item.created_at.isoformat(),
    }


def _safe_name(name):
    name = str(name or "dosya").replace("\\", "/").split("/")[-1]
    name = "".join(character for character in name if character.isprintable()).strip(" .")
    suffix = Path(name).suffix.lower()
    stem = name[: -len(suffix)] if suffix else name
    return (stem[: max(1, 180 - len(suffix))] + suffix) or "dosya"


def _validate_office(raw, suffix):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 2000 or sum(item.file_size for item in infos) > 50 * 1024 * 1024:
                raise ValueError()
            names = set()
            for item in infos:
                name = item.filename
                if item.flag_bits & 1 or name.startswith(("/", "\\")) or "\\" in name or ".." in PurePosixPath(name).parts:
                    raise ValueError()
                if "vbaproject" in name.lower() or name.lower().endswith((".exe", ".dll", ".js", ".vbs", ".bat", ".ps1")):
                    raise ValueError()
                names.add(name)
            required, mime = OFFICE_TYPES[suffix]
            if "[Content_Types].xml" not in names or required not in names:
                raise ValueError()
            if archive.testzip() is not None:
                raise ValueError()
            return mime
    except (ValueError, OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError):
        raise ValidationError({"file": "Geçerli ve makro içermeyen bir Office dosyası seçin."})


def validate_upload(upload):
    if upload is None or not hasattr(upload, "chunks"):
        raise ValidationError({"file": "Bir dosya seçin."})
    limit = settings.ONECS_UPLOAD_MAX_BYTES
    if getattr(upload, "size", 0) > limit:
        raise ValidationError({"file": "Dosya en fazla 10 MB olabilir."})
    chunks, size = [], 0
    for chunk in upload.chunks():
        size += len(chunk)
        if size > limit:
            raise ValidationError({"file": "Dosya en fazla 10 MB olabilir."})
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise ValidationError({"file": "Boş dosya yüklenemez."})
    name = _safe_name(upload.name)
    suffix = Path(name).suffix.lower()
    mime = None
    if suffix == ".png" and raw.startswith(b"\x89PNG\r\n\x1a\n") and len(raw) > 32 and raw[12:16] == b"IHDR" and b"IEND" in raw[-16:]:
        mime = "image/png"
    elif suffix in (".jpg", ".jpeg") and raw.startswith(b"\xff\xd8\xff") and raw.rstrip().endswith(b"\xff\xd9"):
        mime = "image/jpeg"
    elif suffix == ".webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP" and len(raw) >= 20:
        mime = "image/webp"
    elif suffix == ".pdf" and raw.startswith(b"%PDF-") and b"%%EOF" in raw[-1024:]:
        mime = "application/pdf"
    elif suffix in (".txt", ".csv"):
        try:
            decoded = raw.decode("utf-8-sig")
            if any(ord(character) < 32 and character not in "\r\n\t" for character in decoded):
                raise ValueError()
            if re.search(r"<\s*(?:!doctype\s+html|html\b|script\b|svg\b)", decoded, re.I):
                raise ValueError()
        except (UnicodeError, ValueError):
            raise ValidationError({"file": "UTF-8 biçiminde düz metin veya CSV seçin."})
        mime = "text/plain" if suffix == ".txt" else "text/csv"
    elif suffix in OFFICE_TYPES and raw.startswith(b"PK\x03\x04"):
        mime = _validate_office(raw, suffix)
    if mime is None:
        raise ValidationError({"file": "Dosya türü veya içeriği uygun değil. PNG, JPEG, WebP, PDF, TXT, CSV, DOCX, XLSX veya PPTX seçin."})
    # Browser MIME declarations are untrusted. Verify against the detected type,
    # while accepting generic binary declarations from common file pickers.
    supplied = (getattr(upload, "content_type", "") or "").split(";", 1)[0].strip().lower()
    aliases = {"image/jpg": "image/jpeg", "text/plain": "text/csv" if suffix == ".csv" else "text/plain"}
    if supplied not in ("", "application/octet-stream") and aliases.get(supplied, supplied) != mime:
        raise ValidationError({"file": "Dosya uzantısı, türü ve içeriği eşleşmiyor."})
    return name, raw, mime


def private_path(storage_key):
    """Only opaque, server-created keys may address the private root."""
    if not re.fullmatch(r"[a-f0-9]{2}/[a-f0-9]{32}", storage_key):
        raise NotFound("Dosya bulunamadı.")
    root = Path(settings.ONECS_UPLOAD_ROOT).resolve()
    path = (root / storage_key).resolve()
    if root not in path.parents:
        raise NotFound("Dosya bulunamadı.")
    return path


def unscanned_allowed():
    return bool(settings.ONECS_UPLOAD_ALLOW_UNSCANNED and (settings.DEBUG or settings.ONECS_ENV in ("test", "demo")) and settings.ONECS_ENV != "production")


def scan_file(path):
    command = settings.ONECS_UPLOAD_SCANNER_COMMAND
    if not command:
        return ("READY", "unscanned") if unscanned_allowed() else ("PENDING_SCAN", "pending")
    try:
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        result = subprocess.run(
            [*argv, str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=settings.ONECS_UPLOAD_SCANNER_TIMEOUT,
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return "PENDING_SCAN", "error"
    if result.returncode == 0:
        return "READY", "clean"
    if result.returncode == 1:
        return "REJECTED", "infected"
    return "PENDING_SCAN", "error"


def stage_upload(actor, upload, request_key=None):
    actor = _current_actor(actor)
    name, raw, content_type = validate_upload(upload)
    digest = hashlib.sha256(raw).hexdigest()
    if request_key:
        try:
            request_key = uuid.UUID(str(request_key))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError("X-Request-ID UUID olmalıdır.")
    path = None
    try:
        with transaction.atomic():
            # Serialize staged quota and same-user upload retries.
            User.objects.select_for_update().get(pk=actor.pk, is_active=True)
            if request_key:
                existing = Attachment.objects.filter(uploaded_by=actor, upload_key=request_key).first()
                if existing:
                    if existing.sha256 != digest or existing.name != name or existing.content_type != content_type:
                        raise Conflict("Aynı yükleme anahtarı farklı dosyayla kullanılamaz.")
                    if existing.resource_id:
                        resource_for_actor(actor, existing.resource_type, existing.resource_id)
                    if existing.status == "DELETED":
                        raise Conflict("Bu yükleme silindi. Yeni istek anahtarı kullanın.")
                    return existing
            if Attachment.objects.filter(uploaded_by=actor, resource_id__isnull=True).exclude(status="DELETED").count() >= 30:
                raise ValidationError("İlişkisiz dosya sınırına ulaşıldı. Kullanılmayan yüklemeleri kaldırın.")
            key = uuid.uuid4().hex
            storage_key = f"{key[:2]}/{key}"
            path = private_path(storage_key)
            Path(settings.ONECS_UPLOAD_ROOT).mkdir(mode=0o700, parents=True, exist_ok=True)
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with path.open("xb") as handle:
                path.chmod(0o600)
                handle.write(raw)
            status, scan_status = scan_file(path)
            item = Attachment.objects.create(
                uploaded_by=actor, name=name, storage_key=storage_key, size=len(raw),
                content_type=content_type, sha256=digest, status=status,
                scan_status=scan_status, upload_key=request_key,
            )
            audit(actor, "attachment.staged", item, {"size": item.size, "status": item.status, "scan_status": item.scan_status})
            return item
    except Exception:
        if path is not None:
            path.unlink(missing_ok=True)
        raise


@transaction.atomic
def bind_attachments(actor, resource_type, obj, ids, *, initial=False):
    actor = _current_actor(actor)
    if not isinstance(ids, list) or len(ids) > settings.ONECS_UPLOAD_MAX_FILES:
        raise ValidationError({"attachment_ids": "Bir kayda en fazla 5 dosya ekleyebilirsiniz."})
    try:
        parsed = [uuid.UUID(str(value)) for value in ids]
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"attachment_ids": "Geçerli dosya kimlikleri seçin."})
    if len(set(parsed)) != len(parsed):
        raise ValidationError({"attachment_ids": "Aynı dosya birden fazla seçilemez."})
    if not parsed:
        return []
    model = RESOURCE_MODELS.get(resource_type)
    if model is None or not isinstance(obj, model):
        raise ValidationError({"attachment_ids": "Dosya bağlamı geçerli değil."})
    # All attachment binding paths acquire the owner before attachment rows.
    model.objects.select_for_update().get(pk=obj.pk)
    resource_for_actor(actor, resource_type, obj.pk, write=True, initial=initial)
    if Attachment.objects.filter(resource_type=resource_type, resource_id=obj.pk).exclude(status="DELETED").count() + len(parsed) > settings.ONECS_UPLOAD_MAX_FILES:
        raise ValidationError({"attachment_ids": "Bir kayda en fazla 5 dosya ekleyebilirsiniz."})
    items = list(Attachment.objects.select_for_update().filter(pk__in=parsed))
    if len(items) != len(parsed) or any(item.uploaded_by_id != actor.pk or item.resource_id is not None or item.status not in ("READY", "PENDING_SCAN") for item in items):
        raise ValidationError({"attachment_ids": "Yalnız size ait, kullanılmamış ve reddedilmemiş dosyalar eklenebilir."})
    for item in items:
        item.resource_type, item.resource_id = resource_type, obj.pk
        item.bound_at = timezone.now()
        item.version += 1
        item.save(update_fields=["resource_type", "resource_id", "bound_at", "version", "updated_at"])
        audit(actor, "attachment.bound", item, {"resource_type": resource_type, "resource_id": str(obj.pk)})
    return items


def authorized_attachment(actor, attachment_id):
    actor = _current_actor(actor)
    try:
        item = Attachment.objects.filter(pk=attachment_id).exclude(status="DELETED").first()
    except (ValueError, TypeError, DjangoValidationError):
        item = None
    if item is None:
        raise NotFound("Dosya bulunamadı.")
    if item.resource_id:
        resource_for_actor(actor, item.resource_type, item.resource_id)
    elif item.uploaded_by_id != actor.pk or getattr(actor, "_api_client", None):
        raise NotFound("Dosya bulunamadı.")
    return item


def download_ready(item):
    return item.status == "READY" and (item.scan_status == "clean" or item.scan_status == "unscanned" and unscanned_allowed())


def purge_deleted_file(item_id, storage_key):
    """The tombstone precedes physical deletion and allows retry after I/O failure."""
    private_path(storage_key).unlink(missing_ok=True)
    Attachment.objects.filter(pk=item_id, status="DELETED").update(purged_at=timezone.now())


def scan_pending_attachments(limit=20):
    """Bounded CLI batch; a file lock is held only for its bounded scanner process."""
    if not settings.ONECS_UPLOAD_SCANNER_COMMAND:
        raise ValidationError("ONECS_UPLOAD_SCANNER_COMMAND yapılandırılmalıdır.")
    counts = {"processed": 0, "ready": 0, "rejected": 0, "pending": 0}
    seen = []
    eligible = Q(status="PENDING_SCAN") | Q(status="READY", scan_status="unscanned")
    # Skip already locked files so simultaneous CLI workers never scan one twice.
    for _ in range(limit):
        with transaction.atomic():
            item = Attachment.objects.select_for_update(skip_locked=True).filter(eligible).exclude(pk__in=seen).order_by("updated_at").first()
            if item is None:
                break
            seen.append(item.pk)
            try:
                path = private_path(item.storage_key)
                with path.open("rb") as handle:
                    raw = handle.read(settings.ONECS_UPLOAD_MAX_BYTES + 1)
                if len(raw) != item.size or hashlib.sha256(raw).hexdigest() != item.sha256:
                    item.status, item.scan_status = "REJECTED", "integrity_error"
                else:
                    item.status, item.scan_status = scan_file(path)
            except OSError:
                item.status, item.scan_status = "PENDING_SCAN", "error"
            item.version += 1
            item.save(update_fields=["status", "scan_status", "version", "updated_at"])
            audit(None, "attachment.scan.completed", item, {"status": item.status, "scan_status": item.scan_status})
            counts["processed"] += 1
            counts[{"READY": "ready", "REJECTED": "rejected"}.get(item.status, "pending")] += 1
    return counts
