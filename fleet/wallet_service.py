"""
Wallet Management Service for Fleet COD System

This service handles all business logic related to:
- Driver wallet balance management
- COD collection tracking
- Earnings calculation and processing
- Transaction recording
- Settlement generation
- Wallet status checks
"""

from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import datetime, timedelta

from fleet import models as fleet_models
from delivery import models as delivery_models

# Local aliases for commonly used models
Driver = fleet_models.Driver
DriverTransaction = fleet_models.DriverTransaction
DriverSettlement = fleet_models.DriverSettlement
DeliveryTask = delivery_models.DeliveryTask


class WalletService:
    """Service class for managing driver wallet operations"""

    @staticmethod
    def record_transaction(driver, transaction_type, amount, description,
                          delivery_task=None, settlement=None, created_by=None,
                          reference_number=None, notes=None, payment_method=None,
                          business=None):
        """
        Record a financial transaction and update driver balances

        Args:
            driver: Driver instance (optional for accounting-only transactions)
            transaction_type: One of DriverTransaction.TRANSACTION_TYPES
            amount: Decimal amount (positive for credits, negative for debits)
            description: String description of transaction
            delivery_task: Optional DeliveryTask reference
            settlement: Optional DriverSettlement reference
            created_by: Optional User who created the transaction
            reference_number: Optional reference number
            notes: Optional additional notes
            payment_method: Optional payment method (cash, bank, atm, fawran)
            business: Optional Business instance for business-linked transactions

        Returns:
            DriverTransaction instance
        """
        # Types that affect driver wallet balances
        DRIVER_WALLET_TYPES = [
            'earning', 'cod_collection', 'cod_deposit', 'cod_driver_settle',
            'cod_return', 'settlement', 'deduction', 'bonus', 'adjustment',
        ]

        with transaction.atomic():
            # Lock the driver row if this transaction affects driver balances
            if driver and transaction_type in DRIVER_WALLET_TYPES:
                driver = Driver.objects.select_for_update().get(pk=driver.pk)

                # Update driver balances based on transaction type
                if transaction_type == 'earning':
                    driver.pending_earnings += amount
                    driver.total_earnings += amount
                elif transaction_type == 'cod_collection':
                    driver.wallet_balance -= abs(amount)
                    driver.cod_in_hand += abs(amount)
                elif transaction_type in ['cod_deposit', 'cod_driver_settle']:
                    driver.wallet_balance += abs(amount)
                    driver.cod_in_hand -= abs(amount)
                elif transaction_type == 'cod_return':
                    driver.wallet_balance += abs(amount)
                    driver.cod_in_hand -= abs(amount)
                elif transaction_type == 'settlement':
                    driver.pending_earnings -= abs(amount)
                    driver.last_settlement_date = timezone.now()
                elif transaction_type in ['deduction', 'bonus', 'adjustment']:
                    driver.wallet_balance += amount

                driver.save()

            # Calculate COD breakdown by payment method (running balance up to this point)
            cod_cash_after = Decimal('0')
            cod_pos_after = Decimal('0')
            cod_fawran_after = Decimal('0')
            cod_bank_after = Decimal('0')
            cod_atm_after = Decimal('0')

            if driver and transaction_type in ('cod_collection', 'cod_deposit', 'cod_driver_settle'):
                # Get all COD collected up to now (delivered but not yet settled)
                settled_task_ids = DriverTransaction.objects.filter(
                    driver=driver,
                    transaction_type__in=['cod_driver_settle', 'cod_deposit'],
                    delivery_task_id__isnull=False,
                    created_at__lte=timezone.now()
                ).values_list('delivery_task_id', flat=True)

                cod_collected = DeliveryTask.objects.filter(
                    driver=driver,
                    cod_collected=True,
                    dl_task_status='delivered',
                    completed_at__isnull=False
                ).exclude(id__in=settled_task_ids)

                cod_cash_after = cod_collected.filter(payment_method='cash').aggregate(
                    total=Sum('cod_collected_amount'))['total'] or Decimal('0')
                cod_pos_after = cod_collected.filter(payment_method='pos').aggregate(
                    total=Sum('cod_collected_amount'))['total'] or Decimal('0')
                cod_fawran_after = cod_collected.filter(payment_method='fawran').aggregate(
                    total=Sum('cod_collected_amount'))['total'] or Decimal('0')
                cod_bank_after = cod_collected.filter(payment_method='bank').aggregate(
                    total=Sum('cod_collected_amount'))['total'] or Decimal('0')
                cod_atm_after = cod_collected.filter(payment_method='atm').aggregate(
                    total=Sum('cod_collected_amount'))['total'] or Decimal('0')

            # Create transaction record
            trans = DriverTransaction.objects.create(
                driver=driver,
                business=business,
                transaction_type=transaction_type,
                amount=amount,
                description=description,
                reference_number=reference_number,
                delivery_task=delivery_task,
                settlement=settlement,
                wallet_balance_after=driver.wallet_balance if driver else Decimal('0'),
                cod_in_hand_after=driver.cod_in_hand if driver else Decimal('0'),
                pending_earnings_after=driver.pending_earnings if driver else Decimal('0'),
                cod_cash_after=cod_cash_after,
                cod_pos_after=cod_pos_after,
                cod_fawran_after=cod_fawran_after,
                cod_bank_after=cod_bank_after,
                cod_atm_after=cod_atm_after,
                created_by=created_by,
                notes=notes,
                payment_method=payment_method
            )

            return trans

    @staticmethod
    def process_delivery_completion(delivery_task, created_by=None):
        """
        Process a delivery completion: calculate earnings, handle COD

        Args:
            delivery_task: DeliveryTask instance
            created_by: Optional User processing the completion

        Returns:
            dict with transaction details
        """
        if delivery_task.earnings_processed:
            return {'status': 'error', 'message': 'Earnings already processed'}

        if not delivery_task.driver:
            return {'status': 'error', 'message': 'No driver assigned'}

        with transaction.atomic():
            # Calculate earnings (example: 80% to driver, 20% commission)
            delivery_charge = Decimal(delivery_task.dl_price or 0)
            driver_earnings = delivery_charge * Decimal('0.80')
            company_commission = delivery_charge * Decimal('0.20')

            # Update delivery task
            delivery_task.driver_earnings = driver_earnings
            delivery_task.company_commission = company_commission
            delivery_task.completed_at = timezone.now()
            delivery_task.earnings_processed = True
            delivery_task.save()

            # Record earnings transaction
            earning_trans = WalletService.record_transaction(
                driver=delivery_task.driver,
                transaction_type='earning',
                amount=driver_earnings,
                description=f"Delivery earnings for task {delivery_task.dl_task_number}",
                delivery_task=delivery_task,
                created_by=created_by,
                reference_number=delivery_task.dl_task_number
            )

            # Handle COD if applicable
            cod_trans = None
            if delivery_task.has_cod and delivery_task.cod_collected:
                cod_amount = delivery_task.cod_collected_amount or delivery_task.order.cod_amount

                # Set cod_collected_at timestamp if not already set
                if not delivery_task.cod_collected_at:
                    delivery_task.cod_collected_at = timezone.now()
                    delivery_task.save(update_fields=['cod_collected_at'])

                cod_trans = WalletService.record_transaction(
                    driver=delivery_task.driver,
                    transaction_type='cod_collection',
                    amount=cod_amount,
                    description=f"COD collected for task {delivery_task.dl_task_number}",
                    delivery_task=delivery_task,
                    created_by=created_by,
                    reference_number=delivery_task.dl_task_number
                )

            return {
                'status': 'success',
                'driver_earnings': driver_earnings,
                'company_commission': company_commission,
                'cod_collected': delivery_task.cod_collected_amount if cod_trans else 0,
                'transactions': [earning_trans, cod_trans] if cod_trans else [earning_trans]
            }

    @staticmethod
    def submit_cod_to_admin(driver, amount, created_by=None, reference_number=None, notes=None, payment_method=None, delivery_ids=None):
        """
        Process driver's COD submission to admin

        Args:
            driver: Driver instance
            amount: Decimal amount being submitted
            created_by: User processing the submission
            reference_number: Optional payment/deposit reference
            notes: Optional notes
            payment_method: Optional payment method (cash, bank, atm, fawran)
            delivery_ids: Optional list of delivery task IDs to mark as settled

        Returns:
            DriverTransaction instance
        """
        if driver.cod_in_hand < amount:
            raise ValueError(f"Driver only has {driver.cod_in_hand} QR in hand, cannot submit {amount} QR")

        # Get payment method display name for description
        payment_method_display = {
            'cash': 'Cash',
            'bank': 'Bank Transfer',
            'atm': 'ATM Deposit',
            'fawran': 'Fawran'
        }.get(payment_method, 'Cash')

        trans = WalletService.record_transaction(
            driver=driver,
            transaction_type='cod_deposit',
            amount=amount,
            description=f"COD deposit to admin - {amount} QR via {payment_method_display}",
            created_by=created_by,
            reference_number=reference_number,
            notes=notes,
            payment_method=payment_method
        )

        # Mark corresponding delivery tasks as COD settled
        settled_task_ids = []
        now = timezone.now()
        if delivery_ids:
            # Settle specific deliveries
            settled_task_ids = list(DeliveryTask.objects.filter(
                id__in=delivery_ids,
                driver=driver,
                cod_collected=True,
                cod_settled=False
            ).values_list('id', flat=True))
            DeliveryTask.objects.filter(id__in=settled_task_ids).update(
                cod_settled=True, cod_settled_at=now, cod_submission_txn=trans
            )
        else:
            # No specific IDs provided - settle oldest unsettled tasks up to the deposit amount
            remaining = Decimal(str(amount))
            unsettled_tasks = DeliveryTask.objects.filter(
                driver=driver,
                cod_collected=True,
                cod_settled=False
            ).order_by('completed_at')

            for task in unsettled_tasks:
                task_cod = task.cod_collected_amount or Decimal('0')
                if task_cod <= Decimal('0'):
                    continue
                if remaining >= task_cod:
                    settled_task_ids.append(task.id)
                    remaining -= task_cod
                if remaining <= Decimal('0'):
                    break

            if settled_task_ids:
                DeliveryTask.objects.filter(id__in=settled_task_ids).update(
                    cod_settled=True, cod_settled_at=now, cod_submission_txn=trans
                )

        # Update order COD status to 'cod_with_ezzy' for settled tasks
        if settled_task_ids:
            from orders.models import Order
            order_ids = list(DeliveryTask.objects.filter(
                id__in=settled_task_ids
            ).values_list('order_id', flat=True))
            if order_ids:
                Order.objects.filter(id__in=order_ids).update(
                    cod_status_by_staff='cod_with_ezzy'
                )

        return trans

    @staticmethod
    def recalculate_cod_balances(driver):
        """
        Recalculate cod_cash_after, cod_fawran_after, cod_pos_after for all COD
        transactions in chronological order. Saves any changed values back to DB.
        Called on each fleet_transactions page load to keep balances accurate.
        """
        txns = list(
            DriverTransaction.objects.filter(
                driver=driver,
                transaction_type__in=['cod_collection', 'cod_deposit', 'cod_driver_settle']
            ).select_related('delivery_task').order_by('created_at')
        )

        running_cash = Decimal('0')
        running_fawran = Decimal('0')
        running_pos = Decimal('0')
        to_update = []

        for t in txns:
            if t.transaction_type in ['cod_deposit', 'cod_driver_settle']:
                running_cash = Decimal('0')
                running_fawran = Decimal('0')
                running_pos = Decimal('0')
                # After a deposit the running balance should be 0
                if t.cod_cash_after != 0 or t.cod_fawran_after != 0 or t.cod_pos_after != 0:
                    t.cod_cash_after = Decimal('0')
                    t.cod_fawran_after = Decimal('0')
                    t.cod_pos_after = Decimal('0')
                    to_update.append(t)
                continue

            method = (
                (t.delivery_task.payment_method if t.delivery_task else None)
                or t.payment_method
                or 'cash'
            )
            amt = abs(t.amount)

            if method == 'cash':
                running_cash += amt
            elif method == 'fawran':
                running_fawran += amt
            elif method in ['pos', 'card']:
                running_pos += amt
            else:
                running_cash += amt

            if (t.cod_cash_after != running_cash
                    or t.cod_fawran_after != running_fawran
                    or t.cod_pos_after != running_pos):
                t.cod_cash_after = running_cash
                t.cod_fawran_after = running_fawran
                t.cod_pos_after = running_pos
                to_update.append(t)

        if to_update:
            DriverTransaction.objects.bulk_update(
                to_update, ['cod_cash_after', 'cod_fawran_after', 'cod_pos_after']
            )

        return len(to_update)

    @staticmethod
    def settle_cod_with_client(business, amount, delivery_task_ids=None,
                               created_by=None, reference_number=None, notes=None,
                               payment_method=None):
        """
        Record COD settlement from EzzyDelivery to business client.

        Args:
            business: Business instance receiving the COD
            amount: Decimal amount being settled
            delivery_task_ids: Optional list of DeliveryTask IDs included
            created_by: User processing the settlement
            reference_number: Payment reference
            notes: Optional notes
            payment_method: Payment method used

        Returns:
            DriverTransaction instance
        """
        with transaction.atomic():
            trans = WalletService.record_transaction(
                driver=None,
                transaction_type='cod_client_settle',
                amount=amount,
                description=f"COD settlement to {business.business_name} - {amount} QR",
                created_by=created_by,
                reference_number=reference_number,
                notes=notes,
                payment_method=payment_method,
                business=business
            )

            if delivery_task_ids:
                DeliveryTask.objects.filter(
                    id__in=delivery_task_ids,
                    cod_collected=True
                ).update(
                    cod_client_settled=True,
                    cod_client_settled_at=timezone.now()
                )

            return trans

    @staticmethod
    def record_cod_return(driver, delivery_task, amount, created_by=None, notes=None):
        """
        Record a COD return/reversal for a returned order.

        Args:
            driver: Driver instance
            delivery_task: DeliveryTask being returned
            amount: Decimal COD amount to reverse
            created_by: User processing the return
            notes: Optional notes

        Returns:
            DriverTransaction instance
        """
        trans = WalletService.record_transaction(
            driver=driver,
            transaction_type='cod_return',
            amount=amount,
            description=f"COD return for task {delivery_task.dl_task_number}",
            delivery_task=delivery_task,
            created_by=created_by,
            reference_number=delivery_task.dl_task_number,
            notes=notes
        )
        return trans

    @staticmethod
    def record_charge(charge_type, amount, description, delivery_task=None,
                      driver=None, business=None, created_by=None,
                      reference_number=None, notes=None):
        """
        Record a service charge (delivery, fulfillment, inventory, other).

        Args:
            charge_type: One of 'delivery_charge', 'fulfillment_charge',
                         'inventory_handling', 'other_charge'
            amount: Decimal charge amount
            description: Charge description
            delivery_task: Optional related DeliveryTask
            driver: Optional Driver instance
            business: Optional Business instance
            created_by: User recording the charge
            reference_number: Optional reference
            notes: Optional notes

        Returns:
            DriverTransaction instance
        """
        valid_charge_types = [
            'delivery_charge', 'fulfillment_charge',
            'inventory_handling', 'other_charge'
        ]
        if charge_type not in valid_charge_types:
            raise ValueError(f"Invalid charge type: {charge_type}. Must be one of {valid_charge_types}")

        trans = WalletService.record_transaction(
            driver=driver,
            transaction_type=charge_type,
            amount=amount,
            description=description,
            delivery_task=delivery_task,
            created_by=created_by,
            reference_number=reference_number,
            notes=notes,
            business=business
        )
        return trans

    @staticmethod
    def record_accounting_entry(entry_type, amount, description, business=None,
                                created_by=None, reference_number=None, notes=None):
        """
        Record an accounting entry (bills payable or bills receivable).

        Args:
            entry_type: One of 'bills_payable', 'bills_receivable'
            amount: Decimal amount
            description: Entry description
            business: Optional Business instance
            created_by: User recording the entry
            reference_number: Optional reference
            notes: Optional notes

        Returns:
            DriverTransaction instance
        """
        valid_types = ['bills_payable', 'bills_receivable']
        if entry_type not in valid_types:
            raise ValueError(f"Invalid entry type: {entry_type}. Must be one of {valid_types}")

        trans = WalletService.record_transaction(
            driver=None,
            transaction_type=entry_type,
            amount=amount,
            description=description,
            created_by=created_by,
            reference_number=reference_number,
            notes=notes,
            business=business
        )
        return trans

    @staticmethod
    def can_accept_cod_order(driver, cod_amount):
        """
        Check if driver has sufficient wallet balance to accept COD order

        Args:
            driver: Driver instance
            cod_amount: Decimal COD amount of order

        Returns:
            tuple (bool, str): (can_accept, reason)
        """
        if driver.is_wallet_blocked:
            return False, "Wallet balance exhausted. Please submit COD to admin."

        available_credit = driver.available_credit  # credit_limit - cod_in_hand
        if cod_amount > available_credit:
            return False, f"Insufficient credit. Available: {available_credit} QR, Required: {cod_amount} QR"

        return True, "OK"

    @staticmethod
    def get_wallet_status(driver):
        """
        Get comprehensive wallet status information.
        COD in hand and wallet balance are computed live from DeliveryTask
        to avoid stale cached field values.
        """
        # Live COD: collected but not yet settled
        live_cod = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            cod_collected=True,
            cod_settled=False,
        ).aggregate(total=Sum('cod_collected_amount'))['total'] or Decimal('0.00')

        # Live wallet balance from transactions
        txn_balance = fleet_models.DriverTransaction.objects.filter(
            driver=driver
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        live_wallet = max(txn_balance, Decimal('0.00'))

        credit_limit = driver.credit_limit
        available_credit = max(credit_limit - live_cod, Decimal('0.00'))
        usage_pct = (live_cod / credit_limit * 100) if credit_limit else Decimal('0')
        is_warning = usage_pct >= 80
        is_blocked = live_cod >= credit_limit

        return {
            'wallet_balance': live_wallet,
            'credit_limit': credit_limit,
            'available_credit': available_credit,
            'cod_in_hand': live_cod,
            'pending_earnings': driver.pending_earnings,
            'total_earnings': driver.total_earnings,
            'usage_percentage': usage_pct,
            'is_warning': is_warning,
            'is_blocked': is_blocked,
            'warning_message': "Warning: Wallet usage at 80% or above" if is_warning else None,
            'block_message': "Wallet exhausted. Submit COD to continue accepting orders." if is_blocked else None
        }

    @staticmethod
    def generate_settlement(driver, period_start, period_end, created_by=None, notes=None):
        """
        Generate a settlement for driver's earnings in given period

        Args:
            driver: Driver instance
            period_start: datetime.date for period start
            period_end: datetime.date for period end
            created_by: User creating the settlement
            notes: Optional notes

        Returns:
            DriverSettlement instance
        """
        with transaction.atomic():
            # Get completed deliveries in period
            deliveries = DeliveryTask.objects.filter(
                driver=driver,
                completed_at__date__gte=period_start,
                completed_at__date__lte=period_end,
                earnings_processed=True
            )

            # Calculate statistics
            total_deliveries = deliveries.count()
            stats = deliveries.aggregate(
                total_charges=Sum('dl_price'),
                total_earnings=Sum('driver_earnings')
            )

            gross_earnings = stats['total_earnings'] or Decimal('0.00')
            total_delivery_charges = stats['total_charges'] or Decimal('0.00')

            # Get deductions in period (if any)
            deductions = DriverTransaction.objects.filter(
                driver=driver,
                transaction_type='deduction',
                created_at__date__gte=period_start,
                created_at__date__lte=period_end
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

            # Get bonuses in period (if any)
            bonuses = DriverTransaction.objects.filter(
                driver=driver,
                transaction_type='bonus',
                created_at__date__gte=period_start,
                created_at__date__lte=period_end
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

            # Calculate net amount
            net_amount = gross_earnings + bonuses - abs(deductions)

            # Create settlement
            settlement = DriverSettlement.objects.create(
                driver=driver,
                period_start=period_start,
                period_end=period_end,
                total_deliveries=total_deliveries,
                total_delivery_charges=total_delivery_charges,
                gross_earnings=gross_earnings,
                deductions=abs(deductions),
                bonuses=bonuses,
                net_amount=net_amount,
                status='pending',
                created_by=created_by,
                notes=notes
            )

            return settlement

    @staticmethod
    def approve_settlement(settlement, approved_by):
        """
        Approve a pending settlement

        Args:
            settlement: DriverSettlement instance
            approved_by: User approving the settlement

        Returns:
            Updated DriverSettlement instance
        """
        if settlement.status != 'pending':
            raise ValueError(f"Cannot approve settlement with status: {settlement.status}")

        settlement.status = 'approved'
        settlement.approved_by = approved_by
        settlement.approved_at = timezone.now()
        settlement.save()

        return settlement

    @staticmethod
    def mark_settlement_paid(settlement, payment_method, payment_reference, paid_by=None):
        """
        Mark settlement as paid and record transaction

        Args:
            settlement: DriverSettlement instance
            payment_method: String (Cash, Bank Transfer, etc.)
            payment_reference: Transaction ID or reference
            paid_by: Optional User who processed payment

        Returns:
            tuple (settlement, transaction)
        """
        if settlement.status != 'approved':
            raise ValueError(f"Can only mark approved settlements as paid. Current status: {settlement.status}")

        with transaction.atomic():
            # Update settlement
            settlement.status = 'paid'
            settlement.payment_method = payment_method
            settlement.payment_reference = payment_reference
            settlement.paid_at = timezone.now()
            settlement.save()

            # Record settlement transaction
            trans = WalletService.record_transaction(
                driver=settlement.driver,
                transaction_type='settlement',
                amount=settlement.net_amount,
                description=f"Settlement payment for period {settlement.period_start} to {settlement.period_end}",
                settlement=settlement,
                created_by=paid_by,
                reference_number=settlement.settlement_code,
                notes=f"Paid via {payment_method}: {payment_reference}"
            )

            return settlement, trans

    @staticmethod
    def get_driver_statistics(driver, days=30):
        """
        Get driver performance statistics for dashboard

        Args:
            driver: Driver instance
            days: Number of days to look back (default 30)

        Returns:
            dict with statistics
        """
        if days == 1:
            # "Today" means calendar day midnight-to-now, not last 24h
            today = timezone.localdate()
            start_date = timezone.make_aware(
                timezone.datetime.combine(today, timezone.datetime.min.time())
            )
        else:
            start_date = timezone.now() - timedelta(days=days)

        deliveries = DeliveryTask.objects.filter(
            driver=driver,
            completed_at__gte=start_date
        )

        stats = deliveries.aggregate(
            total_deliveries=Count('id'),
            total_earnings=Sum('driver_earnings'),
            total_cod_collected=Sum('cod_collected_amount'),
            successful=Count('id', filter=Q(dl_task_status='delivered')),
            failed=Count('id', filter=Q(dl_task_status='failed'))
        )

        return {
            'period_days': days,
            'total_deliveries': stats['total_deliveries'] or 0,
            'successful_deliveries': stats['successful'] or 0,
            'failed_deliveries': stats['failed'] or 0,
            'total_earnings': stats['total_earnings'] or Decimal('0.00'),
            'total_cod_collected': stats['total_cod_collected'] or Decimal('0.00'),
            'success_rate': (stats['successful'] / stats['total_deliveries'] * 100) if stats['total_deliveries'] else 0,
            'current_wallet': driver.wallet_balance,
            'cod_in_hand': driver.cod_in_hand,
            'pending_earnings': driver.pending_earnings
        }

    @staticmethod
    def record_earnings_from_batch_pickup(batch):
        """
        Record driver earnings for a completed hub pickup batch ride.
        Called when HubPickupBatch.status → 'at_hub'.

        Args:
            batch: HubPickupBatch instance

        Returns:
            dict with transaction details
        """
        if batch.earnings_processed:
            return {'status': 'error', 'message': 'Batch earnings already processed'}
        if not batch.driver:
            return {'status': 'error', 'message': 'No driver assigned to batch'}
        if not batch.driver_earnings or batch.driver_earnings <= 0:
            return {'status': 'skipped', 'message': 'No earnings to record (driver_earnings = 0)'}

        with transaction.atomic():
            earning_trans = WalletService.record_transaction(
                driver=batch.driver,
                transaction_type='earning',
                amount=batch.driver_earnings,
                description=f"Hub pickup batch earnings — {batch.batch_number} "
                            f"({batch.order_count} order{'s' if batch.order_count != 1 else ''})",
                created_by=None,
                reference_number=batch.batch_number
            )
            from delivery.models import HubPickupBatch as _HubPickupBatch
            _HubPickupBatch.objects.filter(pk=batch.pk).update(earnings_processed=True)

        return {
            'status': 'success',
            'driver_earnings': batch.driver_earnings,
            'transaction': earning_trans,
        }


class WalletAlertService:
    """Service for wallet-related alerts and notifications"""

    @staticmethod
    def check_wallet_alerts(driver):
        """
        Check for wallet alerts that need driver attention

        Args:
            driver: Driver instance

        Returns:
            list of alert dicts
        """
        alerts = []

        # Critical: Wallet blocked
        if driver.is_wallet_blocked:
            alerts.append({
                'level': 'danger',
                'icon': 'fa-ban',
                'title': 'Wallet Blocked',
                'message': f'Your wallet balance is exhausted. You have {driver.cod_in_hand} QR COD in hand. Please submit COD to admin to continue accepting orders.',
                'action': 'Submit COD Now',
                'action_url': '/fleet/cod-submission/'
            })

        # Warning: 80% or above
        elif driver.is_wallet_warning:
            alerts.append({
                'level': 'warning',
                'icon': 'fa-exclamation-triangle',
                'title': 'Wallet Warning',
                'message': f'Your wallet is at {driver.wallet_usage_percentage:.1f}% usage. Available credit: {driver.available_credit} QR. Consider submitting COD soon.',
                'action': 'View COD Status',
                'action_url': '/fleet/cod-collection/'
            })

        # Info: High COD in hand
        if driver.cod_in_hand > 1000:
            alerts.append({
                'level': 'info',
                'icon': 'fa-money-bill',
                'title': 'High COD Amount',
                'message': f'You have {driver.cod_in_hand} QR COD in hand. Consider submitting to admin.',
                'action': 'Submit COD',
                'action_url': '/fleet/cod-submission/'
            })

        # Success: Pending earnings available
        if driver.pending_earnings > 0:
            alerts.append({
                'level': 'success',
                'icon': 'fa-coins',
                'title': 'Earnings Available',
                'message': f'You have {driver.pending_earnings} QR in pending earnings ready for settlement.',
                'action': 'View Earnings',
                'action_url': '/fleet/earnings/'
            })

        return alerts
