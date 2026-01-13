"""
Management command to update existing orders with new order number format
and regenerate barcodes.

Usage:
    python manage.py update_order_numbers          # Dry run (preview changes)
    python manage.py update_order_numbers --apply  # Apply changes
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from orders.models import Order, OrderBarcode
from orders.signals import generate_sequence_code


class Command(BaseCommand):
    help = 'Update existing order numbers to new format: {business_code}-{client_order_code}-{YMMDD}-{sequence}'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply changes (without this flag, only preview)',
        )
        parser.add_argument(
            '--business',
            type=str,
            help='Only update orders for specific business code',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        business_filter = options.get('business')

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                '\n=== DRY RUN MODE ===\n'
                'No changes will be made. Use --apply to apply changes.\n'
            ))

        # Get all orders, optionally filtered by business
        orders = Order.objects.select_related('business').order_by('business', 'created_at')

        if business_filter:
            orders = orders.filter(business__business_code=business_filter)
            self.stdout.write(f'Filtering orders for business: {business_filter}')

        total_orders = orders.count()
        self.stdout.write(f'Total orders to process: {total_orders}\n')

        if total_orders == 0:
            self.stdout.write(self.style.WARNING('No orders found.'))
            return

        # Group orders by business for sequence generation
        business_counts = {}
        updated_count = 0
        skipped_count = 0

        for order in orders:
            business = order.business
            business_code = business.business_code or 'EZY'

            # Initialize or increment business counter
            if business.business_id not in business_counts:
                business_counts[business.business_id] = 0
            business_counts[business.business_id] += 1

            # Generate new order number
            # Use order's created_at date for YMMDD
            order_date = order.created_at or timezone.now()
            if timezone.is_aware(order_date):
                order_date = timezone.localtime(order_date)

            year_digit = str(order_date.year)[-1]
            date_part = f"{year_digit}{order_date.month:02d}{order_date.day:02d}"

            sequence = generate_sequence_code(business_counts[business.business_id])
            client_code = order.client_order_code or 'ORD'

            new_order_number = f"{business_code}-{client_code}-{date_part}-{sequence}"

            # Check if already in new format
            if order.order_number == new_order_number:
                skipped_count += 1
                continue

            old_order_number = order.order_number

            self.stdout.write(
                f'Order #{order.id}: {old_order_number} -> {new_order_number}'
            )

            if apply_changes:
                # Update order number
                order.order_number = new_order_number
                order.save(update_fields=['order_number'])

                # Update or create barcode
                barcode, created = OrderBarcode.objects.get_or_create(
                    order=order,
                    defaults={'order_number': new_order_number}
                )
                if not created:
                    barcode.order_number = new_order_number
                    barcode.save()  # This triggers barcode regeneration

                updated_count += 1

        self.stdout.write('\n' + '=' * 50)

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(
                f'\nCompleted!\n'
                f'  Updated: {updated_count} orders\n'
                f'  Skipped (already updated): {skipped_count} orders'
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f'\nDry run complete.\n'
                f'  Would update: {total_orders - skipped_count} orders\n'
                f'  Would skip: {skipped_count} orders\n'
                f'\nRun with --apply to apply these changes.'
            ))
