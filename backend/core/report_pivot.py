"""Read-only, source-bound team views of a management report snapshot."""

from copy import deepcopy
from datetime import datetime, time
from uuid import UUID

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import PermissionDenied

from .policy import report_source


SECTIONS = (
    ("highlights", "Öne çıkanlar"),
    ("lowlights", "Aksayan konular"),
    ("escalations", "Uyarılar ve karar bekleyenler"),
    ("information", "Bilgi ve projeler"),
    ("next_steps", "Sonraki adımlar"),
)
COMPLETED = {"COMPLETED", "CLOSED"}
TERMINAL = COMPLETED | {"CANCELLED", "REJECTED"}


def _due_before(source, cutoff):
    value = source.get("due_at")
    if not isinstance(value, str) or not value:
        return False
    try:
        due = parse_datetime(value)
        if due is None:
            day = parse_date(value)
            due = datetime.combine(day, time.min) if day else None
    except ValueError:
        return False
    if due is None:
        return False
    if timezone.is_naive(due):
        due = timezone.make_aware(due, timezone.get_default_timezone())
    return due <= cutoff


def _signals(source, cutoff):
    status = source.get("status")
    completed = status in COMPLETED
    active = status not in TERMINAL
    critical = active and source.get("priority") == "CRITICAL"
    overdue = active and _due_before(source, cutoff)
    if completed:
        section = "highlights"
    elif critical or status in {"SUBMITTED", "VERIFYING"}:
        section = "escalations"
    elif overdue or status in {"WAITING", "BLOCKED", "CANCELLED", "REJECTED"}:
        section = "lowlights"
    else:
        section = "information"
    return section, {
        "open": int(active),
        "completed": int(completed),
        "critical": int(critical),
        "overdue": int(overdue),
    }


def _snapshot_org(source):
    org = source.get("owner_org")
    if not isinstance(org, dict):
        return None
    try:
        org_id = str(UUID(str(org.get("id", ""))))
    except (ValueError, TypeError, AttributeError):
        return None
    if not isinstance(org.get("name"), str) or not isinstance(org.get("code"), str):
        return None
    return {"id": org_id, "name": org["name"], "code": org["code"]}


def _team(actor, source):
    frozen = _snapshot_org(source)
    if frozen is not None:
        return frozen, "snapshot"
    # Old reports predate team metadata. Resolve only a currently authorized
    # source; do not query the org directory independently or modify the report.
    current = report_source(actor, source["type"], source["id"])
    if current is None:
        raise PermissionDenied("Rapordaki kaynağa erişiminiz kaldırıldı.")
    org = getattr(current, "owner_org", None)
    if org is None:
        return {"id": None, "name": "Ekip bilgisi yok", "code": ""}, "unassigned"
    return {"id": str(org.pk), "name": org.name, "code": org.code}, "current_authorized"


def _provenance(values):
    unique = set(values)
    return next(iter(unique)) if len(unique) == 1 else "mixed" if unique else "empty"


def _summary(rows):
    sources = [row[0] for row in rows]
    return {
        "source_count": len(sources),
        "counts": {
            name: sum(row[1][name] for row in rows)
            for name in ("open", "completed", "critical", "overdue")
        },
        "sections": [
            {
                "key": key,
                "title": title,
                "count": sum(source["section"] == key for source in sources),
                "sources": [source for source in sources if source["section"] == key],
            }
            for key, title in SECTIONS
        ],
    }


def build_report_pivot(report, actor):
    """Derive team rows from frozen content; never generate or save a report."""
    cutoff = timezone.make_aware(
        datetime.combine(report.period_end, time.max),
        timezone.get_default_timezone(),
    )
    unique_sources = {}
    for source in report.sources:
        key = (source["type"], str(source["id"]))
        unique_sources.setdefault(key, source)
    ordered = sorted(
        unique_sources.values(),
        key=lambda source: (
            str(source.get("title", "")).casefold(),
            source["type"],
            str(source["id"]),
        ),
    )
    rows = []
    groups = {}
    provenances = []
    for original in ordered:
        source = deepcopy(original)
        team, provenance = _team(actor, source)
        section, counts = _signals(source, cutoff)
        source.update({"team_id": team["id"], "section": section})
        row = (source, counts)
        rows.append(row)
        provenances.append(provenance)
        group = groups.setdefault(
            team["id"], {"metadata": [], "rows": [], "provenances": []}
        )
        group["metadata"].append((provenance, team))
        group["rows"].append(row)
        group["provenances"].append(provenance)
    teams = []
    for group in groups.values():
        # Frozen labels take precedence when an old and a new snapshot share
        # an org ID; ties are deterministic even if input order changes.
        _, team = min(
            group["metadata"],
            key=lambda item: (
                item[0] != "snapshot",
                item[1]["name"].casefold(),
                item[1]["code"],
            ),
        )
        teams.append(
            {
                **team,
                "metadata_provenance": _provenance(group["provenances"]),
                **_summary(group["rows"]),
                "sources": [row[0] for row in group["rows"]],
            }
        )
    teams.sort(
        key=lambda team: (team["name"].casefold(), team["code"], team["id"] or "")
    )
    return {
        "report_id": str(report.pk),
        "report_version": report.version,
        "content_hash": report.content_hash,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "as_of": report.period_end.isoformat(),
        "source_count": len(rows),
        "metadata_provenance": _provenance(provenances),
        "section_order": [key for key, _ in SECTIONS],
        "general": _summary(rows),
        "teams": teams,
    }
