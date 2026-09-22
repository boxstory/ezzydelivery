# Purpose: Re-issue every legacy driver_code (6-digit numeric) in the current ABC12 format — 3 letters + 2 digits, no O/I/L.
# Used by: one-off ops run — `manage.py backfill_driver_codes` (dry run) then `--apply`. Safe to re-run; conforming codes are skipped.
# Notes: The old code is kept in driver_meta['previous_driver_codes'] and written to a CSV in logs/, because drivers
#        already quote their old code to ops and it prints on past payouts and exports. Nothing is discarded.

import csv
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from fleet.codes import generate_driver_code, CODE_ALPHABET, LETTERS, DIGITS
from fleet.models import Driver

# A code already in the house format needs no re-issue.
CONFORMING = re.compile(r'^[%s]{%d}\d{%d}$' % (CODE_ALPHABET, LETTERS, DIGITS))


class Command(BaseCommand):
    help = ('Re-issue legacy driver codes in the ABC12 format. '
            'Runs as a dry run unless --apply is given.')

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Commit the new codes (default is a dry run).')
        parser.add_argument('--limit', type=int, default=0,
                            help='Only process the first N drivers (for a cautious first pass).')

    def handle(self, *args, **options):
        apply_changes = options['apply']
        limit = options['limit']

        drivers = Driver.objects.order_by('driver_id')
        pending = [d for d in drivers if d.driver_code and not CONFORMING.match(d.driver_code)]
        if limit:
            pending = pending[:limit]

        total = drivers.count()
        self.stdout.write(f'{total} drivers, {len(pending)} with a legacy code to re-issue.')
        if not pending:
            self.stdout.write(self.style.SUCCESS('Nothing to do.'))
            return

        # Reserve as we go so two drivers in this batch cannot draw the same code.
        taken = set(Driver.objects.exclude(driver_code=None)
                    .values_list('driver_code', flat=True))
        rows = []
        for d in pending:
            new_code = generate_driver_code()
            while new_code in taken:
                new_code = generate_driver_code()
            taken.add(new_code)
            rows.append((d, d.driver_code, new_code))

        for d, old, new in rows[:10]:
            self.stdout.write(f'  {d.driver_id:>5}  {old}  ->  {new}')
        if len(rows) > 10:
            self.stdout.write(f'  ... and {len(rows) - 10} more')

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                'Dry run — nothing written. Re-run with --apply to commit.'))
            return

        stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
        out_path = Path(settings.BASE_DIR) / 'logs' / f'driver_code_backfill_{stamp}.csv'
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with transaction.atomic():
            for d, old, new in rows:
                meta = d.driver_meta if isinstance(d.driver_meta, dict) else {}
                history = meta.get('previous_driver_codes') or []
                if old not in history:
                    history.append(old)
                meta['previous_driver_codes'] = history
                d.driver_meta = meta
                d.driver_code = new
                # Only admin and this command may move a code — see Driver.save().
                d.save(allow_code_change=True,
                       update_fields=['driver_code', 'driver_meta', 'updated_at'])

            with out_path.open('w', newline='') as fh:
                writer = csv.writer(fh)
                writer.writerow(['driver_id', 'old_code', 'new_code', 'driver_status', 'name'])
                for d, old, new in rows:
                    name = (d.user.get_full_name() if d.user else '') or ''
                    writer.writerow([d.driver_id, old, new, d.driver_status, name])

        self.stdout.write(self.style.SUCCESS(
            f'Re-issued {len(rows)} driver codes. Old -> new mapping: {out_path}'))
