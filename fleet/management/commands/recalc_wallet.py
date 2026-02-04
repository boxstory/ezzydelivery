"""
Management command to recalculate driver wallet balances from transaction history.

Fixes mismatches between stored driver fields and actual transaction data.
Also syncs cod_settled flags on delivery tasks.

Usage:
    python manage.py recalc_wallet              # Dry run for all drivers
    python manage.py recalc_wallet --apply      # Apply fixes for all drivers
    python manage.py recalc_wallet --driver 153 # Dry run for specific driver
    python manage.py recalc_wallet --driver 153 --apply  # Apply for specific driver
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal

from fleet.models import Driver, DriverTransaction
from delivery.models import DeliveryTask


class Command(BaseCommand):
    help = 'Recalculate driver wallet balances from transaction history'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply the recalculated values (default is dry run)',
        )
        parser.add_argument(
            '--driver',
            type=int,
            help='Recalculate for a specific driver_id only',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        driver_id = options.get('driver')

        if apply:
            self.stdout.write(self.style.WARNING('APPLY MODE - Changes will be saved'))
        else:
            self.stdout.write(self.style.NOTICE('DRY RUN - No changes will be made'))

        drivers = Driver.objects.all()
        if driver_id:
            drivers = drivers.filter(driver_id=driver_id)

        if not drivers.exists():
            self.stdout.write(self.style.ERROR(f'No drivers found'))
            return

        for driver in drivers:
            self.recalc_driver(driver, apply)

        self.stdout.write(self.style.SUCCESS('Done.'))

    def recalc_driver(self, driver, apply):
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'Driver: {driver.user.first_name} {driver.user.last_name} '
                         f'(ID: {driver.driver_id}, Code: {driver.driver_code})')
        self.stdout.write(f'{"="*60}')

        txns = DriverTransaction.objects.filter(driver=driver)

        # Calculate expected values from transactions
        # COD collection increases cod_in_hand
        cod_collections = txns.filter(transaction_type='cod_collection').aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        # cod_deposit and cod_driver_settle both reduce cod_in_hand
        cod_deposits_abs = abs(txns.filter(
            transaction_type__in=['cod_deposit', 'cod_driver_settle']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))
        # cod_return reverses a collection (reduces cod_in_hand)
        cod_returns_abs = abs(txns.filter(transaction_type='cod_return').aggregate(
            total=Sum('amount'))['total'] or Decimal('0'))
        earnings = txns.filter(transaction_type='earning').aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        settlements_abs = abs(txns.filter(transaction_type='settlement').aggregate(
            total=Sum('amount'))['total'] or Decimal('0'))
        bonuses = txns.filter(transaction_type='bonus').aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        deductions = txns.filter(transaction_type='deduction').aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        adjustments = txns.filter(transaction_type='adjustment').aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        # Non-wallet types (ignored for balance calc): cod_client_settle,
        # delivery_charge, fulfillment_charge, inventory_handling, other_charge,
        # bills_payable, bills_receivable

        # Recalculate from transaction sums
        cod_in_hand_expected = abs(cod_collections) - cod_deposits_abs - cod_returns_abs
        wallet_delta = -abs(cod_collections) + cod_deposits_abs + cod_returns_abs + bonuses + deductions + adjustments
        pending_expected = earnings - settlements_abs
        total_earnings_expected = earnings

        # For wallet_balance, we need the initial value
        # We can infer it: initial = current - delta_from_transactions
        # But that's circular. Instead, let's compute from delivery tasks.

        # COD from delivery tasks
        unsettled_cod = DeliveryTask.objects.filter(
            driver=driver, cod_collected=True, cod_settled=False
        ).aggregate(total=Sum('cod_collected_amount'))['total'] or Decimal('0')

        settled_cod = DeliveryTask.objects.filter(
            driver=driver, cod_collected=True, cod_settled=True
        ).aggregate(total=Sum('cod_collected_amount'))['total'] or Decimal('0')

        self.stdout.write(f'\nCurrent stored values:')
        self.stdout.write(f'  wallet_balance:   {driver.wallet_balance}')
        self.stdout.write(f'  cod_in_hand:      {driver.cod_in_hand}')
        self.stdout.write(f'  pending_earnings: {driver.pending_earnings}')
        self.stdout.write(f'  total_earnings:   {driver.total_earnings}')

        self.stdout.write(f'\nTransaction sums:')
        self.stdout.write(f'  COD collected:    {abs(cod_collections)}')
        self.stdout.write(f'  COD deposited:    {cod_deposits_abs}')
        self.stdout.write(f'  COD returns:      {cod_returns_abs}')
        self.stdout.write(f'  Earnings:         {earnings}')
        self.stdout.write(f'  Settlements:      {settlements_abs}')
        self.stdout.write(f'  Bonuses:          {bonuses}')
        self.stdout.write(f'  Deductions:       {deductions}')

        self.stdout.write(f'\nExpected from transactions:')
        self.stdout.write(f'  cod_in_hand:      {cod_in_hand_expected}')
        self.stdout.write(f'  pending_earnings: {pending_expected}')

        self.stdout.write(f'\nDelivery tasks:')
        self.stdout.write(f'  Unsettled COD:    {unsettled_cod}')
        self.stdout.write(f'  Settled COD:      {settled_cod}')

        # Check mismatches
        mismatches = []

        if driver.cod_in_hand != cod_in_hand_expected:
            mismatches.append(f'cod_in_hand: {driver.cod_in_hand} -> {cod_in_hand_expected}')

        if driver.pending_earnings != pending_expected:
            mismatches.append(f'pending_earnings: {driver.pending_earnings} -> {pending_expected}')

        # cod_in_hand should match unsettled COD from tasks
        # If not, we need to sync the cod_settled flags
        cod_task_mismatch = unsettled_cod - cod_in_hand_expected
        if cod_task_mismatch != Decimal('0'):
            mismatches.append(f'Delivery task cod_settled flags out of sync by {cod_task_mismatch} QR')

        if not mismatches:
            self.stdout.write(self.style.SUCCESS('  No mismatches found'))
            return

        self.stdout.write(self.style.WARNING(f'\nMismatches found:'))
        for m in mismatches:
            self.stdout.write(self.style.WARNING(f'  - {m}'))

        if apply:
            with transaction.atomic():
                # Fix driver fields
                driver.cod_in_hand = cod_in_hand_expected
                driver.pending_earnings = pending_expected
                # Recalculate wallet_balance: start from credit_limit, subtract net COD usage
                # wallet = credit_limit + wallet_delta (from COD and adjustments)
                # But we don't know the true initial. Better approach: use cod_in_hand alignment.
                # wallet_balance should be: initial_balance + deposits - collections + bonuses + deductions + adjustments
                # Since initial_balance was set during driver creation and we can't recover it
                # from transactions alone, we align based on the current stored wallet_balance
                # adjusted for the cod_in_hand correction.
                cod_in_hand_diff = driver.cod_in_hand - cod_in_hand_expected
                # If cod_in_hand was too high, wallet was too low by that much (and vice versa)
                # Actually: cod_collection does wallet -= X, cod += X
                #          cod_deposit does wallet += X, cod -= X
                # So wallet + cod = constant (for COD operations only)
                # Therefore: new_wallet = old_wallet + old_cod - new_cod
                # But we already set new cod_in_hand above, use the OLD values
                old_cod = Driver.objects.get(pk=driver.pk).cod_in_hand
                old_wallet = Driver.objects.get(pk=driver.pk).wallet_balance
                # wallet + cod_in_hand should be constant through COD operations
                # so: new_wallet = old_wallet + old_cod - new_cod
                new_wallet = old_wallet + old_cod - cod_in_hand_expected
                driver.wallet_balance = new_wallet

                driver.save(update_fields=['wallet_balance', 'cod_in_hand', 'pending_earnings'])

                self.stdout.write(self.style.SUCCESS(f'  Updated driver fields:'))
                self.stdout.write(f'    wallet_balance:   {new_wallet}')
                self.stdout.write(f'    cod_in_hand:      {cod_in_hand_expected}')
                self.stdout.write(f'    pending_earnings: {pending_expected}')

                # Sync cod_settled flags on delivery tasks
                # Mark tasks as settled to match the deposited amount
                if cod_task_mismatch > Decimal('0'):
                    remaining = cod_task_mismatch
                    tasks_to_settle = DeliveryTask.objects.filter(
                        driver=driver,
                        cod_collected=True,
                        cod_settled=False
                    ).order_by('completed_at')

                    settle_ids = []
                    for task in tasks_to_settle:
                        task_cod = task.cod_collected_amount or Decimal('0')
                        if task_cod <= Decimal('0'):
                            continue
                        if remaining >= task_cod:
                            settle_ids.append(task.id)
                            remaining -= task_cod
                        if remaining <= Decimal('0'):
                            break

                    if settle_ids:
                        DeliveryTask.objects.filter(id__in=settle_ids).update(
                            cod_settled=True, cod_settled_at=timezone.now()
                        )
                        self.stdout.write(self.style.SUCCESS(
                            f'  Marked {len(settle_ids)} delivery tasks as cod_settled'))

            self.stdout.write(self.style.SUCCESS('  Changes applied successfully'))
        else:
            self.stdout.write(self.style.NOTICE('  Run with --apply to fix'))
