"""Calendar targets and scheduler recovery (K23, K25–K27)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import SimpleTestCase, TransactionTestCase, skipUnlessDBFeature

from core.models import (
    Notification,
    OrgNode,
    OutboxEvent,
    SLAEvent,
    SLAPolicy,
    User,
    WorkItem,
)
from core.services import assign_work, calculate_due, create_sla, scan_slas, stop_sla
from core.tests.base import AtlasTestCase


class SLACalendarTests(SimpleTestCase):
    def test_critical_target_is_twenty_four_elapsed_hours(self):
        start = datetime(2026, 11, 18, 21, 35, tzinfo=timezone.utc)
        self.assertEqual(calculate_due(start, 24, "HOURS"), start + timedelta(hours=24))

    def test_high_target_includes_weekend_and_preserves_local_time(self):
        start = datetime(2026, 11, 20, 16, 15, tzinfo=ZoneInfo("Europe/Istanbul"))
        expected = datetime(2026, 11, 27, 16, 15, tzinfo=ZoneInfo("Europe/Istanbul"))
        self.assertEqual(calculate_due(start, 7, "DAYS"), expected)

    def test_calendar_month_clamps_month_end_and_handles_leap_year(self):
        local_zone = ZoneInfo("Europe/Istanbul")
        cases = [
            ((2026, 1, 31), 1, (2026, 2, 28)),
            ((2024, 1, 31), 1, (2024, 2, 29)),
            ((2026, 3, 31), 1, (2026, 4, 30)),
            ((2026, 12, 31), 1, (2027, 1, 31)),
            ((2024, 2, 29), 12, (2025, 2, 28)),
            ((2026, 1, 31), 2, (2026, 3, 31)),
        ]
        for start_date, months, expected_date in cases:
            with self.subTest(start=start_date, months=months):
                start = datetime(*start_date, 23, 30, 12, tzinfo=local_zone)
                expected = datetime(*expected_date, 23, 30, 12, tzinfo=local_zone)
                self.assertEqual(calculate_due(start, months, "MONTHS"), expected)

    def test_calendar_math_uses_istanbul_date_even_for_utc_input(self):
        # UTC 30 January is already 31 January locally. Clamping February in
        # UTC would accidentally move the local deadline to 1 March.
        start = datetime(2026, 1, 30, 22, 30, tzinfo=timezone.utc)
        expected = datetime(2026, 2, 28, 1, 30, tzinfo=ZoneInfo("Europe/Istanbul"))
        self.assertEqual(calculate_due(start, 1, "MONTHS"), expected)


class SLALifecycleTests(AtlasTestCase):
    def setUp(self):
        super().setUp()
        self.start = datetime(2026, 1, 31, 9, tzinfo=timezone.utc)
        self.work = WorkItem.objects.create(
            title="Critical remediation",
            created_by=self.unit_head,
            assigned_to=self.employee,
            owner_org=self.team,
            formal=True,
            priority="CRITICAL",
        )
        self.sla = create_sla(work=self.work, now=self.start)

    def test_policy_is_snapshotted_and_does_not_rewrite_active_target(self):
        policy = SLAPolicy.objects.create(
            priority="HIGH",
            context="UNIT_WORK",
            amount=3,
            unit="DAYS",
            warning_percent=70,
        )
        work = WorkItem.objects.create(
            title="Configured target",
            created_by=self.unit_head,
            assigned_to=self.employee,
            owner_org=self.team,
            formal=True,
            priority="HIGH",
        )
        sla = create_sla(work=work, now=self.start)
        original = sla.original_due_at
        self.assertEqual(sla.policy_snapshot["amount"], 3)
        self.assertEqual(sla.policy_snapshot["warning_percent"], 70)
        policy.amount = 14
        policy.version += 1
        policy.save()
        sla.refresh_from_db()
        self.assertEqual(sla.policy_snapshot["amount"], 3)
        self.assertEqual(sla.original_due_at, original)
        self.assertEqual(sla.current_due_at, original)

    def test_reassignment_preserves_start_due_and_parent_owner(self):
        parent = WorkItem.objects.create(
            title="Parent commitment",
            created_by=self.director,
            assigned_to=self.unit_head,
            owner_org=self.unit,
            formal=True,
        )
        self.work.parent = parent
        self.work.save()
        original = (
            self.sla.started_at,
            self.sla.original_due_at,
            self.sla.current_due_at,
        )
        assign_work(self.unit_head, self.work, self.colleague)
        self.sla.refresh_from_db()
        parent.refresh_from_db()
        self.assertEqual(
            (self.sla.started_at, self.sla.original_due_at, self.sla.current_due_at),
            original,
        )
        self.assertEqual(parent.assigned_to_id, self.unit_head.pk)
        self.assertEqual(parent.status, "OPEN")

    def test_early_scan_emits_nothing_and_warning_is_deduplicated(self):
        self.assertEqual(scan_slas(now=self.start + timedelta(hours=19)), 0)
        warning_time = self.start + timedelta(hours=19, minutes=12)
        self.assertEqual(scan_slas(now=warning_time), 1)
        first_counts = (
            SLAEvent.objects.count(),
            Notification.objects.count(),
            OutboxEvent.objects.count(),
        )
        self.assertEqual(scan_slas(now=warning_time + timedelta(minutes=1)), 0)
        self.assertEqual(
            (
                SLAEvent.objects.count(),
                Notification.objects.count(),
                OutboxEvent.objects.count(),
            ),
            first_counts,
        )
        event = SLAEvent.objects.get(sla=self.sla)
        self.assertEqual(event.kind, "WARNING")
        self.assertEqual(event.threshold_at, warning_time)
        self.sla.refresh_from_db()
        self.assertIsNone(self.sla.breached_at)

    def test_restart_after_due_coalesces_stale_warning_into_one_current_event(self):
        detected_at = self.start + timedelta(days=3)
        self.assertEqual(scan_slas(now=detected_at), 1)
        self.assertEqual(SLAEvent.objects.filter(sla=self.sla).count(), 1)
        event = SLAEvent.objects.get(sla=self.sla)
        self.assertEqual(event.kind, "BREACH")
        self.assertEqual(event.threshold_at, self.start + timedelta(hours=24))
        self.assertEqual(event.data["detected_at"], detected_at.isoformat())
        self.sla.refresh_from_db()
        self.assertEqual(self.sla.breached_at, self.sla.current_due_at)
        counts = (Notification.objects.count(), OutboxEvent.objects.count())
        self.assertEqual(scan_slas(now=detected_at + timedelta(days=1)), 0)
        self.assertEqual(
            (Notification.objects.count(), OutboxEvent.objects.count()), counts
        )
        self.assertFalse(Notification.objects.filter(recipient=self.outsider).exists())

    def test_completed_target_does_not_become_breached_during_downtime(self):
        stop_sla(self.work, now=self.start + timedelta(hours=1))
        self.assertEqual(scan_slas(now=self.start + timedelta(days=10)), 0)
        self.sla.refresh_from_db()
        self.assertIsNotNone(self.sla.stopped_at)
        self.assertIsNone(self.sla.breached_at)

    def test_overdue_close_records_breach_even_without_prior_scheduler_run(self):
        stop_sla(self.work, now=self.start + timedelta(days=2))
        self.sla.refresh_from_db()
        self.assertEqual(self.sla.breached_at, self.sla.original_due_at)
        self.assertEqual(self.sla.stopped_at, self.start + timedelta(days=2))


class SLASchedulerConcurrencyTests(TransactionTestCase):
    """Uses independent PostgreSQL connections, rather than an in-memory mock."""

    @skipUnlessDBFeature("has_select_for_update_skip_locked")
    def test_two_restarted_workers_emit_one_logical_breach(self):
        org = OrgNode.objects.create(
            code="SCHEDULER-TEST", name="Scheduler", kind="UNIT"
        )
        person = User.objects.create_user(username="scheduler-person", primary_org=org)
        start = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        work = WorkItem.objects.create(
            title="Concurrent target",
            assigned_to=person,
            created_by=person,
            owner_org=org,
            formal=True,
            priority="CRITICAL",
        )
        sla = create_sla(work=work, now=start)
        barrier = Barrier(2)

        def restarted_worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return scan_slas(now=start + timedelta(days=3))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: restarted_worker(), range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(SLAEvent.objects.filter(sla=sla, kind="BREACH").count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=person).count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(recipient=person).count(), 1)
