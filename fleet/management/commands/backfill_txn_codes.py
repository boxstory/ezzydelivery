"""
Management command to backfill transaction codes for existing transactions.
Usage: python manage.py backfill_txn_codes
"""
from django.core.management.base import BaseCommand
from fleet.models import DriverTransaction


class Command(BaseCommand):
    help = 'Backfill transaction codes for existing transactions that have empty codes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find transactions without transaction codes
        transactions_to_fix = DriverTransaction.objects.filter(
            transaction_code__isnull=True
        ) | DriverTransaction.objects.filter(transaction_code='')

        count = transactions_to_fix.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('All transactions already have codes.'))
            return

        self.stdout.write(f'Found {count} transactions without codes.')

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run - no changes made.'))
            return

        fixed = 0
        for txn in transactions_to_fix:
            # The save() method will auto-generate the transaction_code
            txn.save()
            fixed += 1
            if fixed % 100 == 0:
                self.stdout.write(f'Processed {fixed}/{count} transactions...')

        self.stdout.write(self.style.SUCCESS(f'Successfully backfilled {fixed} transaction codes.'))
