#!/usr/bin/env python3
"""Prove QA fixture cleanup only on a new isolated local PostgreSQL clone."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main():
    import django

    django.setup()
    from django.conf import settings
    from core.models import Project

    cfg = settings.DATABASES["default"]
    if cfg["HOST"] not in {
        "127.0.0.1",
        "localhost",
        "::1",
    } or settings.ONECS_ENV not in {"development", "test", "demo"}:
        raise RuntimeError("Clone proof yalnız yerel nonproduction hedef içindir")
    pg_bin = Path("/opt/homebrew/opt/postgresql@17/bin")
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d_%H%M%S")
    clone = "onecs_cleanup_proof_" + timestamp
    if clone == cfg["NAME"]:
        raise RuntimeError("Clone ve canlı veritabanı aynı olamaz")
    env = dict(os.environ)
    if cfg.get("PASSWORD"):
        env["PGPASSWORD"] = cfg["PASSWORD"]
    flags = ["-h", str(cfg["HOST"]), "-p", str(cfg["PORT"]), "-U", str(cfg["USER"])]
    prefixes = [
        "QA-INSIGHTS-73f9c543b2",
        "QA-INSIGHTS-687ac5e41f",
        "QA-e3cc696020",
        "QA-7efa202cd3",
    ]
    prefix_flags = [part for prefix in prefixes for part in ("--run-prefix", prefix)]
    started = time.monotonic()
    live_before = Project.objects.filter(
        title__regex=r"^QA-(INSIGHTS-)?(73f9c543b2|687ac5e41f|e3cc696020|7efa202cd3) "
    ).count()
    if not live_before:
        raise RuntimeError("Exact QA kökü yok; boş veriyle cleanup proof üretilemez")
    log = runtime / f"cleanup-clone-proof-{timestamp}.log"

    def run(label, args, task_env=None):
        result = subprocess.run(
            args, cwd=ROOT, env=task_env or env, text=True, capture_output=True
        )
        with log.open("a") as stream:
            stream.write(f"{label}: exit={result.returncode}\n")
            stream.write(result.stdout)
            stream.write(result.stderr)
        if result.returncode:
            raise RuntimeError(
                f"Clone proof adımı başarısız: {label}; ayrıntı ignored runtime logunda"
            )

    source_dump = runtime / f"cleanup-proof-source-{timestamp}.dump"
    run(
        "source-readonly-dump",
        [
            str(pg_bin / "pg_dump"),
            *flags,
            "-Fc",
            "-f",
            str(source_dump),
            str(cfg["NAME"]),
        ],
    )
    run("create-new-isolated-database", [str(pg_bin / "createdb"), *flags, clone])
    run(
        "restore-isolated-clone",
        [
            str(pg_bin / "pg_restore"),
            *flags,
            "--no-owner",
            "--no-acl",
            "--exit-on-error",
            "-d",
            clone,
            str(source_dump),
        ],
    )
    clone_env = dict(env)
    userinfo = quote(str(cfg["USER"]), safe="")
    if cfg.get("PASSWORD"):
        userinfo += ":" + quote(cfg["PASSWORD"], safe="")
    clone_env["DATABASE_URL"] = (
        f"postgresql://{userinfo}@{cfg['HOST']}:{cfg['PORT']}/{clone}"
    )
    clone_env["ONECS_ENV"] = "test"
    preview = runtime / f"cleanup-clone-preview-{timestamp}.json"
    applied = runtime / f"cleanup-clone-applied-{timestamp}.json"
    after_path = runtime / f"cleanup-clone-after-{timestamp}.json"
    script = [sys.executable, "tests/cleanup_acceptance.py", *prefix_flags]
    run("clone-preview", [*script, "--output", str(preview)], clone_env)
    backup = runtime / f"cleanup-clone-before-apply-{timestamp}.dump"
    run(
        "clone-backup-after-preview",
        [str(pg_bin / "pg_dump"), *flags, "-Fc", "-f", str(backup), clone],
    )
    run(
        "clone-apply",
        [
            *script,
            "--apply",
            "--approved-plan",
            str(preview),
            "--backup-file",
            str(backup),
            "--output",
            str(applied),
        ],
        clone_env,
    )
    run("clone-after-preview", [*script, "--output", str(after_path)], clone_env)
    before = json.loads(preview.read_text())
    proof = json.loads(applied.read_text())
    after = json.loads(after_path.read_text())
    if (
        not proof["applied"]
        or after["counts"]
        or before["protected_state"] != after["protected_state"]
    ):
        raise RuntimeError("Clone apply/preserve eşleşmesi başarısız")
    live_after = Project.objects.filter(
        title__regex=r"^QA-(INSIGHTS-)?(73f9c543b2|687ac5e41f|e3cc696020|7efa202cd3) "
    ).count()
    if live_after != live_before:
        raise RuntimeError("Canlı exact QA kök sayısı değişti; proof durdu")
    artifact = {
        "operation": "exact-qa-cleanup-clone-proof",
        "at": dt.datetime.now(dt.UTC).isoformat(),
        "status": "passed",
        "scope": "new isolated local PostgreSQL clone only",
        "clone_database": clone,
        "duration_seconds": round(time.monotonic() - started, 3),
        "deleted_counts": before["counts"],
        "protected_models": len(before["protected_state"]),
        "all_protected_row_hashes_equal": True,
        "users_preserved": after["protected_state"]["core.user"]["count"],
        "non_qa_projects_preserved": after["protected_state"]["core.project"]["count"],
        "roles_preserved": after["protected_state"]["core.rolegrant"]["count"],
        "live_target_qa_projects_before": live_before,
        "live_target_qa_projects_after": live_after,
        "live_cleanup_applied": False,
        "clone_retained_for_review": True,
        "secrets_logged": False,
    }
    destination = ROOT / "tests/artifacts/cleanup-clone-proof.json"
    destination.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(artifact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
