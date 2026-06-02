"""
manage.py drain_address_verification_queue

Cron-driven runner for the AddressVerificationJob queue. Mirrors what the
Celery beat task `whatsapp.tasks.drain_verification_queue` would do — but
this server uses cron, not Celery, so the cron entry calls this command
once a minute instead.

Same rate limits, same per-business cap, same kill switch (WahaConfig).
"""
import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        'Drain the AddressVerificationJob queue: send rate-limited WhatsApp '
        'verify-link messages and flip jobs to status=sent. Idempotent — safe '
        'to run on a tight cron schedule.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--quiet', action='store_true',
            help='Suppress output unless something was sent or failed.',
        )

    def handle(self, *args, **options):
        # Import the same function the Celery task wraps. Calling it directly
        # (no Celery dispatch) executes the drain inline in this process.
        from whatsapp.tasks import drain_verification_queue

        # The Celery decorator makes drain_verification_queue a Task object,
        # but the underlying function is still callable via `.run()` or via
        # the task object itself (Task.__call__ runs synchronously).
        result = drain_verification_queue()

        if options['quiet']:
            sent = (result or {}).get('sent', 0)
            failed = (result or {}).get('failed', 0)
            if sent or failed:
                self.stdout.write(json.dumps(result))
            return

        if result is None:
            self.stdout.write('drain_verification_queue returned None')
        else:
            self.stdout.write(json.dumps(result))
