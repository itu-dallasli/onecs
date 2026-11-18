"""Project-scoped insight endpoints; session auth and shared idempotency apply."""

import uuid
from datetime import timedelta

from django.http import HttpResponse
from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .exceptions import Conflict
from .models import (
    BackgroundJob,
    ProjectClosureSurvey,
    ProjectDeliverable,
    ProjectInsightEdit,
    ProjectInsightReport,
    ProjectSurveyResponse,
    ProjectTeamPlan,
)
from .policy import can_read_project_detail
from .project_insights import (
    SCORE_KEYS,
    can_read_report,
    deliverable_data,
    eligible_stakeholders,
    get_project,
    insight_permissions,
    number,
    record_progress,
    report_data,
    report_sources,
    require_action,
    resolve_team,
    summary_data,
    survey_data,
    validate_report_snapshot,
)
from .services import (
    access_fingerprint,
    audit,
    bump,
    check_version,
    enqueue_notification,
    ensure,
)
from .views import DomainViewSet, text, timestamp, unknown


@extend_schema_view(
    **{
        name: extend_schema(
            tags=["Project insights"],
            request=OpenApiTypes.OBJECT
            if name not in ("summary", "get_report", "export_report")
            else None,
            responses=OpenApiTypes.OBJECT,
        )
        for name in (
            "summary",
            "create_plan",
            "update_plan",
            "create_delivery",
            "update_delivery",
            "create_survey",
            "respond_survey",
            "close_survey",
            "create_report",
            "get_report",
            "edit_report",
            "publish_report",
            "export_report",
        )
    }
)
class ProjectInsightViewSet(DomainViewSet):
    serializer_class = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.project = get_project(
            request.user,
            kwargs["project_id"],
            lock=request.method not in ("GET", "HEAD", "OPTIONS"),
        )
        actions = {
            "create_plan": "deliverables",
            "update_plan": "deliverables",
            "create_delivery": "deliverables",
            "create_survey": "survey",
            "close_survey": "survey",
            "create_report": "report",
            "edit_report": "report",
            "publish_report": "report",
        }
        if self.action in actions:
            require_action(request.user, self.project, actions[self.action])
        if self.action == "edit_report":
            permissions = insight_permissions(request.user, self.project)
            ensure(
                permissions["manage"] or permissions["quality"],
                "Rapor düzenlemesi PM yönetimi veya açık kapanış yetkisi ister.",
            )

    @action(detail=False, methods=["get"])
    def summary(self, request, project_id):
        return Response(summary_data(self.project, request.user))

    @action(detail=False, methods=["post"])
    def create_plan(self, request, project_id):
        unknown(request.data, {"org_id", "weight"})
        if self.project.team_plans.count() >= 30:
            raise ValidationError("Proje başına en fazla 30 ekip planı desteklenir.")
        org = resolve_team(self.project, request.data.get("org_id"))
        weight = number(request.data.get("weight", 1), "weight", 1, 100)
        if self.project.team_plans.filter(org=org).exists():
            raise Conflict("Bu ekip için plan zaten var; sürümlü güncelleme kullanın.")
        plan = ProjectTeamPlan.objects.create(
            project=self.project, org=org, weight=weight
        )
        audit(request.user, "project.team_plan.created", plan)
        record_progress(self.project, request.user)
        return Response(summary_data(self.project, request.user), status=201)

    @action(detail=False, methods=["patch"])
    def update_plan(self, request, project_id, plan_id):
        unknown(request.data, {"version", "weight"})
        plan = self.project.team_plans.select_for_update().filter(pk=plan_id).first()
        if plan is None:
            raise NotFound("Ekip planı bulunamadı.")
        check_version(plan, request.data)
        plan.weight = number(request.data.get("weight"), "weight", 1, 100)
        bump(plan)
        audit(request.user, "project.team_plan.updated", plan)
        record_progress(self.project, request.user)
        return Response(summary_data(self.project, request.user))

    def delivery_fields(self, request, existing=None):
        allowed = {
            "version",
            "title",
            "org_id",
            "kind",
            "weight",
            "progress",
            "evidence",
            "quality_rating",
            "due_at",
        }
        unknown(request.data, allowed)
        if "quality_rating" in request.data:
            require_action(request.user, self.project, "quality")
        values = {}
        for field, default, low, high in [
            ("weight", 1, 1, 100),
            ("progress", 0, 0, 100),
            ("quality_rating", None, 1, 5),
        ]:
            value = request.data.get(field, getattr(existing, field, default))
            values[field] = number(
                value, field, low, high, nullable=field == "quality_rating"
            )
        values["title"] = (
            text(request.data, "title", True, 240)
            if not existing or "title" in request.data
            else existing.title
        )
        values["evidence"] = (
            text(request.data, "evidence", limit=10000)
            if "evidence" in request.data
            else existing.evidence
            if existing
            else ""
        )
        values["kind"] = request.data.get(
            "kind", existing.kind if existing else "DELIVERABLE"
        )
        if values["kind"] not in ("DELIVERABLE", "MILESTONE"):
            raise ValidationError("kind DELIVERABLE veya MILESTONE olmalıdır.")
        if (
            values["progress"] > 0 or values["quality_rating"] is not None
        ) and not values["evidence"]:
            raise ValidationError(
                {
                    "evidence": "İlerleme veya kalite değerlendirmesi için kaynak/sonuç kanıtı gerekir."
                }
            )
        values["due_at"] = (
            timestamp(request.data["due_at"])
            if "due_at" in request.data
            else existing.due_at
            if existing
            else None
        )
        values["updated_by"] = request.user
        return values

    @action(detail=False, methods=["post"])
    def create_delivery(self, request, project_id):
        if ProjectDeliverable.objects.filter(plan__project=self.project).count() >= 100:
            raise ValidationError("Proje başına en fazla 100 teslimat desteklenir.")
        values = self.delivery_fields(request)
        org = resolve_team(self.project, request.data.get("org_id"))
        plan, _ = ProjectTeamPlan.objects.get_or_create(project=self.project, org=org)
        obj = ProjectDeliverable.objects.create(plan=plan, **values)
        audit(request.user, "project.deliverable.created", obj)
        record_progress(self.project, request.user)
        return Response(deliverable_data(obj), status=201)

    @action(detail=False, methods=["patch"])
    def update_delivery(self, request, project_id, delivery_id):
        obj = (
            ProjectDeliverable.objects.select_for_update()
            .select_related("plan")
            .filter(pk=delivery_id, plan__project=self.project)
            .first()
        )
        if obj is None:
            raise NotFound("Teslimat bulunamadı.")
        check_version(obj, request.data)
        quality_fields = {"version", "quality_rating", "evidence"}
        if set(request.data) <= quality_fields and "quality_rating" in request.data:
            require_action(request.user, self.project, "quality")
        else:
            require_action(request.user, self.project, "deliverables")
        values = self.delivery_fields(request, obj)
        if "org_id" in request.data and str(obj.plan.org_id) != str(
            request.data["org_id"]
        ):
            raise ValidationError(
                "Teslimatın ekibi değiştirilmez; doğru ekipte ayrı teslimat açın."
            )
        for field, value in values.items():
            setattr(obj, field, value)
        bump(obj)
        audit(
            request.user,
            "project.deliverable.updated",
            obj,
            {"progress": obj.progress, "quality_rating": obj.quality_rating},
        )
        record_progress(self.project, request.user)
        return Response(deliverable_data(obj))

    @action(detail=False, methods=["post"])
    def create_survey(self, request, project_id):
        if self.project.closure_surveys.count() >= 8:
            raise ValidationError(
                "Proje başına en fazla 8 değerlendirme anketi desteklenir."
            )
        unknown(request.data, {"title", "questions", "invitee_ids", "closes_at"})
        questions = request.data.get("questions")
        invitees = request.data.get("invitee_ids")
        if not isinstance(questions, list) or not 1 <= len(questions) <= 10:
            raise ValidationError("1–10 soru gerekir.")
        if not isinstance(invitees, list) or not 1 <= len(invitees) <= 200:
            raise ValidationError("1–200 açık paydaş daveti gerekir.")
        normalized = []
        for question in questions:
            if (
                not isinstance(question, str)
                or not question.strip()
                or len(question) > 500
            ):
                raise ValidationError("Her soru 1–500 karakter metin olmalıdır.")
            normalized.append({"id": str(uuid.uuid4()), "label": question.strip()})
        if any(not isinstance(value, str) for value in invitees):
            raise ValidationError("Davetli kimlikleri metin olmalıdır.")
        selected = set(invitees)
        eligible = {str(user.pk): user for user in eligible_stakeholders(self.project)}
        if not selected <= eligible.keys():
            raise ValidationError(
                "Davetliler projenin etkin ve erişimi olan paydaşlarından seçilmelidir."
            )
        closes_at = timestamp(
            request.data.get("closes_at")
        ) or timezone.now() + timedelta(days=7)
        if closes_at <= timezone.now() or closes_at > timezone.now() + timedelta(
            days=366
        ):
            raise ValidationError(
                "Anket son tarihi gelecekte ve en fazla 366 gün içinde olmalıdır."
            )
        survey = ProjectClosureSurvey.objects.create(
            project=self.project,
            title=text(request.data, "title", True, 240),
            questions=normalized,
            created_by=request.user,
            closes_at=closes_at,
        )
        survey.invitees.set([eligible[pk] for pk in selected])
        for pk in selected:
            enqueue_notification(
                eligible[pk],
                "Proje kapanış değerlendirmesi bekleniyor",
                "project",
                self.project.pk,
                f"project-survey:{survey.pk}:{pk}",
            )
        audit(
            request.user,
            "project.survey.created",
            survey,
            {"invitees": len(selected), "questions": len(normalized)},
        )
        return Response(survey_data(survey, request.user), status=201)

    def survey(self, survey_id):
        survey = (
            self.project.closure_surveys.select_for_update()
            .filter(pk=survey_id)
            .first()
        )
        if survey is None:
            raise NotFound("Anket bulunamadı.")
        return survey

    @action(detail=False, methods=["post"])
    def respond_survey(self, request, project_id, survey_id):
        unknown(request.data, {"version", "answers", "response_version"})
        survey = self.survey(survey_id)
        check_version(survey, request.data)
        ensure(
            survey.invitees.filter(pk=request.user.pk, is_active=True).exists(),
            "Yalnız davetli paydaş yanıtlayabilir.",
        )
        if (
            survey.status != "OPEN"
            or survey.closes_at <= timezone.now()
            or self.project.status in ("ARCHIVED", "CANCELLED")
        ):
            raise ValidationError("Anket yanıt kabul etmiyor.")
        answers = request.data.get("answers")
        if not isinstance(answers, dict) or set(answers) != {
            q["id"] for q in survey.questions
        }:
            raise ValidationError("Bütün sorular için tam bir yanıt gerekir.")
        answers = {
            key: number(value, "answers", 1, 5) for key, value in answers.items()
        }
        old = survey.responses.filter(user=request.user).first()
        if old:
            if old.answers != answers:
                check_version(old, {"version": request.data.get("response_version")})
                previous = old.answers
                old.answers = answers
                bump(old)
                audit(
                    request.user,
                    "project.survey.response.edited",
                    old,
                    {
                        "survey_id": str(survey.pk),
                        "previous_answers": previous,
                        "answers": answers,
                    },
                )
                record_progress(self.project, request.user)
            return Response(survey_data(survey, request.user))
        response = ProjectSurveyResponse.objects.create(
            survey=survey, user=request.user, answers=answers
        )
        audit(
            request.user,
            "project.survey.responded",
            response,
            {"survey_id": str(survey.pk)},
        )
        record_progress(self.project, request.user)
        return Response(survey_data(survey, request.user))

    @action(detail=False, methods=["post"])
    def close_survey(self, request, project_id, survey_id):
        unknown(request.data, {"version"})
        survey = self.survey(survey_id)
        check_version(survey, request.data)
        if survey.status != "CLOSED":
            survey.status = "CLOSED"
            bump(survey)
            audit(request.user, "project.survey.closed", survey)
        return Response(survey_data(survey, request.user))

    @action(detail=False, methods=["post"])
    def create_report(self, request, project_id):
        from administration.profiles import selected_ai_snapshot

        unknown(request.data, {"kind", "period_start", "period_end", "generation_mode"})
        kind = request.data.get("kind")
        if kind not in ("DAILY", "WEEKLY", "CLOSURE"):
            raise ValidationError("Rapor türü DAILY, WEEKLY veya CLOSURE olmalıdır.")
        if kind == "CLOSURE":
            require_action(request.user, self.project, "quality")
        try:
            start = parse_date(str(request.data.get("period_start", "")))
            end = parse_date(str(request.data.get("period_end", "")))
        except ValueError:
            raise ValidationError("Geçerli rapor tarihleri gerekir.")
        if not start or not end or end < start or (end - start).days > 365:
            raise ValidationError("Rapor dönemi sıralı ve en fazla 366 gün olmalıdır.")
        ensure(can_read_project_detail(request.user, self.project))
        sources, scores, fingerprint = report_sources(self.project, start, end)
        report = ProjectInsightReport.objects.create(
            project=self.project,
            created_by=request.user,
            kind=kind,
            period_start=start,
            period_end=end,
            sources=sources,
            computed_values=scores,
            source_hash=fingerprint,
        )
        generation_mode = request.data.get("generation_mode", "AI")
        if generation_mode not in ("AI", "RULE_BASED"):
            raise ValidationError("generation_mode AI veya RULE_BASED olmalıdır.")
        snapshot = (
            selected_ai_snapshot()
            if generation_mode == "AI"
            else {"profile_id": None, "configuration_version": 0, "settings_version": 0}
        )
        job = BackgroundJob.objects.create(
            kind="PROJECT_INSIGHT",
            actor=request.user,
            payload={
                "report_id": str(report.pk),
                "report_version": report.version,
                "generation_mode": generation_mode,
                "access_fingerprint": access_fingerprint(request.user),
                "ai_profile_id": snapshot["profile_id"],
                "ai_configuration_version": snapshot["configuration_version"],
                "ai_settings_version": snapshot["settings_version"],
            },
        )
        report.job = job
        report.save(update_fields=["job"])
        audit(request.user, "project.insight.queued", report, {"kind": kind})
        return Response(report_data(report), status=202)

    def report(self, report_id, actor, *, write=False):
        qs = ProjectInsightReport.objects.select_related(
            "job", "project__appointment__user"
        )
        if write:
            qs = qs.select_for_update(of=("self",))
        report = qs.filter(pk=report_id, project=self.project).first()
        if report is None or not can_read_report(actor, report):
            raise NotFound("Rapor bulunamadı.")
        return report

    @action(detail=False, methods=["get"])
    def get_report(self, request, project_id, report_id):
        return Response(report_data(self.report(report_id, request.user)))

    @action(detail=False, methods=["patch"])
    def edit_report(self, request, project_id, report_id):
        unknown(request.data, {"version", "markdown", "reviewed_scores", "edit_reason"})
        report = self.report(report_id, request.user, write=True)
        check_version(report, request.data)
        if report.kind == "CLOSURE":
            require_action(request.user, self.project, "quality")
        if report.status != "READY":
            raise ValidationError(
                "Yalnız hazır ve henüz yayımlanmamış taslak düzenlenebilir."
            )
        validate_report_snapshot(report, request.user)
        reason = text(request.data, "edit_reason", True, 2000)
        if "markdown" not in request.data and "reviewed_scores" not in request.data:
            raise ValidationError(
                "Düzenlenecek metin veya gözden geçirilmiş puan gerekir."
            )
        if "markdown" in request.data:
            report.markdown = text(request.data, "markdown", True, 100000)
        if "reviewed_scores" in request.data:
            require_action(request.user, self.project, "quality")
            scores = request.data["reviewed_scores"]
            if not isinstance(scores, dict) or not scores or set(scores) - SCORE_KEYS:
                raise ValidationError(
                    "Yalnız delivery/quality/stakeholder/overall puanları düzenlenebilir."
                )
            reviewed = dict(report.reviewed_scores)
            for key, value in scores.items():
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0 <= value <= 100
                ):
                    raise ValidationError(
                        "Gözden geçirilmiş puan 0–100 sayı veya null olmalıdır."
                    )
                reviewed[key] = value
            report.reviewed_scores = reviewed
        report.edit_reason = reason
        bump(report)
        ProjectInsightEdit.objects.create(
            report=report,
            author=request.user,
            markdown=report.markdown,
            reviewed_scores=report.reviewed_scores,
            reason=reason,
        )
        audit(
            request.user,
            "project.insight.edited",
            report,
            {
                "reviewed_fields": sorted(request.data.get("reviewed_scores", {})),
                "reason": reason,
            },
        )
        return Response(report_data(report))

    @action(detail=False, methods=["post"])
    def publish_report(self, request, project_id, report_id):
        unknown(request.data, {"version"})
        report = self.report(report_id, request.user, write=True)
        check_version(report, request.data)
        # Final publication is a management decision; task-only grants cannot publish.
        require_action(
            request.user,
            self.project,
            "quality" if report.kind == "CLOSURE" else "manage",
        )
        if report.status != "READY":
            raise ValidationError("Yalnız hazır rapor yayımlanabilir.")
        if report.kind == "CLOSURE" and self.project.status != "COMPLETED":
            raise ValidationError(
                "Kapanış başarı endeksi ancak proje tamamlandıktan sonra yayımlanabilir."
            )
        validate_report_snapshot(report, request.user)
        report.status = "PUBLISHED"
        report.published_by = request.user
        report.published_at = timezone.now()
        bump(report)
        audit(request.user, "project.insight.published", report)
        return Response(report_data(report))

    @action(detail=False, methods=["get"])
    def export_report(self, request, project_id, report_id):
        report = self.report(report_id, request.user)
        # Includes the human review disclosure; immutable original remains in the API.
        markdown = report.markdown
        if report.reviewed_scores:
            import json

            markdown += (
                "\n\n## Yönetici gözden geçirmesi\n\n"
                + json.dumps(report.reviewed_scores, ensure_ascii=False)
                + "\n\nGerekçe: "
                + report.edit_reason
                + "\n"
            )
        return HttpResponse(
            markdown,
            content_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="onecs-project-report.md"'
            },
        )


