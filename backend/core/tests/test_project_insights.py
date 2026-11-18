"""Project evidence, reviewer overrides, poll scope and durable generation boundaries."""

import uuid
from datetime import date, timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.exceptions import APIException

from core.models import (
    BackgroundJob,
    Notification,
    OutboxEvent,
    ProgressEntry,
    Project,
    ProjectAuthorityGrant,
    ProjectClosureSurvey,
    ProjectDeliverable,
    ProjectInsightEdit,
    ProjectInsightReport,
    ProjectMembership,
    ProjectTeamPlan,
    User,
)
from core.project_insights import (
    generate_project_insight,
    project_metrics,
    report_sources,
)
from core.tests.base import OnecsTestCase
from core.worker import claim_job, process_job


class ProjectInsightTests(OnecsTestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            title="Evidence-based API programme",
            created_by=self.employee,
            owner_org=self.unit,
            appointment=self.appointment,
            status="IN_PROGRESS",
            published_revision=1,
        )
        ProjectMembership.objects.create(project=self.project, user=self.employee)
        ProjectMembership.objects.create(project=self.project, user=self.colleague)
        self.base = f"/api/v1/projects/{self.project.pk}"
        self.day = date.today().isoformat()

    def call(self, actor, endpoint, data, method="post", **headers):
        return getattr(self.as_user(actor), method)(
            self.base + endpoint, data, format="json", **headers
        )

    def delivery(self, **changes):
        data = {
            "title": "Validated control",
            "org_id": str(self.team.pk),
            "weight": 1,
            "progress": 50,
            "evidence": "Signed evidence reference",
        }
        data.update(changes)
        response = self.call(self.pm, "/deliverables/", data)
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def survey(self, **changes):
        data = {
            "title": "Closure feedback",
            "questions": ["Evidence quality?", "Handover usefulness?"],
            "invitee_ids": [
                str(self.employee.pk),
                str(self.colleague.pk),
                str(self.employee.pk),
            ],
        }
        data.update(changes)
        response = self.call(self.pm, "/surveys/", data)
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def report(self, **changes):
        data = {
            "kind": "DAILY",
            "period_start": self.day,
            "period_end": self.day,
            "generation_mode": "RULE_BASED",
        }
        data.update(changes)
        response = self.call(self.pm, "/insight-reports/", data)
        self.assertEqual(response.status_code, 202, response.data)
        return ProjectInsightReport.objects.get(pk=response.data["id"])

    def delegate(self, permissions):
        return ProjectAuthorityGrant.objects.create(
            project=self.project,
            user=self.colleague,
            granted_by=self.pm,
            permissions=permissions,
            expires_at=timezone.now() + timedelta(days=1),
            reason="Focused delegation",
        )

    def test_unit_role_does_not_grant_project_mutations(self):
        response = self.call(
            self.unit_head,
            "/deliverables/",
            {"title": "Unapproved", "org_id": str(self.team.pk)},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProjectDeliverable.objects.exists())
        response = self.call(self.unit_head, "/surveys/", {"title": "Unapproved"})
        self.assertEqual(response.status_code, 403)

    def test_two_stage_team_weights_prevent_task_count_bias(self):
        ProjectMembership.objects.create(project=self.project, user=self.outsider)
        self.delivery(progress=100, weight=100)
        self.delivery(progress=100, weight=1)
        self.delivery(org_id=str(self.other_unit.pk), progress=0, evidence="")
        teams, scores = project_metrics(self.project)
        self.assertEqual(len(teams), 2)
        self.assertEqual(scores["delivery"], 50)
        self.assertIsNone(scores["quality"])
        self.assertIsNone(scores["overall"])
        plan = self.project.team_plans.get(org=self.team)
        response = self.call(
            self.pm,
            f"/team-plans/{plan.pk}/",
            {"version": plan.version, "weight": 3},
            method="patch",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scores"]["delivery"], 75)
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.progress,
            0,
            "Calculated progress must not silently overwrite the approved project field",
        )

    def test_progress_requires_evidence_and_invalid_team_rolls_back(self):
        response = self.call(
            self.pm,
            "/deliverables/",
            {"title": "No evidence", "org_id": str(self.team.pk), "progress": 70},
        )
        self.assertEqual(response.status_code, 400)
        response = self.call(
            self.pm,
            "/deliverables/",
            {"title": "Wrong team", "org_id": str(self.other_unit.pk)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProjectTeamPlan.objects.count(), 0)
        self.assertEqual(ProjectDeliverable.objects.count(), 0)

    def test_tasks_delegate_cannot_set_quality_or_edit_report(self):
        self.delegate(["tasks"])
        response = self.call(
            self.colleague,
            "/deliverables/",
            {
                "title": "Delivery",
                "org_id": str(self.team.pk),
                "progress": 20,
                "evidence": "E",
            },
        )
        self.assertEqual(response.status_code, 201)
        obj = response.data
        response = self.call(
            self.colleague,
            f"/deliverables/{obj['id']}/",
            {"version": obj["version"], "quality_rating": 5, "evidence": "E"},
            method="patch",
        )
        self.assertEqual(response.status_code, 403)
        report = self.report()
        process_job()
        report.refresh_from_db()
        response = self.call(
            self.colleague,
            f"/insight-reports/{report.pk}/",
            {
                "version": report.version,
                "markdown": "Modified",
                "edit_reason": "Review",
            },
            method="patch",
        )
        self.assertEqual(response.status_code, 403)

    def test_close_delegate_can_rate_but_cannot_change_progress(self):
        obj = self.delivery()
        self.delegate(["close"])
        response = self.call(
            self.colleague,
            f"/deliverables/{obj['id']}/",
            {
                "version": obj["version"],
                "quality_rating": 4,
                "evidence": "Acceptance evidence",
            },
            method="patch",
        )
        self.assertEqual(response.status_code, 200, response.data)
        response = self.call(
            self.colleague,
            f"/deliverables/{obj['id']}/",
            {"version": response.data["version"], "progress": 100, "evidence": "E"},
            method="patch",
        )
        self.assertEqual(response.status_code, 403)

    def test_stale_delivery_version_preserves_original(self):
        obj = self.delivery()
        response = self.call(
            self.pm,
            f"/deliverables/{obj['id']}/",
            {"version": 999, "progress": 100, "evidence": "Changed"},
            method="patch",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(ProjectDeliverable.objects.get(pk=obj["id"]).progress, 50)

    def test_survey_invitation_deduplicates_and_keeps_recipient_scope(self):
        survey = self.survey()
        self.assertEqual(survey["invited"], 2)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(OutboxEvent.objects.count(), 2)
        answers = {q["id"]: 4 for q in survey["questions"]}
        response = self.call(
            self.outsider,
            f"/surveys/{survey['id']}/respond/",
            {"version": survey["version"], "answers": answers},
        )
        self.assertIn(response.status_code, (403, 404))
        response = self.call(
            self.pm,
            "/surveys/",
            {
                "title": "Wrong invitee",
                "questions": ["Q?"],
                "invitee_ids": [str(self.outsider.pk)],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProjectClosureSurvey.objects.count(), 1)

    def test_survey_answers_are_idempotent_and_revisions_are_optimistic(self):
        survey = self.survey()
        path = f"/surveys/{survey['id']}/respond/"
        answers = {q["id"]: 4 for q in survey["questions"]}
        payload = {"version": survey["version"], "answers": answers}
        response = self.call(self.employee, path, payload)
        self.assertEqual(response.status_code, 200)
        version = response.data["my_response_version"]
        response = self.call(self.employee, path, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["responded"], 1)
        changed = {q["id"]: 5 for q in survey["questions"]}
        response = self.call(
            self.employee,
            path,
            {"version": survey["version"], "response_version": 999, "answers": changed},
        )
        self.assertEqual(response.status_code, 409)
        response = self.call(
            self.employee,
            path,
            {
                "version": survey["version"],
                "response_version": version,
                "answers": changed,
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["my_response_version"], version + 1)
        self.assertEqual(response.data["response_rate"], 50)
        self.assertNotIn("responses", response.data)
        self.assertEqual(
            ProjectClosureSurvey.objects.get(pk=survey["id"]).responses.count(), 1
        )

    def test_expired_survey_and_non_integer_answers_are_rejected(self):
        survey = self.survey()
        path = f"/surveys/{survey['id']}/respond/"
        response = self.call(
            self.employee,
            path,
            {
                "version": survey["version"],
                "answers": {q["id"]: True for q in survey["questions"]},
            },
        )
        self.assertEqual(response.status_code, 400)
        ProjectClosureSurvey.objects.filter(pk=survey["id"]).update(
            closes_at=timezone.now() - timedelta(seconds=1)
        )
        response = self.call(
            self.employee,
            path,
            {
                "version": survey["version"],
                "answers": {q["id"]: 5 for q in survey["questions"]},
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_report_creation_is_idempotent_and_offline_never_calls_provider(self):
        data = {
            "kind": "WEEKLY",
            "period_start": self.day,
            "period_end": self.day,
            "generation_mode": "RULE_BASED",
        }
        key = str(uuid.uuid4())
        first = self.call(self.pm, "/insight-reports/", data, HTTP_X_REQUEST_ID=key)
        second = self.call(self.pm, "/insight-reports/", data, HTTP_X_REQUEST_ID=key)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(BackgroundJob.objects.count(), 1)
        job = BackgroundJob.objects.get()
        self.assertIsNone(job.payload["ai_profile_id"])
        self.assertEqual(job.payload["ai_settings_version"], 0)
        with patch("administration.services.generate_ai_report") as adapter:
            self.assertTrue(process_job())
            adapter.assert_not_called()
        report = ProjectInsightReport.objects.get()
        self.assertEqual(report.status, "READY")
        self.assertEqual(report.generated_mode, "RULE_BASED")
        self.assertIn("RULE_BASED", report.markdown)
        self.assertEqual(report.original_markdown, report.markdown)

    def test_numeric_review_is_separate_from_original_and_requires_reason(self):
        self.delivery(quality_rating=4)
        report = self.report()
        process_job()
        report.refresh_from_db()
        original = report.original_markdown
        computed = report.computed_values
        url = f"/insight-reports/{report.pk}/"
        response = self.call(
            self.pm,
            url,
            {"version": report.version, "reviewed_scores": {"overall": 85}},
            method="patch",
        )
        self.assertEqual(response.status_code, 400)
        response = self.call(
            self.pm,
            url,
            {
                "version": report.version,
                "markdown": "Reviewed draft",
                "reviewed_scores": {"overall": 85},
                "edit_reason": "Documented exception accepted",
            },
            method="patch",
        )
        self.assertEqual(response.status_code, 200, response.data)
        report.refresh_from_db()
        self.assertEqual(report.original_markdown, original)
        self.assertEqual(report.computed_values, computed)
        self.assertEqual(report.reviewed_scores["overall"], 85)
        self.assertIsNone(report.computed_values["overall"])
        self.assertEqual(ProjectInsightEdit.objects.count(), 1)
        response = self.call(
            self.pm,
            url,
            {"version": 1, "markdown": "Stale overwrite", "edit_reason": "Late edit"},
            method="patch",
        )
        self.assertEqual(response.status_code, 409)

    def test_stale_snapshot_blocks_generation_before_external_call(self):
        obj = self.delivery()
        report = self.report()
        ProjectDeliverable.objects.filter(pk=obj["id"]).update(version=2, progress=75)
        with patch("administration.services.generate_ai_report") as adapter:
            process_job()
            adapter.assert_not_called()
        report.refresh_from_db()
        self.assertEqual(report.status, "FAILED")
        self.assertEqual(report.original_markdown, "")

    def test_profile_and_versions_are_pinned_into_job(self):
        snapshot = {
            "profile_id": str(uuid.uuid4()),
            "configuration_version": 4,
            "settings_version": 8,
        }
        with patch(
            "administration.profiles.selected_ai_snapshot", return_value=snapshot
        ):
            report = self.report(generation_mode="AI")
        job = claim_job()
        with patch(
            "administration.services.generate_ai_report",
            return_value={"mode": "AI", "markdown": "Source-based advice"},
        ) as adapter:
            generate_project_insight(job)
        self.assertEqual(adapter.call_args.kwargs["profile_id"], snapshot["profile_id"])
        self.assertEqual(adapter.call_args.kwargs["configuration_version"], 4)
        self.assertEqual(adapter.call_args.kwargs["settings_version"], 8)
        report.refresh_from_db()
        self.assertEqual(report.generated_mode, "AI")

    def test_late_ai_answer_after_actor_revocation_is_not_published(self):
        report = self.report(generation_mode="AI")
        job = claim_job()

        def revoke(*args, **kwargs):
            User.objects.filter(pk=self.pm.pk).update(is_active=False)
            return {"mode": "AI", "markdown": "Late answer"}

        with patch("administration.services.generate_ai_report", side_effect=revoke):
            with self.assertRaises(APIException):
                generate_project_insight(job)
        report.refresh_from_db()
        self.assertEqual(report.markdown, "")
        self.assertEqual(report.status, "GENERATING")

    def test_late_ai_answer_from_old_lease_is_rejected(self):
        report = self.report(generation_mode="AI")
        job = claim_job()

        def replace(*args, **kwargs):
            BackgroundJob.objects.filter(pk=job.pk).update(lease_token=uuid.uuid4())
            return {"mode": "AI", "markdown": "Orphan answer"}

        with patch("administration.services.generate_ai_report", side_effect=replace):
            with self.assertRaises(APIException):
                generate_project_insight(job)
        report.refresh_from_db()
        self.assertEqual(report.original_markdown, "")

    def test_closure_publication_requires_completed_project(self):
        report = self.report(kind="CLOSURE")
        process_job()
        report.refresh_from_db()
        response = self.call(
            self.pm,
            f"/insight-reports/{report.pk}/publish/",
            {"version": report.version},
        )
        self.assertEqual(response.status_code, 400)
        self.project.status = "COMPLETED"
        self.project.version += 1
        self.project.save()
        report = self.report(kind="CLOSURE")
        process_job()
        report.refresh_from_db()
        response = self.call(
            self.pm,
            f"/insight-reports/{report.pk}/publish/",
            {"version": report.version},
        )
        self.assertEqual(response.status_code, 200, response.data)
        response = self.call(
            self.pm,
            f"/insight-reports/{report.pk}/",
            {
                "version": response.data["version"],
                "markdown": "Silent rewrite",
                "edit_reason": "Edit",
            },
            method="patch",
        )
        self.assertEqual(response.status_code, 400)

    def test_summary_reader_cannot_read_evidence_or_report_sources(self):
        self.delivery()
        report = self.report()
        process_job()
        response = self.as_user(self.unit_head).get(self.base + "/insights/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["reports"], [])
        self.assertTrue(
            all(not team["deliverables"] for team in response.data["teams"])
        )
        response = self.as_user(self.unit_head).get(
            self.base + f"/insight-reports/{report.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_period_contribution_filter_and_score_coverage_are_explicit(self):
        ProgressEntry.objects.create(
            project=self.project,
            author=self.employee,
            author_org=self.team,
            done="Today evidence",
        )
        entry = ProgressEntry.objects.create(
            project=self.project,
            author=self.employee,
            author_org=self.team,
            done="Old evidence",
        )
        ProgressEntry.objects.filter(pk=entry.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        sources, scores, _ = report_sources(self.project, date.today(), date.today())
        self.assertEqual(len([s for s in sources if s["type"] == "contribution"]), 1)
        self.assertIsNone(scores["delivery"])
        self.assertIsNone(scores["stakeholder"])
        self.assertIsNone(scores["overall"])
        self.assertEqual(scores["coverage"]["survey_responded"], 0)

    def test_missing_participating_team_is_not_silently_omitted(self):
        ProjectMembership.objects.create(project=self.project, user=self.outsider)
        self.delivery(progress=100, quality_rating=5)
        _, scores = project_metrics(self.project)
        self.assertIsNone(scores["delivery"])
        self.assertIsNone(scores["quality"])
        self.assertEqual(scores["coverage"]["unplanned_teams"], 1)
        self.assertEqual(
            scores["coverage"]["unplanned_org_ids"], [str(self.other_unit.pk)]
        )

    def test_team_member_rolls_up_to_existing_parent_unit_plan(self):
        self.delivery(org_id=str(self.unit.pk), progress=100, quality_rating=5)
        _, scores = project_metrics(self.project)
        self.assertEqual(scores["delivery"], 100)
        self.assertEqual(scores["coverage"]["unplanned_teams"], 0)
        snapshot = self.project.progress_snapshots.first()
        self.assertNotIn("deliverables", snapshot.teams[0])
        self.assertNotIn("evidence", str(snapshot.teams))

    def test_summary_reader_has_no_unpublished_team_scores_or_trend(self):
        self.delivery(quality_rating=4)
        response = self.as_user(self.unit_head).get(self.base + "/insights/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["teams"], [])
        self.assertEqual(response.data["trend"], [])
        self.assertIsNone(response.data["scores"]["quality"])
        self.assertIsNone(response.data["scores"]["stakeholder"])
        self.assertEqual(response.data["scores"]["coverage"], {})

    def test_stale_worker_exception_does_not_fail_new_worker_report(self):
        from core.exceptions import Conflict

        report = self.report()

        def lose_lease(job):
            BackgroundJob.objects.filter(pk=job.pk).update(lease_token=uuid.uuid4())
            raise Conflict("Former worker lost its lease")

        with patch(
            "core.project_insights.generate_project_insight", side_effect=lose_lease
        ):
            process_job()
        report.refresh_from_db()
        report.job.refresh_from_db()
        self.assertEqual(report.status, "GENERATING")
        self.assertEqual(report.job.status, "RUNNING")

    def test_new_nested_routes_require_csrf_and_readonly_jwt_scope(self):
        from rest_framework.test import APIClient
        from core.models import ApiClient
        from core.views import issue_token

        strict = APIClient(enforce_csrf_checks=True)
        strict.force_login(self.pm)
        response = strict.post(
            self.base + "/surveys/", {"title": "No csrf"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        client = ApiClient.objects.create(
            name="Scoped reader",
            user=self.pm,
            org_node=self.other_unit,
            scopes=["projects:read"],
        )
        token = issue_token(client)
        external = APIClient()
        external.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(external.get(self.base + "/insights/").status_code, 404)
        client.org_node = self.unit
        client.save()
        self.assertEqual(external.get(self.base + "/insights/").status_code, 200)
        self.assertEqual(
            external.post(self.base + "/deliverables/", {}, format="json").status_code,
            403,
        )

    def test_exhausted_durable_job_marks_report_failed_and_never_calls_provider(self):
        report = self.report()
        BackgroundJob.objects.filter(pk=report.job_id).update(attempts=3)
        with patch("administration.services.generate_ai_report") as adapter:
            self.assertFalse(process_job())
            adapter.assert_not_called()
        report.refresh_from_db()
        report.job.refresh_from_db()
        self.assertEqual(report.status, "FAILED")
        self.assertEqual(report.job.status, "FAILED")

    def test_invited_summary_reader_sees_only_own_answers_even_in_mutation_response(
        self,
    ):
        from core.models import ParticipationRequest

        ParticipationRequest.objects.create(
            project=self.project,
            requested_by=self.pm,
            user=self.employee,
            target_org=self.unit,
            status="ACCEPTED",
            decided_by=self.unit_head,
            summary="Accepted team participation",
        )
        survey = self.survey(
            invitee_ids=[str(self.unit_head.pk), str(self.employee.pk)]
        )
        answers = {question["id"]: 4 for question in survey["questions"]}
        response = self.call(
            self.unit_head,
            f"/surveys/{survey['id']}/respond/",
            {"version": survey["version"], "answers": answers},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["my_answers"], answers)
        self.assertEqual(response.data["results"], [])
        self.assertIsNone(response.data["responded"])
        self.assertIsNone(response.data["response_rate"])
        self.assertNotIn("responses", response.data)

    def test_raw_ai_original_is_distinct_from_indexed_draft_and_survives_human_edit(
        self,
    ):
        report = self.report(generation_mode="AI")
        job = claim_job()
        original = "## AI değerlendirmesi\n\nEksik kalite kanıtlarını tamamlayın."
        indexed = (
            original
            + "\n\n## onecs kaynak dizini\n\n- Proje kaydı: "
            + str(self.project.pk)
        )
        with patch(
            "administration.services.generate_ai_report",
            return_value={
                "mode": "AI",
                "ai_original_text": original,
                "markdown": indexed,
            },
        ):
            generate_project_insight(job)
        report.refresh_from_db()
        computed_values = report.computed_values
        self.assertEqual(report.original_markdown, original)
        self.assertEqual(report.markdown, indexed)
        self.assertNotEqual(report.original_markdown, report.markdown)
        response = self.call(
            self.pm,
            f"/insight-reports/{report.pk}/",
            {
                "version": report.version,
                "markdown": "Yönetici değerlendirmesi: kalite kanıtları haftalık takibe alındı.",
                "edit_reason": "Yönetim toplantısı aksiyonları eklendi.",
            },
            method="patch",
        )
        self.assertEqual(response.status_code, 200, response.data)
        report.refresh_from_db()
        self.assertEqual(report.original_markdown, original)
        self.assertEqual(
            report.markdown,
            "Yönetici değerlendirmesi: kalite kanıtları haftalık takibe alındı.",
        )
        self.assertEqual(report.computed_values, computed_values)
        self.assertEqual(report.edits.count(), 1)


    def test_fallback_diagnostics_survive_job_completion_and_use_safe_fields(self):
        report = self.report(generation_mode="AI")
        job = claim_job()
        with patch(
            "administration.services.generate_ai_report",
            return_value={
                "mode": "RULE_BASED", "status": "failed",
                "failure_code": "output_truncated", "context_abridged": True,
                "provider_body": "private provider body must remain internal",
            },
        ):
            outcome = generate_project_insight(job)
        job.refresh_from_db()
        self.assertEqual(job.status, "COMPLETED")
        self.assertEqual(outcome, job.result)
        response = self.call(self.pm, f"/insight-reports/{report.pk}/", {}, method="get")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["mode"], "RULE_BASED")
        self.assertEqual(response.data["job"]["fallback_reason"], "output_truncated")
        self.assertEqual(response.data["job"]["generation_status"], "failed")
        self.assertIs(response.data["job"]["context_abridged"], True)
        self.assertNotIn("provider_body", str(response.data))
