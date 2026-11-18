"""PostgreSQL-backed leased jobs and transactional notification outbox."""

import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from .models import (
    BackgroundJob,
    OutboxEvent,
    User,
    Credential,
    Notification,
    SLAInstance,
)
from .policy import report_source, can_manage_org
from .services import generate_report, scan_slas, enqueue_notification
from .record_notifications import email_delivery_access


def fail_related_reports(job):
    from .models import Report, ProjectInsightReport

    Report.objects.filter(job=job, status="GENERATING").update(status="FAILED")
    ProjectInsightReport.objects.filter(job=job, status="GENERATING").update(
        status="FAILED"
    )


def claim_job():
    now = timezone.now()
    with transaction.atomic():
        expired = BackgroundJob.objects.filter(status="RUNNING", lease_until__lt=now)
        expired.update(status="RETRY", next_attempt_at=now)
        job = (
            BackgroundJob.objects.select_for_update(skip_locked=True)
            .filter(status__in=["PENDING", "RETRY"], next_attempt_at__lte=now)
            .order_by("created_at")
            .first()
        )
        if not job:
            return None
        if job.attempts >= 3:
            job.status = "FAILED"
            job.last_error = "Yeniden deneme sınırına ulaşıldı."
            job.save()
            fail_related_reports(job)
            return None
        job.status = "RUNNING"
        job.lease_token = uuid.uuid4()
        # The provider may use the configured 180-second timeout. Leave time
        # for validation and committing its result before the lease expires.
        job.lease_until = now + timedelta(seconds=240)
        job.attempts += 1
        job.checkpoint = {"stage": "claimed", "at": now.isoformat()}
        job.save()
        return job


def process_job():
    job = claim_job()
    if not job:
        return False
    try:
        if job.kind == "PROJECT_INSIGHT":
            from .project_insights import generate_project_insight

            result = generate_project_insight(job)
        elif job.kind == "REPORT":
            result = generate_report(job)
        else:
            raise ValidationError("Desteklenmeyen iş türü.")
        BackgroundJob.objects.filter(
            pk=job.pk, lease_token=job.lease_token, status="RUNNING"
        ).update(
            status="COMPLETED",
            result=result,
            checkpoint={"stage": "completed"},
            lease_until=None,
            last_error="",
        )
    except Exception as exc:
        permanent = isinstance(exc, APIException) and exc.status_code < 500
        status = "FAILED" if permanent or job.attempts >= 3 else "RETRY"
        with transaction.atomic():
            updated = BackgroundJob.objects.filter(
                pk=job.pk, lease_token=job.lease_token, status="RUNNING"
            ).update(
                status=status,
                last_error="İş kuralları veya kaynak erişimi doğrulanamadı."
                if permanent
                else "Sağlayıcı/işlem hatası; sınırlı yeniden deneme uygulanıyor.",
                next_attempt_at=timezone.now() + timedelta(seconds=15 * job.attempts),
                lease_until=None,
            )
            if updated and status == "FAILED":
                fail_related_reports(job)
    return True


def claim_outbox():
    now = timezone.now()
    with transaction.atomic():
        # Delivery might have happened before interruption. Never blindly resend an ambiguous send.
        OutboxEvent.objects.filter(status="SENDING", lease_until__lt=now).update(
            status="UNKNOWN",
            last_error="Kesinti sırasında teslim sonucu belirsiz. Yeniden gönderim için kontrol gerekir.",
        )
        event = (
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(
                status__in=["PENDING", "RETRY", "WAITING_CONFIGURATION"],
                next_attempt_at__lte=now,
            )
            .order_by("created_at")
            .first()
        )
        if not event:
            return None
        if event.attempts >= 5:
            event.status = "FAILED"
            event.save()
            return None
        event.status = "SENDING"
        event.lease_token = uuid.uuid4()
        event.lease_until = now + timedelta(seconds=90)
        event.save()
        return event


