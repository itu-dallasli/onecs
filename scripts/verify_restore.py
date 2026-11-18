#!/usr/bin/env python3
"""Verify a consistent onecs PostgreSQL backup in a new disposable database."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from urllib.parse import unquote, urlparse
import uuid

import psycopg
from psycopg import sql

from dev import ROOT, RUNTIME, environment


def counts(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )
        tables = [row[0] for row in cursor.fetchall()]
        result = {}
        for table in tables:
            cursor.execute(
                sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
            )
            result[table] = cursor.fetchone()[0]
        return result


def main():
    env = environment()
    parsed = urlparse(env["DATABASE_URL"])
    if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit(
            "Bu doğrulayıcı yalnız yerel geliştirme PostgreSQL üzerinde çalışır."
        )
    source_name = parsed.path.lstrip("/")
    restore_name = "onecs_restore_" + uuid.uuid4().hex[:12]
    RUNTIME.mkdir(exist_ok=True)
    dump_file = RUNTIME / "onecs-verified-backup.dump"
    cli_env = dict(
        env,
        PGHOST=parsed.hostname,
        PGPORT=str(parsed.port or 5432),
        PGUSER=unquote(parsed.username or "onecs"),
        PGPASSWORD=unquote(parsed.password or ""),
    )
    pg_dump = shutil.which("pg_dump", path=env["PATH"])
    pg_restore = shutil.which("pg_restore", path=env["PATH"])
    if not pg_dump or not pg_restore:
        raise SystemExit("pg_dump ve pg_restore araçları gerekli.")
    started = dt.datetime.now(dt.timezone.utc)
    created = False
    admin_dsn = psycopg.conninfo.make_conninfo(env["DATABASE_URL"], dbname="postgres")
    restore_dsn = psycopg.conninfo.make_conninfo(
        env["DATABASE_URL"], dbname=restore_name
    )
    try:
        with psycopg.connect(env["DATABASE_URL"]) as source:
            source.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            snapshot = source.execute("SELECT pg_export_snapshot()").fetchone()[0]
            expected = counts(source)
            subprocess.run(
                [
                    pg_dump,
                    "-Fc",
                    "--no-owner",
                    "--snapshot",
                    snapshot,
                    "-f",
                    str(dump_file),
                    source_name,
                ],
                env=cli_env,
                check=True,
            )
        dump_file.chmod(0o600)
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restore_name))
            )
            created = True
        subprocess.run(
            [
                pg_restore,
                "--no-owner",
                "--exit-on-error",
                "--dbname",
                restore_name,
                str(dump_file),
            ],
            env=cli_env,
            check=True,
        )
        with psycopg.connect(restore_dsn) as restored:
            actual = counts(restored)
            if actual != expected:
                raise RuntimeError(
                    "Geri yüklenen tablo sayıları snapshot ile eşleşmiyor."
                )
            restored.execute("SET CONSTRAINTS ALL IMMEDIATE")
        elapsed = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
        report = {
            "status": "passed",
            "kind": "local_postgresql_restore",
            "at": started.isoformat(),
            "duration_seconds": round(elapsed, 3),
            "tables": len(actual),
            "rows": sum(actual.values()),
            "row_counts": actual,
            "checks": [
                "consistent_exported_snapshot",
                "pg_dump_custom_format",
                "restore_into_new_database",
                "all_table_counts_match",
                "foreign_keys_restored",
            ],
            "scope": "Sentetik yerel verinin geri yüklenmesi; kurumsal RPO/RTO ve dış secret deposunu doğrulamaz.",
        }
        artifact = ROOT / "tests" / "artifacts" / "restore-check.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            f"PASS: {len(actual)} tablo ve {sum(actual.values())} kayıt geri yüklenerek doğrulandı ({elapsed:.2f}s)."
        )
        print(f"Kanıt: {artifact}")
    finally:
        if created:
            with psycopg.connect(admin_dsn, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP DATABASE {}").format(sql.Identifier(restore_name))
                )


if __name__ == "__main__":
    main()
