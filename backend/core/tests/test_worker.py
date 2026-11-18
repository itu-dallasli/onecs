"""Restart/revocation boundaries for durable jobs and notification delivery."""

import uuid
from datetime import date, timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from core.models import BackgroundJob, OutboxEvent, Report, User, WorkItem
from core.services import create_sla, generate_report, snapshot_source
from core.tests.base import AtlasTestCase
from core.worker import claim_job, process_outbox


class ReportJobRecoveryTests(AtlasTestCase):
    def report_job(self, **extra):
        work = WorkItem.objects.create(
            title="Review evidence",
            assigned_to=self.employee,
            created_by=self.unit_head,
            owner_org=self.team,
        )
        report = Report.objects.create(
            title="Weekly summary",
            created_by=self.employee,
            period_start=date(2026, 11, 16),
            period_end=date(2026, 11, 23),
            sources=[snapshot_source(work, "work")],
            status="GENERATING",
        )
        data = {
            "kind": "REPORT",
            "actor": self.employee,
            "payload": {"report_id": str(report.pk)},
            "status": "RUNNING",
            "lease_token": uuid.uuid4(),
            "lease_until": timezone.now() + timedelta(minutes=3),
        }
        data.update(extra)
        job = BackgroundJob.objects.create(**data)
        report.job = job
        report.save()
        return report, job

    def test_expired_running_job_is_reclaimed_with_new_lease_and_attempt(self):
        _, job = self.report_job(
            lease_until=timezone.now() - timedelta(seconds=1), attempts=1
        )
        original_token = job.lease_token
        claimed = claim_job()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.pk, job.pk)
        self.assertNotEqual(claimed.lease_token, original_token)
        self.assertEqual(claimed.attempts, 2)
        self.assertEqual(claimed.status, "RUNNING")
        self.assertEqual(claimed.checkpoint["stage"], "claimed")

    def test_late_ai_result_is_discarded_when_database_actor_is_disabled(self):
        report, job = self.report_job()

        def disable_actor(*args, **kwargs):
            User.objects.filter(pk=self.employee.pk).update(is_active=False)
            return {
                "markdown": "A late model answer must not publish",
                "mode": "TEST_PROVIDER",
            }

        with patch(
            "administration.services.generate_ai_report", side_effect=disable_actor
        ):
            with self.assertRaises(APIException):
                generate_report(job)
        report.refresh_from_db()
        self.assertEqual(report.status, "GENERATING")
        self.assertEqual(report.markdown, "")

    def test_expired_worker_cannot_publish_after_lease_is_reassigned(self):
        report, job = self.report_job()

        def replace_worker_lease(*args, **kwargs):
            BackgroundJob.objects.filter(pk=job.pk).update(
                lease_token=uuid.uuid4(),
                lease_until=timezone.now() + timedelta(minutes=3),
            )
            return {
                "markdown": "A stale worker answer must not publish",
                "mode": "TEST_PROVIDER",
            }

        with patch(
            "administration.services.generate_ai_report",
            side_effect=replace_worker_lease,
        ):
            with self.assertRaises(APIException):
                generate_report(job)
        report.refresh_from_db()
        self.assertEqual(report.status, "GENERATING")
        self.assertEqual(report.markdown, "")

    def test_report_job_passes_its_pinned_ai_profile_and_versions_to_adapter(self):
        report, job = self.report_job()
        profile_id = str(uuid.uuid4())
        job.payload.update(
            {
                "ai_profile_id": profile_id,
                "ai_configuration_version": 4,
                "ai_settings_version": 7,
            }
        )
        job.save(update_fields=["payload"])
        with patch(
            "administration.services.generate_ai_report",
            return_value={"markdown": "Pinned configuration test output", "mode": "TEST_PROVIDER"},
        ) as adapter:
            result = generate_report(job)
        adapter.assert_called_once_with(
            self.employee,
            report.sources,
            report_kind="weekly",
            request_id=str(job.pk),
            profile_id=profile_id,
            configuration_version=4,
            settings_version=7,
        )
        report.refresh_from_db()
        self.assertEqual(report.status, "READY")
        self.assertEqual(report.markdown, "Pinned configuration test output")
        self.assertEqual(result["report_id"], str(report.pk))

    def test_legacy_report_job_uses_zero_versions_and_explicit_rule_based_fallback(self):
        report, job = self.report_job()
        self.assertNotIn("ai_profile_id", job.payload)
        with patch(
            "administration.services.generate_ai_report",
            return_value={"markdown": "", "mode": "RULE_BASED", "status": "unconfigured"},
        ) as adapter:
            generate_report(job)
        adapter.assert_called_once_with(
            self.employee,
            report.sources,
            report_kind="weekly",
            request_id=str(job.pk),
            profile_id=None,
            configuration_version=0,
            settings_version=0,
        )
        report.refresh_from_db()
        self.assertEqual(report.status, "READY")
        self.assertEqual(report.generated_mode, "RULE_BASED")
        self.assertIn("canlı AI çıktısı değildir", report.markdown)
        self.assertIn(report.sources[0]["id"], report.markdown)

    def test_report_queue_captures_selected_ai_snapshot_in_durable_job_payload(self):
        work = WorkItem.objects.create(
            title="Manager review evidence",
            assigned_to=self.employee,
            created_by=self.unit_head,
            owner_org=self.team,
        )
        report = Report.objects.create(
            title="Queued manager summary",
            created_by=self.unit_head,
            period_start=date(2026, 11, 16),
            period_end=date(2026, 11, 23),
            sources=[snapshot_source(work, "work")],
        )
        snapshot = {
            "profile_id": str(uuid.uuid4()),
            "configuration_version": 4,
            "settings_version": 7,
        }
        with patch(
            "administration.profiles.selected_ai_snapshot", return_value=snapshot
        ) as selected:
            response = self.as_user(self.unit_head).post(
                f"/api/v1/reports/{report.pk}/generate/",
                {"version": report.version},
                format="json",
            )
        self.assertEqual(response.status_code, 202, response.content)
        selected.assert_called_once_with()
        report.refresh_from_db()
        self.assertEqual(report.status, "GENERATING")
        self.assertEqual(report.job.payload["report_id"], str(report.pk))
        self.assertEqual(report.job.payload["ai_profile_id"], snapshot["profile_id"])
        self.assertEqual(report.job.payload["ai_configuration_version"], 4)
        self.assertEqual(report.job.payload["ai_settings_version"], 7)
        self.assertTrue(report.job.payload["access_fingerprint"])


