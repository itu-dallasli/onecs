import calendar
import hashlib
import json
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from .exceptions import Conflict

from .models import (
    AuditEvent,
    BackgroundJob,
    Notification,
    OutboxEvent,
    PMAppointment,
    ProgressEntry,
    Project,
    ProjectAuthorityGrant,
    Report,
    SLAEvent,
    SLAInstance,
    SLAPolicy,
    User,
    WorkItem,
)
from .policy import (
    active_grants,
    can_manage_org,
    can_manage_project,
    can_manage_work,
    can_read_case,
    can_read_project,
    can_read_project_detail,
    can_read_work,
    report_source,
)

PRIORITIES = {"CRITICAL", "HIGH", "NORMAL"}
TERMINAL = {"COMPLETED", "CANCELLED"}


def audit(actor, action, obj, data=None):
    return AuditEvent.objects.create(
        actor=actor,
        real_actor=getattr(actor, "_real_actor", None),
        action=action,
        object_type=obj.__class__.__name__,
        object_id=str(obj.pk),
        data=data or {},
    )


def check_version(obj, data):
    if "version" not in data:
        raise ValidationError({"version": "Güncel kayıt sürümü zorunludur."})
    try:
        version = int(data["version"])
    except (TypeError, ValueError):
        raise ValidationError({"version": "Geçerli sürüm girin."})
    if obj.version != version:
        raise Conflict()


def bump(obj):
    obj.version += 1
    obj.save()


def ensure(condition, message="Bu işlem için yetkiniz yok."):
    if not condition:
        raise PermissionDenied(message)


def priority(value):
    if not isinstance(value, str) or value not in PRIORITIES:
        raise ValidationError({"priority": "CRITICAL, HIGH veya NORMAL seçin."})
    return value


def enqueue_notification(recipient, title, resource_type, resource_id, key, message=""):
    Notification.objects.get_or_create(
        dedup_key=key + ":inapp",
        defaults={
            "recipient": recipient,
            "title": title,
            "message": message,
            "resource_type": resource_type,
            "resource_id": str(resource_id),
        },
    )
    OutboxEvent.objects.get_or_create(
        key=key + ":email",
        defaults={
            "recipient": recipient,
            "title": title,
            "resource_type": resource_type,
            "resource_id": str(resource_id),
        },
    )


def calculate_due(start, amount, unit):
    amount = int(amount)
    if amount <= 0:
        raise ValidationError("Süre pozitif olmalıdır.")
    if unit == "HOURS":
        return start + timedelta(hours=amount)
    local = start.astimezone(ZoneInfo("Europe/Istanbul"))
    if unit == "DAYS":
        return (local + timedelta(days=amount)).astimezone(ZoneInfo("UTC"))
    if unit == "MONTHS":
        month = local.month - 1 + amount
        year = local.year + month // 12
        month = month % 12 + 1
        return local.replace(
            year=year,
            month=month,
            day=min(local.day, calendar.monthrange(year, month)[1]),
        ).astimezone(ZoneInfo("UTC"))
    raise ValidationError("Desteklenmeyen süre birimi.")


def create_sla(work=None, case=None, now=None):
    obj = work or case
    now = now or timezone.now()
    context = "UNIT_WORK" if work else "CASE"
    policy = (
        SLAPolicy.objects.filter(
            active=True, priority=obj.priority, context__in=[context, "ALL"]
        )
        .order_by("-created_at")
        .first()
    )
    default = {"CRITICAL": (24, "HOURS"), "HIGH": (7, "DAYS"), "NORMAL": (1, "MONTHS")}[
        obj.priority
    ]
    snap = {
        "id": str(policy.id) if policy else None,
        "priority": obj.priority,
        "amount": policy.amount if policy else default[0],
        "unit": policy.unit if policy else default[1],
        "warning_percent": policy.warning_percent if policy else 80,
        "timezone": "Europe/Istanbul",
        "policy_version": policy.version if policy else 1,
    }
    due = calculate_due(now, snap["amount"], snap["unit"])
    sla = SLAInstance.objects.create(
        work=work,
        case=case,
        started_at=now,
        original_due_at=due,
        current_due_at=due,
        policy_snapshot=snap,
    )
    if work:
        work.due_at = due
        work.save(update_fields=["due_at", "updated_at"])
    return sla


