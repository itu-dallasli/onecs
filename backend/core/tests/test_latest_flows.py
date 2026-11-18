"""Final integration regressions for controlled sharing and self-service."""

import uuid
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    ApiClient,
    Case,
    CaseNotice,
    CommunityCard,
    ProgressEntry,
    Project,
    ProjectMembership,
    ProjectRevision,
    SLAInstance,
    WorkItem,
)
from core.services import create_sla
from core.tests.base import AtlasTestCase


class ControlledSharingTests(AtlasTestCase):
    def submitted_card(self):
        project = Project.objects.create(
            title="Private project scope",
            description="INTERNAL_PROJECT_DESCRIPTION",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="PLANNED",
            published_revision=1,
        )
        ProjectMembership.objects.create(
            project=project, user=self.employee, accepted_by=self.unit_head
        )
        ProjectRevision.objects.create(
            project=project,
            number=1,
            author=self.employee,
            decision="APPROVE",
            content={
                "title": "Reviewed project summary",
                "expected_outcome": "Shareable outcome",
            },
        )
        response = self.as_user(self.employee).post(
            "/api/v1/community/",
            {
                "title": "Knowledge sharing session",
                "body": "Learn how our team organises access reviews",
                "source_type": "project",
                "source_id": str(project.pk),
                "all_cs": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        card = CommunityCard.objects.get(pk=response.json()["id"])
        response = self.client.post(
            f"/api/v1/community/{card.pk}/submit/",
            {"version": card.version},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        card.refresh_from_db()
        return project, card

    def test_pm_content_approval_and_unit_audience_publication_are_separate(self):
        project, card = self.submitted_card()
        response = self.as_user(self.unit_head).post(
            f"/api/v1/community/{card.pk}/publish/",
            {"version": card.version},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        response = self.as_user(self.pm).post(
            f"/api/v1/community/{card.pk}/approve-content/",
            {"version": card.version},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        card.refresh_from_db()
        self.assertEqual(card.status, "CONTENT_APPROVED")
        self.assertEqual(card.content_approved_by_id, self.pm.pk)
        response = self.client.post(
            f"/api/v1/community/{card.pk}/publish/",
            {"version": card.version},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        response = self.as_user(self.unit_head).post(
            f"/api/v1/community/{card.pk}/publish/",
            {"version": card.version},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        response = self.as_user(self.outsider).get(f"/api/v1/community/{card.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["source_id"])
        self.assertFalse(response.json()["source_accessible"])
        self.assertNotIn("INTERNAL_PROJECT_DESCRIPTION", response.content.decode())
        self.assertEqual(
            self.client.get(f"/api/v1/projects/{project.pk}/").status_code, 404
        )
        before = (WorkItem.objects.count(), ProjectMembership.objects.count())
        response = self.client.post(
            f"/api/v1/community/{card.pk}/interest/",
            {"interested": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            (WorkItem.objects.count(), ProjectMembership.objects.count()), before
        )

    def test_source_change_invalidates_previously_approved_card(self):
        project, card = self.submitted_card()
        response = self.as_user(self.pm).post(
            f"/api/v1/community/{card.pk}/approve-content/",
            {"version": card.version},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        card.refresh_from_db()
        project.version += 1
        project.save()
        response = self.as_user(self.unit_head).post(
            f"/api/v1/community/{card.pk}/publish/",
            {"version": card.version},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        card.refresh_from_db()
        self.assertEqual(card.status, "CONTENT_APPROVED")


class NoticeAndVerificationTests(AtlasTestCase):
    def test_notice_conversion_retry_creates_one_formal_case_and_sla(self):
        notice = CaseNotice.objects.create(
            title="Reported suspicious access",
            description="Observation awaiting review",
            created_by=self.employee,
            owner_org=self.team,
        )
        request_id = str(uuid.uuid4())
        payload = {"version": notice.version, "priority": "CRITICAL"}
        response = self.as_user(self.unit_head).post(
            f"/api/v1/case-notices/{notice.pk}/convert/",
            payload,
            format="json",
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(response.status_code, 201, response.content)
        repeated = self.client.post(
            f"/api/v1/case-notices/{notice.pk}/convert/",
            payload,
            format="json",
            HTTP_X_REQUEST_ID=request_id,
        )
        self.assertEqual(repeated.status_code, 201, repeated.content)
        self.assertEqual(repeated.json(), response.json())
        notice.refresh_from_db()
        self.assertEqual(notice.status, "CONVERTED")
        self.assertEqual(str(notice.case_id), response.json()["id"])
        self.assertEqual(Case.objects.count(), 1)
        self.assertEqual(SLAInstance.objects.count(), 1)

    def test_notice_dismissal_requires_case_authority_and_reason(self):
        notice = CaseNotice.objects.create(
            title="Observation",
            description="No case yet",
            created_by=self.employee,
            owner_org=self.team,
        )
        url = f"/api/v1/case-notices/{notice.pk}/dismiss/"
        response = self.as_user(self.employee).post(
            url,
            {"version": notice.version, "reason": "Employee decision"},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        response = self.as_user(self.unit_head).post(
            url, {"version": notice.version}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        notice.refresh_from_db()
        self.assertEqual(notice.status, "PENDING")
        response = self.client.post(
            url,
            {
                "version": notice.version,
                "reason": "Duplicate of an existing observation",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        notice.refresh_from_db()
        self.assertEqual(notice.status, "DISMISSED")
        self.assertEqual(Case.objects.count(), 0)
        self.assertEqual(SLAInstance.objects.count(), 0)

    def test_ordinary_team_management_does_not_grant_independent_case_verification(
        self,
    ):
        case = Case.objects.create(
            title="Team-scoped case",
            description="Awaiting independent decision",
            created_by=self.unit_head,
            coordinator=self.unit_head,
            owner_org=self.team,
            status="VERIFYING",
            closure_requested_by=self.unit_head,
            closure_summary="Contained",
            verification_evidence="Evidence reference",
        )
        create_sla(case=case)
        payload = {"version": case.version, "evidence": "Independent review evidence"}
        response = self.as_user(self.team_manager).post(
            f"/api/v1/cases/{case.pk}/verify-close/", payload, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        case.refresh_from_db()
        self.assertEqual(case.status, "VERIFYING")
        grant = self.team_manager.role_grants.get(role="TEAM_MANAGER")
        grant.permissions = ["case.verify"]
        grant.save()
        response = self.client.post(
            f"/api/v1/cases/{case.pk}/verify-close/", payload, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        case.refresh_from_db()
        self.assertEqual(case.status, "CLOSED")
        self.assertEqual(case.verifier_id, self.team_manager.pk)


class SelfServiceAndApiScopeTests(AtlasTestCase):
    def test_expertise_is_voluntary_self_declaration_and_cannot_edit_another_person(
        self,
    ):
        response = self.as_user(self.employee).patch(
            f"/api/v1/people/{self.employee.pk}/",
            {"expertise": ["  IAM  ", "IAM", "Threat modelling"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.expertise, ["IAM", "Threat modelling"])
        response = self.as_user(self.unit_head).patch(
            f"/api/v1/people/{self.employee.pk}/",
            {"expertise": ["Forced assignment"]},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.expertise, ["IAM", "Threat modelling"])
        self.assertEqual(WorkItem.objects.count(), 0)

    def test_contribution_correction_preserves_original_record_author_org_and_chain(
        self,
    ):
        work = WorkItem.objects.create(
            title="Personal review",
            created_by=self.employee,
            assigned_to=self.employee,
            owner_org=self.team,
        )
        original = ProgressEntry.objects.create(
            work=work,
            author=self.employee,
            author_org=self.team,
            done="Original result",
        )
        self.employee.primary_org = self.other_unit
        self.employee.save()
        response = self.as_user(self.employee).patch(
            f"/api/v1/contributions/{original.pk}/",
            {
                "version": original.version,
                "done": "Corrected result",
                "next_step": "Collect evidence",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        new = ProgressEntry.objects.get(pk=response.json()["id"])
        self.assertEqual(new.previous_id, original.pk)
        self.assertEqual(new.author_id, self.employee.pk)
        self.assertEqual(new.author_org_id, self.team.pk)
        self.assertEqual(new.version, 2)
        original.refresh_from_db()
        self.assertEqual(original.done, "Original result")
        repeated = self.client.patch(
            f"/api/v1/contributions/{original.pk}/",
            {"version": original.version, "done": "Forked result"},
            format="json",
        )
        self.assertEqual(repeated.status_code, 409, repeated.content)
        response = self.as_user(self.unit_head).patch(
            f"/api/v1/contributions/{new.pk}/",
            {"version": new.version, "done": "Manager pretending to be author"},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(ProgressEntry.objects.count(), 2)

    def test_external_token_org_scope_narrows_directory_people_and_resources(self):
        inside = WorkItem.objects.create(
            title="In token scope",
            assigned_to=self.employee,
            created_by=self.unit_head,
            owner_org=self.team,
        )
        outside = WorkItem.objects.create(
            title="OUT_OF_TOKEN_SCOPE",
            assigned_to=self.outsider,
            created_by=self.other_head,
            owner_org=self.other_unit,
        )
        api_client = ApiClient.objects.create(
            name="Scoped read-only client",
            user=self.director,
            org_node=self.unit,
            scopes=["atlas:read"],
        )
        now = timezone.now()
        token = jwt.encode(
            {
                "sub": str(api_client.pk),
                "ver": api_client.token_version,
                "aud": settings.JWT_AUDIENCE,
                "iss": settings.JWT_ISSUER,
                "iat": now,
                "exp": now + timedelta(minutes=5),
                "jti": str(uuid.uuid4()),
            },
            settings.SECRET_KEY,
            algorithm="HS256",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = client.get("/api/v1/organization/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertSetEqual(
            {row["id"] for row in self.rows(response)},
            {str(self.unit.pk), str(self.team.pk)},
        )
        response = client.get("/api/v1/people/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(
            all(
                row["primary_org_id"] in {str(self.unit.pk), str(self.team.pk)}
                for row in self.rows(response)
            )
        )
        response = client.get("/api/v1/work/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertSetEqual(
            {row["id"] for row in self.rows(response)}, {str(inside.pk)}
        )
        self.assertEqual(client.get(f"/api/v1/work/{outside.pk}/").status_code, 404)
        self.assertEqual(
            client.post(
                "/api/v1/work/", {"title": "Token write"}, format="json"
            ).status_code,
            403,
        )
