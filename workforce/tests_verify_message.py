# Purpose: Tests for the money figure in the customer location-verification WhatsApp message.
# Used by: manage.py test workforce.tests_verify_message
# Notes: The message must quote the same "collect" figure the printed waybill does — the driver
#        reads the label, the customer reads the message, and the two disagreeing is a doorstep row.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from delivery.charges import collect_totals
from orders import models as orders_models
from workforce.views import _build_order_whatsapp_message

User = get_user_model()

_SEQ = [9400]


def _order(cod=Decimal('250.00'), dl_amount=Decimal('0.00'), client_status=None):
    _SEQ[0] += 1
    idx = _SEQ[0]

    user = User.objects.create_user(username=f'vm_biz_{idx}', password='x')
    profile = core_models.Profile.objects.create(
        user=user, first_name='V', last_name='M', phone=83000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=user, profile=profile,
        business_name=f'Verify Biz {idx}', business_code=f'VM{idx}',
        business_status='active')
    return orders_models.Order.objects.create(
        business=business, client_order_code=f'VM-ORD-{idx}',
        customer_name='Ahmed', customer_phone='97455500000', customer_address='Zone 26',
        cod_amount=cod, dl_amount=dl_amount, order_status='pending',
        cod_status_by_client=client_status)


def _task(order, dl_price=None, verified=None):
    return delivery_models.DeliveryTask.objects.create(
        dl_task_number=f'VM-T-{order.id}', order=order, business=order.business,
        dl_task_status='pending', dl_price=dl_price,
        verified_delivery_charge=verified)


class VerifyMessageTotalTests(TestCase):
    """{total_amount} is COD + delivery charge, resolved the label's way."""

    def setUp(self):
        core_models.MessageTemplate.objects.update_or_create(
            key='order_verify_manual',
            defaults={'is_enabled': True,
                      'body': 'total=[{total_amount}] cod=[{cod_amount}] '
                              'dl=[{delivery_charge}] {verify_url}'})

    def test_seller_delivery_fee_is_added_to_the_cod(self):
        order = _order(cod=Decimal('1350.00'), dl_amount=Decimal('25.00'))
        body = _build_order_whatsapp_message(order)
        self.assertIn('total=[1375.00]', body)
        self.assertIn('cod=[1350.00]', body)
        self.assertIn('dl=[25.00]', body)

    def test_verified_task_charge_wins_over_the_imported_fee(self):
        """The Client Charges console is the figure that will actually bill."""
        order = _order(cod=Decimal('100.00'), dl_amount=Decimal('25.00'))
        _task(order, dl_price=Decimal('20.00'), verified=Decimal('30.00'))
        body = _build_order_whatsapp_message(order)
        self.assertIn('total=[130.00]', body)
        self.assertIn('dl=[30.00]', body)

    def test_an_unpriced_task_falls_back_to_the_cod_alone(self):
        """dl_price sits at 0.00 until verification, which is long after this
        message goes out — quoting 0 as "free delivery" would be a lie either way."""
        order = _order(cod=Decimal('200.00'))
        _task(order, dl_price=Decimal('0.00'))
        body = _build_order_whatsapp_message(order)
        self.assertIn('total=[200.00]', body)
        self.assertIn('dl=[]', body)

    def test_a_fully_prepaid_order_quotes_no_money_at_all(self):
        order = _order(cod=Decimal('0.00'), client_status='online_paid')
        body = _build_order_whatsapp_message(order)
        self.assertIn('total=[]', body)
        self.assertIn('dl=[]', body)

    def test_prepaid_goods_still_quote_the_delivery_fee(self):
        """online_paid with a delivery fee means the goods were settled online
        and the delivery is cash at the door — which is what the label already
        sends the driver to collect. Staying silent here would have the customer
        open the door with nothing ready."""
        order = _order(cod=Decimal('0.00'), dl_amount=Decimal('25.00'),
                       client_status='online_paid')
        body = _build_order_whatsapp_message(order)
        self.assertIn('total=[25.00]', body)
        self.assertIn('dl=[25.00]', body)
        # The goods ladder is still honoured — no COD is claimed on a paid order.
        self.assertIn('cod=[]', body)

    def test_the_total_matches_what_the_waybill_prints(self):
        """One definition of "collect" — collect_totals() — or the driver's
        label and the customer's message name two different numbers."""
        for cod, fee, status in ((Decimal('1350.00'), Decimal('25.00'), 'pending'),
                                 (Decimal('0.00'), Decimal('30.00'), 'online_paid'),
                                 (Decimal('0.00'), Decimal('30.00'), None),
                                 (Decimal('480.00'), Decimal('0.00'), None)):
            with self.subTest(cod=cod, fee=fee, status=status):
                order = _order(cod=cod, dl_amount=fee, client_status=status)
                body = _build_order_whatsapp_message(order)
                expected = collect_totals([order])[order.id]
                self.assertIn(f'total=[{expected:.2f}]', body)

    def test_the_breakdown_only_shows_when_there_are_two_numbers(self):
        order = _order(cod=Decimal('0.00'), dl_amount=Decimal('30.00'))
        core_models.MessageTemplate.objects.update_or_create(
            key='order_verify_manual',
            defaults={'is_enabled': True, 'body': '{total_line}{verify_url}'})
        self.assertIn('💵 To pay on delivery: QAR 30.00\n',
                      _build_order_whatsapp_message(order))

        both = _order(cod=Decimal('100.00'), dl_amount=Decimal('30.00'))
        self.assertIn('QAR 130.00 (order 100.00 + delivery 30.00)',
                      _build_order_whatsapp_message(both))
