# Purpose: Refresh the WhatsAppContact label mirror from WhatsApp — one pass per number, label by label.
# Used by: crontab (nightly); also runnable ad hoc via manage.py sync_wa_chat_labels [--session X] [--dry-run].
# Notes: Reconcile only — it never writes to WhatsApp, so a label removed on a phone is dropped here too.
#        Group chats and lids we have never synced have no contact row and are counted as skipped.

from django.core.management.base import BaseCommand
from django.utils import timezone

from whatsapp import chat_labels, sessions as wa_sessions
from whatsapp.models import WhatsAppContact


class Command(BaseCommand):
    help = 'Mirror every chat\'s WhatsApp labels onto its WhatsAppContact row'

    def add_arguments(self, parser):
        parser.add_argument('--session', help='One WAHA session; default is every linked number')
        parser.add_argument('--dry-run', action='store_true', help='Report only, write nothing')
        parser.add_argument('--quiet', action='store_true', help='Only print warnings and errors')

    def handle(self, *args, **options):
        quiet, dry = options['quiet'], options['dry_run']
        if options.get('session'):
            targets = [options['session']]
        else:
            targets = [str(s.get('name') or '') for s in wa_sessions.list_sessions()
                       if isinstance(s, dict) and s.get('name')]
        for session in targets:
            self._one(session, quiet=quiet, dry=dry)

    def _one(self, session, quiet, dry):
        labels = chat_labels.session_labels(session)
        if labels is None:
            self.stderr.write(f'{session}: could not read its labels from WhatsApp')
            return
        from whatsapp import label_access

        # chat id -> [label row], built from the cheap per-label listing rather
        # than asking for each chat's labels one by one.
        by_chat = {}
        for label in labels:
            if not isinstance(label, dict) or label.get('id') is None:
                continue
            chats = label_access.label_chats(session, str(label['id']))
            if chats is None:
                self.stderr.write(f'{session}: could not list chats for label {label.get("name")!r}')
                continue
            for chat_id in chats:
                by_chat.setdefault(chat_id, []).append(label)

        stored = skipped = 0
        seen_phones = set()
        for chat_id, rows in by_chat.items():
            phone = chat_labels.chat_phone(session, chat_id)
            if not phone:
                skipped += 1
                continue
            seen_phones.add(phone)
            if not dry and chat_labels.store(session, chat_id, rows, phone=phone):
                stored += 1
            elif dry:
                stored += 1

        # A label taken off a chat on the phone leaves no trace in the listings
        # above, so anything we hold but no longer see is cleared.
        stale = WhatsAppContact.objects.filter(session=session).exclude(labels=[]).exclude(phone__in=seen_phones)
        cleared = stale.count()
        if cleared and not dry:
            stale.update(labels=[], labels_synced_at=timezone.now())
        if not quiet:
            self.stdout.write(
                f'{session}: {stored} contacts labelled, {cleared} cleared, {skipped} chats without a contact'
                + (' (dry run)' if dry else ''))
