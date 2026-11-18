import signal
import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from core.worker import run_tick


class Command(BaseCommand):
    help = "Atlas kalıcı iş, SLA ve bildirim workerı."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=2)

    def handle(self, *args, **options):
        running = True

        def stop(*_):
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        while running:
            close_old_connections()
            try:
                run_tick()
            except Exception:
                if options["once"]:
                    raise
                self.stderr.write(
                    "Atlas worker: geçici işlem hatası; sonraki turda yeniden denenecek."
                )
            if options["once"]:
                break
            deadline = time.monotonic() + max(0.2, options["interval"])
            while running and time.monotonic() < deadline:
                time.sleep(0.1)
