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

from fleet.models import Driver, DriverTransaction, DriverSettlement
from delivery.models import DeliveryTask


class WalletService:
    """Service class for managing driver wallet operations"""

    @staticmethod
    def record_transaction(driver, transaction_type, amount, description,
                          delivery_task=None, settlement=None, created_by=None,
                          reference_number=None, notes=None):
        """
        Record a financial transaction and update driver balances

        Args:
            driver: Driver instance
            transaction_type: One of DriverTransaction.TRANSACTION_TYPES
            amount: Decimal amount (positive for credits, negative for debits)
            description: String description of transaction
            delivery_task: Optional DeliveryTask reference
            settlement: Optional DriverSettlement reference
            created_by: Optional User who created the transaction
            reference_number: Optional reference number
            notes: Optional additional notes

        Returns:
            DriverTransaction instance
        """
        with transaction.atomic():
            # Lock the driver row to prevent race conditions
            driver = Driver.objects.select_for_update().get(pk=driver.pk)

            # Update driver balances based on transaction type
            if transaction_type == 'earning':
                driver.pending_earnings += amount
                driver.total_earnings += amount
            elif transaction_type == 'cod_collection':
                # COD collection decreases wallet (like using credit)
                driver.wallet_balance -= abs(amount)
                driver.cod_in_hand += abs(amount)
            elif transaction_type == 'cod_deposit':
                # COD deposit increases wallet (like making payment)
                driver.wallet_balance += abs(amount)
                driver.cod_in_hand -= abs(amount)
            elif transaction_type == 'settlement':
                # Settlement clears pending earnings
                driver.pending_earnings -= abs(amount)
                driver.last_settlement_date = timezone.now()
            elif transaction_type in ['deduction', 'bonus', 'adjustment']:
                # These affect wallet balance directly
                driver.wallet_balance += amount

            driver.save()

            # Create transaction record
            trans = DriverTransaction.objects.create(
                driver=driver,
                transaction_type=transaction_type,
                amount=amount,
                description=description,
                reference_number=reference_number,
                delivery_task=delivery_task,
                settlement=settlement,
                wallet_balance_after=driver.wallet_balance,
                cod_in_hand_after=driver.cod_in_hand,
                pending_earnings_after=driver.pending_earnings,
                created_by=created_by,
                notes=notes
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
    def submit_cod_to_admin(driver, amount, created_by=None, reference_number=None, notes=None):
        """
        Process driver's COD submission to admin

        Args:
            driver: Driver instance
            amount: Decimal amount being submitted
            created_by: User processing the submission
            reference_number: Optional payment/deposit reference
            notes: Optional notes

        Returns:
            DriverTransaction instance
        """
        if driver.cod_in_hand < amount:
            raise ValueError(f"Driver only has {driver.cod_in_hand} QR in hand, cannot submit {amount} QR")

        trans = WalletService.record_transaction(
            driver=driver,
            transaction_type='cod_deposit',
            amount=amount,
            description=f"COD deposit to admin - {amount} QR",
            created_by=created_by,
            reference_number=reference_number,
            notes=notes
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

        available_credit = driver.available_credit
        if cod_amount > available_credit:
            return False, f"Insufficient credit. Available: {available_credit} QR, Required: {cod_amount} QR"

        # Check if accepting would exceed limit
        new_balance = driver.wallet_balance - cod_amount
        if new_balance < 0 and abs(new_balance) > driver.credit_limit:
            return False, f"This order would exceed your credit limit of {driver.credit_limit} QR"

        return True, "OK"

    @staticmethod
    def get_wallet_status(driver):
        """
        Get comprehensive wallet status information

        Args:
            driver: Driver instance

        Returns:
            dict with wallet status details
        """
        return {
            'wallet_balance': driver.wallet_balance,
            'credit_limit': driver.credit_limit,
            'available_credit': driver.available_credit,
            'cod_in_hand': driver.cod_in_hand,
            'pending_earnings': driver.pending_earnings,
            'total_earnings': driver.total_earnings,
            'usage_percentage': driver.wallet_usage_percentage,
            'is_warning': driver.is_wallet_warning,
            'is_blocked': driver.is_wallet_blocked,
            'warning_message': "Warning: Wallet usage at 80% or above" if driver.is_wallet_warning else None,
            'block_message': "Wallet exhausted. Submit COD to continue accepting orders." if driver.is_wallet_blocked else None
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
        start_date = timezone.now() - timedelta(days=days)

        deliveries = DeliveryTask.objects.filter(
            driver=driver,
            completed_at__gte=start_date
        )

        stats = deliveries.aggregate(
            total_deliveries=Count('id'),
            total_earnings=Sum('driver_earnings'),
            total_cod_collected=Sum('cod_collected_amount'),
            successful=Count('id', filter=Q(dl_task_status_dms='2')),
            failed=Count('id', filter=Q(dl_task_status_dms='3'))
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
