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

from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import datetime, timedelta

from fleet import models as fleet_models
from delivery import models as delivery_models
from orders.cod_status import CLIENT_STATES_NOT_DERIVED

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

                # Update driver balances based on transaction type.
                # NOTE: neither cod_in_hand nor wallet_balance is accumulated here.
                # Both are denormalizations of the task truth and are re-derived by
                # sync_cod_in_hand() at the point the task COD state actually changes
                # (collection / submission / return). Accumulating a COD delta here
                # as well would double-count, and accumulating it from the passed
                # payment_method — which is null on ~14% of rows — is what let
                # wallet_balance drift away from cod_in_hand in the first place.
                if transaction_type == 'earning':
                    driver.pending_earnings += amount
                    driver.total_earnings += amount
                    driver.save(update_fields=['pending_earnings', 'total_earnings'])
                elif transaction_type == 'settlement':
                    driver.pending_earnings -= abs(amount)
                    driver.last_settlement_date = timezone.now()
                    driver.save(update_fields=['pending_earnings', 'last_settlement_date'])
                # deduction / bonus / adjustment and every COD type are folded in
                # by the sync_cod_in_hand() call after the row exists — running it
                # here would miss the row being written right now.

            # Per-method COD balances are stamped after the row exists, by
            # replaying the ledger in recalculate_cod_balances() below. They
            # cannot be derived from a point-in-time query here: a deposit links
            # the tasks it settled through DeliveryTask.cod_submission_txn, not
            # through DriverTransaction.delivery_task, so a "not yet settled"
            # lookup from this side sees nothing and returns lifetime totals.
            cod_cash_after = Decimal('0')
            cod_pos_after = Decimal('0')
            cod_fawran_after = Decimal('0')
            cod_bank_after = Decimal('0')
            cod_atm_after = Decimal('0')

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

            # Stamp the running per-method balances on the new row immediately.
            # Without this the row carries zeros until the staff transactions
            # page happens to run the recalc (once per driver per day), so any
            # consumer reading it before then — CSV export, print voucher,
            # driver PWA, API — sees a balance that was never true.
            if driver and transaction_type in DRIVER_WALLET_TYPES:
                # Re-derive cod_in_hand and wallet_balance from the task truth now
                # that this row exists. Doing it here rather than trusting each
                # caller means no COD path can leave the cached balances stale.
                WalletService.sync_cod_in_hand(driver)

                # Re-stamp the "after" columns from the just-synced driver. They
                # were written above from the pre-sync values, which is the
                # balance BEFORE this transaction — every ledger row (COD ledger,
                # PWA transaction detail, print voucher, CSV, API) was showing a
                # running balance one row behind itself.
                trans.wallet_balance_after = driver.wallet_balance
                trans.cod_in_hand_after = driver.cod_in_hand
                trans.pending_earnings_after = driver.pending_earnings
                trans.save(update_fields=[
                    'wallet_balance_after', 'cod_in_hand_after', 'pending_earnings_after',
                ])

            if driver and transaction_type in ('cod_collection', 'cod_deposit', 'cod_driver_settle'):
                WalletService.recalculate_cod_balances(driver)
                trans.refresh_from_db()

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

        Concurrency: the whole check-and-act runs in one transaction with the
        driver row and the candidate task rows locked (select_for_update). The
        deposit amount is derived from the tasks that are ACTUALLY newly settled
        inside the lock, so two concurrent submissions of the same cash cannot
        both decrement cod_in_hand, and a duplicate submission is a no-op
        (nothing left to settle -> ValueError, no money movement).
        """
        # Get payment method display name for description
        payment_method_display = {
            'cash': 'Cash',
            'bank': 'Bank Transfer',
            'atm': 'ATM Deposit',
            'fawran': 'Fawran'
        }.get(payment_method, 'Cash')

        now = timezone.now()

        with transaction.atomic():
            # Lock the driver row for the entire check-and-act so concurrent
            # submissions serialize instead of both reading a stale cod_in_hand.
            driver = Driver.objects.select_for_update().get(pk=driver.pk)

            # Lock the candidate unsettled tasks so a concurrent submission cannot
            # claim the same rows. Determine which to settle and their COD sum.
            # A task counts for its CASH LEG only: electronic collections
            # (Fawran/POS/bank/ATM) settled to Ezzy at collection and are never
            # part of a hand-in, while a mixed collection still owes its cash
            # portion. task_cash_leg() returns 0 for the electronic-only ones,
            # so they drop out of both loops below on their own.
            base_qs = DeliveryTask.objects.select_for_update().filter(
                driver=driver, cod_collected=True, cod_settled=False
            )
            settled_task_ids = []
            settled_amount = Decimal('0')

            if delivery_ids:
                # Itemized submission: settle exactly the requested tasks that are
                # still unsettled, and deposit their actual COD sum. This makes a
                # duplicate submission of the same tasks a no-op.
                for task in base_qs.filter(id__in=delivery_ids):
                    task_cod = WalletService.task_cash_leg(task)
                    if task_cod <= Decimal('0'):
                        continue
                    settled_task_ids.append(task.id)
                    settled_amount += task_cod

                # Idempotency: the specific tasks were already settled -> no money moves.
                if not settled_task_ids:
                    raise ValueError("No unsettled COD found for this submission (already submitted?)")
                deposit_amount = settled_amount
            else:
                # Amount-based submission: settle oldest unsettled tasks up to the
                # requested amount, and deposit the requested amount. cod_in_hand is
                # re-read under the lock below, so this is race-safe.
                remaining = Decimal(str(amount))
                for task in base_qs.order_by('completed_at'):
                    task_cod = WalletService.task_cash_leg(task)
                    if task_cod <= Decimal('0'):
                        continue
                    if remaining >= task_cod:
                        settled_task_ids.append(task.id)
                        remaining -= task_cod
                    if remaining <= Decimal('0'):
                        break
                deposit_amount = Decimal(str(amount))

            # Re-validate against the single source of truth (derived from tasks).
            # A concurrent submission that already ran will have settled the tasks,
            # so the loser sees a reduced live balance and fails here.
            live_before = WalletService.live_cod_in_hand(driver)
            if live_before < deposit_amount:
                raise ValueError(
                    f"Driver only has {live_before} QR in hand, cannot submit {deposit_amount} QR"
                )

            # Settle the tasks FIRST so cod_in_hand derives to its post-submit value,
            # then refresh the cached denormalization before snapshotting it.
            if settled_task_ids:
                DeliveryTask.objects.filter(id__in=settled_task_ids).update(
                    cod_settled=True, cod_settled_at=now
                )
            WalletService.sync_cod_in_hand(driver)

            trans = WalletService.record_transaction(
                driver=driver,
                transaction_type='cod_deposit',
                amount=deposit_amount,
                description=f"COD deposit to admin - {deposit_amount} QR via {payment_method_display}",
                created_by=created_by,
                reference_number=reference_number,
                notes=notes,
                payment_method=payment_method
            )

            if settled_task_ids:
                DeliveryTask.objects.filter(id__in=settled_task_ids).update(
                    cod_submission_txn=trans
                )
                # Update order COD status to 'cod_with_ezzy' for settled tasks
                from orders.models import Order
                order_ids = list(DeliveryTask.objects.filter(
                    id__in=settled_task_ids
                ).values_list('order_id', flat=True))
                if order_ids:
                    Order.objects.filter(id__in=order_ids).exclude(
                        cod_status_by_client__in=CLIENT_STATES_NOT_DERIVED
                    ).update(
                        cod_status_by_staff='cod_with_ezzy',
                        cod_status_by_client='received_by_company',
                    )
                    Order.objects.filter(
                        id__in=order_ids,
                        cod_status_by_client__in=CLIENT_STATES_NOT_DERIVED,
                    ).update(cod_status_by_staff='cod_with_ezzy')

            # Stamp the running COD balances on the whole ledger now that the
            # settled tasks are linked, so the new deposit row shows the amount
            # still in hand immediately (not only after the next page load).
            WalletService.recalculate_cod_balances(driver)
            trans.refresh_from_db()

        return trans

    @staticmethod
    def recalculate_cod_balances(driver):
        """
        Recalculate cod_cash_after, cod_fawran_after, cod_pos_after for all COD
        transactions in chronological order. Saves any changed values back to DB.
        Called on each fleet_transactions page load to keep balances accurate.

        A deposit does NOT blank the ledger: it subtracts what was actually
        handed in, so a partial hand-in leaves the remaining cash on the
        driver's running balance. Per-method amounts come from the tasks the
        deposit settled (cod_submission_txn); older deposits with no linked
        tasks fall back to debiting the deposit amount against cash. Fawran/POS
        are already in Ezzy's bank, so any deposit sweeps them off the ledger.
        """
        txns = list(
            DriverTransaction.objects.filter(
                driver=driver,
                transaction_type__in=['cod_collection', 'cod_deposit', 'cod_driver_settle']
            ).select_related('delivery_task').order_by('created_at')
        )

        # Per-deposit settled amounts by method, from the tasks each deposit settled
        deposit_ids = [t.id for t in txns
                       if t.transaction_type in ('cod_deposit', 'cod_driver_settle')]
        settled_by_txn = {}
        if deposit_ids:
            rows = DeliveryTask.objects.filter(
                cod_submission_txn_id__in=deposit_ids
            ).values_list(
                'cod_submission_txn_id', 'payment_method',
                'payment_split', 'cod_collected_amount',
            )
            for txn_id, method, split, total in rows:
                bucket = settled_by_txn.setdefault(
                    txn_id,
                    {'cash': Decimal('0'), 'fawran': Decimal('0'), 'pos': Decimal('0')})
                cash_leg = WalletService.split_cash_leg(split)
                if cash_leg is not None:
                    # Mixed collection — credit each leg to its own bucket.
                    bucket['cash'] += cash_leg
                    bucket['fawran'] += Decimal(str(split.get('fawran') or 0))
                    bucket['pos'] += Decimal(str(split.get('pos') or 0))
                    continue
                key = 'fawran' if method == 'fawran' else (
                    'pos' if method in ('pos', 'card') else 'cash')
                bucket[key] += total or Decimal('0')

        running_cash = Decimal('0')
        running_fawran = Decimal('0')
        running_pos = Decimal('0')
        running_bank = Decimal('0')
        running_atm = Decimal('0')
        to_update = []
        zero = Decimal('0')

        for t in txns:
            if t.transaction_type in ['cod_deposit', 'cod_driver_settle']:
                settled = settled_by_txn.get(t.id)
                cash_paid = settled['cash'] if settled else abs(t.amount)
                running_cash = max(running_cash - cash_paid, zero)
                # Electronic collections were never in the driver's hands —
                # a deposit closes them out on the ledger.
                running_fawran = zero
                running_pos = zero
                running_bank = zero
                running_atm = zero
                if (t.cod_cash_after != running_cash
                        or t.cod_fawran_after != running_fawran
                        or t.cod_pos_after != running_pos
                        or t.cod_bank_after != running_bank
                        or t.cod_atm_after != running_atm):
                    t.cod_cash_after = running_cash
                    t.cod_fawran_after = running_fawran
                    t.cod_pos_after = running_pos
                    t.cod_bank_after = running_bank
                    t.cod_atm_after = running_atm
                    to_update.append(t)
                continue

            method = (
                (t.delivery_task.payment_method if t.delivery_task else None)
                or t.payment_method
                or 'cash'
            )
            amt = abs(t.amount)

            # A mixed-method collection splits across buckets — booking the whole
            # amount under the dominant method would misstate both sides.
            split = t.delivery_task.payment_split if t.delivery_task else None
            cash_leg = WalletService.split_cash_leg(split)
            if cash_leg is not None:
                running_cash += cash_leg
                running_fawran += Decimal(str(split.get('fawran') or 0))
                running_pos += Decimal(str(split.get('pos') or 0))
                running_bank += Decimal(str(split.get('bank') or 0))
                running_atm += Decimal(str(split.get('atm') or 0))
            elif method == 'fawran':
                running_fawran += amt
            elif method in ['pos', 'card']:
                running_pos += amt
            elif method == 'bank':
                running_bank += amt
            elif method == 'atm':
                running_atm += amt
            else:
                running_cash += amt

            if (t.cod_cash_after != running_cash
                    or t.cod_fawran_after != running_fawran
                    or t.cod_pos_after != running_pos
                    or t.cod_bank_after != running_bank
                    or t.cod_atm_after != running_atm):
                t.cod_cash_after = running_cash
                t.cod_fawran_after = running_fawran
                t.cod_pos_after = running_pos
                t.cod_bank_after = running_bank
                t.cod_atm_after = running_atm
                to_update.append(t)

        if to_update:
            DriverTransaction.objects.bulk_update(
                to_update,
                ['cod_cash_after', 'cod_fawran_after', 'cod_pos_after',
                 'cod_bank_after', 'cod_atm_after']
            )

        return len(to_update)

    @staticmethod
    def ledger_cod_balances(driver):
        """Running COD balances by method since the driver's last deposit —
        the same numbers the workforce fleet-transactions ledger shows.
        Cash is the physical hand-in liability; Fawran/POS are already in
        Ezzy's bank but stay on the ledger until a deposit transaction
        resets the running balances."""
        WalletService.recalculate_cod_balances(driver)
        latest = DriverTransaction.objects.filter(
            driver=driver,
            transaction_type__in=['cod_collection', 'cod_deposit', 'cod_driver_settle']
        ).order_by('-created_at').first()
        cash = latest.cod_cash_after if latest else Decimal('0')
        fawran = latest.cod_fawran_after if latest else Decimal('0')
        pos = latest.cod_pos_after if latest else Decimal('0')

        # Orders on the ledger: distinct tasks collected since the last deposit
        # (multiple partial-collection txns on one task count once)
        last_deposit = DriverTransaction.objects.filter(
            driver=driver,
            transaction_type__in=['cod_deposit', 'cod_driver_settle']
        ).order_by('-created_at').first()
        coll_qs = DriverTransaction.objects.filter(
            driver=driver, transaction_type='cod_collection')
        if last_deposit:
            coll_qs = coll_qs.filter(created_at__gt=last_deposit.created_at)
        counts = WalletService._collection_method_counts(coll_qs)
        orders = counts['cash'] + counts['fawran'] + counts['pos']

        return {'cash': cash, 'fawran': fawran, 'pos': pos,
                'total': cash + fawran + pos, 'orders': orders,
                'cash_orders': counts['cash'], 'fawran_orders': counts['fawran'],
                'pos_orders': counts['pos'],
                'since': last_deposit.created_at if last_deposit else None}

    @staticmethod
    def _collection_method_counts(coll_qs):
        """Distinct collected tasks per method in a cod_collection queryset
        (txns without a linked task count once each).

        Zero-amount rows are excluded: they exist so a prepaid delivery still has
        a ledger entry to bill the delivery fee against, but no cash was handed
        over, and the settlement pages already count them separately as zero-COD
        deliveries. Including them here would double-count those orders."""
        seen = {'cash': set(), 'fawran': set(), 'pos': set()}
        extra = {'cash': 0, 'fawran': 0, 'pos': 0}
        for c in coll_qs.exclude(amount=0).select_related('delivery_task'):
            method = (
                (c.delivery_task.payment_method if c.delivery_task else None)
                or c.payment_method or 'cash'
            )
            key = 'fawran' if method == 'fawran' else (
                'pos' if method in ('pos', 'card') else 'cash')
            if c.delivery_task_id:
                seen[key].add(c.delivery_task_id)
            else:
                extra[key] += 1
        return {k: len(seen[k]) + extra[k] for k in seen}

    @staticmethod
    def deposit_method_breakdown(txn):
        """Method breakdown of one settlement (cod_deposit/cod_driver_settle):
        cash is the deposited amount; Fawran/card are the electronic
        collections this deposit swept off the ledger (everything collected
        between the previous deposit and this one). Works for historical
        settlements too — derived from the transaction ledger, not notes."""
        if txn.transaction_type not in ('cod_deposit', 'cod_driver_settle'):
            return None
        prev = DriverTransaction.objects.filter(
            driver=txn.driver,
            transaction_type__in=['cod_deposit', 'cod_driver_settle'],
            created_at__lt=txn.created_at,
        ).order_by('-created_at').first()
        coll = DriverTransaction.objects.filter(
            driver=txn.driver,
            transaction_type='cod_collection',
            created_at__lt=txn.created_at,
        ).select_related('delivery_task')
        if prev:
            coll = coll.filter(created_at__gt=prev.created_at)

        fawran = Decimal('0')
        pos = Decimal('0')
        for c in coll:
            method = (
                (c.delivery_task.payment_method if c.delivery_task else None)
                or c.payment_method or 'cash'
            )
            if method == 'fawran':
                fawran += abs(c.amount)
            elif method in ('pos', 'card'):
                pos += abs(c.amount)

        cash = abs(txn.amount)
        counts = WalletService._collection_method_counts(coll)
        return {'cash': cash, 'fawran': fawran, 'pos': pos,
                'total': cash + fawran + pos,
                'cash_orders': counts['cash'], 'fawran_orders': counts['fawran'],
                'pos_orders': counts['pos'],
                'total_orders': counts['cash'] + counts['fawran'] + counts['pos']}

    @staticmethod
    def settle_cod_with_client(business, amount, delivery_task_ids=None,
                               created_by=None, reference_number=None, notes=None,
                               payment_method=None, delivery_charge=None,
                               deductions=None):
        """
        Record COD settlement from EzzyDelivery to business client.

        Args:
            business: Business instance receiving the COD
            amount: Decimal GROSS COD being settled
            delivery_task_ids: Optional list of DeliveryTask IDs included
            created_by: User processing the settlement
            reference_number: Payment reference
            notes: Optional notes
            payment_method: Payment method used
            delivery_charge: Legacy single-figure delivery fee. Folded into
                ``deductions`` as one line; prefer passing ``deductions``.
            deductions: List of dicts ``{kind, label, amount}`` — every charge
                taken off the gross at payout (delivery, fulfilment, cargo
                handling, ad-hoc). Each becomes an invoice line, a revenue
                transaction and a BusinessPayoutDeduction row.

        Returns:
            (DriverTransaction, settled_count)
        """
        from fleet.models import BusinessPayoutDeduction

        valid_kinds = {k for k, _ in BusinessPayoutDeduction.KIND_CHOICES}
        lines = []
        for raw in (deductions or []):
            line_amount = Decimal(str(raw.get('amount') or '0'))
            if line_amount < 0:
                raise ValueError("Deduction amount cannot be negative")
            if line_amount == 0:
                continue
            kind = raw.get('kind') or 'other_charge'
            if kind not in valid_kinds:
                raise ValueError(f"Unknown deduction kind '{kind}'")
            lines.append({
                'kind': kind,
                'label': (raw.get('label') or dict(BusinessPayoutDeduction.KIND_CHOICES)[kind])[:120],
                'amount': line_amount,
            })

        # Back-compat: callers still passing a bare delivery_charge get it as a
        # line, so old and new callers produce the same invoice shape.
        delivery_charge = Decimal(str(delivery_charge or '0'))
        if delivery_charge < 0:
            raise ValueError("Delivery charge cannot be negative")
        if delivery_charge > 0 and not any(l['kind'] == 'delivery_charge' for l in lines):
            lines.insert(0, {
                'kind': 'delivery_charge',
                'label': 'Delivery charges',
                'amount': delivery_charge,
            })

        total_deductions = sum((l['amount'] for l in lines), Decimal('0'))
        if total_deductions > amount:
            raise ValueError(
                f"Deductions {total_deductions} exceed the COD being settled {amount}"
            )
        net_amount = amount - total_deductions

        with transaction.atomic():
            # The COD row records the cash that actually left the bank, so it
            # matches the transfer the business will see on their statement.
            trans = WalletService.record_transaction(
                driver=None,
                transaction_type='cod_client_settle',
                amount=net_amount,
                description=(
                    f"COD settlement to {business.business_name} - {net_amount} QR"
                    + (f" (gross {amount} less {total_deductions} deductions)"
                       if total_deductions else "")
                ),
                created_by=created_by,
                reference_number=reference_number,
                notes=notes,
                payment_method=payment_method,
                business=business
            )

            # Each charge is booked as its own revenue row rather than netted
            # away silently — otherwise what Ezzy earned leaves no trace — and
            # is recorded as an invoice line linked to both transactions.
            for line in lines:
                charge_txn = WalletService.record_transaction(
                    driver=None,
                    transaction_type=line['kind'],
                    amount=line['amount'],
                    description=(
                        f"{line['label']} recovered from {business.business_name} "
                        f"at COD payout {trans.transaction_code or trans.pk}"
                    ),
                    created_by=created_by,
                    reference_number=reference_number,
                    business=business,
                )
                BusinessPayoutDeduction.objects.create(
                    settle_txn=trans,
                    charge_txn=charge_txn,
                    kind=line['kind'],
                    label=line['label'],
                    amount=line['amount'],
                    created_by=created_by,
                )

            settled_count = 0
            if delivery_task_ids:
                # Idempotent: only flag tasks not already client-settled, so a
                # re-run never re-flags or links to a second payout transaction.
                now = timezone.now()
                settled_ids = list(DeliveryTask.objects.filter(
                    id__in=delivery_task_ids,
                    cod_collected=True,
                    cod_client_settled=False,
                ).values_list('id', flat=True))
                settled_count = len(settled_ids)
                if settled_ids:
                    DeliveryTask.objects.filter(id__in=settled_ids).update(
                        cod_client_settled=True,
                        cod_client_settled_at=now,
                        cod_client_settle_txn=trans,
                    )
                    # Advance order COD status to 'settled with business', but only
                    # for orders whose every COD-collected task is now client-settled
                    # (last-task rule — handles multi-task orders correctly).
                    from orders.models import Order
                    order_ids = set(DeliveryTask.objects.filter(
                        id__in=settled_ids
                    ).values_list('order_id', flat=True))
                    for oid in order_ids:
                        if oid is None:
                            continue
                        remaining = DeliveryTask.objects.filter(
                            order_id=oid, cod_collected=True, cod_client_settled=False
                        ).exists()
                        if not remaining:
                            Order.objects.filter(id=oid).exclude(
                                cod_status_by_client__in=CLIENT_STATES_NOT_DERIVED
                            ).update(
                                cod_status_by_staff='cod_settled_with_business',
                                cod_status_by_client='settled',
                            )
                            Order.objects.filter(
                                id=oid,
                                cod_status_by_client__in=CLIENT_STATES_NOT_DERIVED,
                            ).update(cod_status_by_staff='cod_settled_with_business')

            return trans, settled_count

    @staticmethod
    def reverse_cod_client_settlement(settle_txn=None, task_ids=None, amount=None,
                                      created_by=None, notes=None):
        """
        Reverse a business COD payout (Leg 3). Used when a settled order is later
        returned/reversed and EzzyDelivery must claw the payout back from the business.

        Resolves the affected tasks from ``settle_txn`` (via the
        ``cod_client_settle_txn`` back-link) or an explicit ``task_ids`` list,
        resets their client-settlement flags, restores order status to
        'cod_with_ezzy', and records an offsetting ``cod_client_settle_reversal``
        transaction against the business so the finance ledger self-corrects.

        Returns: (reversal_txn, reversed_count)
        """
        with transaction.atomic():
            tasks_qs = DeliveryTask.objects.select_for_update().filter(
                cod_client_settled=True
            )
            if settle_txn is not None:
                tasks_qs = tasks_qs.filter(cod_client_settle_txn=settle_txn)
            elif task_ids:
                tasks_qs = tasks_qs.filter(id__in=task_ids)
            else:
                raise ValueError("Provide either settle_txn or task_ids")

            tasks = list(tasks_qs.select_related('order', 'order__business'))
            if not tasks:
                return None, 0

            business = None
            if settle_txn is not None and settle_txn.business_id:
                business = settle_txn.business
            else:
                business = tasks[0].order.business if tasks[0].order else None

            # Reverse the NET that was actually paid, not the gross — otherwise
            # unwinding a payout hands back money that was never sent. The
            # invoice lines say exactly what was deducted, so follow those.
            deduction_lines = []
            charge_recovered = Decimal('0')
            if settle_txn is not None:
                deduction_lines = list(settle_txn.payout_deductions.all())
                charge_recovered = sum(
                    (l.amount or Decimal('0') for l in deduction_lines), Decimal('0'))

                # Payouts made before deduction lines existed booked their fee
                # as a loose delivery_charge row — fall back to matching it.
                if not deduction_lines:
                    charge_recovered = DriverTransaction.objects.filter(
                        transaction_type='delivery_charge',
                        business=settle_txn.business,
                        reference_number=settle_txn.reference_number,
                        created_at__gte=settle_txn.created_at,
                    ).exclude(reference_number__isnull=True).exclude(
                        reference_number=''
                    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            reversed_amount = amount if amount is not None else (
                sum((t.cod_collected_amount or Decimal('0')) for t in tasks)
                - charge_recovered
            )

            # Give the charges back too — the deliveries were un-settled, so
            # everything recovered against them comes off the books as well.
            if deduction_lines:
                for line in deduction_lines:
                    if not line.amount:
                        continue
                    WalletService.record_transaction(
                        driver=None,
                        transaction_type=line.kind,
                        amount=-line.amount,
                        description=(
                            f"{line.label} reversed for "
                            f"{business.business_name if business else 'business'} "
                            f"(payout {settle_txn.transaction_code if settle_txn else ''} reversed)"
                        ),
                        created_by=created_by,
                        business=business,
                    )
            elif charge_recovered > 0:
                WalletService.record_transaction(
                    driver=None,
                    transaction_type='delivery_charge',
                    amount=-charge_recovered,
                    description=(
                        f"Delivery charges reversed for "
                        f"{business.business_name if business else 'business'} "
                        f"(payout {settle_txn.transaction_code if settle_txn else ''} reversed)"
                    ),
                    created_by=created_by,
                    business=business,
                )

            reversal = WalletService.record_transaction(
                driver=None,
                transaction_type='cod_client_settle_reversal',
                amount=reversed_amount,
                description=(
                    f"COD payout reversal for {business.business_name} - {reversed_amount} QR"
                    if business else f"COD payout reversal - {reversed_amount} QR"
                ),
                created_by=created_by,
                reference_number=(settle_txn.transaction_code if settle_txn else None),
                notes=notes,
                business=business,
            )

            task_ids_to_reset = [t.id for t in tasks]
            DeliveryTask.objects.filter(id__in=task_ids_to_reset).update(
                cod_client_settled=False,
                cod_client_settled_at=None,
                cod_client_settle_txn=None,
            )
            # Restore order COD status to 'with ezzy' (cash is back with EzzyDelivery)
            from orders.models import Order
            order_ids = {t.order_id for t in tasks if t.order_id}
            if order_ids:
                Order.objects.filter(id__in=order_ids).exclude(
                    cod_status_by_client__in=CLIENT_STATES_NOT_DERIVED
                ).update(
                    cod_status_by_staff='cod_with_ezzy',
                    cod_status_by_client='received_by_company',
                )
                Order.objects.filter(
                    id__in=order_ids,
                    cod_status_by_client__in=CLIENT_STATES_NOT_DERIVED,
                ).update(cod_status_by_staff='cod_with_ezzy')

            return reversal, len(task_ids_to_reset)

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

        Idempotent: a second return for the same task is rejected so repeated
        calls cannot keep crediting the driver and drive cod_in_hand negative.
        The amount is validated positive and capped at what was collected.
        """
        amount = Decimal(str(amount or '0'))
        if amount <= Decimal('0'):
            raise ValueError("COD return amount must be positive")

        collected = delivery_task.cod_collected_amount or Decimal('0')
        if collected and amount > collected:
            raise ValueError(
                f"COD return {amount} exceeds collected amount {collected} for this task"
            )

        with transaction.atomic():
            # Lock the driver row for the whole check-and-act (consistent driver->task
            # lock order with the rest of the COD paths, so no deadlock).
            driver = Driver.objects.select_for_update().get(pk=driver.pk)

            # Guard against a duplicate return for the same task.
            already_returned = DriverTransaction.objects.filter(
                delivery_task=delivery_task, transaction_type='cod_return'
            ).exists()
            if already_returned:
                raise ValueError("A COD return has already been recorded for this task")

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
            # The return txn now excludes this task from live_cod_in_hand; refresh
            # the cached denormalization to match.
            WalletService.sync_cod_in_hand(driver)
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
        # Gate on the single source of truth, not the cached column, so a stale
        # denormalization can never wrongly block or admit a COD order.
        live_cod = WalletService.live_cod_in_hand(driver)
        credit_limit = driver.credit_limit or Decimal('0')
        available_credit = max(credit_limit - live_cod, Decimal('0'))

        if credit_limit and live_cod >= credit_limit:
            return False, "Wallet balance exhausted. Please submit COD to admin."

        if cod_amount > available_credit:
            return False, f"Insufficient credit. Available: {available_credit} QR, Required: {cod_amount} QR"

        return True, "OK"

    # Payment methods that go straight to Ezzy's account at collection — the
    # driver never physically holds this money, so it is never 'in hand'.
    ELECTRONIC_METHODS = ['pos', 'fawran', 'bank', 'atm']

    @staticmethod
    def split_cash_leg(payment_split):
        """Cash portion of a mixed-method collection, or None if not a mix.

        payment_method only records the *dominant* method of a split, so on a
        {cash: 200, fawran: 500} collection it reads 'fawran' and would classify
        the whole 700 as electronic — silently erasing 200 QR of driver
        liability. Whenever a real split is present the cash leg is the only
        part the driver actually holds.
        """
        if not isinstance(payment_split, dict) or len(payment_split) < 2:
            return None
        try:
            return Decimal(str(payment_split.get('cash') or 0))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def task_cash_leg(task):
        """Cash a driver is holding for one collected task (0 for electronic)."""
        mixed = WalletService.split_cash_leg(task.payment_split)
        if mixed is not None:
            return mixed
        if (task.payment_method or '') in WalletService.ELECTRONIC_METHODS:
            return Decimal('0.00')
        return Decimal(str(task.cod_collected_amount or 0))

    @staticmethod
    def is_electronic_only(task):
        """True when nothing about this collection is cash the driver holds."""
        return (task.payment_method or '') in WalletService.ELECTRONIC_METHODS \
            and WalletService.task_cash_leg(task) <= Decimal('0')

    @staticmethod
    def live_cod_in_hand(driver):
        """Single source of truth for a driver's COD-in-hand, derived from tasks.

        COD is 'in hand' only when it was collected as CASH and has NOT left the
        driver by either route: submitted to admin (cod_settled=True) or handed
        back to the customer (a cod_return transaction). Electronic payments
        (Fawran/POS/bank/ATM) land in Ezzy's account directly, so they never count
        as the driver's in-hand liability. Everything that reports or gates on
        cod_in_hand goes through this — the cached Driver.cod_in_hand column is
        only a denormalization kept in sync with it.

        A return is subtracted by AMOUNT, not by dropping the task: refunding
        100 of a 300 collection leaves 200 in the driver's hands, and excluding
        the whole task would wipe all 300 off the liability.
        """
        base = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            cod_collected=True,
            cod_settled=False,
        )

        # Mixed-method collections are counted by their cash leg only; their
        # payment_method is just the dominant method and cannot classify the
        # whole amount. Handled separately so the common case stays one query.
        mixed_ids, mixed_cash = [], Decimal('0.00')
        for task_id, split in base.exclude(
            payment_split__isnull=True
        ).values_list('id', 'payment_split'):
            leg = WalletService.split_cash_leg(split)
            if leg is not None:
                mixed_ids.append(task_id)
                mixed_cash += leg

        plain = base.exclude(id__in=mixed_ids).exclude(
            payment_method__in=WalletService.ELECTRONIC_METHODS
        ).aggregate(total=Sum('cod_collected_amount'))['total'] or Decimal('0.00')

        # Cash already handed back to customers on these still-unsettled tasks.
        refunded = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            transaction_type='cod_return',
            delivery_task_id__in=base.values('id'),
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        return max(plain + mixed_cash - abs(refunded), Decimal('0.00'))

    @staticmethod
    def sync_cod_in_hand(driver, save=True):
        """Recompute the cached Driver.cod_in_hand from the task truth and persist it.

        Call this inside the same locked transaction as any change to a driver's
        COD task state (collection, submission, return). Callers should already
        hold a select_for_update lock on the driver row. Returns the live value.

        wallet_balance is re-derived here too. It used to be accumulated
        independently inside record_transaction, which let it drift from the
        task truth (a collection recorded without a payment_method was debited
        as cash even when the task was Fawran). Deriving both from the same
        source means they cannot disagree again.
        """
        live = WalletService.live_cod_in_hand(driver)

        # COD is the only thing that moves the wallet today; manual bonuses and
        # deductions are added on top so they are never silently discarded.
        adjustments = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            transaction_type__in=['deduction', 'bonus', 'adjustment'],
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        wallet = adjustments - live

        changed = []
        if driver.cod_in_hand != live:
            driver.cod_in_hand = live
            changed.append('cod_in_hand')
        if driver.wallet_balance != wallet:
            driver.wallet_balance = wallet
            changed.append('wallet_balance')
        if save and changed:
            driver.save(update_fields=changed)
        return live

    @staticmethod
    def get_wallet_status(driver):
        """
        Get comprehensive wallet status information.
        COD in hand and wallet balance are computed live from DeliveryTask
        to avoid stale cached field values.
        """
        # Live COD: single source of truth (collected, not submitted, not returned)
        live_cod = WalletService.live_cod_in_hand(driver)

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
            successful=Count('id', filter=Q(dl_task_status__in=['delivered', 'partial_delivery'])),
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