def mark_breach(sla, now=None):
    now = now or timezone.now()
    if sla.current_due_at <= now and sla.breached_at is None:
        sla.breached_at = sla.current_due_at
        sla.save(update_fields=["breached_at", "updated_at"])
    return sla


def stop_sla(obj, now=None):
    try:
        sla = obj.sla
    except SLAInstance.DoesNotExist:
        return
    now = now or timezone.now()
    mark_breach(sla, now)
    sla.stopped_at = now
    sla.save(update_fields=["stopped_at", "updated_at"])


@transaction.atomic
def scan_slas(now=None):
    now = now or timezone.now()
    count = 0
    for sla in (
        SLAInstance.objects.select_for_update(skip_locked=True, of=("self",))
        .filter(stopped_at__isnull=True)
        .select_related("work__assigned_to", "case__coordinator")
    ):
        elapsed = (now - sla.started_at).total_seconds()
        duration = (sla.current_due_at - sla.started_at).total_seconds()
        if duration <= 0:
            continue
        fraction = elapsed / duration
        threshold = sla.policy_snapshot.get("warning_percent", 80) / 100
        if fraction < threshold:
            continue
        kind = "BREACH" if fraction >= 1 else "WARNING"
        when = (
            sla.current_due_at
            if kind == "BREACH"
            else sla.started_at + timedelta(seconds=duration * threshold)
        )
        key = f"{sla.pk}:{sla.revision}:{kind}"
        event, created = SLAEvent.objects.get_or_create(
            key=key,
            defaults={
                "sla": sla,
                "kind": kind,
                "threshold_at": when,
                "data": {"detected_at": now.isoformat()},
            },
        )
        if kind == "BREACH":
            mark_breach(sla, now)
        if not created:
            continue
        if kind == "BREACH":
            OutboxEvent.objects.filter(
                key__startswith=f"sla:{sla.pk}:{sla.revision}:WARNING:",
                status__in=["PENDING", "RETRY", "WAITING_CONFIGURATION"],
            ).update(
                status="CANCELLED",
                last_error="Daha güncel ihlal bildirimi oluşturuldu.",
            )
        obj = sla.work or sla.case
        recipient = obj.assigned_to if sla.work else obj.coordinator
        rtype = "work" if sla.work else "case"
        targets = {recipient.pk: recipient}
        for manager in User.objects.filter(
            is_active=True,
            role_grants__active=True,
            role_grants__role__in=["UNIT_HEAD", "TEAM_MANAGER", "DIRECTOR"],
        ).distinct():
            if can_manage_org(manager, obj.owner_org_id):
                targets[manager.pk] = manager
        for target in targets.values():
            if can_read_work(target, obj) if sla.work else can_read_case(target, obj):
                enqueue_notification(
                    target,
                    "Süre hedefi aşıldı"
                    if kind == "BREACH"
                    else "Süre hedefi yaklaşıyor",
                    rtype,
                    obj.pk,
                    f"sla:{key}:{target.pk}",
                )
        count += 1
    return count


def contribute(actor, obj, data):
    done = str(data.get("done", "")).strip()
    if not done:
        raise ValidationError({"done": "Yapılan çalışma zorunludur."})
    kwargs = {"work": None, "project": None, "case": None}
    kind = (
        "work"
        if isinstance(obj, WorkItem)
        else "project"
        if isinstance(obj, Project)
        else "case"
    )
    kwargs[kind] = obj
    entry = ProgressEntry.objects.create(
        author=actor,
        author_org=actor.primary_org,
        done=done,
        next_step=data.get("next_step", ""),
        blocker=data.get("blocker", ""),
        **kwargs,
    )
    audit(
        actor, "progress.created", entry, {"context": kind, "context_id": str(obj.pk)}
    )
    return entry


