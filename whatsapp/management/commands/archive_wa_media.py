# Purpose: Cron wrapper for whatsapp.media_archive.archive_pending_media (WAHA media → Django storage).
# Used by: crontab (every minute); also runnable ad hoc via manage.py archive_wa_media.
# Notes: Must run frequently — WAHA purges its media copies ~3 minutes after download.

from django.core.management.base import BaseCommand

from whatsapp.media_archive import archive_pending_media


class Command(BaseCommand):
    help = 'Download pending WAHA media files into local Django storage'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=25)
        parser.add_argument('--quiet', action='store_true')

    def handle(self, *args, **opts):
        counts = archive_pending_media(limit=opts['limit'])
        if not opts['quiet'] or counts['saved'] or counts['failed']:
            self.stdout.write(
                f"saved={counts['saved']} skipped={counts['skipped']} failed={counts['failed']}"
            )
