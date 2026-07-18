# Purpose: Daily cron command — WhatsApp digest of due/overdue CRM lead follow-ups, one message per assigned staff (unassigned go to admin).
# Used by: system crontab (daily 08:00 Asia/Qatar); mirrors the flush_autoflow_digests cron pattern since this server uses cron, not Celery beat.
# Notes: Read-only over leads — safe to re-run; --dry-run lists recipients without sending.

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ('Send a WhatsApp digest of due/overdue CRM lead follow-ups to each '
            'assigned staff member. Unassigned due leads go to the admin number.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet', action='store_true',
            help='Suppress output unless a digest was sent or an error occurred.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List recipients and lead counts without sending anything.',
        )

    def handle(self, *args, **options):
        from crm.services import send_followup_digests

        result = send_followup_digests(dry_run=options['dry_run'])
        sent = result.get('sent', 0)
        skipped = result.get('skipped', 0)
        errors = result.get('errors', [])
        recipients = result.get('recipients', [])

        if options['quiet'] and not sent and not errors:
            return

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(f'{prefix}Sent {sent} digest(s), skipped {skipped}.')
        for line in recipients:
            self.stdout.write(f'  {line}')
        for err in errors:
            self.stderr.write(f'ERROR: {err}')
