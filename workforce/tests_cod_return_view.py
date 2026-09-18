# Purpose: Tests for the staff COD return endpoint (workforce:process_cod_return).
# Used by: manage.py test workforce.tests_cod_return_view
# Notes: Covers the two bugs a partial refund used to leave behind — a green "Processed" badge on
#        a return that was only part-paid, and a seller still reading "Collected" after a full one.

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from fleet import models as fleet_models
from fleet.wallet_service import WalletService
from orders import models as orders_models

User = get_user_model()

_SEQ = [8800]


def _fixtures(collected=Decimal('300.00'), settled=False):
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'cr_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='C', last_name='R', phone=81000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'CodRet Biz {idx}', business_code=f'CR{idx}',
        business_status='active')
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'CR-ORD-{idx}',
        customer_name='C', customer_phone='1', customer_address='Z',
        cod_amount=collected, order_status='delivered',
        cod_status_by_staff='cod_with_driver', cod_status_by_client='collected')

    drv_user = User.objects.create_user(username=f'cr_drv_{idx}', password='x')
    drv_profile = core_models.Profile.objects.create(
        user=drv_user, first_name='C', last_name='D', phone=82000000 + idx)
    driver = fleet_models.Driver.objects.create(
        driver_id=idx, user=drv_user, profile=drv_profile,
        driver_code=f'CD{idx}', driver_phone='2', driver_whatsapp='2',
        driver_languages='english', driver_license_number=f'L{idx}',
        driver_status='approved', cod_in_hand=Decimal('0.00'))

    task = delivery_models.DeliveryTask.objects.create(
        dl_task_number=f'CR-T-{idx}', order=order, business=business, driver=driver,
        dl_task_status='delivered', cod_collected=True, cod_settled=False,
        cod_collected_amount=collected, cod_collected_at=timezone.now(),
        completed_at=timezone.now(), payment_method='cash',
        cod_client_settled=settled)
    WalletService.sync_cod_in_hand(driver)

    staff = User.objects.create_user(
        username=f'cr_staff_{idx}', password='x', is_staff=True, is_superuser=True)
    return business, order, driver, task, staff


def _ret(order, business, amount):
    return orders_models.ReturnRequest.objects.create(
        return_number=f'RET-{order.id}-{amount}', order=order, business=business,
        reason='damaged', status='pending', cod_reversal_amount=amount)


class CodReturnViewTests(TestCase):
    def _post(self, task, amount):
        return self.client.post(
            reverse('workforce:process_cod_return', args=[task.id]),
            data=json.dumps({'amount': str(amount)}),
            content_type='application/json')

    def test_a_partial_refund_does_not_mark_a_bigger_return_processed(self):
        """Refunding 100 of a 300 reversal used to show the seller a green badge."""
        business, order, _, task, staff = _fixtures(collected=Decimal('300.00'))
        ret = _ret(order, business, Decimal('300.00'))
        self.client.force_login(staff)

        resp = self._post(task, Decimal('100.00'))
        self.assertEqual(resp.status_code, 200)
        ret.refresh_from_db()
        self.assertFalse(ret.cod_reversal_processed,
                         'a 100 refund marked a 300 reversal as processed')

    def test_covering_the_full_amount_does_mark_it_processed(self):
        business, order, _, task, staff = _fixtures(collected=Decimal('300.00'))
        ret = _ret(order, business, Decimal('300.00'))
        self.client.force_login(staff)

        self._post(task, Decimal('100.00'))
        self._post(task, Decimal('200.00'))
        ret.refresh_from_db()
        self.assertTrue(ret.cod_reversal_processed)

    def test_a_smaller_return_is_closed_by_a_partial_refund(self):
        business, order, _, task, staff = _fixtures(collected=Decimal('300.00'))
        small = _ret(order, business, Decimal('80.00'))
        large = _ret(order, business, Decimal('250.00'))
        self.client.force_login(staff)

        self._post(task, Decimal('100.00'))
        small.refresh_from_db()
        large.refresh_from_db()
        self.assertTrue(small.cod_reversal_processed)
        self.assertFalse(large.cod_reversal_processed)

    def test_a_full_refund_updates_the_seller_facing_status(self):
        """cod_status_by_client used to stay 'collected' after the money went back."""
        _, order, _, task, staff = _fixtures(collected=Decimal('300.00'))
        self.client.force_login(staff)

        self._post(task, Decimal('300.00'))
        order.refresh_from_db()
        self.assertEqual(order.cod_status_by_staff, 'not_collected')
        self.assertEqual(order.cod_status_by_client, 'pending',
                         'seller still sees the old COD status after a full refund')

    def test_a_partial_refund_leaves_custody_alone(self):
        _, order, _, task, staff = _fixtures(collected=Decimal('300.00'))
        self.client.force_login(staff)

        self._post(task, Decimal('100.00'))
        order.refresh_from_db()
        self.assertEqual(order.cod_status_by_staff, 'cod_with_driver')

    def test_two_partial_refunds_are_accepted(self):
        _, order, driver, task, staff = _fixtures(collected=Decimal('300.00'))
        self.client.force_login(staff)

        self.assertEqual(self._post(task, Decimal('100.00')).status_code, 200)
        self.assertEqual(self._post(task, Decimal('150.00')).status_code, 200)
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('50.00'))

    def test_refunding_past_the_collection_is_refused(self):
        _, order, driver, task, staff = _fixtures(collected=Decimal('300.00'))
        self.client.force_login(staff)

        self._post(task, Decimal('250.00'))
        resp = self._post(task, Decimal('100.00'))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('still refundable', resp.json()['error'])
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('50.00'))

    def test_settled_cod_is_still_blocked_here(self):
        """Once paid to the seller the liability is theirs, not the driver's."""
        _, order, _, task, staff = _fixtures(settled=True)
        self.client.force_login(staff)

        resp = self._post(task, Decimal('50.00'))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already paid to the business', resp.json()['error'])