class NotificationRecoveryTests(AtlasTestCase):
    def pending(self, **extra):
        work = WorkItem.objects.create(
            title="Sensitive work title",
            assigned_to=self.employee,
            created_by=self.unit_head,
            owner_org=self.team,
        )
        data = {
            "key": f"assign:{work.pk}:1:email",
            "recipient": self.employee,
            "title": "Assignment update",
            "resource_type": "work",
            "resource_id": str(work.pk),
        }
        data.update(extra)
        return work, OutboxEvent.objects.create(**data)

    def test_expired_sending_lease_is_unknown_and_not_automatically_resent(self):
        _, event = self.pending(
            status="SENDING",
            lease_token=uuid.uuid4(),
            lease_until=timezone.now() - timedelta(seconds=1),
        )
        with patch("administration.services.deliver_email") as deliver:
            self.assertFalse(process_outbox())
            deliver.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "UNKNOWN")

    def test_reassigned_work_cancels_old_pending_delivery(self):
        work, event = self.pending()
        work.assigned_to = self.colleague
        work.save()
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
            deliver.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "CANCELLED")

    def test_disabled_recipient_cannot_receive_queued_mail(self):
        _, event = self.pending()
        self.employee.is_active = False
        self.employee.save()
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
            deliver.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "CANCELLED")

    def test_missing_email_is_visible_blocked_state_without_losing_assignment(self):
        work, event = self.pending()
        self.employee.email = ""
        self.employee.save()
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
            deliver.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "BLOCKED")
        self.assertTrue(WorkItem.objects.filter(pk=work.pk).exists())

    def test_refused_connection_is_bounded_retry_and_keeps_domain_commit(self):
        work, event = self.pending()
        with patch(
            "administration.services.deliver_email", side_effect=ConnectionRefusedError
        ):
            self.assertTrue(process_outbox())
        event.refresh_from_db()
        self.assertEqual(event.status, "RETRY")
        self.assertEqual(event.attempts, 1)
        self.assertGreater(event.next_attempt_at, timezone.now())
        self.assertTrue(WorkItem.objects.filter(pk=work.pk).exists())
        self.assertFalse(process_outbox())

    def test_unconfigured_smtp_persists_waiting_state_without_counting_a_delivery_attempt(
        self,
    ):
        work, event = self.pending()
        with patch(
            "administration.services.deliver_email",
            side_effect=ValidationError("SMTP connection is not configured"),
        ) as deliver:
            self.assertTrue(process_outbox())
            self.assertFalse(process_outbox())
            self.assertEqual(deliver.call_count, 1)
        event.refresh_from_db()
        self.assertEqual(event.status, "WAITING_CONFIGURATION")
        self.assertEqual(event.attempts, 0)
        self.assertGreater(event.next_attempt_at, timezone.now())
        self.assertIsNone(event.lease_until)
        self.assertTrue(WorkItem.objects.filter(pk=work.pk).exists())

    def test_queued_warning_from_old_target_revision_is_cancelled_after_extension(self):
        work, event = self.pending(status="WAITING_CONFIGURATION")
        work.priority = "CRITICAL"
        work.save()
        sla = create_sla(work=work, now=timezone.now() - timedelta(hours=20))
        event.key = f"sla:{sla.pk}:{sla.revision}:WARNING:{self.employee.pk}:email"
        event.next_attempt_at = timezone.now() - timedelta(seconds=1)
        event.save()
        sla.current_due_at += timedelta(days=2)
        sla.revision += 1
        sla.save()
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
            deliver.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "CANCELLED")
        self.assertEqual(event.attempts, 0)

    def test_warning_is_not_sent_after_deadline_even_before_breach_scan_runs(self):
        work, event = self.pending()
        work.priority = "CRITICAL"
        work.save()
        sla = create_sla(work=work, now=timezone.now() - timedelta(days=2))
        event.key = f"sla:{sla.pk}:{sla.revision}:WARNING:{self.employee.pk}:email"
        event.save()
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
            deliver.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, "CANCELLED")
        self.assertEqual(event.attempts, 0)

    def test_ambiguous_send_is_not_blindly_retried(self):
        _, event = self.pending()
        with patch(
            "administration.services.deliver_email",
            side_effect=RuntimeError("Provider response lost"),
        ) as deliver:
            self.assertTrue(process_outbox())
            self.assertFalse(process_outbox())
            self.assertEqual(deliver.call_count, 1)
        event.refresh_from_db()
        self.assertEqual(event.status, "UNKNOWN")

    def test_successful_mail_is_one_delivery_with_generic_body(self):
        _, event = self.pending()
        with patch("administration.services.deliver_email") as deliver:
            self.assertTrue(process_outbox())
            self.assertFalse(process_outbox())
            self.assertEqual(deliver.call_count, 1)
            self.assertNotIn("Sensitive work title", str(deliver.call_args))
        event.refresh_from_db()
        self.assertEqual(event.status, "SENT")
