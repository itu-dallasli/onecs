"""Evidence-based project delivery, named closure surveys and reviewable reports."""

import hashlib
import json
import math
from datetime import datetime, time

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .exceptions import Conflict
from .models import (
    BackgroundJob,
    OrgNode,
    Project,
    ProjectInsightReport,
    ProjectProgressSnapshot,
    ProgressEntry,
    User,
)
from .policy import (
    active_actor,
    api_org_allowed,
    can_manage_project,
    can_read_project,
    can_read_project_detail,
)
from .services import access_fingerprint, audit, bump, ensure

SCORE_KEYS = {"delivery", "quality", "stakeholder", "overall"}
FORMULA = {
    "label": "Proje başarı endeksi; olasılık veya kişisel performans puanı değildir.",
    "weights": {"delivery": 0.5, "quality": 0.3, "stakeholder": 0.2},
    "delivery": "Önce ekip içi teslimat ağırlıklı ilerleme; sonra bağımsız ekip planı ağırlıkları.",
    "quality": "Kanıtlı 1–5 teslimat değerlendirmesi: (puan−1)×25; aynı iki aşamalı ağırlık.",
    "stakeholder": "Son anketin kişi başına eşit ağırlıklı 1–5 ortalaması: (ortalama−1)×25.",
    "missing": "Eksik ekip/teslimat/kalite veya yanıtsız ankette ilgili bileşen null; üç bileşen yoksa toplam null.",
}


def insight_permissions(actor, project):
    if getattr(actor, "_api_client", None) is not None:
        return {
            key: False
            for key in ("manage", "deliverables", "quality", "survey", "report")
        }
    tasks = can_manage_project(actor, project, "tasks")
    close = can_manage_project(actor, project, "close")
    manage = can_manage_project(actor, project, "manage")
    return {
        "manage": manage,
        "deliverables": tasks,
        "quality": close,
        "survey": close,
        "report": tasks or close or manage,
    }


def get_project(actor, project_id, *, lock=False):
    qs = Project.objects.select_related("appointment__user", "owner_org")
    if lock:
        qs = qs.select_for_update(of=("self",))
    project = qs.filter(pk=project_id).first()
    if project is None or not can_read_project(actor, project):
        raise NotFound("Proje bulunamadı.")
    return project


def require_action(actor, project, permission):
    ensure(active_actor(actor) and api_org_allowed(actor, project.owner_org_id))
    ensure(
        insight_permissions(actor, project)[permission],
        "Bu proje işlemi için açık PM yetkisi gerekir.",
    )
    if project.status in (
        "DRAFT",
        "SUBMITTED",
        "REVISION",
        "REJECTED",
        "CANCELLED",
        "ARCHIVED",
    ):
        raise ValidationError(
            "İşlem yalnız onaylanmış, etkin veya tamamlanmış projede kullanılabilir."
        )


def eligible_stakeholders(project):
    ids = set(
        project.memberships.filter(active=True, user__is_active=True).values_list(
            "user_id", flat=True
        )
    )
    ids.update([project.created_by_id, project.appointment.user_id])
    ids.update(
        project.authorities.filter(
            active=True, expires_at__gt=timezone.now(), user__is_active=True
        ).values_list("user_id", flat=True)
    )
    ids.update(
        project.resource_requests.filter(status="ACCEPTED").values_list(
            "user_id", flat=True
        )
    )
    ids.update(
        project.resource_requests.filter(
            status="ACCEPTED", decided_by__isnull=False
        ).values_list("decided_by_id", flat=True)
    )
    return [
        person
        for person in User.objects.filter(pk__in=ids, is_active=True).order_by(
            "display_name"
        )
        if can_read_project(person, project)
    ]


def expected_team_ids(project):
    ids = set(
        project.memberships.filter(active=True, user__is_active=True)
        .exclude(user_id=project.appointment.user_id)
        .values_list("user__primary_org_id", flat=True)
    )
    ids.update(
        project.resource_requests.filter(
            status="ACCEPTED", user__is_active=True
        ).values_list("target_org_id", flat=True)
    )
    return ids - {None}


