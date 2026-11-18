"""Management reporting retains team signals without widening source access."""

from datetime import timedelta
from django.utils import timezone
from core.models import Project, ProjectRevision, Report, ReportSelection, WorkItem
from core.services import snapshot_source
from core.tests.base import AtlasTestCase


class ReportRollupTests(AtlasTestCase):
    def ordinary_work(self):
        return WorkItem.objects.create(
            title="Noncritical milestone completed",
            priority="NORMAL",
            status="COMPLETED",
            created_by=self.unit_head,
            assigned_to=self.employee,
            owner_org=self.team,
        )

    def test_team_selection_reaches_director_but_not_sibling_manager(self):
        work = self.ordinary_work()
        start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        ReportSelection.objects.create(
            user=self.unit_head, source_type="work", source_id=work.pk, week_start=start
        )
        payload = {
            "period_start": start.isoformat(),
            "period_end": (start + timedelta(days=6)).isoformat(),
        }
        response = self.as_user(self.director).post(
            "/api/v1/reports/", payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(
            any(
                source["id"] == str(work.pk)
                and source["selection_reason"] == "TEAM_SELECTED"
                for source in response.json()["sources"]
            )
        )
        sibling = self.as_user(self.other_head).post(
            "/api/v1/reports/", payload, format="json"
        )
        self.assertEqual(sibling.status_code, 201, sibling.content)
        self.assertFalse(
            any(source["id"] == str(work.pk) for source in sibling.json()["sources"])
        )

    def test_approved_unit_report_is_read_only_for_scoped_superior(self):
        work = self.ordinary_work()
        today = timezone.localdate()
        report = Report.objects.create(
            title="Unit report",
            created_by=self.unit_head,
            period_start=today,
            period_end=today,
            sources=[snapshot_source(work, "work", self.unit_head)],
            markdown="A source-bound approved summary",
            status="APPROVED",
        )
        response = self.as_user(self.director).get(f"/api/v1/reports/{report.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["permissions"]["manage"])
        self.assertEqual(
            self.as_user(self.director)
            .post(
                f"/api/v1/reports/{report.pk}/generate/",
                {"version": report.version},
                format="json",
            )
            .status_code,
            403,
        )
        self.assertEqual(
            self.as_user(self.other_head)
            .get(f"/api/v1/reports/{report.pk}/")
            .status_code,
            404,
        )
        report.status = "READY"
        report.save(update_fields=["status"])
        self.assertEqual(
            self.as_user(self.director)
            .get(f"/api/v1/reports/{report.pk}/")
            .status_code,
            404,
        )

    def test_summary_project_access_does_not_open_a_detailed_pm_report(self):
        project = Project.objects.create(
            title="Published summary",
            description="Restricted detail",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="PLANNED",
            published_revision=1,
        )
        ProjectRevision.objects.create(
            project=project,
            number=1,
            author=self.employee,
            content={"title": project.title, "expected_outcome": "Approved outcome"},
            decision="APPROVE",
        )
        today = timezone.localdate()
        report = Report.objects.create(
            title="Detailed PM report",
            created_by=self.pm,
            period_start=today,
            period_end=today,
            sources=[snapshot_source(project, "project", self.pm)],
            markdown="Restricted project detail",
            status="APPROVED",
        )
        self.assertEqual(
            self.as_user(self.director)
            .get(f"/api/v1/reports/{report.pk}/")
            .status_code,
            404,
        )
        self.assertEqual(
            self.as_user(self.pm_head).get(f"/api/v1/reports/{report.pk}/").status_code,
            200,
        )
