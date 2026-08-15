# Purpose: Cron wrapper for whatsapp.contacts.sync_contacts (WhatsAppContact directory refresh).
# Used by: crontab (daily); also runnable ad hoc via manage.py sync_wa_contacts.
# Notes: With no --session it syncs EVERY linked WhatsApp number, so adding a session needs no crontab edit.

from django.core.management.base import BaseCommand

from whatsapp import sessions as wa_sessions
from whatsapp.contacts import sync_contacts


class Command(BaseCommand):
    help = 'Sync the WhatsAppContact directory (phones, lids, names) from WAHA'

    def add_arguments(self, parser):
        parser.add_argument('--session', type=str, default=None,
                            help='One WAHA session. Omit to sync every linked number.')
        parser.add_argument('--quiet', action='store_true')

    def handle(self, *args, **opts):
        if opts['session']:
            names = [wa_sessions.normalize(opts['session'])]
        else:
            names = [s['name'] for s in wa_sessions.list_sessions()]

        failures = 0
        for name in names:
            try:
                result = sync_contacts(session=name)
            except Exception as exc:
                failures += 1
                # Keep going: one unreachable number must not stop the others.
                self.stderr.write(self.style.ERROR(f'[{name}] contact sync failed: {exc}'))
                continue
            if not opts['quiet']:
                self.stdout.write(self.style.SUCCESS(
                    f"[{name}] seen={result['seen']} created={result['created']} "
                    f"updated={result['updated']}"
                ))
        if failures == len(names):
            raise SystemExit(1)
