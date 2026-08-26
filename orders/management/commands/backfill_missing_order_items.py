# Purpose: Re-add OrderItems that sheet imports dropped while _extract_products_from_raw_row was
#          capped at product_1..3, and repair the package description/qty derived from them.
# Used by: one-off repair after the MAX_PRODUCT_COLUMNS fix; safe to re-run (a settled order reports 0).
# Notes: Dry-run by default, like backfill_delivery_area. Only touches orders whose delivery task is
#        still open — a delivered/cancelled order's items are history, not something to rewrite.
#        Re-reads the stored raw_row through the *fixed* extractor, so it produces exactly what a
#        correct import would have produced.

from django.core.management.base import BaseCommand
from django.db import transaction

from delivery.models import DeliveryTask
from orders.models import OrderItem, TempOrder

# Task states where the order has already been settled one way or another. Anything
# else — including 'failed', which can be retried back into 'accepted' — is still live
# and can still be packed, so a missing line there is worth fixing.
CLOSED_TASK_STATUSES = {
    'delivered', 'partial_delivery', 'rejected', 'cancelled', 'dropsownlost',
}

LIST_SOURCE_TYPES = ['onedrive', 'google_sheet', 'public_link']


class Command(BaseCommand):
    help = "Re-add order items dropped by the product_1..3 import cap (dry run by default)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the missing items (default is a dry run)',
        )
        parser.add_argument(
            '--order', type=str,
            help='Limit to one order_number',
        )
        parser.add_argument(
            '--business', type=int,
            help='Limit to one business_id',
        )
        parser.add_argument(
            '--include-closed', action='store_true',
            help='Also repair orders whose delivery task is already delivered/cancelled',
        )

    def handle(self, *args, **options):
        from workforce.views import (
            _extract_products_from_raw_row,
            _match_product_by_name,
            _parse_coded_product_name,
        )

        apply_changes = options['apply']

        temp_orders = (
            TempOrder.objects
            .filter(status='imported', imported_order__isnull=False,
                    source_type__in=LIST_SOURCE_TYPES)
            .select_related('business', 'imported_order', 'onedrive_source',
                            'public_link_source', 'api_settings')
            .order_by('pk')
        )
        if options.get('order'):
            temp_orders = temp_orders.filter(imported_order__order_number=options['order'])
        if options.get('business'):
            temp_orders = temp_orders.filter(business_id=options['business'])

        self.stdout.write(f'Examining {temp_orders.count()} imported row(s)')

        repaired = skipped_closed = lines_added = 0
        desc_updated = qty_updated = qty_kept = 0
        drifted = []

        for temp_order in temp_orders.iterator(chunk_size=200):
            if not isinstance(temp_order.raw_row, list):
                continue

            order = temp_order.imported_order
            products = _extract_products_from_raw_row(temp_order)
            if not products:
                continue

            existing = list(OrderItem.objects.filter(order=order))

            resolved = []
            for entry in products:
                pname = entry['name']
                matched = _match_product_by_name(pname, temp_order.business)
                clean_name, _ = _parse_coded_product_name(pname)
                resolved.append({
                    'product': matched, 'qty': entry['qty'],
                    'pname': pname, 'clean_name': clean_name,
                })

            # Pair each sheet line with an item already on the order. An item may have been
            # written before its name was mappable (product=None, notes=raw name), so fall
            # back to the notes text — otherwise the same product gets added twice.
            unclaimed = list(existing)

            def claim(line):
                names = {line['pname'].strip(), line['clean_name'].strip()}
                if line['product']:
                    names.add((line['product'].item_name or '').strip())
                for item in unclaimed:
                    same_product = line['product'] and item.product_id == line['product'].pk
                    if same_product or (item.notes or '').strip() in names:
                        unclaimed.remove(item)
                        return True
                return False

            missing = [line for line in resolved if not claim(line)]
            if not missing:
                continue

            # An item we cannot pair with any current sheet line means the order and the row
            # have diverged: usually a stale fuzzy match (the line was matched to the wrong
            # product before the right one existed), sometimes a reused row or a staff edit.
            # Which line is which is no longer decidable here — report and leave it alone.
            if unclaimed:
                drifted.append((
                    order.order_number, temp_order.business.business_name,
                    [f"{i.notes or '?'} (product {i.product_id})" for i in unclaimed],
                    [f"{line['clean_name']} x{line['qty']}" for line in missing],
                ))
                continue

            statuses = list(
                DeliveryTask.objects.filter(order=order)
                .values_list('dl_task_status', flat=True)
            )
            is_closed = bool(statuses) and all(s in CLOSED_TASK_STATUSES for s in statuses)
            if is_closed and not options.get('include_closed'):
                skipped_closed += 1
                continue

            # package_description / package_qty are only rewritten when the import derived
            # them from the (truncated) product list. A value that came from the sheet's own
            # description column, or that staff edited, is left alone.
            derived_desc = ', '.join(
                f"{line['clean_name']} x{line['qty']}" for line in resolved
            )[:255]
            old_derived_desc = ', '.join(
                f"{_parse_coded_product_name(i.notes or '')[0]} x{i.quantity}"
                for i in existing
            )[:255]
            desc_is_derived = (
                not (temp_order.package_desc or '').strip()
                and (order.package_description or '').strip() == old_derived_desc.strip()
            )
            new_qty = sum(line['qty'] for line in resolved)
            old_qty = sum(i.quantity for i in existing)
            qty_is_derived = order.package_qty in (old_qty, 0, 1, None)

            added_names = ', '.join(
                f"{line['clean_name']} x{line['qty']}"
                f"{'' if line['product'] else ' (unmatched)'}"
                for line in missing
            )
            self.stdout.write(
                f"  {order.order_number:<24} {temp_order.business.business_name:<20} "
                f"{len(existing)} -> {len(resolved)} items"
                f"{'  [task closed]' if is_closed else ''}"
            )
            self.stdout.write(f"      + {added_names}")
            if not desc_is_derived:
                self.stdout.write(
                    f"      description left as-is: {order.package_description!r}"
                )

            repaired += 1
            lines_added += len(missing)
            if desc_is_derived:
                desc_updated += 1
            if qty_is_derived:
                qty_updated += 1
            else:
                qty_kept += 1

            if not apply_changes:
                continue

            with transaction.atomic():
                for line in missing:
                    matched = line['product']
                    OrderItem.objects.create(
                        order=order,
                        product=matched,
                        quantity=line['qty'],
                        unit_price=(matched.item_price or 0) if matched else 0,
                        notes=matched.item_name if matched else line['pname'],
                    )

                update_fields = ['original_order_data']
                if desc_is_derived:
                    order.package_description = derived_desc
                    update_fields.append('package_description')
                if qty_is_derived:
                    order.package_qty = new_qty
                    update_fields.append('package_qty')

                ood = dict(order.original_order_data or {})
                ood['products'] = [
                    {'name': line['clean_name'], 'qty': str(line['qty'])} for line in resolved
                ]
                ood['products_backfilled'] = True
                order.original_order_data = ood
                order.save(update_fields=update_fields)

                temp_order.append_change_log(
                    'backfill-products',
                    {'order_items': len(existing)},
                    {'order_items': len(resolved), 'added': added_names},
                )

        if drifted:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Skipped — these orders carry an item that matches no current sheet line, so the '
                'missing line cannot be added safely (usually a stale product match). Review by hand:'
            ))
            for order_number, biz, leftovers, would_add in drifted:
                self.stdout.write(f'  {order_number:<24} {biz}')
                self.stdout.write(f'      on order, not in sheet: {", ".join(leftovers)}')
                self.stdout.write(f'      in sheet, not on order: {", ".join(would_add)}')

        self.stdout.write('')
        self.stdout.write(f'  orders repaired:            {repaired}')
        self.stdout.write(f'  product lines added:        {lines_added}')
        self.stdout.write(f'  package descriptions fixed: {desc_updated}')
        self.stdout.write(f'  package qty fixed:          {qty_updated} (kept {qty_kept})')
        self.stdout.write(f'  skipped, task already closed: {skipped_closed}')
        self.stdout.write(f'  skipped, row drifted:         {len(drifted)}')
        if skipped_closed and not options.get('include_closed'):
            self.stdout.write(self.style.WARNING(
                '  closed orders keep their under-counted items — re-run with '
                '--include-closed to rewrite them too.'
            ))
        if apply_changes:
            self.stdout.write(self.style.SUCCESS('Missing order items written.'))
        else:
            self.stdout.write(self.style.NOTICE('Dry run — re-run with --apply to write.'))
