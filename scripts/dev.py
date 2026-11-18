#!/usr/bin/env python3
"""Run Atlas's isolated local stack without changing another application's ports."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def environment():
    values = os.environ.copy()
    path = ROOT / ".env"
    if not path.exists():
        raise SystemExit(
            "Önce .env dosyasını .env.example temelinde oluşturun; README kurulum adımlarına bakın."
        )
    for line in path.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    for prefix in [
        "/opt/homebrew/opt/node@22/bin",
        "/opt/homebrew/opt/postgresql@17/bin",
    ]:
        if Path(prefix).exists():
            values["PATH"] = prefix + os.pathsep + values.get("PATH", "")
    return values


def execute(args, *, cwd=ROOT, env=None):
    subprocess.run([str(a) for a in args], cwd=cwd, env=env, check=True)


def port_open(port):
    with socket.socket() as conn:
        conn.settimeout(0.2)
        return conn.connect_ex(("127.0.0.1", port)) == 0


def local_postgres(env):
    port = int(env.get("POSTGRES_PORT", "55432"))
    if env.get("POSTGRES_HOST", "127.0.0.1") not in {"127.0.0.1", "localhost"}:
        return
    if port_open(port):
        return
    pg_ctl = shutil.which("pg_ctl", path=env["PATH"])
    initdb = shutil.which("initdb", path=env["PATH"])
    createdb = shutil.which("createdb", path=env["PATH"])
    if not (pg_ctl and initdb and createdb):
        raise SystemExit(
            "PostgreSQL başlatılmadı. PostgreSQL 17 kurun veya compose ile veritabanını başlatın."
        )
    RUNTIME.mkdir(exist_ok=True)
    data = RUNTIME / "postgres"
    user = env.get("POSTGRES_USER", "atlas")
    if not (data / "PG_VERSION").exists():
        execute(
            [
                initdb,
                "-D",
                data,
                "-U",
                user,
                "-A",
                "trust",
                "--encoding=UTF8",
                "--locale=C",
            ],
            env=env,
        )
    execute(
        [
            pg_ctl,
            "-D",
            data,
            "-l",
            RUNTIME / "postgres.log",
            "-o",
            f"-p {port} -h 127.0.0.1",
            "start",
        ],
        env=env,
    )
    # This isolated development cluster accepts loopback connections only.
    result = subprocess.run(
        [
            createdb,
            "-h",
            "127.0.0.1",
            "-p",
            str(port),
            "-U",
            user,
            env.get("POSTGRES_DB", "atlas"),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode and "already exists" not in result.stderr:
        raise SystemExit(result.stderr)


def main():
    parser = argparse.ArgumentParser(description="Atlas yerel geliştirme yöneticisi")
    parser.add_argument(
        "--check", action="store_true", help="Django kontrolünü çalıştır ve çık"
    )
    parser.add_argument(
        "--seed", action="store_true", help="Sentetik demo verilerini oluştur/güncelle"
    )
    args = parser.parse_args()
    env = environment()
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        raise SystemExit(
            "Önce python3 -m venv .venv ve .venv/bin/pip install -r requirements.lock.txt çalıştırın."
        )
    local_postgres(env)
    execute(
        [python, "manage.py", "migrate", "--noinput"], cwd=ROOT / "backend", env=env
    )
    if args.seed:
        execute([python, "manage.py", "seed_demo"], cwd=ROOT / "backend", env=env)
    execute([python, "manage.py", "check"], cwd=ROOT / "backend", env=env)
    if args.check:
        return
    if port_open(8000) or port_open(3100):
        raise SystemExit(
            "8000 veya 3100 portu kullanılıyor. Çalışan Atlas sürecini kullanın veya önce durdurun."
        )
    npm = shutil.which("npm", path=env["PATH"])
    if not npm:
        raise SystemExit("Node.js 22.12+ ve npm gerekli.")
    commands = [
        (
            "API",
            [python, "manage.py", "runserver", "127.0.0.1:8000", "--noreload"],
            ROOT / "backend",
        ),
        ("Worker", [python, "manage.py", "runworker"], ROOT / "backend"),
        (
            "Frontend",
            [
                npm,
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "3100",
                "--strictPort",
            ],
            ROOT / "frontend",
        ),
    ]
    processes = []

    def stop(*_):
        for _, proc in processes:
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for name, command, cwd in commands:
            proc = subprocess.Popen([str(a) for a in command], cwd=cwd, env=env)
            processes.append((name, proc))
        print(
            "\nAtlas: http://localhost:3100 · API: http://127.0.0.1:8000/api/v1/\n",
            flush=True,
        )
        while all(proc.poll() is None for _, proc in processes):
            time.sleep(0.5)
        for name, proc in processes:
            if proc.poll() is not None and proc.returncode:
                print(
                    f"{name} beklenmedik biçimde durdu ({proc.returncode}). Kalan süreçler kapatılıyor.",
                    file=sys.stderr,
                )
                raise SystemExit(proc.returncode)
    finally:
        stop()
        for _, proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