def allowed_team_ids(project):
    ids = expected_team_ids(project) | {project.owner_org_id}
    nodes = {node.pk: node for node in OrgNode.objects.filter(active=True)}
    for org_id in list(ids):
        node = nodes.get(org_id)
        while node and node.kind == "TEAM" and node.parent_id:
            node = nodes.get(node.parent_id)
            if node and node.kind in ("UNIT", "TEAM"):
                ids.add(node.pk)
    return {pk for pk in ids if pk in nodes and nodes[pk].kind in ("UNIT", "TEAM")}


def missing_team_ids(project, planned_ids):
    parents = dict(OrgNode.objects.filter(active=True).values_list("pk", "parent_id"))
    missing = set()
    for org_id in expected_team_ids(project):
        current = org_id
        visited = set()
        while (
            current is not None
            and current not in planned_ids
            and current not in visited
        ):
            visited.add(current)
            current = parents.get(current)
        if current not in planned_ids:
            missing.add(org_id)
    return missing


def resolve_team(project, org_id):
    org = OrgNode.objects.filter(pk=org_id, active=True).first()
    if not org or org.pk not in allowed_team_ids(project):
        raise ValidationError(
            "Ekip, projenin sahibi veya kabul edilmiş katılımcı ekiplerinden biri olmalıdır."
        )
    return org


def number(value, field, lower, upper, *, nullable=False):
    if value is None and nullable:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value != int(value)
        or not lower <= value <= upper
    ):
        raise ValidationError({field: f"{lower}–{upper} aralığında tam sayı girin."})
    return int(value)


def deliverable_data(obj):
    return {
        "id": str(obj.pk),
        "version": obj.version,
        "title": obj.title,
        "kind": obj.kind,
        "org_id": str(obj.plan.org_id),
        "weight": obj.weight,
        "progress": obj.progress,
        "evidence": obj.evidence,
        "quality_rating": obj.quality_rating,
        "due_at": obj.due_at.isoformat() if obj.due_at else None,
        "updated_at": obj.updated_at.isoformat(),
    }


def survey_data(survey, actor, *, detail=True):
    detail = detail and can_read_project_detail(actor, survey.project)
    rows = list(survey.responses.select_related("user").order_by("created_at"))
    invited = survey.invitees.count()
    results = []
    for question in survey.questions:
        values = [
            r.answers[question["id"]] for r in rows if question["id"] in r.answers
        ]
        results.append(
            {
                "question_id": question["id"],
                "label": question["label"],
                "average": round(sum(values) / len(values), 2) if values else None,
                "count": len(values),
            }
        )
    own_response = next((r for r in rows if r.user_id == actor.pk), None)
    own = own_response.answers if own_response else None
    can_respond = (
        active_actor(actor)
        and can_read_project(actor, survey.project)
        and survey.status == "OPEN"
        and survey.project.status not in ("ARCHIVED", "CANCELLED")
        and survey.closes_at > timezone.now()
        and survey.invitees.filter(pk=actor.pk).exists()
    )
    data = {
        "id": str(survey.pk),
        "title": survey.title,
        "version": survey.version,
        "status": survey.status,
        "closes_at": survey.closes_at.isoformat(),
        "questions": survey.questions,
        "invited": invited,
        "responded": len(rows),
        "response_rate": round(len(rows) / invited * 100, 2) if invited else None,
        "results": results,
        "my_answers": own,
        "my_response_version": own_response.version if own_response else None,
        "can_respond": bool(can_respond),
        "named": True,
    }
    if detail and insight_permissions(actor, survey.project)["survey"]:
        data["invitee_ids"] = [
            str(pk) for pk in survey.invitees.values_list("pk", flat=True)
        ]
        data["responses"] = [
            {
                "user_id": str(row.user_id),
                "display_name": row.user.display_name,
                "answers": row.answers,
            }
            for row in rows
        ]
    if not detail:
        data.update(
            {"results": [], "invited": None, "responded": None, "response_rate": None}
        )
    return data


