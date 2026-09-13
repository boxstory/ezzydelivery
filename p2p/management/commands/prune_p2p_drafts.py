# Purpose: Age out P2P quotes that were accepted but never signed in for.
# Used by: cron / manual run — `python manage.py prune_p2p_drafts`
# Notes: Marks, never deletes. An abandoned draft is the conversion funnel for the pricing page,
#        so the row is the data; only its status is stale.

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from p2p.models import P2PBooking

DEFAULT_DAYS = 7


class Command(BaseCommand):
    help = "Mark unclaimed P2P drafts as abandoned after a grace period."

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=DEFAULT_DAYS,
                            help=f'Grace period in days (default {DEFAULT_DAYS})')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing')

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['days'])
        # Only drafts nobody ever claimed. A booking with a customer attached is a real
        # person mid-flow, and a booking with an order is live work.
        stale = P2PBooking.objects.filter(
            status='draft', customer__isnull=True, order__isnull=True,
            created_at__lt=cutoff)
        count = stale.count()

        if options['dry_run']:
            self.stdout.write(f'{count} draft(s) older than {options["days"]} days would be marked abandoned.')
            return

        updated = stale.update(status='abandoned', updated_at=timezone.now())
        self.stdout.write(self.style.SUCCESS(
            f'Marked {updated} abandoned P2P draft(s) older than {options["days"]} days.'))
