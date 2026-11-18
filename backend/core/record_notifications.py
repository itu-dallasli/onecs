"""Optional record emails never change the source record's reader scope.

Call these helpers inside the domain mutation transaction. Draft preferences
are durable, while the existing mandatory assignment/review outbox stays intact.
"""

from copy import copy
import uuid

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import (
    Announcement,
    CaseNotice,
    CommunityCard,
    Event,
    Notification,
    OutboxEvent,
    RecordEmailPreference,
    User,
)
from .notifications import notification_access
from .policy import (
    active_actor,
    api_org_allowed,
    audience_visible,
    can_manage_org,
    can_read_case,
    can_read_project,
    can_read_work,
    report_source,
    visible_credentials,
)
from .services import audit


EMAIL_FIELDS = {"send_email", "notification_recipient_ids"}
STAGED_TYPES = {"project", "announcement", "community"}
RESOURCE_TYPES = STAGED_TYPES | {"work", "case", "case_notice", "event", "credential"}
TITLES = {
    "work": "İş kaydı bildirimi",
    "project": "Proje başvurusu bildirimi",
    "case": "Vaka kaydı bildirimi",
    "case_notice": "Vaka bildirimi kaydı",
    "announcement": "Yeni anons bildirimi",
    "community": "Yeni paylaşım bildirimi",
    "event": "Etkinlik kaydı bildirimi",
    "credential": "Sertifika kaydı bildirimi",
}


def _recipient_ids(data):
    send_email = data.get("send_email", False)
    if not isinstance(send_email, bool):
        raise ValidationError({"send_email": "E-posta tercihi boolean olmalıdır."})
    values = data.get("notification_recipient_ids", [])
    if not isinstance(values, list) or len(values) > 20:
        raise ValidationError({"notification_recipient_ids": "En fazla 20 kişi seçin."})
    ids = []
    for value in values:
        if not isinstance(value, str):
            raise ValidationError({"notification_recipient_ids": "Geçerli kişi kimlikleri seçin."})
        try:
            person_id = str(uuid.UUID(value))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError({"notification_recipient_ids": "Geçerli kişi kimlikleri seçin."})
        if person_id not in ids:
            ids.append(person_id)
    if send_email and not ids:
        raise ValidationError({"notification_recipient_ids": "E-posta gönderilecek kişileri seçin."})
    return send_email, ids


def _can_receive(person, resource_type, obj, *, prospective=False):
    if not active_actor(person):
        return False
    if resource_type == "work":
        return can_read_work(person, obj)
    if resource_type == "case":
        return can_read_case(person, obj)
    if resource_type == "project":
        source = obj
        if prospective and obj.status in {"DRAFT", "REVISION"}:
            source = copy(obj)
            source.status = "SUBMITTED"
        return can_read_project(person, source)
    if resource_type in {"announcement", "community"}:
        return audience_visible(person, obj) and (
            prospective or obj.status == "PUBLISHED"
        )
    if resource_type == "case_notice":
        return api_org_allowed(person, obj.owner_org_id) and (
            obj.created_by_id == person.pk or can_manage_org(person, obj.owner_org_id)
        )
    if resource_type == "event":
        return api_org_allowed(person, obj.owner_org_id) and (
            obj.invitees.filter(pk=person.pk).exists()
            or can_manage_org(person, obj.owner_org_id)
        )
    if resource_type == "credential":
        return visible_credentials(person).filter(pk=obj.pk).exists()
    return False


