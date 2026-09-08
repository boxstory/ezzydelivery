# Purpose: Open location reviews for past deliveries completed far from the customer's pin.
# Used by: one-off backfill after migration delivery/0042, and after any change to DELIVERY_GPS_FLAG_KM; safe to re-run.
# Notes: Read-only on orders and tasks — it only raises questions, it never moves a coordinate.
#        --prune drops still-pending flags that the current threshold would no longer raise;
#        a review with a verdict is never touched, because that verdict is a record.

from django.conf import settings
from django.core.management.base import BaseCommand

from delivery.geo import in_qatar
from delivery.models import DeliveryTask, DeliveryLocationReview, TaskStatusPoint


class Command(BaseCommand):
    help = "Flag past deliveries whose completion GPS is far from the customer's marked location"

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Create the reviews (default is a dry run)')
        parser.add_argument('--threshold', type=float,
                            default=getattr(settings, 'DELIVERY_GPS_FLAG_KM', 3.0),
                            help='Gap in km at or above which a delivery is flagged')
        parser.add_argument('--prune', action='store_true',
                            help='Also close pending reviews whose gap is now under the threshold '
                                 '(reviews that already have a verdict are left alone)')

    def handle(self, *args, **options):
        apply_changes = options['apply']
        threshold = options['threshold']
        prune = options['prune']

        tasks = DeliveryTask.objects.filter(
            completion_latitude__isnull=False,
            completion_longitude__isnull=False,
            dl_task_status__in=['delivered', 'partial_delivery'],
        ).select_related('order', 'driver')

        existing = set(
            DeliveryLocationReview.objects.values_list('task_id', flat=True)
        )

        flagged, skipped_bad_coords, buckets = [], 0, {'1-2': 0, '2-5': 0, '5-20': 0, '20+': 0}
        for task in tasks.iterator(chunk_size=500):
            order = task.order
            if not order or order.latitude is None or order.longitude is None:
                continue
            try:
                dlat, dlon = float(task.completion_latitude), float(task.completion_longitude)
                clat, clon = float(order.latitude), float(order.longitude)
            except (TypeError, ValueError):
                continue
            # A point outside Qatar is corrupt data, not a discrepancy to review.
            if not in_qatar(dlat, dlon) or not in_qatar(clat, clon):
                skipped_bad_coords += 1
                continue

            gap = TaskStatusPoint.haversine_km(dlat, dlon, clat, clon)
            if gap < threshold:
                continue

            key = '1-2' if gap < 2 else '2-5' if gap < 5 else '5-20' if gap < 20 else '20+'
            buckets[key] += 1

            if task.id in existing:
                continue
            flagged.append(DeliveryLocationReview(
                task=task, order=order, driver=task.driver, gap_km=round(gap, 3),
                driver_latitude=task.completion_latitude,
                driver_longitude=task.completion_longitude,
                customer_latitude=order.latitude,
                customer_longitude=order.longitude,
            ))

        self.stdout.write(f'Deliveries at or over {threshold} km apart: {sum(buckets.values())}')
        for label in ('1-2', '2-5', '5-20', '20+'):
            self.stdout.write(f'  {label:>5} km: {buckets[label]}')
        self.stdout.write(f'  skipped (coordinates outside Qatar): {skipped_bad_coords}')
        self.stdout.write(f'  new reviews to open: {len(flagged)}')

        # Raising the threshold leaves flags behind that it would no longer raise.
        # Only the undecided ones go: a verdict is somebody's judgement on the record,
        # and it stays whatever the threshold does afterwards.
        stale = DeliveryLocationReview.objects.none()
        if prune:
            stale = DeliveryLocationReview.objects.filter(
                status='pending', gap_km__lt=threshold,
            )
            self.stdout.write(f'  pending flags now under {threshold} km: {stale.count()}')

        if apply_changes and flagged:
            DeliveryLocationReview.objects.bulk_create(flagged, batch_size=500)
            self.stdout.write(self.style.SUCCESS(f'Opened {len(flagged)} review(s).'))
        elif apply_changes:
            self.stdout.write(self.style.SUCCESS('Nothing new to open.'))

        if prune and apply_changes:
            removed = stale.delete()[0]
            self.stdout.write(self.style.SUCCESS(f'Closed {removed} flag(s) now under the threshold.'))

        if not apply_changes:
            self.stdout.write(self.style.NOTICE('Dry run — re-run with --apply to write the changes.'))
