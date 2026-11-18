"""A bearer client can only observe its org through every secondary surface."""

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    Announcement,
    ApiClient,
    AuditEvent,
    CommunityCard,
    CaseNotice,
    Credential,
    Notification,
    ParticipationRequest,
    PMAppointment,
    ProgressEntry,
    Project,
    ProjectMembership,
    ProjectRevision,
    Report,
    ReportSelection,
    WorkItem,
)
from core.policy import can_read_work, report_source
from core.tests.base import AtlasTestCase
from core.views import issue_token


class SecondaryBearerScopeTests(AtlasTestCase):
    def setUp(self):
        super().setUp()
        self.inside_work = WorkItem.objects.create(
            title="Inside scoped action",
            owner_org=self.team,
            assigned_to=self.employee,
            created_by=self.director,
            priority="CRITICAL",
        )
        self.outside_work = WorkItem.objects.create(
            title="Outside scoped sentinel",
            owner_org=self.other_unit,
            assigned_to=self.outsider,
            created_by=self.director,
            priority="CRITICAL",
        )
        self.inside_project = self.project("Inside project", self.team)
        self.outside_project = self.project("Outside project sentinel", self.other_unit)
        self.inside_card = self.card("Inside card", self.team, self.employee)
        self.outside_card = self.card(
            "Outside card sentinel", self.other_unit, self.outsider
        )
        self.inside_announcement = self.announcement("Inside announcement", self.unit)
        self.outside_announcement = self.announcement(
            "Outside announcement sentinel", self.other_unit
        )
        self.inside_credential = self.credential(
            self.employee, "Inside credential", 45, 60
        )
        self.short_window_credential = self.credential(
            self.employee, "Not due for its selected threshold", 10, 5
        )
        self.default_window_credential = self.credential(
            self.employee, "Inside default window", 20, 30
        )
        self.outside_credential = self.credential(
            self.outsider, "Outside credential sentinel", 1, 30
        )
        self.personal_credential = self.credential(
            self.director, "Director outside personal certificate", 1, 30
        )
        self.inside_request = ParticipationRequest.objects.create(
            project=self.inside_project,
            requested_by=self.pm,
            user=self.direct_employee,
            target_org=self.unit,
            summary="Inside request",
        )
        self.outside_request = ParticipationRequest.objects.create(
            project=self.outside_project,
            requested_by=self.director,
            user=self.outsider,
            target_org=self.other_unit,
            summary="Outside request sentinel",
        )
        self.client_record = ApiClient.objects.create(
            name="OS-scoped director API",
            user=self.director,
            org_node=self.unit,
            scopes=["atlas:read"],
        )
        self.bearer = APIClient()
        self.bearer.credentials(
            HTTP_AUTHORIZATION="Bearer " + issue_token(self.client_record)
        )

    def project(self, title, org):
        project = Project.objects.create(
            title=title,
            owner_org=org,
            appointment=self.appointment,
            created_by=self.employee,
            status="PLANNED",
            published_revision=1,
        )
        ProjectRevision.objects.create(
            project=project,
            number=1,
            author=self.employee,
            decision="APPROVE",
            content={"title": title, "expected_outcome": "Approved summary"},
        )
        return project

    @staticmethod
    def card(title, org, author):
        return CommunityCard.objects.create(
            title=title,
            body="A published share",
            owner_org=org,
            created_by=author,
            all_cs=True,
            status="PUBLISHED",
        )

    def announcement(self, title, org):
        return Announcement.objects.create(
            title=title,
            body="A published announcement",
            owner_org=org,
            created_by=self.director,
            all_cs=True,
            status="PUBLISHED",
        )

    @staticmethod
    def credential(user, name, days, alert_days):
        return Credential.objects.create(
            user=user,
            name=name,
            issuer="Synthetic issuer",
            important=True,
            expires_on=timezone.localdate() + timedelta(days=days),
            alert_days=alert_days,
        )

    def ids(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        return {str(row["id"]) for row in self.rows(response)}

    def test_dashboard_reuses_scoped_credentials_and_each_selected_alert_window(self):
        response = self.bearer.get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["kpis"]["credentials"], 2)
        self.assertEqual(data["kpis"]["decisions"], 1)
        self.assertEqual(data["kpis"]["critical"], 1)
        self.assertEqual(
            {row["id"] for row in data["community"]}, {str(self.inside_card.pk)}
        )
        self.assertEqual(
            {row["id"] for row in data["announcements"]},
            {str(self.inside_announcement.pk)},
        )
        self.assertNotIn("Outside", str(data))
        self.assertEqual(
            {row["id"] for row in data["unit_summaries"]}, {str(self.unit.pk)}
        )
        # No bearer narrowing is imposed on the internal director's normal session.
        internal = self.as_user(self.director).get("/api/v1/dashboard/").json()
        self.assertEqual(internal["kpis"]["credentials"], 4)
        self.assertEqual(internal["kpis"]["decisions"], 2)

    def test_secondary_collections_and_detail_urls_share_the_same_client_boundary(self):
        for route, inside, outside in [
            ("community", self.inside_card, self.outside_card),
            ("announcements", self.inside_announcement, self.outside_announcement),
            ("credentials", self.inside_credential, self.outside_credential),
            ("participation-requests", self.inside_request, self.outside_request),
        ]:
            with self.subTest(route=route):
                ids = self.ids(self.bearer.get(f"/api/v1/{route}/"))
                self.assertIn(str(inside.pk), ids)
                self.assertNotIn(str(outside.pk), ids)
                self.assertEqual(
                    self.bearer.get(f"/api/v1/{route}/{outside.pk}/").status_code, 404
                )
        self.assertNotIn(
            str(self.personal_credential.pk),
            self.ids(self.bearer.get("/api/v1/credentials/")),
        )

    def test_notification_secondary_and_unknown_sources_fail_closed_for_scoped_client(
        self,
    ):
        visible = []
        hidden = []
        for kind, inside, outside in [
            ("community", self.inside_card, self.outside_card),
            ("credential", self.inside_credential, self.outside_credential),
            ("participation", self.inside_request, self.outside_request),
            ("announcement", self.inside_announcement, self.outside_announcement),
            ("work", self.inside_work, self.outside_work),
        ]:
            for obj, result in [(inside, visible), (outside, hidden)]:
                result.append(
                    Notification.objects.create(
                        recipient=self.director,
                        title=f"{kind} notice",
                        resource_type=kind,
                        resource_id=str(obj.pk),
                        dedup_key=f"{kind}:{obj.pk}",
                    )
                )
        unknown = Notification.objects.create(
            recipient=self.director,
            title="No trusted org relation",
            resource_type="unknown",
            resource_id="opaque",
            dedup_key="unknown:opaque",
        )
        ids = self.ids(self.bearer.get("/api/v1/notifications/"))
        self.assertEqual(ids, {str(obj.pk) for obj in visible})
        for obj in [*hidden, unknown]:
            self.assertEqual(
                self.bearer.get(f"/api/v1/notifications/{obj.pk}/").status_code, 404
            )
        internal_ids = self.ids(
            self.as_user(self.director).get("/api/v1/notifications/")
        )
        self.assertIn(str(unknown.pk), internal_ids)
        self.assertIn(str(hidden[0].pk), internal_ids)

    def test_activity_does_not_infer_resource_scope_from_its_actors_current_org(self):
        inside_events = []
        outside_events = []
        for kind, inside, outside in [
            ("WorkItem", self.inside_work, self.outside_work),
            ("CommunityCard", self.inside_card, self.outside_card),
            ("Credential", self.inside_credential, self.outside_credential),
            ("ParticipationRequest", self.inside_request, self.outside_request),
        ]:
            for obj, result in [(inside, inside_events), (outside, outside_events)]:
                result.append(
                    AuditEvent.objects.create(
                        actor=self.director,
                        action="scope.test",
                        object_type=kind,
                        object_id=str(obj.pk),
                        data={"sentinel": str(obj.pk)},
                    )
                )
        AuditEvent.objects.create(
            actor=self.director,
            action="auth.login",
            object_type="Unscoped",
            object_id="opaque",
        )
        ids = self.ids(self.bearer.get("/api/v1/activity/"))
        self.assertEqual(ids, {str(event.pk) for event in inside_events})
        dashboard = self.bearer.get("/api/v1/dashboard/").json()
        recent = {row["id"] for row in dashboard["recent_activity"]}
        self.assertFalse(recent & {str(event.pk) for event in outside_events})

    def test_cross_scope_parent_and_progress_backrefs_are_not_exposed(self):
        child = WorkItem.objects.create(
            title="Inside child",
            owner_org=self.team,
            assigned_to=self.employee,
            created_by=self.director,
            parent=self.outside_work,
        )
        ProjectMembership.objects.create(
            project=self.outside_project, user=self.employee
        )
        outside_entry = ProgressEntry.objects.create(
            project=self.outside_project,
            author=self.employee,
            author_org=self.team,
            done="Outside project contribution sentinel",
        )
        response = self.bearer.get(f"/api/v1/work/{child.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["parent_id"])
        rows = self.ids(
            self.bearer.get(f"/api/v1/people/{self.employee.pk}/contributions/")
        )
        self.assertNotIn(str(outside_entry.pk), rows)
        self.assertEqual(
            self.bearer.get(f"/api/v1/contributions/{outside_entry.pk}/").status_code,
            404,
        )

    def test_own_case_notice_history_does_not_override_the_bearer_org_scope(self):
        inside = CaseNotice.objects.create(
            title="Inside notice",
            description="Reported inside",
            created_by=self.director,
            owner_org=self.unit,
        )
        outside = CaseNotice.objects.create(
            title="Outside notice sentinel",
            description="Reported outside",
            created_by=self.director,
            owner_org=self.other_unit,
        )
        self.assertEqual(
            self.ids(self.bearer.get("/api/v1/case-notices/")), {str(inside.pk)}
        )
        self.assertEqual(
            self.bearer.get(f"/api/v1/case-notices/{outside.pk}/").status_code, 404
        )
        self.assertIn(
            str(outside.pk),
            self.ids(self.as_user(self.director).get("/api/v1/case-notices/")),
        )

    def test_directory_search_pm_and_report_selections_do_not_return_outside_ids(self):
        self.outsider.display_name = "UniqueOutsidePersonSentinel"
        self.outsider.save(update_fields=["display_name"])
        outside_appointment = PMAppointment.objects.create(
            user=self.outsider, governing_org=self.other_unit
        )
        inside_appointment = PMAppointment.objects.create(
            user=self.direct_employee, governing_org=self.unit
        )
        for work in [self.inside_work, self.outside_work]:
            ReportSelection.objects.create(
                user=self.director,
                source_type="work",
                source_id=work.pk,
                week_start=timezone.localdate(),
            )
        search = self.bearer.get(
            "/api/v1/search/", {"q": "UniqueOutsidePersonSentinel"}
        )
        self.assertEqual(self.ids(search), set())
        pm_ids = self.ids(self.bearer.get("/api/v1/project-managers/"))
        self.assertEqual(pm_ids, {str(inside_appointment.pk)})
        self.assertNotIn(str(outside_appointment.pk), pm_ids)
        selections = self.rows(self.bearer.get("/api/v1/report-selections/"))
        self.assertEqual(
            {row["source_id"] for row in selections}, {str(self.inside_work.pk)}
        )
        empty = Report.objects.create(
            title="Unscoped empty report",
            created_by=self.director,
            period_start=timezone.localdate(),
            period_end=timezone.localdate(),
        )
        self.assertEqual(
            self.bearer.get(f"/api/v1/reports/{empty.pk}/").status_code, 404
        )


class SingleSourceLookupTests(AtlasTestCase):
    def test_lookup_checks_only_one_requested_record_even_with_large_unrelated_collection(
        self,
    ):
        wanted = WorkItem.objects.create(
            title="Requested source",
            owner_org=self.team,
            assigned_to=self.employee,
            created_by=self.unit_head,
        )
        WorkItem.objects.bulk_create(
            [
                WorkItem(
                    title=f"Unrelated work {number}",
                    owner_org=self.other_unit,
                    assigned_to=self.outsider,
                    created_by=self.other_head,
                )
                for number in range(100)
            ]
        )
        with patch("core.policy.can_read_work", wraps=can_read_work) as check:
            with self.assertNumQueries(1):
                self.assertEqual(
                    report_source(self.employee, "work", wanted.pk).pk, wanted.pk
                )
            self.assertEqual(check.call_count, 1)
        self.assertIsNone(
            report_source(
                self.employee,
                "work",
                WorkItem.objects.filter(owner_org=self.other_unit).first().pk,
            )
        )