def _enqueue(preference, obj, person):
    resource_type = preference.resource_type
    resource_id = str(obj.pk)
    # A mandatory assignment/review message already covers this recipient.
    # BLOCKED/UNKNOWN/SENT also remain a single logical delivery to recover.
    if OutboxEvent.objects.filter(
        resource_type=resource_type,
        resource_id=resource_id,
        recipient=person,
    ).exclude(status="CANCELLED").exists():
        return False
    key = f"record-mail:{resource_type}:{obj.pk}:{preference.pk}:{person.pk}"
    if not Notification.objects.filter(
        resource_type=resource_type, resource_id=resource_id, recipient=person,
    ).exists():
        Notification.objects.get_or_create(
            dedup_key=key + ":inapp",
            defaults={
                "recipient": person,
                "title": TITLES[resource_type],
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
    next_attempt = timezone.now()
    if resource_type == "announcement":
        next_attempt = max(next_attempt, obj.starts_at)
    _, created = OutboxEvent.objects.get_or_create(
        key=key + ":email",
        defaults={
            "recipient": person,
            "title": TITLES[resource_type],
            "resource_type": resource_type,
            "resource_id": resource_id,
            "next_attempt_at": next_attempt,
        },
    )
    return created


def save_record_email_preference(actor, resource_type, obj, data):
    """Validate recipients before committing a create; stage unpublished data."""
    if resource_type not in RESOURCE_TYPES:
        raise ValidationError("Desteklenmeyen bildirim kaydı.")
    if not EMAIL_FIELDS.intersection(data):
        return None
    send_email, ids = _recipient_ids(data)
    people = {str(person.pk): person for person in User.objects.filter(pk__in=ids)}
    if len(people) != len(ids) or any(
        not _can_receive(people[person_id], resource_type, obj, prospective=True)
        for person_id in ids
    ):
        raise PermissionDenied("Seçilen kişiler aktif olmalı ve kaydın izinli okuyucu kapsamında bulunmalıdır.")
    preference, _ = RecordEmailPreference.objects.update_or_create(
        resource_type=resource_type,
        resource_id=obj.pk,
        defaults={"send_email": send_email, "recipient_ids": ids, "created_by": actor},
    )
    audit(actor, "record.email_preference.saved", obj, {
        "resource_type": resource_type,
        "send_email": send_email,
        "recipient_count": len(ids),
    })
    if resource_type not in STAGED_TYPES:
        dispatch_record_email_preference(actor, resource_type, obj)
    return preference


def dispatch_record_email_preference(actor, resource_type, obj):
    """The source domain authorizes submit/publication before calling here."""
    preference = RecordEmailPreference.objects.filter(
        resource_type=resource_type, resource_id=obj.pk, send_email=True,
    ).first()
    if preference is None:
        return 0
    if resource_type == "project" and obj.status in {"DRAFT", "REVISION"}:
        return 0
    if resource_type in {"announcement", "community"} and obj.status != "PUBLISHED":
        return 0
    # A preference cannot preserve a revoked reader. Invalidated selections
    # are skipped rather than blocking a mandatory submission/publication.
    people = {str(person.pk): person for person in User.objects.filter(pk__in=preference.recipient_ids)}
    queued, skipped = 0, 0
    for person_id in preference.recipient_ids:
        person = people.get(person_id)
        if person is None or not _can_receive(person, resource_type, obj):
            skipped += 1
            continue
        queued += int(_enqueue(preference, obj, person))
    audit(actor, "record.email_preference.dispatched", obj, {
        "resource_type": resource_type, "queued": queued, "skipped": skipped,
    })
    return queued


def email_delivery_access(person, event):
    """Return (allowed, defer_until) using current source policy at send time."""
    kind = event.resource_type
    if not active_actor(person):
        return False, None
    if kind in {"work", "project", "case"}:
        return report_source(person, kind, event.resource_id) is not None, None
    try:
        resource_id = uuid.UUID(str(event.resource_id))
    except (ValueError, TypeError, AttributeError):
        return False, None
    if kind == "announcement":
        obj = Announcement.objects.filter(pk=resource_id).first()
        now = timezone.now()
        if (obj is None or obj.status != "PUBLISHED"
                or not audience_visible(person, obj)
                or obj.ends_at is not None and obj.ends_at <= now):
            return False, None
        return True, obj.starts_at if obj.starts_at > now else None
    if kind == "community":
        obj = CommunityCard.objects.filter(pk=resource_id).first()
        if obj is None or obj.status != "PUBLISHED":
            return False, None
        if event.key.startswith("record-mail:"):
            return audience_visible(person, obj), None
    if kind == "case_notice":
        obj = CaseNotice.objects.filter(pk=resource_id).first()
        return obj is not None and _can_receive(person, kind, obj), None
    if kind == "event":
        obj = Event.objects.filter(pk=resource_id).first()
        return obj is not None and _can_receive(person, kind, obj), None
    # Reuse inbox policy for existing participation/credential/community mail.
    # Its minimal notice interface avoids duplicating their reader rules.
    notice = type("MailNotice", (), {
        "resource_type": kind, "resource_id": str(resource_id), "dedup_key": event.key,
    })()
    return notification_access(person, notice)[0], None
