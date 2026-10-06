# Purpose: Backfill — copy each contact's WhatsApp labels onto our other numbers that also chat with them.
# Used by: run by hand: manage.py push_wa_chat_labels [--sessions default,Ezzy6000] [--labels Driver] [--phone 974…] [--apply].
# Notes: Dry run unless --apply. Adds only, never removes, and skips WhatsApp's own list filters (Unread/Favorites/Groups).
#        Every write goes through chat_labels.propagate(), the same push the inbox uses on save.

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from whatsapp import chat_labels, sessions as wa_sessions
from whatsapp.models import WhatsAppContact


class Command(BaseCommand):
    help = 'Copy labels between our WhatsApp numbers for contacts that chat with more than one of them'

    def add_arguments(self, parser):
        parser.add_argument('--sessions', help='Comma-separated WAHA sessions; default is every working number')
        parser.add_argument('--phone', help='Only this contact (digits, e.g. 97430664611)')
        parser.add_argument('--labels', help='Comma-separated label names to copy (Driver matches Drivers); default is all')
        parser.add_argument('--apply', action='store_true', help='Write to WhatsApp; without it nothing is changed')
        parser.add_argument('--no-refresh', action='store_true',
                            help='Skip re-reading the label mirror from WhatsApp first')

    def handle(self, *args, **options):
        live = [str(s.get('name') or '') for s in wa_sessions.list_sessions()
                if isinstance(s, dict) and str(s.get('status') or '') == 'WORKING']
        if options.get('sessions'):
            sessions = [s.strip() for s in options['sessions'].split(',') if s.strip()]
            bad = [s for s in sessions if not wa_sessions.is_valid(s) or s not in live]
            if bad:
                raise CommandError(f'Not a working session: {", ".join(bad)} (working: {", ".join(live)})')
        else:
            sessions = live
        if len(sessions) < 2:
            raise CommandError('Need at least two working sessions to copy labels between.')
        apply = options['apply']
        wanted = {chat_labels.norm(n) for n in (options.get('labels') or '').split(',') if n.strip()}

        # The plan is read from the mirror, so make it today's view of WhatsApp:
        # a label removed on a phone since the nightly sync must not be copied back.
        if not options['no_refresh']:
            for session in sessions:
                call_command('sync_wa_chat_labels', session=session, quiet=True)

        rows = WhatsAppContact.objects.filter(session__in=sessions)
        if options.get('phone'):
            rows = rows.filter(phone=options['phone'].strip())
        held = {}   # phone -> session -> {norm: label name}
        for session, phone, labels in rows.values_list('session', 'phone', 'labels'):
            names = {}
            for row in labels or []:
                name = str((row or {}).get('name') or '').strip() if isinstance(row, dict) else ''
                if (name and chat_labels.norm(name) not in chat_labels.LIST_FILTERS
                        and (not wanted or chat_labels.norm(name) in wanted)):
                    names.setdefault(chat_labels.norm(name), name)
            held.setdefault(phone, {})[session] = names

        own = {wa_sessions.sender_number(s): s for s in sessions}
        planned = copied = skipped = failed = 0
        for phone in sorted(held):
            by_session = {s: n for s, n in held[phone].items() if own.get(phone) != s}
            union = {}
            for names in by_session.values():
                for key, name in names.items():
                    union.setdefault(key, name)
            if len(by_session) < 2 or not union:
                continue
            for target, names in sorted(by_session.items()):
                missing = [k for k in union if k not in names]
                if not missing:
                    continue
                if not chat_labels.has_real_chat(target, phone):
                    skipped += 1
                    self.stdout.write(f'{phone}: {target} skipped, no conversation on that number')
                    continue
                planned += 1
                # Copy each name from a number that carries it, keeping its colour.
                by_source = {}
                for key in missing:
                    source = next(s for s in sorted(by_session) if key in by_session[s])
                    by_source.setdefault(source, []).append(by_session[source][key])
                if not apply:
                    plan = ', '.join(f'+{n} (from {s})' for s, ns in by_source.items() for n in ns)
                    self.stdout.write(f'{phone}: {target} would get {plan}')
                    continue
                for source, add in by_source.items():
                    for entry in chat_labels.propagate(source, f'{phone}@c.us', add, [],
                                                       actor='push_wa_chat_labels', only={target}):
                        if entry.get('error'):
                            failed += 1
                            self.stderr.write(f'{phone}: {target} {entry["error"]}')
                        elif entry.get('added'):
                            copied += 1
                            created = f' (created {", ".join(entry["created"])})' if entry.get('created') else ''
                            self.stdout.write(f'{phone}: {target} +{", +".join(entry["added"])}{created}')

        if apply:
            self.stdout.write(f'Done: {copied} label writes, {failed} failed, {skipped} skipped (no conversation).')
        else:
            self.stdout.write(f'Dry run: {planned} chats would change, {skipped} skipped (no conversation). '
                              'Re-run with --apply to write to WhatsApp.')