def assign_work(actor, work, assignee):
    ensure(can_manage_work(actor, work))
    if work.context == "UNIT_WORK":
        ensure(can_manage_org(actor, assignee.primary_org_id))
    elif work.context == "PROJECT_TASK":
        ensure(
            work.project.memberships.filter(user=assignee, active=True).exists()
            or work.project.appointment.user_id == assignee.pk,
            "Önce kaynak kabulü ve proje üyeliği gerekir.",
        )
    else:
        ensure(
            work.case.members.filter(pk=assignee.pk).exists()
            or work.case.coordinator_id == assignee.pk,
            "Önce vaka katılımı kabul edilmelidir.",
        )
    if not assignee.is_active:
        raise ValidationError("Pasif kişiye atama yapılamaz.")
    old = str(work.assigned_to_id)
    work.assigned_to = assignee
    work.owner_org = assignee.primary_org
    work.assignment_version += 1
    bump(work)
    OutboxEvent.objects.filter(
        resource_type="work", resource_id=str(work.pk), status="PENDING"
    ).exclude(recipient=assignee).update(status="CANCELLED")
    enqueue_notification(
        assignee,
        "Size bir iş atandı",
        "work",
        work.pk,
        f"assign:{work.pk}:{work.assignment_version}",
        work.title,
    )
    audit(
        actor,
        "work.assigned",
        work,
        {"previous_assignee": old, "assigned_to": str(assignee.pk)},
    )


def snapshot_source(obj, kind, actor=None):
    owner_org = obj.owner_org
    org_snapshot = {
        "id": str(owner_org.pk),
        "name": owner_org.name,
        "code": owner_org.code,
    }
    if (
        kind == "project"
        and actor is not None
        and not can_read_project_detail(actor, obj)
    ):
        revision = obj.revisions.filter(number=obj.published_revision).first()
        content = revision.content if revision else {}
        return {
            "type": kind,
            "id": str(obj.pk),
            "version": obj.version,
            "title": content.get("title", obj.title),
            "status": obj.status,
            "priority": obj.priority,
            "description": content.get("expected_outcome", ""),
            "due_at": content.get("due_at"),
            "visibility": "SUMMARY",
            "owner_org": org_snapshot,
        }
    return {
        "type": kind,
        "id": str(obj.pk),
        "version": obj.version,
        "title": obj.title,
        "status": obj.status,
        "priority": obj.priority,
        "description": obj.description[:1200],
        "due_at": getattr(obj, "due_at", None).isoformat()
        if getattr(obj, "due_at", None)
        else None,
        "visibility": "DETAIL",
        "owner_org": org_snapshot,
    }


