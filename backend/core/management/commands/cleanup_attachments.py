"""Expire abandoned staged uploads; default mode previews counts only."""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.attachments import purge_deleted_file
from core.models import Attachment
from core.services import audit


class Command(BaseCommand):
    help = "İlişkisiz eski yüklemeleri temizler. Varsayılan yalnız önizlemedir."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        if options["hours"] < 1:
            raise CommandError("En az 1 saat saklama süresi gerekir.")
        cutoff = timezone.now() - timedelta(hours=options["hours"])
        eligible = Q(status="DELETED", purged_at__isnull=True) | Q(resource_id__isnull=True, created_at__lt=cutoff, purged_at__isnull=True)
        candidates = Attachment.objects.filter(eligible)
        if not options["apply"]:
            self.stdout.write(f"Önizleme: {candidates.count()} ilişkisiz/silinmiş dosya; bağlı etkin dosyalar korunur.")
            return
        removed = 0
        # Recheck under row locks so a concurrent domain claim cannot be deleted.
        for item_id in candidates.values_list("id", flat=True).iterator():
            with transaction.atomic():
                item = Attachment.objects.select_for_update().filter(pk=item_id).filter(eligible).first()
                if item is None:
                    continue
                item.status = "DELETED"
                item.version += 1
                item.save(update_fields=["status", "version", "updated_at"])
                audit(None, "attachment.cleanup", item)
            # Retain the tombstone if unlink fails; the next cleanup retries it.
            purge_deleted_file(item.pk, item.storage_key)
            removed += 1
        self.stdout.write(f"Temizlenen dosya: {removed}. Bağlı etkin dosyalar korundu.")
