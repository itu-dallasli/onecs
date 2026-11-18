"""Report pivots preserve source policy and frozen report content."""

from copy import deepcopy
from datetime import date, datetime
from uuid import uuid4

from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    ApiClient,
    AuditEvent,
    BackgroundJob,
    OrgNode,
    Project,
    ProjectRevision,
    Report,
    RoleGrant,
    WorkItem,
)
from core.services import report_hash, snapshot_source
from core.tests.base import OnecsTestCase
from core.views import issue_token


class ReportPivotTests(OnecsTestCase):
    period_start = date(2028, 6, 1)
    period_end = date(2028, 6, 7)

    def work(self, title="Synthetic report source", **overrides):
        fields = {
            "title": title,
            "owner_org": self.team,
            "assigned_to": self.employee,
            "created_by": self.unit_head,
        }
        fields.update(overrides)
        return WorkItem.objects.create(**fields)

    def report(self, sources=None, **overrides):
        fields = {
            "title": "Synthetic team report",
            "created_by": self.unit_head,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "status": "APPROVED",
            "sources": sources if sources is not None else [],
            "markdown": "Frozen synthetic report text",
        }
        fields.update(overrides)
        report = Report.objects.create(**fields)
        report.content_hash = report_hash(report)
        report.save(update_fields=["content_hash"])
        return report

    @staticmethod
    def pivot_url(report):
        return f"/api/v1/reports/{report.pk}/pivot/"

    def pivot(self, report, user=None, client=None):
        client = client or self.as_user(user or self.unit_head)
        response = client.get(self.pivot_url(report))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def assert_hidden(self, report, user=None, client=None):
        client = client or self.as_user(user or self.unit_head)
        listing = client.get("/api/v1/reports/")
        self.assertEqual(listing.status_code, 200, listing.content)
        self.assertNotIn(str(report.pk), {row["id"] for row in self.rows(listing)})
        for suffix in ("", "pivot/"):
            response = client.get(f"/api/v1/reports/{report.pk}/{suffix}")
            self.assertEqual(response.status_code, 404, response.content)

    def test_owner_and_approved_superior_share_source_bound_read_only_pivot(self):
        work = self.work()
        report = self.report([snapshot_source(work, "work", self.unit_head)])
        owner = self.pivot(report)
        superior = self.pivot(report, self.director)
        self.assertEqual(owner, superior)
        self.assertEqual(owner["report_id"], str(report.pk))
        self.assertEqual(owner["report_version"], report.version)
        self.assertEqual(owner["content_hash"], report.content_hash)
        self.assertEqual(owner["general"]["source_count"], 1)
        self.assertEqual(owner["teams"][0]["id"], str(self.team.pk))
        self.assert_hidden(report, self.other_head)
        self.assert_hidden(report, self.colleague)
        report.status = "READY"
        report.save(update_fields=["status"])
        self.assert_hidden(report, self.director)
        self.assertEqual(self.pivot(report)["source_count"], 1)

    def test_summary_project_access_does_not_open_detailed_report_or_pivot(self):
        project = Project.objects.create(
            title="Synthetic approved project",
            description="Restricted synthetic project detail",
            owner_org=self.unit,
            created_by=self.employee,
            appointment=self.appointment,
            status="PLANNED",
            published_revision=1,
        )
        ProjectRevision.objects.create(
            project=project,
            number=1,
            author=self.employee,
            decision="APPROVE",
            content={"title": project.title, "expected_outcome": "Public outcome"},
        )
        source = snapshot_source(project, "project", self.pm)
        self.assertEqual(source["visibility"], "DETAIL")
        report = self.report([source], created_by=self.pm)
        self.assert_hidden(report, self.director)
        self.assert_hidden(report, self.employee)
        self.assertEqual(self.pivot(report, self.pm_head)["source_count"], 1)

    def test_scoped_read_token_cannot_cross_source_org_boundary(self):
        inside = self.work()
        outside = self.work(
            "Outside scoped synthetic source",
            owner_org=self.other_unit,
            assigned_to=self.outsider,
        )
        visible = self.report(
            [snapshot_source(inside, "work", self.director)], created_by=self.director
        )
        hidden = self.report(
            [snapshot_source(outside, "work", self.director)], created_by=self.director
        )
        client_record = ApiClient.objects.create(
            name="Synthetic pivot read client",
            user=self.director,
            org_node=self.unit,
            scopes=["onecs:read"],
        )
        bearer = APIClient()
        bearer.credentials(HTTP_AUTHORIZATION="Bearer " + issue_token(client_record))
        self.assertEqual(self.pivot(visible, client=bearer)["source_count"], 1)
        self.assert_hidden(hidden, client=bearer)

    def test_revoked_manager_grant_removes_owner_report_from_all_surfaces(self):
        work = self.work()
        report = self.report([snapshot_source(work, "work", self.unit_head)])
        self.pivot(report)
        RoleGrant.objects.filter(user=self.unit_head, role="UNIT_HEAD").update(
            active=False
        )
        self.assert_hidden(report)

    def test_source_transfer_to_unrelated_unit_revokes_stale_report(self):
        work = self.work()
        report = self.report([snapshot_source(work, "work", self.unit_head)])
        self.pivot(report)
        work.owner_org = self.other_unit
        work.assigned_to = self.outsider
        work.save(update_fields=["owner_org", "assigned_to"])
        self.assert_hidden(report)

    def test_deleted_or_malformed_sources_fail_closed_without_server_error(self):
        for source in (
            {"type": "work", "id": str(uuid4())},
            {"type": "work", "id": "not-a-uuid"},
            {"type": "not-a-source", "id": str(uuid4())},
            {"type": "work"},
            {"id": str(uuid4())},
            "invalid snapshot",
            None,
        ):
            with self.subTest(source=source):
                report = self.report([source])
                self.assert_hidden(report)

    def test_malformed_optional_snapshot_fields_fail_closed_but_missing_legacy_fields_are_valid(
        self,
    ):
        work = self.work()
        original = snapshot_source(work, "work", self.unit_head)
        for field, value in (
            ("status", []),
            ("status", {}),
            ("priority", []),
            ("priority", {}),
            ("title", {"unexpected": "object"}),
            ("description", {"unexpected": "object"}),
            ("version", False),
            ("version", 0),
            ("version", "1"),
        ):
            with self.subTest(field=field, value=value):
                malformed = deepcopy(original)
                malformed[field] = value
                self.assert_hidden(self.report([malformed]))
        legacy = {"type": "work", "id": str(work.pk)}
        self.assertEqual(self.pivot(self.report([legacy]))["source_count"], 1)

    def test_legacy_pivot_get_preserves_sources_markdown_hash_version_and_rows(self):
        work = self.work()
        source = snapshot_source(work, "work", self.unit_head)
        source.pop("owner_org", None)
        report = self.report([source])
        before = deepcopy(Report.objects.values().get(pk=report.pk))
        audit_count = AuditEvent.objects.count()
        jobs = BackgroundJob.objects.count()
        first = self.pivot(report)
        second = self.pivot(report)
        self.assertEqual(first, second)
        self.assertEqual(first["metadata_provenance"], "current_authorized")
        self.assertEqual(first["teams"][0]["metadata_provenance"], "current_authorized")
        self.assertEqual(first["teams"][0]["id"], str(self.team.pk))
        self.assertEqual(before, Report.objects.values().get(pk=report.pk))
        self.assertEqual(AuditEvent.objects.count(), audit_count)
        self.assertEqual(BackgroundJob.objects.count(), jobs)

    def test_new_snapshots_freeze_team_metadata_across_rename_and_allowed_transfer(
        self,
    ):
        work = self.work()
        snapshot = snapshot_source(work, "work", self.unit_head)
        self.assertEqual(
            snapshot["owner_org"],
            {"id": str(self.team.pk), "name": self.team.name, "code": self.team.code},
        )
        report = self.report([snapshot])
        before = self.pivot(report)
        other_team = OrgNode.objects.create(
            code="SYNTHETIC-SECOND-TEAM",
            name="Other synthetic team",
            kind="TEAM",
            parent=self.unit,
        )
        self.team.name = "Renamed synthetic team"
        self.team.code = "RENAMED-SYNTHETIC-TEAM"
        self.team.save(update_fields=["name", "code"])
        work.owner_org = other_team
        work.save(update_fields=["owner_org"])
        after = self.pivot(report)
        self.assertEqual(before, after)
        self.assertEqual(after["metadata_provenance"], "snapshot")
        self.assertEqual(after["teams"][0]["metadata_provenance"], "snapshot")
        report.refresh_from_db()
        self.assertEqual(report.sources, [snapshot])

    def test_duplicate_snapshots_count_once_globally_and_keep_first_primary_team(self):
        work = self.work()
        first = snapshot_source(work, "work", self.unit_head)
        duplicate = deepcopy(first)
        duplicate["title"] = "Duplicate must not appear"
        duplicate["owner_org"] = {
            "id": str(self.other_unit.pk),
            "name": "Duplicate team",
            "code": "DUP",
        }
        report = self.report([first, duplicate, deepcopy(first)])
        data = self.pivot(report)
        self.assertEqual(data["source_count"], 1)
        self.assertEqual(data["general"]["source_count"], 1)
        self.assertEqual(sum(team["source_count"] for team in data["teams"]), 1)
        self.assertEqual(len(data["teams"]), 1)
        self.assertEqual(data["teams"][0]["id"], str(self.team.pk))
        self.assertNotIn("Duplicate must not appear", str(data))

    def test_period_end_classification_is_stable_in_future_and_exclusive_per_section(
        self,
    ):
        due_in_period = timezone.make_aware(datetime(2028, 6, 7, 23, 59, 59))
        due_after_period = timezone.make_aware(datetime(2028, 6, 8))
        records = [
            self.work(
                "A completed",
                status="COMPLETED",
                priority="CRITICAL",
                due_at=due_in_period,
            ),
            self.work("B critical overdue", priority="CRITICAL", due_at=due_in_period),
            self.work("C waiting", status="WAITING", due_at=due_after_period),
            self.work("D ordinary future", due_at=due_after_period),
            self.work("E decision", status="SUBMITTED"),
            self.work("F rejected", status="REJECTED", due_at=due_in_period),
        ]
        report = self.report(
            [snapshot_source(work, "work", self.unit_head) for work in records]
        )
        data = self.pivot(report)
        self.assertEqual(data["as_of"], self.period_end.isoformat())
        self.assertEqual(
            data["general"]["counts"],
            {"open": 4, "completed": 1, "critical": 1, "overdue": 1},
        )
        self.assertEqual(
            data["section_order"],
            ["highlights", "lowlights", "escalations", "information", "next_steps"],
        )
        sections = {section["key"]: section for section in data["general"]["sections"]}
        self.assertEqual(sections["highlights"]["count"], 1)
        self.assertEqual(sections["lowlights"]["count"], 2)
        self.assertEqual(sections["escalations"]["count"], 2)
        self.assertEqual(sections["information"]["count"], 1)
        self.assertEqual(sections["next_steps"]["sources"], [])
        rows = [
            source for section in sections.values() for source in section["sources"]
        ]
        self.assertEqual(len(rows), len(records))
        self.assertEqual(
            {row["id"] for row in rows}, {str(work.pk) for work in records}
        )

    def test_frozen_source_status_and_due_date_are_used_instead_of_mutated_live_values(
        self,
    ):
        work = self.work(
            priority="CRITICAL", due_at=timezone.make_aware(datetime(2028, 6, 2))
        )
        report = self.report([snapshot_source(work, "work", self.unit_head)])
        initial = self.pivot(report)
        work.status = "COMPLETED"
        work.priority = "LOW"
        work.due_at = None
        work.version += 1
        work.save(update_fields=["status", "priority", "due_at", "version"])
        self.assertEqual(self.pivot(report), initial)

    def test_empty_report_has_general_summary_and_no_invented_team_or_next_steps(self):
        report = self.report([])
        data = self.pivot(report)
        self.assertEqual(data["metadata_provenance"], "empty")
        self.assertEqual(data["source_count"], 0)
        self.assertEqual(data["teams"], [])
        self.assertEqual(
            data["general"]["counts"],
            {"open": 0, "completed": 0, "critical": 0, "overdue": 0},
        )
        for section in data["general"]["sections"]:
            self.assertEqual(section["count"], 0)
            self.assertEqual(section["sources"], [])

    def test_team_and_source_order_is_deterministic(self):
        second_team = OrgNode.objects.create(
            code="SYNTHETIC-Z", name="Z synthetic team", kind="TEAM", parent=self.unit
        )
        z = self.work("Z source")
        a = self.work("A source")
        second = self.work("Second team source", owner_org=second_team)
        report = self.report(
            [snapshot_source(work, "work", self.unit_head) for work in (second, z, a)]
        )
        data = self.pivot(report)
        self.assertEqual(
            [team["id"] for team in data["teams"]],
            [str(self.team.pk), str(second_team.pk)],
        )
        self.assertEqual(
            [source["title"] for source in data["teams"][0]["sources"]],
            [a.title, z.title],
        )
