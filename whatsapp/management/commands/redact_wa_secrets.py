# Purpose: One-off/rerunnable sweep that strips one-time codes out of WhatsAppMessage rows already stored before redaction was added at ingest.
# Used by: `python manage.py redact_wa_secrets [--dry-run]`; safe to re-run, and worth re-running after any bulk backfill.
# Notes: Rewrites body AND raw_payload in place — the code is unrecoverable afterwards, which is the point. Ingest-time redaction lives in whatsapp/secrets.py.

from django.core.management.base import BaseCommand

from whatsapp.models import WhatsAppMessage
from whatsapp.secrets import _first_text, looks_like_secret, redact_payload, redact_text


class Command(BaseCommand):
    help = 'Strip stored one-time codes (password reset / OTP) out of WhatsApp messages.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing.')
        parser.add_argument('--quiet', action='store_true')

    def handle(self, *args, **options):
        dry = options['dry_run']
        quiet = options['quiet']

        # Narrow with a cheap DB filter first, then confirm in Python — the regex
        # context check is what decides, so the filter only has to be a superset.
        candidates = WhatsAppMessage.objects.filter(
            body__iregex=r'(verification code|password reset|reset code|one.time (password|code|pin)|OTP|security code|login code|confirmation code)'
        ).only('id', 'body', 'raw_payload')

        checked = changed = 0
        for msg in candidates.iterator(chunk_size=200):
            checked += 1
            # Gate on the payload as well as the body: a row whose body was already
            # cleaned but whose payload still holds the code would otherwise be
            # invisible here, because the body no longer looks like a secret.
            payload_text = _first_text(msg.raw_payload)
            if not (looks_like_secret(msg.body) or looks_like_secret(payload_text)):
                continue
            new_body, body_changed = redact_text(msg.body)
            new_payload, payload_changed = redact_payload(
                msg.raw_payload, msg.body if looks_like_secret(msg.body) else payload_text)
            if not (body_changed or payload_changed):
                continue
            changed += 1
            if not quiet:
                self.stdout.write(f'  msg {msg.pk}: redacting code')
            if not dry:
                msg.body = new_body
                msg.raw_payload = new_payload
                msg.save(update_fields=['body', 'raw_payload'])

        verb = 'would redact' if dry else 'redacted'
        if not quiet:
            self.stdout.write(self.style.SUCCESS(
                f'Checked {checked} candidate message(s); {verb} {changed}.'
            ))