def project_metrics(project):
    teams = []
    quality_teams = []
    total_deliveries = rated = 0
    for plan in (
        project.team_plans.select_related("org")
        .prefetch_related("deliverables")
        .order_by("org__name", "org_id")
    ):
        deliveries = list(plan.deliverables.order_by("pk"))
        total_deliveries += len(deliveries)
        rated += sum(d.quality_rating is not None for d in deliveries)
        weight = sum(d.weight for d in deliveries)
        progress = (
            round(sum(d.progress * d.weight for d in deliveries) / weight, 2)
            if weight
            else None
        )
        quality = (
            sum((d.quality_rating - 1) * 25 * d.weight for d in deliveries) / weight
            if weight and all(d.quality_rating is not None for d in deliveries)
            else None
        )
        quality_teams.append((quality, plan.weight))
        teams.append(
            {
                "id": str(plan.pk),
                "version": plan.version,
                "org_id": str(plan.org_id),
                "org_name": plan.org.name,
                "weight": plan.weight,
                "progress": progress,
                "coverage": {
                    "deliverables": len(deliveries),
                    "quality_rated": sum(
                        d.quality_rating is not None for d in deliveries
                    ),
                },
                "deliverables": [deliverable_data(d) for d in deliveries],
            }
        )
    missing = missing_team_ids(
        project,
        {
            plan.pk
            for plan in OrgNode.objects.filter(pk__in=[t["org_id"] for t in teams])
        },
    )
    total_weight = sum(t["weight"] for t in teams)
    delivery = (
        round(sum(t["progress"] * t["weight"] for t in teams) / total_weight, 2)
        if teams and not missing and all(t["progress"] is not None for t in teams)
        else None
    )
    quality = (
        round(sum(value * weight for value, weight in quality_teams) / total_weight, 2)
        if teams
        and not missing
        and all(value is not None for value, _ in quality_teams)
        else None
    )
    survey = project.closure_surveys.order_by("-created_at").first()
    values = []
    invited = responded = 0
    if survey:
        invited = survey.invitees.count()
        answers = list(survey.responses.values_list("answers", flat=True))
        responded = len(answers)
        values = [sum(a.values()) / len(a) for a in answers if a]
    stakeholder = round((sum(values) / len(values) - 1) * 25, 2) if values else None
    overall = (
        round(delivery * 0.5 + quality * 0.3 + stakeholder * 0.2, 2)
        if all(v is not None for v in (delivery, quality, stakeholder))
        else None
    )
    scores = {
        "delivery": delivery,
        "quality": quality,
        "stakeholder": stakeholder,
        "overall": overall,
        "coverage": {
            "teams": len(teams),
            "unplanned_teams": len(missing),
            "unplanned_org_ids": sorted(str(pk) for pk in missing),
            "deliverables": total_deliveries,
            "quality_rated": rated,
            "survey_invited": invited,
            "survey_responded": responded,
            "response_rate": round(responded / invited * 100, 2) if invited else None,
        },
        "formula": FORMULA,
    }
    return teams, scores


def record_progress(project, actor):
    teams, scores = project_metrics(project)
    compact = [
        {
            key: team[key]
            for key in ("id", "version", "org_id", "weight", "progress", "coverage")
        }
        for team in teams
    ]
    ProjectProgressSnapshot.objects.create(
        project=project, created_by=actor, teams=compact, scores=scores
    )


