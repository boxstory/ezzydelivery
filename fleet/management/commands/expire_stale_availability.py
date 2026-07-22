# Purpose: Auto-offline drivers whose availability is stale (no activity for N hours, no active task)
# Used by: hourly crontab entry (manage.py expire_stale_availability --quiet)
# Notes: activity = latest of GPS ping, activity log, or Driver row update; active-task drivers are never touched

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from fleet import models as fleet_models
from delivery import models as delivery_models

ACTIVE_TASK_STATUSES = [
    'assigned', 'accepted', 'picked_up', 'start_ride',
    'out_for_delivery', 'in_transit', 'contacted',
]

DEFAULT_STALE_HOURS = 12


class Command(BaseCommand):
    help = ("Set drivers back to 'offline' when they have been marked "
            "available/on_break/returning with no activity for N hours "
            "(default 12) and hold no active task.")

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=DEFAULT_STALE_HOURS,
                            help='Inactivity window in hours before going offline')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without saving')
        parser.add_argument('--quiet', action='store_true',
                            help='Only print when something changes')

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=options['hours'])
        candidates = fleet_models.Driver.objects.filter(
            driver_availability__in=['available', 'on_break', 'returning'])

        expired = []
        for driver in candidates:
            if delivery_models.DeliveryTask.objects.filter(
                    driver=driver, dl_task_status__in=ACTIVE_TASK_STATUSES).exists():
                continue

            last_seen = driver.updated_at
            last_ping = driver.locations.order_by('-created_at').values_list(
                'created_at', flat=True).first()
            if last_ping and last_ping > last_seen:
                last_seen = last_ping
            last_log = fleet_models.DriverActivityLog.objects.filter(
                driver=driver).order_by('-created_at').values_list(
                'created_at', flat=True).first()
            if last_log and last_log > last_seen:
                last_seen = last_log

            if last_seen < cutoff:
                expired.append((driver, last_seen))
                if not options['dry_run']:
                    driver.driver_availability = 'offline'
                    driver.save(update_fields=['driver_availability'])

        if expired:
            verb = 'Would set' if options['dry_run'] else 'Set'
            for driver, last_seen in expired:
                self.stdout.write(
                    f"{verb} driver {driver.driver_code or driver.driver_id} offline "
                    f"(last activity {last_seen:%Y-%m-%d %H:%M})")
        elif not options['quiet']:
            self.stdout.write('No stale availability found.')
