"""Person drawers aggregate only records the reader may currently access."""
from datetime import timedelta

from django.utils import timezone

from core.models import Case, ProgressEntry, Project, ProjectMembership, ProjectRevision, WorkItem
from core.tests.base import OnecsTestCase


class PersonWorkloadTests(OnecsTestCase):
    def setUp(self):
        super().setUp()
        self.work = WorkItem.objects.create(title="Visible unit task", description="Unit details", assigned_to=self.employee, created_by=self.unit_head, owner_org=self.team, priority="CRITICAL", due_at=timezone.now() - timedelta(days=1))
        self.project = Project.objects.create(title="Technical project internal title", description="PROJECT-TECHNICAL-SECRET", created_by=self.pm, owner_org=self.other_unit, appointment=self.appointment, status="ACTIVE", published_revision=1)
        ProjectRevision.objects.create(project=self.project, number=1, author=self.pm, content={"title": "Approved project summary", "expected_outcome": "Approved outcome"})
        ProjectMembership.objects.create(project=self.project, user=self.employee, role="CONTRIBUTOR")
        self.project_work = WorkItem.objects.create(title="Assigned project task", description="PROJECT-TASK-SECRET", result="PROJECT-RESULT-SECRET", context="PROJECT_TASK", project=self.project, owner_org=self.team, assigned_to=self.employee, created_by=self.pm)
        self.case = Case.objects.create(title="Visible case", owner_org=self.team, created_by=self.unit_head, coordinator=self.team_manager)
        self.case.members.add(self.employee)
        self.case_work = WorkItem.objects.create(title="Visible case action", context="CASE_ACTION", case=self.case, owner_org=self.team, assigned_to=self.employee, created_by=self.unit_head)
        ProgressEntry.objects.create(work=self.work, author=self.employee, author_org=self.team, done="Visible completed unit step")
        ProgressEntry.objects.create(project=self.project, author=self.employee, author_org=self.team, done="PROJECT-CONTRIBUTION-SECRET")
        ProgressEntry.objects.create(case=self.case, author=self.employee, author_org=self.team, done="Visible case contribution")
        hidden_case = Case.objects.create(title="UNRELATED-CASE-SECRET", description="UNRELATED-DESCRIPTION-SECRET", owner_org=self.other_unit, created_by=self.other_head, coordinator=self.other_head)
        ProgressEntry.objects.create(case=hidden_case, author=self.employee, author_org=self.team, done="HIDDEN-CONTRIBUTION-SECRET")
        hidden_project = Project.objects.create(title="DRAFT-PROJECT-SECRET", description="DRAFT-DESCRIPTION-SECRET", created_by=self.employee, owner_org=self.team, appointment=self.appointment, status="DRAFT")
        ProjectMembership.objects.create(project=hidden_project, user=self.employee)

    def endpoint(self, person=None, action="workload"):
        return f"/api/v1/people/{(person or self.employee).pk}/{action}/"

    def test_unit_manager_sees_visible_assigned_contexts_and_safe_project_summary(self):
        response = self.as_user(self.unit_head).get(self.endpoint())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["summary"]["work_total"], 3)
        self.assertEqual(response.data["summary"]["by_context"], {"UNIT_WORK": 1, "PROJECT_TASK": 1, "CASE_ACTION": 1})
        self.assertEqual(response.data["summary"]["overdue_work"], 1)
        self.assertEqual(response.data["summary"]["projects"], 1)
        self.assertEqual(response.data["summary"]["cases"], 1)
        self.assertEqual(response.data["summary"]["contributions"], 3)
        self.assertTrue(response.data["permissions"]["can_assign_work"])
        self.assertEqual(response.data["assignment"]["allowed_target"]["person_id"], str(self.employee.pk))
        self.assertEqual(response.data["projects"][0]["visibility"], "SUMMARY")
        self.assertEqual(response.data["projects"][0]["membership_role"], "CONTRIBUTOR")
        body = response.content.decode()
        for secret in ("PROJECT-TECHNICAL-SECRET", "PROJECT-TASK-SECRET", "PROJECT-RESULT-SECRET", "PROJECT-CONTRIBUTION-SECRET", "DRAFT-PROJECT-SECRET", "UNRELATED-CASE-SECRET", "HIDDEN-CONTRIBUTION-SECRET"):
            self.assertNotIn(secret, body)

    def test_self_keeps_project_detail_but_has_no_formal_assignment_authority(self):
        response = self.as_user(self.employee).get(self.endpoint())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["permissions"]["can_assign_work"])
        self.assertTrue(response.data["permissions"]["can_create_personal_work"])
        self.assertIn("PROJECT-TASK-SECRET", response.content.decode())

    def test_colleague_and_unrelated_manager_cannot_inspect_person_workload(self):
        for actor in (self.colleague, self.other_head, self.pm, self.admin):
            with self.subTest(actor=actor.username):
                response = self.as_user(actor).get(self.endpoint())
                self.assertEqual(response.status_code, 403, response.data)
                self.assertNotIn("Visible unit task", response.content.decode())

    def test_inactive_person_is_not_an_assignment_target_or_detail(self):
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        self.assertEqual(self.as_user(self.unit_head).get(self.endpoint()).status_code, 404)
        response = self.as_user(self.unit_head).get("/api/v1/people/?assignable=true")
        self.assertNotIn(str(self.employee.pk), {str(item["id"]) for item in response.data["results"]})

    def test_assignable_people_follow_org_hierarchy_and_pm_does_not_assign_unit_work(self):
        response = self.as_user(self.unit_head).get("/api/v1/people/?assignable=true")
        ids = {str(item["id"]) for item in response.data["results"]}
        self.assertIn(str(self.employee.pk), ids)
        self.assertIn(str(self.direct_employee.pk), ids)
        self.assertIn(str(self.team_manager.pk), ids)
        self.assertNotIn(str(self.outsider.pk), ids)
        response = self.as_user(self.team_manager).get("/api/v1/people/?assignable=true")
        ids = {str(item["id"]) for item in response.data["results"]}
        self.assertIn(str(self.employee.pk), ids)
        self.assertNotIn(str(self.direct_employee.pk), ids)
        response = self.as_user(self.pm).get("/api/v1/people/?assignable=true")
        self.assertEqual(response.data["count"], 0)

    def test_director_sees_descendants_and_revoked_manager_role_is_effective_immediately(self):
        self.assertEqual(self.as_user(self.director).get(self.endpoint()).status_code, 200)
        self.assertEqual(self.as_user(self.unit_head).get(self.endpoint()).status_code, 200)
        self.unit_head.role_grants.filter(role="UNIT_HEAD").update(active=False)
        response = self.as_user(self.unit_head).get(self.endpoint())
        self.assertEqual(response.status_code, 403)
        scope = self.as_user(self.unit_head).get(self.endpoint(action="assignable-scope"))
        self.assertEqual(scope.status_code, 200, scope.data)
        self.assertFalse(scope.data["permissions"]["can_assign_work"])
        self.assertIsNone(scope.data["assignment"]["allowed_target"])

    def test_expired_role_removes_person_assignment_scope(self):
        self.unit_head.role_grants.filter(role="UNIT_HEAD").update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.as_user(self.unit_head).get("/api/v1/people/?assignable=true&search=employee")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
