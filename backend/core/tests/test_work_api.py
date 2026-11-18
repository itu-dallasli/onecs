"""Unit commitments, personal work and safe retries through real sessions."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from core.models import (
    IdempotencyRecord,
    Notification,
    OutboxEvent,
    SLAInstance,
    WorkItem,
)
from core.tests.base import AtlasTestCase


WORK_URL = "/api/v1/work/"


class WorkAPITests(AtlasTestCase):
    def create_work(self, actor=None, assignee=None, **extra):
        actor = actor or self.unit_head
        data = {
            "title": "Remediate critical access",
            "expected_outcome": "Review evidence recorded",
            "assignee_id": str((assignee or self.employee).pk),
            "priority": "CRITICAL",
            "personal": False,
        }
        data.update(extra)
        response = self.as_user(actor).post(WORK_URL, data, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return WorkItem.objects.get(pk=response.json()["id"])

    def post_action(self, actor, work, action, **data):
        return self.as_user(actor).post(
            f"{WORK_URL}{work.pk}/{action}/",
            {"version": work.version, **data},
            format="json",
        )

    def test_login_is_required_for_list_and_create(self):
        self.assertIn(self.client.get(WORK_URL).status_code, (401, 403))
        self.assertIn(
            self.client.post(
                WORK_URL, {"title": "Unauthenticated"}, format="json"
            ).status_code,
            (401, 403),
        )
        self.assertEqual(WorkItem.objects.count(), 0)

    def test_manager_assignment_commits_work_sla_and_both_notification_channels(self):
        work = self.create_work()
        self.assertEqual(work.owner_org_id, self.team.pk)
        self.assertTrue(work.formal)
        self.assertEqual(
            work.sla.current_due_at - work.sla.started_at, timedelta(hours=24)
        )
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.employee, resource_id=str(work.pk)
            ).count(),
            1,
        )
        self.assertEqual(
            OutboxEvent.objects.filter(
                recipient=self.employee, resource_id=str(work.pk)
            ).count(),
            1,
        )

    def test_team_manager_cannot_assign_parent_unit_or_other_unit_employee(self):
        for person in (self.direct_employee, self.outsider):
            with self.subTest(assignee=person.username):
                response = self.as_user(self.team_manager).post(
                    WORK_URL,
                    {
                        "title": "Out of scope",
                        "assignee_id": str(person.pk),
                        "personal": False,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(WorkItem.objects.count(), 0)
        self.assertEqual(SLAInstance.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_employee_cannot_create_task_for_colleague_or_forge_formal_self_task(self):
        for data in (
            {"assignee_id": str(self.colleague.pk)},
            {"assignee_id": str(self.employee.pk), "personal": False},
        ):
            with self.subTest(data=data):
                response = self.as_user(self.employee).post(
                    WORK_URL, {"title": "Unauthorized", **data}, format="json"
                )
                self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(WorkItem.objects.count(), 0)

    def test_personal_task_can_complete_without_management_sla(self):
        work = self.create_work(actor=self.employee, personal=True, due_at="2026-12-31")
        self.assertFalse(work.formal)
        self.assertFalse(SLAInstance.objects.filter(work=work).exists())
        response = self.post_action(
            self.employee,
            work,
            "status",
            status="COMPLETED",
            result="Personal review finished",
        )
        self.assertEqual(response.status_code, 200, response.content)
        work.refresh_from_db()
        self.assertEqual(work.status, "COMPLETED")
        self.assertFalse(SLAInstance.objects.filter(work=work).exists())

    def test_adoption_starts_now_and_does_not_backdate_personal_target(self):
        work = self.create_work(actor=self.employee, personal=True, due_at="2020-01-01")
        adopted_at = timezone.now()
        with patch("django.utils.timezone.now", return_value=adopted_at):
            response = self.post_action(self.unit_head, work, "adopt", priority="HIGH")
        self.assertEqual(response.status_code, 200, response.content)
        work.refresh_from_db()
        self.assertTrue(work.formal)
        self.assertEqual(work.sla.started_at, adopted_at)
        self.assertIsNone(work.sla.breached_at)
        self.assertGreater(work.sla.current_due_at, adopted_at)

    def test_formal_completion_waits_for_independent_acceptance_and_clock_keeps_running(
        self,
    ):
        work = self.create_work()
        response = self.post_action(
            self.employee,
            work,
            "status",
            status="COMPLETED",
            result="All evidence attached",
        )
        self.assertEqual(response.status_code, 200, response.content)
        work.refresh_from_db()
        self.assertEqual(work.status, "VERIFYING")
        self.assertIsNone(work.sla.stopped_at)
        response = self.post_action(self.unit_head, work, "accept")
        self.assertEqual(response.status_code, 200, response.content)
        work.refresh_from_db()
        self.assertEqual(work.status, "COMPLETED")
        self.assertEqual(work.accepted_by_id, self.unit_head.pk)
        self.assertIsNotNone(work.sla.stopped_at)

    def test_manager_cannot_accept_own_formal_work(self):
        work = self.create_work(assignee=self.unit_head)
        response = self.post_action(
            self.unit_head,
            work,
            "status",
            status="COMPLETED",
            result="Manager completion",
        )
        self.assertEqual(response.status_code, 200, response.content)
        work.refresh_from_db()
        response = self.post_action(self.unit_head, work, "accept")
        self.assertEqual(response.status_code, 403, response.content)
        work.refresh_from_db()
        self.assertEqual(work.status, "VERIFYING")
        response = self.post_action(self.director, work, "accept")
        self.assertEqual(response.status_code, 200, response.content)

    def test_open_mandatory_child_blocks_parent_completion_and_preserves_owner(self):
        parent = self.create_work(actor=self.director, assignee=self.unit_head)
        child = self.create_work(
            actor=self.unit_head,
            assignee=self.employee,
            parent_id=str(parent.pk),
            shared_parent_summary="Shareable target only",
        )
        response = self.post_action(
            self.unit_head,
            parent,
            "status",
            status="COMPLETED",
            result="Premature completion",
        )
        self.assertEqual(response.status_code, 400, response.content)
        parent.refresh_from_db()
        self.assertEqual(parent.assigned_to_id, self.unit_head.pk)
        self.assertEqual(parent.status, "OPEN")
        child.status = "COMPLETED"
        child.save()
        parent.refresh_from_db()
        self.assertEqual(
            parent.status, "OPEN", "Completing children must not auto-close the parent"
        )

    def test_child_assignee_does_not_receive_private_parent_identity(self):
        parent = self.create_work(
            actor=self.director,
            assignee=self.unit_head,
            title="CONFIDENTIAL_BOARD_TARGET",
        )
        child = self.create_work(
            parent_id=str(parent.pk),
            shared_parent_summary="Deliver the approved testing evidence",
        )
        response = self.as_user(self.employee).get(f"{WORK_URL}{child.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["parent_id"])
        self.assertNotIn("CONFIDENTIAL_BOARD_TARGET", response.content.decode())
        self.assertNotIn(str(parent.pk), response.content.decode())
        self.assertEqual(
            response.json()["shared_parent_summary"],
            "Deliver the approved testing evidence",
        )

    def test_waiting_requires_reason_and_does_not_stop_sla(self):
        work = self.create_work()
        response = self.post_action(self.employee, work, "status", status="WAITING")
        self.assertEqual(response.status_code, 400, response.content)
        work.refresh_from_db()
        self.assertEqual(work.status, "OPEN")
        response = self.post_action(
            self.employee,
            work,
            "status",
            status="WAITING",
            blocker="Waiting for approved change window",
        )
        self.assertEqual(response.status_code, 200, response.content)
        work.refresh_from_db()
        self.assertIsNone(work.sla.stopped_at)

    def test_reassignment_keeps_sla_and_cancels_old_pending_mail(self):
        work = self.create_work()
        original = (work.sla.started_at, work.sla.original_due_at)
        response = self.post_action(
            self.unit_head, work, "assign", assignee_id=str(self.colleague.pk)
        )
        self.assertEqual(response.status_code, 200, response.content)
        work.refresh_from_db()
        self.assertEqual((work.sla.started_at, work.sla.original_due_at), original)
        self.assertEqual(work.assignment_version, 2)
        self.assertEqual(
            OutboxEvent.objects.get(
                recipient=self.employee, resource_id=str(work.pk)
            ).status,
            "CANCELLED",
        )
        self.assertEqual(
            OutboxEvent.objects.filter(
                recipient=self.colleague, resource_id=str(work.pk), status="PENDING"
            ).count(),
            1,
        )

    def test_unknown_sensitive_patch_fields_are_rejected_without_mutation(self):
        work = self.create_work()
        for field, value in (
            ("formal", False),
            ("context", "PROJECT_TASK"),
            ("assigned_to_id", str(self.outsider.pk)),
            ("approved_by", str(self.employee.pk)),
        ):
            with self.subTest(field=field):
                response = self.as_user(self.employee).patch(
                    f"{WORK_URL}{work.pk}/",
                    {"version": work.version, field: value},
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.content)
                work.refresh_from_db()
                self.assertTrue(work.formal)
                self.assertEqual(work.context, "UNIT_WORK")
                self.assertEqual(work.assigned_to_id, self.employee.pk)

    def test_stale_version_does_not_overwrite_newer_update(self):
        work = self.create_work()
        response = self.as_user(self.employee).patch(
            f"{WORK_URL}{work.pk}/",
            {"version": work.version, "title": "Newer title"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.as_user(self.employee).patch(
            f"{WORK_URL}{work.pk}/",
            {"version": work.version, "title": "Stale overwrite"},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        work.refresh_from_db()
        self.assertEqual(work.title, "Newer title")

    def test_create_retry_is_one_committed_operation_and_conflicting_payload_is_rejected(
        self,
    ):
        request_id = str(uuid.uuid4())
        payload = {
            "title": "Durable assignment",
            "assignee_id": str(self.employee.pk),
            "personal": False,
            "priority": "CRITICAL",
        }
        self.as_user(self.unit_head)
        first = self.client.post(
            WORK_URL, payload, format="json", HTTP_X_REQUEST_ID=request_id
        )
        self.assertEqual(first.status_code, 201, first.content)
        first_counts = (
            WorkItem.objects.count(),
            SLAInstance.objects.count(),
            Notification.objects.count(),
            OutboxEvent.objects.count(),
        )
        repeated = self.client.post(
            WORK_URL, payload, format="json", HTTP_X_REQUEST_ID=request_id
        )
        self.assertEqual(repeated.status_code, 201, repeated.content)
        self.assertEqual(repeated.json(), first.json())
        self.assertEqual(
            (
                WorkItem.objects.count(),
                SLAInstance.objects.count(),
                Notification.objects.count(),
                OutboxEvent.objects.count(),
            ),
            first_counts,
        )
        self.assertEqual(
            IdempotencyRecord.objects.filter(
                actor=self.unit_head, key=request_id
            ).count(),
            1,
        )
        conflict = self.client.post(
            WORK_URL,
            {**payload, "title": "Conflicting assignment"},
            format="json",
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(conflict.status_code, 409, conflict.content)
        self.assertEqual(WorkItem.objects.count(), 1)

    def test_failed_validation_rolls_back_earlier_domain_writes(self):
        response = self.as_user(self.unit_head).post(
            WORK_URL,
            {
                "title": "Invalid kind",
                "assignee_id": str(self.employee.pk),
                "personal": False,
                "kind": "NOT_A_KIND",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            WorkItem.objects.count(),
            0,
            "A 400 response must not commit the partially created task",
        )
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(OutboxEvent.objects.count(), 0)

    def test_out_of_scope_work_is_absent_from_search_and_detail(self):
        work = self.create_work(
            actor=self.other_head,
            assignee=self.outsider,
            title="SECRET_IAM_CASE_REFERENCE",
        )
        response = self.as_user(self.employee).get(WORK_URL, {"search": "SECRET_IAM"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.rows(response), [])
        self.assertNotIn(str(work.pk), response.content.decode())
        self.assertEqual(self.client.get(f"{WORK_URL}{work.pk}/").status_code, 404)

    def test_overdue_extension_preserves_original_due_and_records_breach_before_change(
        self,
    ):
        work = self.create_work()
        old_due = timezone.now() - timedelta(hours=1)
        original_start = old_due - timedelta(hours=24)
        SLAInstance.objects.filter(work=work).update(
            started_at=original_start,
            original_due_at=old_due,
            current_due_at=old_due,
            breached_at=None,
        )
        response = self.post_action(
            self.unit_head,
            work,
            "sla-adjust",
            due_at=(timezone.now() + timedelta(days=2)).isoformat(),
            reason="Approved change window moved",
        )
        self.assertEqual(response.status_code, 200, response.content)
        work.refresh_from_db()
        self.assertEqual(work.sla.original_due_at, old_due)
        self.assertEqual(work.sla.started_at, original_start)
        self.assertEqual(work.sla.breached_at, old_due)
        self.assertGreater(work.sla.current_due_at, old_due)
        from django.utils.dateparse import parse_datetime

        self.assertEqual(
            parse_datetime(response.json()["sla"]["current_due_at"]),
            work.sla.current_due_at,
        )
        self.assertEqual(response.json()["sla"]["revision"], work.sla.revision)

    def test_self_extension_cannot_be_approved_by_changing_manager_role(self):
        work = self.create_work(assignee=self.unit_head)
        before = work.sla.current_due_at
        response = self.post_action(
            self.unit_head,
            work,
            "sla-adjust",
            due_at=(before + timedelta(days=2)).isoformat(),
            reason="My extension",
        )
        self.assertEqual(response.status_code, 403, response.content)
        work.refresh_from_db()
        self.assertEqual(work.sla.current_due_at, before)
