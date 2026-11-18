#!/usr/bin/env python3
"""Preview exact local QA ownership roots; apply only after review and a later backup."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def matches(value, ids, prefixes):
    if isinstance(value, dict):
        return any(matches(v, ids, prefixes) for v in value.values())
    if isinstance(value, list):
        return any(matches(v, ids, prefixes) for v in value)
    return isinstance(value, str) and (
        value in ids or any(value.startswith(p + " ") for p in prefixes)
    )


def protected_state(selected):
    """Hash values locally; never emit config, secret ciphertext or business rows."""
    from django.apps import apps

    labels = [
        "core.User",
        "core.RoleGrant",
        "core.OrgNode",
        "core.PMAppointment",
        "core.SLAPolicy",
        "core.Project",
        "core.ProjectRevision",
        "core.ProjectMembership",
        "core.ProjectAuthorityGrant",
        "core.ProjectTeamPlan",
        "core.ProjectDeliverable",
        "core.ProjectProgressSnapshot",
        "core.ProjectClosureSurvey",
        "core.ProjectSurveyResponse",
        "core.ProjectInsightReport",
        "core.ProjectInsightEdit",
        "core.ParticipationRequest",
        "core.WorkItem",
        "core.Case",
        "core.Report",
        "core.BackgroundJob",
        "core.IdempotencyRecord",
        "administration.IntegrationConfiguration",
        "administration.ConfigurationVersion",
        "administration.AIConnectionProfile",
        "administration.AIUsage",
        "administration.LDAPIdentity",
        "administration.LDAPImportBatch",
    ]
    result = {}
    for label in labels:
        model = apps.get_model(label)
        digest = hashlib.sha256()
        count = 0
        for row in (
            model._default_manager.exclude(pk__in=selected.get(model, set()))
            .order_by("pk")
            .values()
            .iterator()
        ):
            digest.update(json.dumps(row, sort_keys=True, default=str).encode())
            digest.update(b"\n")
            count += 1
        result[model._meta.label_lower] = {"count": count, "sha256": digest.hexdigest()}
    return result


def build_plan(prefixes):
    from django.apps import apps
    from django.db.models import Q

    models = list(apps.get_models(include_auto_created=True))
    selected = defaultdict(set)
    blockers = []
    roots = {}

    def add(label, query):
        model = apps.get_model(label)
        selected[model].update(
            model._default_manager.filter(query).values_list("pk", flat=True)
        )
        return selected[model]

    def ids(label):
        return selected[apps.get_model(label)]

    for label, field in {
        "core.Project": "title",
        "core.WorkItem": "title",
        "core.Case": "title",
        "core.CaseNotice": "title",
        "core.Announcement": "title",
        "core.CommunityCard": "title",
        "core.Event": "title",
        "core.Credential": "name",
        "core.Report": "title",
        "core.ApiClient": "name",
        "administration.AIConnectionProfile": "name",
    }.items():
        query = Q(pk__in=[])
        for prefix in prefixes:
            query |= Q(**{field + "__startswith": prefix + " "})
        add(label, query)
        roots[label.lower()] = len(ids(label))

    # Only declared ownership edges extend a root. Actor, recipient, grantor,
    # created_by and arbitrary reverse PROTECT relations NEVER extend selection.
    for label in (
        "core.ProjectRevision",
        "core.ProjectMembership",
        "core.ProjectAuthorityGrant",
        "core.ProjectTeamPlan",
        "core.ProjectProgressSnapshot",
        "core.ProjectClosureSurvey",
        "core.ProjectInsightReport",
    ):
        add(label, Q(project_id__in=ids("core.Project")))
    add("core.ProjectDeliverable", Q(plan_id__in=ids("core.ProjectTeamPlan")))
    add("core.ProjectSurveyResponse", Q(survey_id__in=ids("core.ProjectClosureSurvey")))
    add("core.ProjectInsightEdit", Q(report_id__in=ids("core.ProjectInsightReport")))
    add(
        "core.ParticipationRequest",
        Q(project_id__in=ids("core.Project")) | Q(case_id__in=ids("core.Case")),
    )
    add(
        "core.ProgressEntry",
        Q(project_id__in=ids("core.Project"))
        | Q(work_id__in=ids("core.WorkItem"))
        | Q(case_id__in=ids("core.Case")),
    )
    add(
        "core.SLAInstance",
        Q(work_id__in=ids("core.WorkItem")) | Q(case_id__in=ids("core.Case")),
    )
    add("core.SLAEvent", Q(sla_id__in=ids("core.SLAInstance")))
    for label in ("core.EventRSVP", "core.EventAttendance", "core.Poll"):
        add(label, Q(event_id__in=ids("core.Event")))
    add("core.PollResponse", Q(poll_id__in=ids("core.Poll")))

    for label, parents in {
        "core.WorkItem": {
            "project_id": "core.Project",
            "case_id": "core.Case",
            "parent_id": "core.WorkItem",
        },
        "core.CaseNotice": {"case_id": "core.Case"},
        "core.ProgressEntry": {
            "project_id": "core.Project",
            "case_id": "core.Case",
            "work_id": "core.WorkItem",
        },
        "core.ParticipationRequest": {
            "project_id": "core.Project",
            "case_id": "core.Case",
        },
        "core.SLAInstance": {"work_id": "core.WorkItem", "case_id": "core.Case"},
    }.items():
        model = apps.get_model(label)
        for row in model.objects.filter(pk__in=ids(label)).values("pk", *parents):
            for field, parent_label in parents.items():
                if row[field] is not None and row[field] not in ids(parent_label):
                    blockers.append(
                        f"QA kökü dış hedefe bağlı: {label}:{row['pk']}:{field}"
                    )

    # Background jobs must be directly and exclusively bound to target reports.
    jobs = apps.get_model("core.BackgroundJob")
    for label, kind in (
        ("core.Report", "REPORT"),
        ("core.ProjectInsightReport", "PROJECT_INSIGHT"),
    ):
        model = apps.get_model(label)
        for report in model.objects.filter(pk__in=ids(label)).only("pk", "job_id"):
            if report.job_id:
                job = jobs.objects.get(pk=report.job_id)
                if job.kind != kind or str(job.payload.get("report_id")) != str(
                    report.pk
                ):
                    blockers.append("QA raporunun job bağlamı uyuşmuyor")
                else:
                    selected[jobs].add(job.pk)
    if jobs.objects.filter(pk__in=selected[jobs], status="RUNNING").exists():
        blockers.append("RUNNING QA job var; worker/recovery koordinasyonu gerekli")

    profiles = apps.get_model("administration.AIConnectionProfile")
    configs = apps.get_model("administration.IntegrationConfiguration")
    for profile in profiles.objects.filter(pk__in=selected[profiles]).select_related(
        "configuration"
    ):
        if profile.active or profile.configuration.section in {
            "ai",
            "ldap",
            "smtp",
            "teams",
            "general",
        }:
            blockers.append("Etkin veya ortak ayar kullanan QA profili korunuyor")
        else:
            selected[configs].add(profile.configuration_id)
    add(
        "administration.ConfigurationVersion", Q(configuration_id__in=selected[configs])
    )
    add("administration.IntegrationTest", Q(configuration_id__in=selected[configs]))
    profile_ids = set(map(str, selected[profiles]))
    versions = apps.get_model("administration.ConfigurationVersion")
    for config in versions.objects.exclude(pk__in=selected[versions]).values_list(
        "config", flat=True
    ):
        if matches(config, profile_ids, set()):
            blockers.append("QA profiline non-QA ayar sürümünden JSON referansı var")
    clients = apps.get_model("core.ApiClient")
    if clients.objects.filter(pk__in=selected[clients], active=True).exists():
        blockers.append("Etkin QA API istemcisi önce iptal edilmeli")

    resource_models = {
        "project": "core.Project",
        "work": "core.WorkItem",
        "case": "core.Case",
        "participation": "core.ParticipationRequest",
        "event": "core.Event",
        "community": "core.CommunityCard",
        "announcement": "core.Announcement",
        "credential": "core.Credential",
    }
    for label in ("core.Notification", "core.OutboxEvent"):
        query = Q(pk__in=[])
        for resource_type, target in resource_models.items():
            query |= Q(
                resource_type=resource_type, resource_id__in=list(map(str, ids(target)))
            )
        add(label, query)
    query = Q(pk__in=[])
    for resource_type, target in (
        ("project", "core.Project"),
        ("work", "core.WorkItem"),
        ("case", "core.Case"),
    ):
        query |= Q(source_type=resource_type, source_id__in=ids(target))
    add("core.ReportSelection", query)
    query = Q(pk__in=[])
    for model, rows in list(selected.items()):
        query |= Q(object_type=model.__name__, object_id__in=list(map(str, rows)))
    add("core.AuditEvent", query)

    # Automatically created through tables are ownership children. This is the
    # only metadata traversal that selects rows; real model FKs below only block.
    for model in models:
        if not model._meta.auto_created:
            continue
        for field in model._meta.fields:
            parent = getattr(field.remote_field, "model", None)
            if parent and selected.get(parent):
                selected[model].update(
                    model._default_manager.filter(
                        **{field.attname + "__in": selected[parent]}
                    ).values_list("pk", flat=True)
                )
    selected = {model: rows for model, rows in selected.items() if rows}
    for model in models:
        for field in model._meta.fields:
            parent = getattr(field.remote_field, "model", None)
            if parent and selected.get(parent):
                outside = model._default_manager.filter(
                    **{field.attname + "__in": selected[parent]}
                ).exclude(pk__in=selected.get(model, set()))
                count = outside.count()
                if count:
                    blockers.append(
                        f"Silme kapsamı dışı ters FK: {model._meta.label_lower}.{field.name} ({count})"
                    )
    forbidden = {
        "core.user",
        "core.rolegrant",
        "core.orgnode",
        "core.pmappointment",
        "core.slapolicy",
        "administration.aiusage",
        "administration.ldapidentity",
        "administration.ldapmanagedgrant",
        "administration.ldapimportbatch",
    }
    for model in selected:
        if model._meta.label_lower in forbidden:
            blockers.append(
                "Korunan model seçimi engellendi: " + model._meta.label_lower
            )
    order = []
    pending = set(selected)
    while pending:
        ready = [
            model
            for model in pending
            if not any(
                child != model
                and any(
                    getattr(f.remote_field, "model", None) == model
                    for f in child._meta.fields
                )
                for child in pending
            )
        ]
        if not ready:
            blockers.append("Modeller arası FK döngüsü")
            break
        ready.sort(key=lambda model: model._meta.label_lower)
        order.extend(ready)
        pending -= set(ready)
    plan = {
        "ownership_version": 2,
        "run_prefixes": sorted(prefixes),
        "roots": roots,
        "counts": {
            m._meta.label_lower: len(rows)
            for m, rows in sorted(
                selected.items(), key=lambda pair: pair[0]._meta.label_lower
            )
        },
        "objects": {
            m._meta.label_lower: sorted(map(str, rows)) for m, rows in selected.items()
        },
        "delete_order": [m._meta.label_lower for m in order],
        "blockers": sorted(set(blockers)),
        "protected_state": protected_state(selected),
    }
    plan["plan_sha256"] = hashlib.sha256(
        json.dumps(plan, sort_keys=True).encode()
    ).hexdigest()
    return plan, selected, order


def delete_owned(model, rows):
    self_fields = [
        field.attname
        for field in model._meta.fields
        if getattr(field.remote_field, "model", None) == model
    ]
    if not self_fields:
        model._default_manager.filter(pk__in=rows).delete()
        return
    # Self-PROTECT chains include both WorkItem.parent and progress revision
    # history. Django's bulk Collector cannot delete those ancestors together.
    remaining = set(rows)
    while remaining:
        parents = set()
        for field in self_fields:
            parents.update(
                model._default_manager.filter(
                    **{field + "__in": remaining}
                ).values_list(field, flat=True)
            )
        leaves = remaining - parents
        if not leaves:
            raise RuntimeError("Self-FK döngüsü; transaction geri alınacak")
        model._default_manager.filter(pk__in=leaves).delete()
        remaining -= leaves


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-prefix", action="append", required=True)
    parser.add_argument("--output", default=".runtime/cleanup-preview.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-plan")
    parser.add_argument("--backup-file")
    args = parser.parse_args()
    if any(
        not re.fullmatch(r"QA-(?:INSIGHTS-)?[a-f0-9]{10}", p) for p in args.run_prefix
    ):
        parser.error("Yalnız exact 10-hex QA run öneki kabul edilir")
    import django

    django.setup()
    from django.conf import settings
    from django.db import transaction

    database = settings.DATABASES["default"]
    if settings.ATLAS_ENV not in {"development", "test", "demo"} or database[
        "HOST"
    ] not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Yalnız yerel development/test/demo veritabanı kullanılabilir")
    if args.apply and (not args.approved_plan or not args.backup_file):
        parser.error("--apply için --approved-plan ve --backup-file zorunlu")
    with transaction.atomic():
        plan, selected, order = build_plan(set(args.run_prefix))
        plan["preview_at_utc"] = dt.datetime.now(dt.UTC).isoformat()
        plan["applied"] = False
        if args.apply:
            approved = json.loads(Path(args.approved_plan).read_text())
            backup = Path(args.backup_file).resolve()
            if (
                not backup.is_file()
                or not backup.stat().st_size
                or backup.stat().st_mtime
                < dt.datetime.fromisoformat(approved["preview_at_utc"]).timestamp()
            ):
                parser.error("Onaylı preview'den sonra alınmış dolu backup gerekir")
            with backup.open("rb") as dump:
                if dump.read(5) != b"PGDMP":
                    parser.error("Backup PostgreSQL custom dump (PGDMP) olmalıdır")
            if approved["plan_sha256"] != plan["plan_sha256"] or plan["blockers"]:
                parser.error("Onaylı ownership planı değişmiş veya blocker var")
            for model, rows in selected.items():
                list(
                    model._default_manager.select_for_update()
                    .filter(pk__in=rows)
                    .values_list("pk", flat=True)
                )
            check, _, _ = build_plan(set(args.run_prefix))
            if check["plan_sha256"] != plan["plan_sha256"]:
                parser.error("Kilit sırasında kapsam veya korunan kayıt değişti")
            for model in order:
                delete_owned(model, selected[model])
            if protected_state(selected) != plan["protected_state"]:
                raise RuntimeError("Korunan veri değişti; transaction geri alınacak")
            plan["applied"] = True
            plan["backup_verified_nonempty"] = True
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {k: plan[k] for k in ("counts", "blockers", "plan_sha256", "applied")},
            ensure_ascii=False,
        )
    )
    return 1 if plan["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
