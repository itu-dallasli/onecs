"""Database boundaries that must survive a missed application validation."""

from datetime import datetime, timedelta, timezone

from django.db import IntegrityError, transaction

from core.models import Case, Project, ProjectMembership, SLAInstance, WorkItem
from core.tests.base import OnecsTestCase


class ContextConstraintTests(OnecsTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            title="Private proposal",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
        )
        self.case = Case.objects.create(
            title="Incident",
            created_by=self.unit_head,
            owner_org=self.unit,
            coordinator=self.unit_head,
        )

    def work(self, **extra):
        data = {
            "title": "Action",
            "created_by": self.unit_head,
            "assigned_to": self.employee,
            "owner_org": self.team,
        }
        data.update(extra)
        return WorkItem.objects.create(**data)

    def test_unit_work_cannot_hold_project_or_case_reference(self):
        for reference in ({"project": self.project}, {"case": self.case}):
            with self.subTest(reference=list(reference)):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    self.work(context="UNIT_WORK", **reference)

    def test_project_task_requires_project_and_forbids_case(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.work(context="PROJECT_TASK")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.work(context="PROJECT_TASK", project=self.project, case=self.case)
        self.assertEqual(
            self.work(context="PROJECT_TASK", project=self.project).project,
            self.project,
        )

    def test_case_action_requires_case_and_forbids_project(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.work(context="CASE_ACTION")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.work(context="CASE_ACTION", project=self.project, case=self.case)
        self.assertEqual(
            self.work(context="CASE_ACTION", case=self.case).case, self.case
        )

    def test_service_target_has_exactly_one_source(self):
        now = datetime(2026, 11, 18, 9, tzinfo=timezone.utc)
        data = {
            "policy_snapshot": {},
            "started_at": now,
            "original_due_at": now + timedelta(days=1),
            "current_due_at": now + timedelta(days=1),
        }
        work = self.work()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SLAInstance.objects.create(**data)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SLAInstance.objects.create(work=work, case=self.case, **data)
        SLAInstance.objects.create(work=work, **data)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SLAInstance.objects.create(work=work, **data)

    def test_one_membership_per_project_and_person(self):
        ProjectMembership.objects.create(project=self.project, user=self.employee)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectMembership.objects.create(
                project=self.project, user=self.employee, role="LEAD"
            )
