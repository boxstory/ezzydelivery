"""
Management command to generate missing QR codes for delivery tasks.

Usage:
    python manage.py generate_missing_qrcodes
    python manage.py generate_missing_qrcodes --dry-run
"""

from django.core.management.base import BaseCommand
from delivery import models as delivery_models
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Generate missing QR codes for delivery tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find tasks without QR codes
        tasks_without_qr = delivery_models.DeliveryTask.objects.exclude(
            task_qrcode__isnull=False
        )

        count = tasks_without_qr.count()
        self.stdout.write(f"Found {count} delivery tasks without QR codes")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes made"))
            for task in tasks_without_qr[:10]:  # Show first 10
                self.stdout.write(f"  Would create QR for: {task.dl_task_number}")
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")
            return

        created_count = 0
        error_count = 0

        for task in tasks_without_qr:
            try:
                # Check if QR code already exists (double check)
                if not delivery_models.DeliveryTaskQRCode.objects.filter(
                    delivery_task=task
                ).exists():
                    qr = delivery_models.DeliveryTaskQRCode.objects.create(
                        delivery_task=task,
                        task_number=task.dl_task_number
                    )
                    created_count += 1
                    self.stdout.write(f"Created QR for task: {task.dl_task_number}")
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"Error creating QR for {task.dl_task_number}: {e}")
                )
                logger.exception(f"Error creating QR code for task {task.dl_task_number}")

        self.stdout.write(
            self.style.SUCCESS(f"Created {created_count} QR codes, {error_count} errors")
        )
