"""
Delete DriverLocation records older than N days (default 7).
Usage: python manage.py prune_driver_locations [--days 7]

Nav handoffs age out on the same cutoff: they only exist to explain gaps in the
trail, so they are worthless once the trail they annotate is gone.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from fleet.models import DriverLocation, DriverNavHandoff


class Command(BaseCommand):
    help = 'Delete DriverLocation records older than N days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=7,
            help='Delete records older than this many days (default: 7)',
        )

    def handle(self, *args, **options):
        days = options['days']
        cutoff = timezone.now() - timedelta(days=days)
        count, _ = DriverLocation.objects.filter(created_at__lt=cutoff).delete()
        handoffs, _ = DriverNavHandoff.objects.filter(opened_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {count} DriverLocation and {handoffs} nav handoff record(s) '
            f'older than {days} day(s).'
        ))