def report_hash(report):
    return hashlib.sha256(
        json.dumps(
            {"markdown": report.markdown, "sources": report.sources},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def generate_report(job):
    report = Report.objects.get(pk=job.payload["report_id"])
    actor = User.objects.get(pk=job.actor_id)
    ensure(actor.is_active, "Rapor sahibinin hesabı etkin değil.")
    expected_access = job.payload.get("access_fingerprint") or access_fingerprint(actor)
    ensure(expected_access == access_fingerprint(actor), "Rapor kapsamı değişti.")
    sources = []
    for source in report.sources:
        obj = report_source(actor, source["type"], source["id"])
        if obj is None or not source_visibility_valid(actor, source):
            raise PermissionDenied(
                "Rapor kaynağına erişim kaldırıldı veya görünürlük değişti."
            )
        if obj.version != source["version"]:
            raise Conflict(
                "Rapor kaynağı değişti. Kaynakları güncelleyip tekrar üretin."
            )
        sources.append(source)
    mode = "RULE_BASED"
    markdown = ""
    try:
        from administration.services import generate_ai_report

        result = (
            generate_ai_report(
                actor,
                sources,
                report_kind="weekly",
                request_id=str(job.pk),
                profile_id=job.payload.get("ai_profile_id"),
                configuration_version=job.payload.get("ai_configuration_version", 0),
                settings_version=job.payload.get("ai_settings_version", 0),
            )
            if sources
            else {}
        )
        markdown = result.get("markdown") or result.get("text") or ""
        mode = result.get("mode", "AI")
    except ImportError:
        pass
    if not markdown:
        markdown = f"# {report.title}\n\n{report.period_start} – {report.period_end}\n\nBu taslak kurallı olarak hazırlanmıştır; canlı AI çıktısı değildir.\n\n"
        for s in sources:
            markdown += f"- **{s['title']}** — {s['status']} / {s['priority']} [Kaynak: {s['type']}:{s['id']} v{s['version']}]\n"
        if not sources:
            markdown += "Bu dönemde seçilmiş görünür kaynak bulunamadı.\n"
    with transaction.atomic():
        current_job = BackgroundJob.objects.select_for_update().get(pk=job.pk)
        if (
            current_job.status != "RUNNING"
            or current_job.lease_token != job.lease_token
            or current_job.lease_until is None
            or current_job.lease_until <= timezone.now()
        ):
            raise Conflict("İşin çalışma yetkisi sona erdi.")
        current = Report.objects.select_for_update().get(pk=report.pk)
        if current.job_id != job.pk or current.status != "GENERATING":
            raise Conflict("Rapor işi artık güncel değil.")
        actor = User.objects.get(pk=actor.pk)
        ensure(actor.is_active, "Rapor sahibinin hesabı etkin değil.")
        ensure(
            expected_access == access_fingerprint(actor),
            "Rapor kapsamı üretim sırasında değişti.",
        )
        for source in sources:
            obj = report_source(actor, source["type"], source["id"])
            if (
                obj is None
                or obj.version != source["version"]
                or not source_visibility_valid(actor, source)
            ):
                raise PermissionDenied(
                    "Üretim sırasında kaynak erişimi/sürümü değişti."
                )
        current.markdown = markdown
        current.generated_mode = mode
        current.status = "READY"
        current.content_hash = report_hash(current)
        bump(current)
        audit(
            actor,
            "report.generated",
            current,
            {"mode": mode, "source_count": len(sources)},
        )
    return {"report_id": str(report.pk), "mode": mode}


def access_fingerprint(user):
    user = User.objects.get(pk=user.pk)
    data = {
        "active": user.is_active,
        "org": str(user.primary_org_id),
        "access_version": user.access_version,
        "roles": [
            (
                str(g.pk),
                g.role,
                str(g.org_node_id),
                g.includes_descendants,
                g.permissions,
            )
            for g in active_grants(user).order_by("id")
        ],
        "pm": list(
            PMAppointment.objects.filter(user=user, active=True).values_list(
                "id", "version"
            )
        ),
        "project_visibility": [
            (
                str(p.pk),
                can_read_project(user, p),
                can_read_project_detail(user, p),
                can_manage_project(user, p),
            )
            for p in Project.objects.select_related("appointment__user")
        ],
        "project_grants": list(
            ProjectAuthorityGrant.objects.filter(
                user=user, active=True, expires_at__gt=timezone.now()
            ).values_list("id", "version")
        ),
    }
    return hashlib.sha256(
        json.dumps(
            data,
            sort_keys=True,
            cls=__import__(
                "django.core.serializers.json", fromlist=["DjangoJSONEncoder"]
            ).DjangoJSONEncoder,
        ).encode()
    ).hexdigest()


def source_visibility_valid(actor, source):
    if not isinstance(source, dict):
        return False
    if not isinstance(source.get("type"), str) or not source.get("id"):
        return False
    if any(
        key in source and not isinstance(source[key], str)
        for key in ("status", "priority", "title", "description")
    ):
        return False
    if "version" in source and (
        type(source["version"]) is not int or source["version"] < 1
    ):
        return False
    obj = report_source(actor, source["type"], source["id"])
    if obj is None:
        return False
    if source["type"] == "project":
        current = "DETAIL" if can_read_project_detail(actor, obj) else "SUMMARY"
        return current == source.get("visibility", "DETAIL")
    return True
