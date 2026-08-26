"""
Purpose: One-time backfill that ties existing flat Product rows back into variant groups.
Used by: `python manage.py backfill_variant_groups [--dry-run] [--business <pk>] [--include-singletons]`
Notes: Two real naming patterns exist in this catalogue — "<Base> - <Colour>" with a colour FK set, and an identical repeated item_name. The shared SKU prefix looks like a variant key but is not one (BMS045-* spans unrelated products), so it is deliberately ignored.
"""

import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from product.models import Product

# A trailing " - Black" / " — Dark Green" / " / Pink" option suffix. Bounded in
# length and digit-free so a real product name ("Kit - 3 Piece", "Cable - 2m")
# is not mistaken for an option.
OPTION_SUFFIX = re.compile(r'\s*[-–—/]\s*([^-–—/]{1,25})$')


def base_name(product):
    """
    The product name with its option suffix removed.

    Only stripped when the row actually carries variant fields — a product with
    no colour and no size is not a variant, so its name is left whole even if it
    happens to contain a dash.
    """
    name = (product.item_name or '').strip()
    has_variant_fields = bool(product.color_id) or bool((product.size or '').strip())
    if not has_variant_fields:
        return name.lower()

    match = OPTION_SUFFIX.search(name)
    if not match:
        return name.lower()

    tail = match.group(1).strip()
    if any(ch.isdigit() for ch in tail):
        return name.lower()

    stripped = name[:match.start()].strip()
    # Never strip the name down to nothing.
    return (stripped or name).lower()


class Command(BaseCommand):
    help = "Assign variant_group to products that do not have one yet."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Report what would change without writing anything.",
        )
        parser.add_argument(
            '--business', type=int, default=None,
            help="Limit to one business (primary key).",
        )
        parser.add_argument(
            '--include-singletons', action='store_true',
            help="Also give a group key to products that have no siblings.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        business_pk = options['business']
        include_singletons = options['include_singletons']

        qs = Product.objects.filter(variant_group='')
        if business_pk:
            qs = qs.filter(business_id=business_pk)

        # Sibling variants were imported as separate rows, either sharing a title
        # outright or differing only by an option suffix on the end of it.
        buckets = defaultdict(list)
        fields = ['id', 'business_id', 'brand_name', 'item_name', 'item_sku',
                  'color_id', 'size', 'variant_group']
        for product in qs.only(*fields):
            key = (
                product.business_id,
                (product.brand_name or '').strip().lower(),
                base_name(product),
            )
            buckets[key].append(product)

        # Continue each business's counter past whatever manual groups exist, so
        # a re-run cannot hand out a key that is already in use.
        next_counter = defaultdict(int)
        for group in Product.objects.exclude(variant_group='').values_list('variant_group', flat=True):
            biz, _, tail = str(group).partition('-G')
            if tail.isdigit():
                try:
                    next_counter[int(biz)] = max(next_counter[int(biz)], int(tail))
                except ValueError:
                    continue

        updates = []
        multi_groups = []
        skipped_singletons = 0
        for (business_id, _brand, name), products in sorted(buckets.items(), key=lambda kv: str(kv[0])):
            # A group of one is not a variant group. Skipping them keeps
            # "has siblings" a meaningful test instead of always true.
            if len(products) < 2 and not include_singletons:
                skipped_singletons += 1
                continue

            biz = business_id or 0
            next_counter[biz] += 1
            group = f"{biz}-G{next_counter[biz]:04d}"
            if len(products) > 1:
                multi_groups.append((group, name, products))
            for product in products:
                product.variant_group = group
                updates.append(product)

        self.stdout.write(
            f"{len(updates)} product(s) in {len(multi_groups)} variant group(s); "
            f"{skipped_singletons} standalone product(s) left ungrouped."
        )

        if not updates:
            self.stdout.write(self.style.SUCCESS("Nothing to backfill."))
            return

        if dry_run:
            for group, name, products in multi_groups[:15]:
                self.stdout.write(f"  {group}  {name[:46]!r}  ({len(products)} variants)")
                for product in products[:6]:
                    self.stdout.write(f"      {product.item_sku:<16} {product.item_name[:52]}")
                if len(products) > 6:
                    self.stdout.write(f"      … and {len(products) - 6} more")
            if len(multi_groups) > 15:
                self.stdout.write(f"  … and {len(multi_groups) - 15} more groups")
            self.stdout.write(self.style.WARNING("Dry run — nothing written."))
            return

        with transaction.atomic():
            Product.objects.bulk_update(updates, ['variant_group'], batch_size=500)

        self.stdout.write(self.style.SUCCESS(f"Backfilled {len(updates)} product(s)."))
