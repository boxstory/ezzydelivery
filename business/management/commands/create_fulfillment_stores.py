"""
Management command to create Fulfillment Store pickup locations
for all businesses that have fulfillment service enabled.

Usage:
    python manage.py create_fulfillment_stores
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from business.models import Business, PickupLocation


class Command(BaseCommand):
    help = 'Create Fulfillment Store pickup locations for businesses with fulfillment service enabled'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("CREATE FULFILLMENT STORES"))
        self.stdout.write("=" * 60)
        self.stdout.write("")

        # Find businesses with fulfillment enabled
        businesses_with_fulfillment = Business.objects.filter(
            fulfillment_service_enabled=True
        )

        total_businesses = businesses_with_fulfillment.count()
        self.stdout.write(f"Found {total_businesses} businesses with fulfillment service enabled")
        self.stdout.write("")

        if total_businesses == 0:
            self.stdout.write(self.style.WARNING("No businesses found with fulfillment service enabled"))
            return

        created_count = 0
        skipped_count = 0

        for business in businesses_with_fulfillment:
            # Check if fulfillment store already exists
            fulfillment_store_exists = PickupLocation.objects.filter(
                business=business,
                pickup_location_title__icontains="fulfillment"
            ).exists()

            if fulfillment_store_exists:
                self.stdout.write(
                    f"  ⏭  Skipped: {business.business_name} (ID: {business.business_id}) - "
                    f"Fulfillment store already exists"
                )
                skipped_count += 1
            else:
                if dry_run:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  🔍 Would create: Fulfillment Store for {business.business_name} "
                            f"(ID: {business.business_id})"
                        )
                    )
                    created_count += 1
                else:
                    try:
                        PickupLocation.objects.create(
                            business=business,
                            pickup_location_title="Fulfillment Store",
                            locality="EzzyDelivery Fulfillment Center",
                            pickup_status='active',
                        )

                        # Update fulfillment_activated_at if not set
                        if not business.fulfillment_activated_at:
                            business.fulfillment_activated_at = timezone.now()
                            business.save(update_fields=['fulfillment_activated_at'])

                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓  Created: Fulfillment Store for {business.business_name} "
                                f"(ID: {business.business_id})"
                            )
                        )
                        created_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"  ✗  Error: Failed to create for {business.business_name} "
                                f"(ID: {business.business_id}): {e}"
                            )
                        )

        self.stdout.write("")
        self.stdout.write("=" * 60)
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes were made"))
            self.stdout.write(f"Would create: {created_count} fulfillment stores")
        else:
            self.stdout.write(self.style.SUCCESS("COMPLETE!"))
            self.stdout.write(f"Created: {created_count} fulfillment stores")
        self.stdout.write(f"Skipped: {skipped_count} existing stores")
        self.stdout.write(f"Total businesses: {total_businesses}")
        self.stdout.write("=" * 60)