def process_outbox():
    event = claim_outbox()
    if not event:
        return False

    def finish(status, **kwargs):
        OutboxEvent.objects.filter(
            pk=event.pk, lease_token=event.lease_token, status="SENDING"
        ).update(status=status, lease_until=None, **kwargs)

    if event.key.startswith("sla:"):
        pieces = event.key.split(":")
        sla = (
            SLAInstance.objects.filter(pk=pieces[1]).first()
            if len(pieces) >= 5
            else None
        )
        if (
            sla is None
            or sla.stopped_at is not None
            or str(sla.revision) != pieces[2]
            or pieces[3] == "WARNING"
            and sla.current_due_at <= timezone.now()
        ):
            finish("CANCELLED", last_error="Süre uyarısı artık güncel değil.")
            return True
    person = User.objects.get(pk=event.recipient_id)
    if not person.is_active:
        finish("CANCELLED", last_error="Alıcı etkin değil.")
        return True
    allowed, defer_until = email_delivery_access(person, event)
    if not allowed:
        finish("CANCELLED", last_error="Alıcının kaynağa erişimi kaldırıldı.")
        return True
    if defer_until is not None:
        finish("PENDING", next_attempt_at=defer_until, last_error="")
        return True
    if event.resource_type in ("work", "project", "case"):
        obj = report_source(person, event.resource_type, event.resource_id)
        if obj is None:
            finish("CANCELLED", last_error="Alıcının kaynağa erişimi kaldırıldı.")
            return True
        if (
            event.resource_type == "work"
            and event.key.startswith("assign:")
            and obj.assigned_to_id != person.pk
        ):
            finish("CANCELLED", last_error="Atama artık güncel değil.")
            return True
    if not person.email:
        finish("BLOCKED", last_error="Alıcının e-posta adresi eksik.")
        return True
    try:
        from administration.services import deliver_email

        deliver_email(
            person.email,
            "onecs: " + event.title,
            "onecs üzerinde yetkili olduğunuz bir kayıt güncellendi. Ayrıntılar için uygulamadaki Bildirimler alanını açın.",
            message_id=f"<onecs-{event.pk}@onecs.local>",
        )
        finish(
            "SENT", sent_at=timezone.now(), attempts=event.attempts + 1, last_error=""
        )
    except ValidationError:
        finish(
            "WAITING_CONFIGURATION",
            last_error="E-posta bağlantısı yapılandırılmalı veya test edilmeli.",
            next_attempt_at=timezone.now() + timedelta(minutes=5),
        )
    except (ConnectionRefusedError, __import__("socket").gaierror):
        finish(
            "RETRY",
            attempts=event.attempts + 1,
            last_error="Posta servisine bağlantı kurulamadı.",
            next_attempt_at=timezone.now()
            + timedelta(seconds=30 * (event.attempts + 1)),
        )
    except Exception:
        finish(
            "UNKNOWN",
            attempts=event.attempts + 1,
            last_error="Teslim sonucu doğrulanamadı; kontrol sonrası yeniden deneyin.",
        )
    return True


def scan_credentials():
    today = timezone.localdate()
    count = 0
    for credential in Credential.objects.filter(
        important=True, no_expiry=False, expires_on__isnull=False
    ).select_related("user__primary_org"):
        if credential.expires_on > today + timedelta(days=credential.alert_days):
            continue
        targets = {credential.user.pk: credential.user}
        for person in User.objects.filter(
            is_active=True,
            role_grants__role__in=["DIRECTOR", "UNIT_HEAD", "TEAM_MANAGER"],
        ).distinct():
            if can_manage_org(person, credential.user.primary_org_id):
                targets[person.pk] = person
        for person in targets.values():
            key = f"credential:{credential.pk}:{credential.expires_on}:{person.pk}"
            before = Notification.objects.filter(dedup_key=key + ":inapp").exists()
            enqueue_notification(
                person,
                "Önemli sertifikanın süresi yaklaşıyor",
                "credential",
                credential.pk,
                key,
            )
            count += not before
    return count


def run_tick():
    sla = scan_slas()
    credentials = scan_credentials()
    jobs = process_job()
    mail = process_outbox()
    return {
        "sla_events": sla,
        "credential_alerts": credentials,
        "job_processed": jobs,
        "mail_processed": mail,
    }