urlpatterns = [
    path(
        "projects/<uuid:project_id>/insights/",
        ProjectInsightViewSet.as_view({"get": "summary"}),
    ),
    path(
        "projects/<uuid:project_id>/team-plans/",
        ProjectInsightViewSet.as_view({"post": "create_plan"}),
    ),
    path(
        "projects/<uuid:project_id>/team-plans/<uuid:plan_id>/",
        ProjectInsightViewSet.as_view({"patch": "update_plan"}),
    ),
    path(
        "projects/<uuid:project_id>/deliverables/",
        ProjectInsightViewSet.as_view({"post": "create_delivery"}),
    ),
    path(
        "projects/<uuid:project_id>/deliverables/<uuid:delivery_id>/",
        ProjectInsightViewSet.as_view({"patch": "update_delivery"}),
    ),
    path(
        "projects/<uuid:project_id>/surveys/",
        ProjectInsightViewSet.as_view({"post": "create_survey"}),
    ),
    path(
        "projects/<uuid:project_id>/surveys/<uuid:survey_id>/respond/",
        ProjectInsightViewSet.as_view({"post": "respond_survey"}),
    ),
    path(
        "projects/<uuid:project_id>/surveys/<uuid:survey_id>/close/",
        ProjectInsightViewSet.as_view({"post": "close_survey"}),
    ),
    path(
        "projects/<uuid:project_id>/insight-reports/",
        ProjectInsightViewSet.as_view({"post": "create_report"}),
    ),
    path(
        "projects/<uuid:project_id>/insight-reports/<uuid:report_id>/",
        ProjectInsightViewSet.as_view({"get": "get_report", "patch": "edit_report"}),
    ),
    path(
        "projects/<uuid:project_id>/insight-reports/<uuid:report_id>/publish/",
        ProjectInsightViewSet.as_view({"post": "publish_report"}),
    ),
    path(
        "projects/<uuid:project_id>/insight-reports/<uuid:report_id>/markdown/",
        ProjectInsightViewSet.as_view({"get": "export_report"}),
    ),
]
