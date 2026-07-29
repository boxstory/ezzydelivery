# Purpose: Recompute PickList.total_items / picked_items from the actual PickListItem rows,
#          fixing counters that drifted out of sync (e.g. items removed without updating the count).
# Used by: manual/ops — `python manage.py recompute_pick_counters [--dry-run]`
# Notes:   Counters are ROW counts (matches warehouse/signals.py): total = items.count(),
#          picked = items.filter(is_picked=True).count(). Only mismatched rows are written.
from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from warehouse import models as warehouse_models


class Command(BaseCommand):
    help = "Recompute PickList total_items/picked_items from real PickListItem rows."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Report what would change without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # One query: annotate each pick list with its real row counts.
        pick_lists = warehouse_models.PickList.objects.annotate(
            real_total=Count('items', distinct=True),
            real_picked=Count('items', filter=Q(items__is_picked=True), distinct=True),
        )

        scanned = 0
        fixed = 0
        empty_active = 0

        for pl in pick_lists.iterator():
            scanned += 1
            if pl.total_items == pl.real_total and pl.picked_items == pl.real_picked:
                continue

            self.stdout.write(
                f"{pl.pick_number} [{pl.status}]: "
                f"total {pl.total_items}→{pl.real_total}, "
                f"picked {pl.picked_items}→{pl.real_picked}"
            )

            if pl.real_total == 0 and pl.status not in ('pending', 'cancelled'):
                empty_active += 1

            if not dry_run:
                pl.total_items = pl.real_total
                pl.picked_items = pl.real_picked
                pl.save(update_fields=['total_items', 'picked_items', 'updated_at'])

            fixed += 1

        verb = "would fix" if dry_run else "fixed"
        self.stdout.write(self.style.SUCCESS(
            f"Scanned {scanned} pick list(s); {verb} {fixed} with drifted counters."
        ))
        if empty_active:
            self.stdout.write(self.style.WARNING(
                f"{empty_active} non-pending pick list(s) now have 0 items "
                f"(empty but still active) — review whether they should be cancelled."
            ))
