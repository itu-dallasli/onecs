"""Run private quarantined files through the configured isolated scanner."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.attachments import scan_pending_attachments


class Command(BaseCommand):
    help = "Bekleyen dosyaları yapılandırılmış tarayıcıyla sınırlı partiler halinde tarar."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100:
            raise CommandError("Parti boyutu 1–100 arasında olmalıdır.")
        if not settings.ONECS_UPLOAD_SCANNER_COMMAND:
            raise CommandError("Önce ONECS_UPLOAD_SCANNER_COMMAND yapılandırılmalıdır.")
        result = scan_pending_attachments(options["limit"])
        self.stdout.write(
            f"Taranan: {result['processed']}; hazır: {result['ready']}; reddedilen: {result['rejected']}; bekleyen: {result['pending']}."
        )
