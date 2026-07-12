"""
Purpose: Cron-driven trailing-edge digest sender for throttled AutoFlows — sends ONE WhatsApp per flow with an accurate {task_count} once throttle_minutes elapse.
Used by: system crontab (every minute); mirrors the drain_address_verification_queue cron pattern since this server uses cron, not Celery beat.
Notes: Idempotent and safe on a per-minute cron. flush_due_digests() clears each batch before sending to avoid double-send on overlapping runs.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Send trailing-edge digests for throttled AutoFlows whose batch window '
        'has elapsed. Renders one message per flow with the accumulated task '
        'count, then clears the batch. Safe to run on a per-minute cron.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet', action='store_true',
            help='Suppress output unless a digest was sent or an error occurred.',
        )

    def handle(self, *args, **options):
        from core.auto_flow_executor import flush_due_digests

        result = flush_due_digests()
        flushed = result.get('flushed', 0)
        sent = result.get('sent', 0)
        skipped = result.get('skipped', 0)
        errors = result.get('errors', [])

        if options['quiet'] and not flushed and not errors:
            return

        self.stdout.write(
            f"Flushed {flushed} digest(s), sent {sent} message(s), skipped {skipped}."
        )
        for err in errors:
            self.stderr.write(f"ERROR: {err}")
