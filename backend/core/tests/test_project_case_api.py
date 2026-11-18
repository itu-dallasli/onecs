"""Project governance and formal incident coordination are separate flows."""

import uuid
from datetime import timedelta

from django.utils import timezone

from core.models import (
    Case,
    CaseNotice,
    Notification,
    PMAppointment,
    ParticipationRequest,
    ProgressEntry,
    Project,
    ProjectAuthorityGrant,
    ProjectMembership,
    ProjectRevision,
    SLAInstance,
    WorkItem,
)
from core.policy import can_approve_project, can_manage_project
from core.tests.base import AtlasTestCase


PROJECT_URL = "/api/v1/projects/"
CASE_URL = "/api/v1/cases/"
NOTICE_URL = "/api/v1/case-notices/"
PARTICIPATION_URL = "/api/v1/participation-requests/"


class ProjectAPITests(AtlasTestCase):
    def draft(self, author=None):
        author = author or self.employee
        response = self.as_user(author).post(
            PROJECT_URL,
            {
                "title": "Access modernisation",
                "description": "Deliver an audited cross-team access review",
                "expected_outcome": "Verified access evidence",
                "pm_id": str(self.pm.pk),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Project.objects.get(pk=response.json()["id"])

    def submitted(self, author=None):
        project = self.draft(author)
        response = self.as_user(author or self.employee).post(
            f"{PROJECT_URL}{project.pk}/submit/",
            {"version": project.version},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        return project

    def published(self):
        project = self.submitted()
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": project.version, "decision": "APPROVE"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        return project

    def test_private_draft_then_submission_routes_to_pm_not_employee_line_manager(self):
        project = self.draft()
        self.assertEqual(
            self.as_user(self.pm).get(f"{PROJECT_URL}{project.pk}/").status_code, 404
        )
        self.assertEqual(
            self.as_user(self.unit_head).get(f"{PROJECT_URL}{project.pk}/").status_code,
            404,
        )
        response = self.as_user(self.employee).post(
            f"{PROJECT_URL}{project.pk}/submit/",
            {"version": project.version},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        self.assertEqual(project.status, "SUBMITTED")
        self.assertEqual(project.submitted_revision, 1)
        self.assertEqual(
            self.as_user(self.pm).get(f"{PROJECT_URL}{project.pk}/").status_code, 200
        )
        self.assertEqual(
            self.as_user(self.unit_head).get(f"{PROJECT_URL}{project.pk}/").status_code,
            404,
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.pm, resource_id=str(project.pk)
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.unit_head, resource_id=str(project.pk)
            ).exists()
        )

    def test_normal_unit_head_cannot_approve_subordinate_project_proposal(self):
        project = self.submitted()
        response = self.as_user(self.unit_head).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": project.version, "decision": "APPROVE"},
            format="json",
        )
        self.assertIn(response.status_code, (403, 404), response.content)
        project.refresh_from_db()
        self.assertEqual(project.status, "SUBMITTED")
        self.assertIsNone(project.published_revision)

    def test_pm_cannot_approve_own_proposal_but_pm_governing_head_can(self):
        project = self.submitted(author=self.pm)
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": project.version, "decision": "APPROVE"},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        project.refresh_from_db()
        self.assertEqual(project.status, "SUBMITTED")
        response = self.as_user(self.pm_head).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": project.version, "decision": "APPROVE"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        self.assertEqual(project.approved_by_id, self.pm_head.pk)
        self.assertEqual(project.status, "PLANNED")

    def test_revision_retains_previous_content_and_decision(self):
        project = self.submitted()
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {
                "version": project.version,
                "decision": "REVISION",
                "note": "Clarify the expected outcome",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        response = self.as_user(self.employee).patch(
            f"{PROJECT_URL}{project.pk}/",
            {
                "version": project.version,
                "description": "Clarified scope and test evidence",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        response = self.client.post(
            f"{PROJECT_URL}{project.pk}/submit/",
            {"version": project.version},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": project.version, "decision": "APPROVE"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        self.assertEqual(project.published_revision, 2)
        previous = ProjectRevision.objects.get(project=project, number=1)
        self.assertEqual(previous.decision, "REVISION")
        self.assertEqual(previous.decision_note, "Clarify the expected outcome")
        self.assertEqual(
            previous.content["description"],
            "Deliver an audited cross-team access review",
        )

    def test_stale_decision_cannot_publish_newer_project_version(self):
        project = self.submitted()
        stale_version = project.version
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {
                "version": project.version,
                "decision": "REVISION",
                "note": "Scope review",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": stale_version, "decision": "APPROVE"},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        project.refresh_from_db()
        self.assertIsNone(project.published_revision)

    def test_repeated_approval_replays_committed_response_without_duplicate_publication(
        self,
    ):
        project = self.submitted()
        payload = {"version": project.version, "decision": "APPROVE"}
        request_id = str(uuid.uuid4())
        self.as_user(self.pm)
        first = self.client.post(
            f"{PROJECT_URL}{project.pk}/review/",
            payload,
            format="json",
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(first.status_code, 200, first.content)
        count = Notification.objects.count()
        retry = self.client.post(
            f"{PROJECT_URL}{project.pk}/review/",
            payload,
            format="json",
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(retry.status_code, 200, retry.content)
        self.assertEqual(first.json(), retry.json())
        self.assertEqual(ProjectRevision.objects.filter(project=project).count(), 1)
        self.assertEqual(Notification.objects.count(), count)

    def test_member_resource_acceptance_does_not_transfer_project_management(self):
        project = self.published()
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/members/",
            {
                "version": project.version,
                "user_id": str(self.employee.pk),
                "summary": "Request two days for review",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        request = ParticipationRequest.objects.get(pk=response.json()["id"])
        response = self.as_user(self.pm).post(
            f"{PARTICIPATION_URL}{request.pk}/decide/",
            {"version": request.version, "decision": "ACCEPT"},
            format="json",
        )
        self.assertIn(response.status_code, (403, 404), response.content)
        self.assertFalse(
            ProjectMembership.objects.filter(
                project=project, user=self.employee, active=True
            ).exists()
        )
        response = self.as_user(self.unit_head).post(
            f"{PARTICIPATION_URL}{request.pk}/decide/",
            {"version": request.version, "decision": "ACCEPT"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        membership = ProjectMembership.objects.get(project=project, user=self.employee)
        self.assertTrue(membership.active)
        self.assertEqual(membership.accepted_by_id, self.unit_head.pk)
        project.audience.add(self.unit)
        project.refresh_from_db()
        response = self.as_user(self.unit_head).post(
            f"{PROJECT_URL}{project.pk}/progress/",
            {
                "version": project.version,
                "done": "Attempted project management",
                "progress": 50,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_project_task_needs_accepted_member_and_never_gets_unit_sla(self):
        project = self.published()
        payload = {
            "version": project.version,
            "title": "Perform evidence review",
            "assignee_id": str(self.employee.pk),
        }
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/tasks/", payload, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(WorkItem.objects.count(), 0)
        ProjectMembership.objects.create(
            project=project, user=self.employee, accepted_by=self.unit_head
        )
        response = self.client.post(
            f"{PROJECT_URL}{project.pk}/tasks/", payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        task = WorkItem.objects.get(pk=response.json()["id"])
        self.assertEqual(task.context, "PROJECT_TASK")
        self.assertEqual(task.project_id, project.pk)
        self.assertFalse(SLAInstance.objects.filter(work=task).exists())

    def test_unpublished_project_cannot_receive_execution_tasks(self):
        project = self.submitted()
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/tasks/",
            {
                "version": project.version,
                "title": "Premature task",
                "assignee_id": str(self.pm.pk),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(WorkItem.objects.filter(project=project).exists())

    def test_invalid_project_progress_rolls_back_new_contribution(self):
        project = self.published()
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/progress/",
            {
                "version": project.version,
                "done": "Invalid percentage mutation",
                "progress": 150,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(ProgressEntry.objects.filter(project=project).count(), 0)
        project.refresh_from_db()
        self.assertEqual(project.progress, 0)
        self.assertEqual(project.status, "PLANNED")

    def test_inactive_pm_cannot_receive_new_proposal_or_publish_existing_one(self):
        project = self.submitted()
        self.pm.is_active = False
        self.pm.save()
        response = self.as_user(self.employee).post(
            PROJECT_URL,
            {
                "title": "New proposal",
                "description": "Should reroute",
                "pm_id": str(self.pm.pk),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        response = self.as_user(self.pm_head).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": project.version, "decision": "APPROVE"},
            format="json",
        )
        self.assertIn(response.status_code, (403, 404), response.content)
        project.refresh_from_db()
        self.assertIsNone(project.published_revision)

    def test_pm_grants_scoped_expiring_authority_without_redelegation(self):
        project = self.published()
        expires_at = timezone.now() + timedelta(days=7)
        payload = {
            "version": project.version,
            "user_id": str(self.colleague.pk),
            "permissions": ["approve"],
            "expires_at": expires_at.isoformat(),
            "reason": "Independent review cover",
        }
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/authorities/", payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        grant = ProjectAuthorityGrant.objects.get(pk=response.json()["id"])
        self.assertEqual(grant.granted_by_id, self.pm.pk)
        self.assertEqual(grant.permissions, ["approve"])
        self.assertEqual(grant.expires_at, expires_at)
        self.assertTrue(can_approve_project(self.colleague, project))
        self.assertFalse(can_manage_project(self.colleague, project))
        project.refresh_from_db()
        response = self.as_user(self.colleague).post(
            f"{PROJECT_URL}{project.pk}/authorities/",
            {
                **payload,
                "version": project.version,
                "user_id": str(self.outsider.pk),
                "permissions": ["manage"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(project.authorities.count(), 1)
        response = self.as_user(self.pm).get(f"{PROJECT_URL}{project.pk}/authorities/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(response.json()["results"][0]["id"], str(grant.pk))

    def test_authority_revocation_is_versioned_and_removes_delegate_access(self):
        project = self.published()
        grant = ProjectAuthorityGrant.objects.create(
            project=project,
            user=self.colleague,
            granted_by=self.pm,
            permissions=["manage"],
            expires_at=timezone.now() + timedelta(days=2),
            reason="Temporary cover",
        )
        self.assertTrue(can_manage_project(self.colleague, project))
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/authority-revoke/",
            {
                "version": project.version,
                "grant_id": str(grant.pk),
                "reason": "PM has returned",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        grant.refresh_from_db()
        project.refresh_from_db()
        self.assertFalse(grant.active)
        self.assertEqual(grant.version, 2)
        self.assertFalse(can_manage_project(self.colleague, project))
        response = self.as_user(self.colleague).post(
            f"{PROJECT_URL}{project.pk}/progress/",
            {"version": project.version, "done": "Revoked operation", "progress": 60},
            format="json",
        )
        self.assertIn(response.status_code, (403, 404), response.content)
        self.assertFalse(ProgressEntry.objects.filter(project=project).exists())

    def test_significant_change_keeps_published_project_live_until_independent_approval(
        self,
    ):
        project = self.published()
        original_title = project.title
        original_status = project.status
        original_audience = set(project.audience.values_list("id", flat=True))
        response = self.as_user(self.pm).post(
            f"{PROJECT_URL}{project.pk}/propose-change/",
            {
                "version": project.version,
                "title": "New approved scope",
                "description": "Expanded scope proposal",
                "audience_org_ids": [str(self.unit.pk), str(self.other_unit.pk)],
                "reason": "Approved programme expansion needs review",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        project.refresh_from_db()
        self.assertEqual(project.status, original_status)
        self.assertEqual(project.title, original_title)
        self.assertEqual(project.published_revision, 1)
        self.assertEqual(project.submitted_revision, 2)
        self.assertSetEqual(
            set(project.audience.values_list("id", flat=True)), original_audience
        )
        revision = ProjectRevision.objects.get(project=project, number=2)
        self.assertEqual(revision.author_id, self.pm.pk)
        self.assertEqual(revision.decision, "PENDING")
        response = self.client.post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": project.version, "decision": "APPROVE"},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        project.refresh_from_db()
        self.assertEqual(project.published_revision, 1)
        response = self.as_user(self.pm_head).post(
            f"{PROJECT_URL}{project.pk}/review/",
            {"version": project.version, "decision": "APPROVE"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        self.assertEqual(project.title, "New approved scope")
        self.assertEqual(project.status, original_status)
        self.assertEqual(project.published_revision, 2)
        self.assertSetEqual(
            set(project.audience.values_list("id", flat=True)),
            {self.unit.pk, self.other_unit.pk},
        )

    def test_pm_transfer_requires_governing_authority_and_invalidates_previous_delegations(
        self,
    ):
        project = self.published()
        project.audience.add(self.unit)
        grant = ProjectAuthorityGrant.objects.create(
            project=project,
            user=self.colleague,
            granted_by=self.pm,
            permissions=["manage"],
            expires_at=timezone.now() + timedelta(days=2),
            reason="Old PM delegate",
        )
        appointment = PMAppointment.objects.create(
            user=self.outsider, governing_org=self.other_unit
        )
        payload = {
            "version": project.version,
            "appointment_id": str(appointment.pk),
            "reason": "Controlled portfolio transfer",
        }
        response = self.as_user(self.unit_head).post(
            f"{PROJECT_URL}{project.pk}/transfer/", payload, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        project.refresh_from_db()
        self.assertEqual(project.appointment_id, self.appointment.pk)
        response = self.as_user(self.pm_head).post(
            f"{PROJECT_URL}{project.pk}/transfer/", payload, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        project.refresh_from_db()
        grant.refresh_from_db()
        self.assertEqual(project.appointment_id, appointment.pk)
        self.assertFalse(grant.active)
        self.assertFalse(can_manage_project(self.pm, project))
        self.assertFalse(can_manage_project(self.pm_head, project))
        self.assertFalse(can_manage_project(self.colleague, project))
        self.assertTrue(can_manage_project(self.outsider, project))
        self.assertTrue(can_manage_project(self.other_head, project))
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.outsider, resource_id=str(project.pk)
            ).exists()
        )

    def test_revision_history_is_available_to_pm_and_author_but_not_general_audience(
        self,
    ):
        project = self.published()
        project.audience.add(self.unit)
        response = self.as_user(self.pm).get(f"{PROJECT_URL}{project.pk}/revisions/")
        self.assertEqual(response.status_code, 200, response.content)
        revision = response.json()["results"][0]
        self.assertEqual(revision["number"], 1)
        self.assertEqual(revision["decision"], "APPROVE")
        self.assertEqual(revision["author_id"], str(self.employee.pk))
        self.assertEqual(
            self.as_user(self.employee)
            .get(f"{PROJECT_URL}{project.pk}/revisions/")
            .status_code,
            200,
        )
        self.assertEqual(
            self.as_user(self.colleague)
            .get(f"{PROJECT_URL}{project.pk}/revisions/")
            .status_code,
            403,
        )
        self.assertEqual(
            self.as_user(self.unit_head)
            .get(f"{PROJECT_URL}{project.pk}/revisions/")
            .status_code,
            403,
        )


class CaseAPITests(AtlasTestCase):
    def case(self, **extra):
        data = {
            "title": "Critical incident coordination",
            "description": "Coordinate containment work",
            "priority": "CRITICAL",
        }
        data.update(extra)
        response = self.as_user(self.unit_head).post(CASE_URL, data, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return Case.objects.get(pk=response.json()["id"])

    def test_unit_head_opens_formal_case_with_target_and_employee_only_sends_notice(
        self,
    ):
        case = self.case()
        self.assertEqual(
            case.sla.current_due_at - case.sla.started_at,
            __import__("datetime").timedelta(hours=24),
        )
        response = self.as_user(self.employee).post(
            CASE_URL,
            {"title": "Unauthorized official case", "priority": "CRITICAL"},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        response = self.client.post(
            NOTICE_URL,
            {
                "title": "Suspicious observation",
                "description": "Observation to review immediately",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        notice = CaseNotice.objects.get(pk=response.json()["id"])
        self.assertIsNone(notice.case_id)
        self.assertEqual(Case.objects.count(), 1)
        self.assertEqual(SLAInstance.objects.count(), 1)

    def test_team_manager_needs_explicit_case_creation_delegation(self):
        response = self.as_user(self.team_manager).post(
            CASE_URL, {"title": "Not delegated"}, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        grant = self.team_manager.role_grants.get(role="TEAM_MANAGER")
        grant.permissions = ["case.create"]
        grant.save()
        response = self.client.post(
            CASE_URL, {"title": "Delegated case", "priority": "HIGH"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_case_closure_needs_evidence_and_independent_verifier(self):
        case = self.case()
        path = f"{CASE_URL}{case.pk}/request-close/"
        response = self.as_user(self.unit_head).post(
            path, {"version": case.version, "summary": "Contained"}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        case.refresh_from_db()
        response = self.client.post(
            path,
            {
                "version": case.version,
                "summary": "Contained",
                "evidence": "Internal ticket E-123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        case.refresh_from_db()
        self.assertEqual(case.status, "VERIFYING")
        self.assertIsNone(case.sla.stopped_at)
        payload = {
            "version": case.version,
            "evidence": "Independent verification V-123",
        }
        response = self.client.post(
            f"{CASE_URL}{case.pk}/verify-close/", payload, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        response = self.as_user(self.director).post(
            f"{CASE_URL}{case.pk}/verify-close/", payload, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        case.refresh_from_db()
        self.assertEqual(case.status, "CLOSED")
        self.assertEqual(case.verifier_id, self.director.pk)
        self.assertIsNotNone(case.sla.stopped_at)

    def test_open_mandatory_case_action_blocks_close(self):
        case = self.case()
        WorkItem.objects.create(
            title="Mandatory containment action",
            context="CASE_ACTION",
            case=case,
            assigned_to=self.unit_head,
            created_by=self.unit_head,
            owner_org=self.unit,
            mandatory=True,
        )
        response = self.as_user(self.unit_head).post(
            f"{CASE_URL}{case.pk}/request-close/",
            {
                "version": case.version,
                "summary": "Too early",
                "evidence": "Not complete",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        case.refresh_from_db()
        self.assertEqual(case.status, "NEW")
        self.assertIsNone(case.sla.stopped_at)

    def test_case_action_requires_accepted_participation_and_uses_case_clock(self):
        case = self.case()
        data = {
            "version": case.version,
            "title": "IAM action",
            "assignee_id": str(self.outsider.pk),
        }
        response = self.as_user(self.unit_head).post(
            f"{CASE_URL}{case.pk}/actions/", data, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        case.members.add(self.outsider)
        response = self.client.post(
            f"{CASE_URL}{case.pk}/actions/", data, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        action = WorkItem.objects.get(pk=response.json()["id"])
        self.assertEqual(action.context, "CASE_ACTION")
        self.assertFalse(SLAInstance.objects.filter(work=action).exists())
        self.assertEqual(SLAInstance.objects.filter(case=case).count(), 1)
