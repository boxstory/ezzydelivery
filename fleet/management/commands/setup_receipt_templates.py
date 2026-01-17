"""
Management command to set up Receipt Templates table and create default templates.

Usage:
    python manage.py setup_receipt_templates

This command:
1. Runs migrations for the fleet app (creates ReceiptTemplate table if missing)
2. Creates default receipt templates for each template type
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection


class Command(BaseCommand):
    help = 'Set up Receipt Templates table and create default templates'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-migrate',
            action='store_true',
            help='Skip running migrations (only create default templates)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreate default templates even if they exist',
        )

    def handle(self, *args, **options):
        skip_migrate = options.get('skip_migrate', False)
        force = options.get('force', False)

        # Step 1: Run migrations if not skipped
        if not skip_migrate:
            self.stdout.write(self.style.NOTICE('Running fleet migrations...'))
            try:
                call_command('migrate', 'fleet', verbosity=1)
                self.stdout.write(self.style.SUCCESS('Fleet migrations applied successfully.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Migration failed: {e}'))
                return

        # Step 2: Check if the table exists
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names()
            if 'fleet_receipttemplate' not in tables:
                self.stdout.write(self.style.ERROR(
                    'ReceiptTemplate table does not exist. '
                    'Run without --skip-migrate to create it.'
                ))
                return

        # Step 3: Import model and create default templates
        from fleet.models import ReceiptTemplate

        self.stdout.write(self.style.NOTICE('Setting up default receipt templates...'))

        # Default templates for each type
        default_templates = [
            {
                'name': 'Default Settlement Receipt',
                'template_type': 'settlement',
                'is_default': True,
                'company_name': 'Ezzy Delivery',
                'company_address': 'Doha, Qatar',
                'company_phone': '+974-XXXX-XXXX',
                'primary_color': '#2196F3',
                'footer_message': 'Thank you for your service!',
            },
            {
                'name': 'Default COD Deposit Receipt',
                'template_type': 'cod_deposit',
                'is_default': True,
                'company_name': 'Ezzy Delivery',
                'company_address': 'Doha, Qatar',
                'company_phone': '+974-XXXX-XXXX',
                'primary_color': '#4CAF50',
                'footer_message': 'COD amount received. Thank you!',
            },
            {
                'name': 'Default Earnings Statement',
                'template_type': 'earnings',
                'is_default': True,
                'company_name': 'Ezzy Delivery',
                'company_address': 'Doha, Qatar',
                'company_phone': '+974-XXXX-XXXX',
                'primary_color': '#FF9800',
                'footer_message': 'Thank you for your hard work!',
            },
            {
                'name': 'Default Transaction Receipt',
                'template_type': 'transaction',
                'is_default': True,
                'company_name': 'Ezzy Delivery',
                'company_address': 'Doha, Qatar',
                'company_phone': '+974-XXXX-XXXX',
                'primary_color': '#9C27B0',
                'footer_message': 'Transaction recorded successfully.',
            },
        ]

        created_count = 0
        skipped_count = 0

        for template_data in default_templates:
            template_type = template_data['template_type']

            # Check if a default template already exists for this type
            existing = ReceiptTemplate.objects.filter(
                template_type=template_type,
                is_default=True
            ).first()

            if existing and not force:
                self.stdout.write(
                    f'  Skipping {template_type}: Default template already exists '
                    f'(ID: {existing.template_id}, Name: {existing.name})'
                )
                skipped_count += 1
                continue

            if existing and force:
                # Delete existing default to recreate
                existing.delete()
                self.stdout.write(f'  Deleted existing default for {template_type}')

            # Create the template
            template = ReceiptTemplate.objects.create(**template_data)
            self.stdout.write(self.style.SUCCESS(
                f'  Created: {template.name} (ID: {template.template_id})'
            ))
            created_count += 1

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Setup complete! Created: {created_count}, Skipped: {skipped_count}'
        ))

        # Show current templates
        total = ReceiptTemplate.objects.count()
        self.stdout.write(f'Total receipt templates in database: {total}')
