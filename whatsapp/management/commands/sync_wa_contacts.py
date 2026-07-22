# Purpose: Cron wrapper for whatsapp.contacts.sync_contacts (WhatsAppContact directory refresh).
# Used by: crontab (daily); also runnable ad hoc via manage.py sync_wa_contacts.

from django.core.management.base import BaseCommand

from whatsapp.contacts import sync_contacts


class Command(BaseCommand):
    help = 'Sync the WhatsAppContact directory (phones, lids, names) from WAHA'

    def add_arguments(self, parser):
        parser.add_argument('--session', type=str, default=None)
        parser.add_argument('--quiet', action='store_true')

    def handle(self, *args, **opts):
        try:
            result = sync_contacts(session=opts['session'])
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'contact sync failed: {exc}'))
            raise SystemExit(1)
        if not opts['quiet']:
            self.stdout.write(self.style.SUCCESS(
                f"seen={result['seen']} created={result['created']} updated={result['updated']}"
            ))