def report_sources(project, period_start, period_end):
    """Canonical snapshots exclude personal ranking and named individual survey answers."""
    teams, scores = project_metrics(project)
    sources = [
        {
            "id": str(project.pk),
            "type": "project",
            "version": project.version,
            "title": project.title,
            "status": project.status,
            "summary": project.expected_outcome or project.description,
        }
    ]
    sources.append(
        {
            "id": str(project.pk) + ":metrics",
            "type": "project_metrics",
            "version": project.version,
            "title": "Hesaplanmış proje başarı endeksi",
            "status": "DETERMINISTIC",
            "summary": json.dumps(scores, ensure_ascii=False),
        }
    )
    for team in teams:
        sources.append(
            {
                "id": team["id"],
                "type": "project_team_plan",
                "version": team["version"],
                "title": team["org_name"],
                "status": "PLAN",
                "summary": f"Ekip ağırlığı {team['weight']}; ilerleme {team['progress']}; kapsam {team['coverage']}",
            }
        )
        for delivery in team["deliverables"]:
            sources.append(
                {
                    "id": delivery["id"],
                    "type": "project_deliverable",
                    "version": delivery["version"],
                    "title": delivery["title"],
                    "status": f"%{delivery['progress']}",
                    "summary": f"Ekip: {team['org_name']}; ağırlık: {delivery['weight']}; kanıt: {delivery['evidence']}; kalite1–5: {delivery['quality_rating']}; termin: {delivery['due_at']}",
                }
            )
    for survey in project.closure_surveys.order_by("created_at"):
        rows = list(survey.responses.values_list("answers", flat=True))
        averages = [
            {
                "question": q["label"],
                "average": sum(a[q["id"]] for a in rows) / len(rows) if rows else None,
            }
            for q in survey.questions
        ]
        sources.append(
            {
                "id": str(survey.pk),
                "type": "project_survey",
                "response_versions": [
                    (str(pk), version)
                    for pk, version in survey.responses.order_by("pk").values_list(
                        "id", "version"
                    )
                ],
                "version": survey.version,
                "title": survey.title,
                "status": survey.status,
                "summary": json.dumps(
                    {
                        "invited": survey.invitees.count(),
                        "responded": len(rows),
                        "results": averages,
                        "closes_at": survey.closes_at.isoformat(),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    start = timezone.make_aware(datetime.combine(period_start, time.min))
    end = timezone.make_aware(datetime.combine(period_end, time.max))
    contributions = (
        ProgressEntry.objects.filter(Q(project=project) | Q(work__project=project))
        .filter(created_at__gte=start, created_at__lte=end)
        .order_by("created_at")
    )
    for entry in contributions[:50]:
        sources.append(
            {
                "id": str(entry.pk),
                "type": "contribution",
                "version": entry.version,
                "title": "Dönem proje katkısı",
                "status": "RECORDED",
                "summary": f"Yapılan: {entry.done}; sonraki adım: {entry.next_step}; engel: {entry.blocker}",
            }
        )
    count = contributions.count()
    scores["source_coverage"] = {
        "selected_sources": len(sources),
        "ai_max_sources": 50,
        "ai_omitted_sources": max(0, len(sources) - 50),
        "period_contributions": count,
        "selected_contributions": min(count, 50),
    }
    sources[1]["summary"] = json.dumps(
        {
            "scores": {key: scores[key] for key in sorted(SCORE_KEYS)},
            "formula_weights": FORMULA["weights"],
            "coverage": scores["coverage"],
            "source_coverage": scores["source_coverage"],
            "interpretation": "İki aşamalı ekip/teslimat ağırlığı; eksik veri null. Endeks olasılık veya kişisel sıralama değildir.",
        },
        ensure_ascii=False,
    )
    inventory = hashlib.sha256()
    for pk, version in (
        contributions.order_by("pk").values_list("pk", "version").iterator()
    ):
        inventory.update(f"{pk}:{version};".encode())
    manifest = {
        "period_inventory_hash": inventory.hexdigest(),
        "sources": sources,
        "computed_values": scores,
        "period_contribution_count": contributions.count(),
    }
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return sources, scores, digest


def report_data(report):
    job = report.job
    return {
        "id": str(report.pk),
        "project_id": str(report.project_id),
        "version": report.version,
        "kind": report.kind,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "status": report.status,
        "mode": report.generated_mode,
        "original_markdown": report.original_markdown,
        "markdown": report.markdown,
        "computed_values": report.computed_values,
        "reviewed_scores": report.reviewed_scores,
        "edit_reason": report.edit_reason,
        "sources": report.sources,
        "source_coverage": report.computed_values.get("source_coverage", {}),
        "job": {
            "id": str(job.pk),
            "status": job.status,
            "last_error": job.last_error,
            "generation_status": job.result.get("generation_status", ""),
            "fallback_reason": job.result.get("fallback_reason", ""),
            "context_abridged": job.result.get("context_abridged", False),
        }
        if job
        else None,
        "published_at": report.published_at.isoformat()
        if report.published_at
        else None,
    }


def can_read_report(actor, report):
    return can_read_project_detail(actor, report.project) and (
        report.status == "PUBLISHED"
        or insight_permissions(actor, report.project)["report"]
    )


def summary_data(project, actor):
    permissions = insight_permissions(actor, project)
    full = can_read_project_detail(actor, project)
    if not full:
        return {
            "project_id": str(project.pk),
            "project_version": project.version,
            "permissions": permissions,
            "teams": [],
            "scores": {
                "delivery": None,
                "quality": None,
                "stakeholder": None,
                "overall": None,
                "coverage": {},
                "formula": FORMULA,
            },
            "surveys": [
                survey_data(survey, actor, detail=False)
                for survey in project.closure_surveys.filter(invitees=actor)
            ],
            "reports": [],
            "stakeholders": [],
            "allowed_teams": [],
            "trend": [],
            "detail_restricted": True,
        }
    teams, scores = project_metrics(project)
    reports = [
        report_data(report)
        for report in project.insight_reports.select_related("job").order_by(
            "-created_at"
        )[:30]
        if can_read_report(actor, report)
    ]
    return {
        "project_id": str(project.pk),
        "project_version": project.version,
        "permissions": permissions,
        "teams": teams,
        "scores": scores,
        "surveys": [
            survey_data(survey, actor)
            for survey in project.closure_surveys.order_by("-created_at")
        ],
        "reports": reports,
        "stakeholders": [
            {
                "id": str(person.pk),
                "display_name": person.display_name or person.username,
                "org_id": str(person.primary_org_id) if person.primary_org_id else None,
            }
            for person in eligible_stakeholders(project)
        ]
        if permissions["survey"]
        else [],
        "allowed_teams": [
            {"id": str(org.pk), "name": org.name}
            for org in OrgNode.objects.filter(
                pk__in=allowed_team_ids(project)
            ).order_by("name")
        ]
        if permissions["deliverables"]
        else [],
        "trend": [
            {"at": snapshot.created_at.isoformat(), "scores": snapshot.scores}
            for snapshot in project.progress_snapshots.order_by("-created_at")[:30]
        ][::-1],
    }


def fallback_markdown(report):
    """Concise Turkish executive copy derived only from immutable report snapshots."""
    scores = report.computed_values
    coverage = scores.get("coverage", {})
    kind = {
        "DAILY": "Günlük yönetim özeti",
        "WEEKLY": "Haftalık yönetim özeti",
        "CLOSURE": "Kapanış değerlendirmesi",
    }.get(report.kind, "Proje yönetim özeti")
    states = {
        "DRAFT": "Taslak",
        "SUBMITTED": "Onay bekliyor",
        "REVISION": "Revizyon bekliyor",
        "PLANNED": "Planlandı",
        "IN_PROGRESS": "Devam ediyor",
        "WAITING": "Beklemede",
        "COMPLETED": "Tamamlandı",
        "CANCELLED": "İptal edildi",
        "ARCHIVED": "Arşivlendi",
    }

    def value(number, *, percent=False):
        if number is None:
            return "Veri yok"
        rendered = f"{number:g}".replace(".", ",")
        return f"%{rendered}" if percent else f"{rendered}/100"

    def brief(text, limit=180):
        normalized = " ".join(str(text or "").split())
        return (
            normalized
            if len(normalized) <= limit
            else normalized[: limit - 1].rstrip() + "…"
        )

    project_source = next(
        (source for source in report.sources if source["type"] == "project"), {}
    )
    status = states.get(project_source.get("status"), "Durum bilgisi yok")
    teams = coverage.get("teams", 0)
    deliveries = coverage.get("deliverables", 0)
    rated = coverage.get("quality_rated", 0)
    invited = coverage.get("survey_invited", 0)
    responded = coverage.get("survey_responded", 0)
    rate = coverage.get("response_rate")
    start = report.period_start.strftime("%d.%m.%Y")
    end = report.period_end.strftime("%d.%m.%Y")
    lines = [
        f"# {report.project.title} · {kind}",
        f"\n**Dönem:** {start} – {end} · **Durum:** {status}",
        "\nBu taslak kayıtlı kaynaklardan kurallı olarak hazırlanmıştır (RULE_BASED). Canlı yapay zekâ çıktısı değildir.",
    ]
    delivery = scores.get("delivery")
    progress_sentence = (
        f"Ağırlıklı teslimat ilerlemesi {value(delivery, percent=True)}."
        if delivery is not None
        else "Genel teslimat ilerlemesi için yeterli plan/veri yok."
    )
    lines.append(
        f"\nProje {teams} ekip ve {deliveries} teslimat üzerinden izleniyor. {progress_sentence} "
        f"Kalite değerlendirmesi {rated}/{deliveries} teslimatta mevcut."
    )
    response_text = f"{responded}/{invited} yanıt" + (
        f" (%{rate:g})".replace(".", ",")
        if rate is not None
        else " (yanıt oranı hesaplanamıyor)"
    )
    lines.extend(
        [
            "\n## Yönetici özeti",
            f"- Teslimat ilerlemesi: {value(delivery, percent=True)}",
            f"- Teslimat kalitesi: {value(scores.get('quality'))}",
            f"- Paydaş değerlendirmesi: {value(scores.get('stakeholder'))} · {response_text}",
            f"- Proje başarı endeksi: {value(scores.get('overall'))}",
            "\nBaşarı endeksi bir olasılık veya kişisel performans sıralaması değildir. "
            "Önce ekip içi teslimat, ardından ekip planı ağırlıkları uygulanır. "
            "Endeksin bileşenleri teslimat %50, kalite %30, paydaş %20'dir; eksik bileşenle toplam üretilmez.",
        ]
    )
    team_sources = [
        source for source in report.sources if source["type"] == "project_team_plan"
    ]
    if team_sources:
        lines.append("\n## Ekiplerin ilerlemesi")
        for source in team_sources[:8]:
            raw = (
                source.get("summary", "")
                .partition("ilerleme ")[2]
                .partition(";")[0]
                .strip()
            )
            try:
                progress = float(raw)
            except (ValueError, TypeError):
                progress = None
            lines.append(
                f"- **{brief(source['title'], 90)}:** {value(progress, percent=True)}"
            )
        if len(team_sources) > 8:
            lines.append(
                f"- Diğer {len(team_sources) - 8} ekibin ayrıntısı kaynak kayıtlarında bulunur."
            )
    recommendations = []
    unplanned = coverage.get("unplanned_teams", 0)
    if unplanned:
        recommendations.append(
            f"{unplanned} katılımcı ekip için teslimat planı eksik; genel ilerlemeyi değerlendirmeden önce kapsamı tamamlayın."
        )
    if delivery is not None and delivery < 100:
        recommendations.append(
            "Açık teslimatların sonraki adımlarını, engellerini ve terminlerini ekip sorumlularıyla netleştirin."
        )
    if scores.get("quality") is None:
        recommendations.append(
            f"Eksik kalite değerlendirmelerini kanıtlarıyla tamamlayın ({rated}/{deliveries} teslimat değerlendirildi)."
        )
    if not responded:
        recommendations.append(
            "Paydaş yanıtı yok; memnuniyet puanı çıkarmadan önce anketi ve davetli kapsamını kontrol edin."
        )
    elif responded < invited:
        recommendations.append(
            f"Anket için {invited - responded} paydaş yanıtı bekleniyor; mevcut sonuç {responded} kişinin görüşünü temsil ediyor."
        )
    if project_source.get("status") == "WAITING":
        recommendations.append(
            "Bekleyen bağımlılıkları ve engelleri proje yöneticisinin gündemine taşıyın."
        )
    if not recommendations:
        recommendations.append(
            "Kapanış kanıtlarını ve paydaş geri bildirimini yönetici gözden geçirmesine sunun."
        )
    lines.append("\n## Takip ve sonraki adımlar")
    lines.extend(f"- {recommendation}" for recommendation in recommendations)
    evidence_sources = [
        source
        for source in report.sources
        if source["type"] in ("project_deliverable", "contribution", "project_survey")
    ]
    selected = evidence_sources[:8]
    if selected:
        lines.append("\n## Seçilmiş kaynak notları")
        for index, source in enumerate(selected, 1):
            if source["type"] == "project_deliverable":
                detail = (
                    source.get("summary", "")
                    .partition("kanıt: ")[2]
                    .partition("; kalite1–5:")[0]
                    .strip()
                )
                status_text = source.get("status", "")
                detail = f"İlerleme {status_text}. " + (
                    brief(detail) if detail else "Henüz ilerleme kanıtı girilmemiş."
                )
            elif source["type"] == "contribution":
                detail = brief(source.get("summary", ""))
            else:
                detail = "Paydaş anketi; örneklem ve yanıt oranı yönetici özetinde gösterilir."
            lines.append(f"- **{brief(source['title'], 90)}:** {detail} [K{index}]")
        if len(evidence_sources) > len(selected):
            lines.append(
                f"\nBu özette {len(selected)} kaynak seçildi; kalan {len(evidence_sources) - len(selected)} kaydın tamamı raporun kaynak ayrıntısında saklanır."
            )
        lines.append("\n### Kaynak dizini")
        for index, source in enumerate(selected, 1):
            lines.append(
                f"- K{index}: `{source['type']}:{source['id']}` · sürüm {source['version']}"
            )
    source_coverage = scores.get("source_coverage", {})
    if source_coverage.get("ai_omitted_sources", 0):
        lines.append(
            "\nAI bağlam sınırını aşan kaynaklar vardır; bu kurallı özet kayıtlı kaynaklar ve hesaplanan kapsam üzerinden hazırlanmıştır."
        )
    return "\n".join(lines) + "\n"


def validate_report_snapshot(report, actor, expected_access=None):
    project = Project.objects.select_related("appointment__user").get(
        pk=report.project_id
    )
    require_action(actor, project, "report")
    ensure(can_read_project_detail(actor, project))
    if expected_access is not None:
        ensure(
            access_fingerprint(actor) == expected_access,
            "Rapor sahibinin erişim kapsamı değişti.",
        )
    _, _, fingerprint = report_sources(project, report.period_start, report.period_end)
    if fingerprint != report.source_hash:
        raise Conflict(
            "Proje, teslimat, anket veya dönem kaynağı değişti; yeni rapor oluşturun."
        )


def generate_project_insight(job):
    report = ProjectInsightReport.objects.select_related("project").get(
        pk=job.payload["report_id"]
    )
    actor = User.objects.get(pk=job.actor_id)
    validate_report_snapshot(report, actor, job.payload["access_fingerprint"])
    if report.version != job.payload["report_version"]:
        raise Conflict("Rapor taslağı değişti.")
    if job.payload.get("generation_mode") == "RULE_BASED":
        result = {}
    else:
        from administration.services import generate_ai_report

        result = generate_ai_report(
            actor,
            report.sources,
            report_kind=f"PROJECT_{report.kind}",
            request_id=str(job.pk),
            profile_id=job.payload.get("ai_profile_id"),
            configuration_version=job.payload.get("ai_configuration_version", 0),
            settings_version=job.payload.get("ai_settings_version", 0),
        )
    markdown = result.get("markdown") or result.get("text") or ""
    mode = result.get("mode", "RULE_BASED") if markdown else "RULE_BASED"
    if not markdown:
        markdown = fallback_markdown(report)
    outcome = {
        "report_id": str(report.pk),
        "mode": mode,
        "generation_status": result.get("status", "rule_based_requested"),
        "fallback_reason": (
            result.get("failure_code") or result.get("status", "rule_based_requested")
        )
        if mode == "RULE_BASED"
        else "",
        "context_abridged": bool(result.get("context_abridged", False)),
    }
    with transaction.atomic():
        current_job = BackgroundJob.objects.select_for_update().get(pk=job.pk)
        if (
            current_job.status != "RUNNING"
            or current_job.lease_token != job.lease_token
            or current_job.lease_until is None
            or current_job.lease_until <= timezone.now()
        ):
            raise Conflict("İşin çalışma yetkisi sona erdi.")
        # Project lock serializes snapshot validation with all insight mutations.
        Project.objects.select_for_update().get(pk=report.project_id)
        current = ProjectInsightReport.objects.select_for_update().get(pk=report.pk)
        if (
            current.status != "GENERATING"
            or current.job_id != job.pk
            or current.version != job.payload["report_version"]
        ):
            raise Conflict("Rapor işi artık güncel değil.")
        actor = User.objects.get(pk=actor.pk)
        validate_report_snapshot(current, actor, job.payload["access_fingerprint"])
        # Preserve the provider's original wording separately from the server
        # source index that accompanies the reviewable report.
        current.original_markdown = result.get("ai_original_text") or markdown
        current.markdown = markdown
        current.generated_mode = mode
        current.status = "READY"
        bump(current)
        audit(
            actor,
            "project.insight.generated",
            current,
            {"mode": mode, "source_count": len(current.sources)},
        )
        current_job.status = "COMPLETED"
        current_job.result = outcome
        current_job.checkpoint = {"stage": "completed"}
        current_job.lease_until = None
        current_job.last_error = ""
        current_job.save(
            update_fields=[
                "status",
                "result",
                "checkpoint",
                "lease_until",
                "last_error",
            ]
        )

    return outcome
