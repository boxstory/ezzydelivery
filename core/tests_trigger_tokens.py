# Purpose: Guard the {placeholders} clients may put in a WhatsApp trigger message.
# Used by: manage.py test core.tests_trigger_tokens
# Notes:   The contract under test is "the settings page never advertises a token we
#          cannot fill" — TOKEN_GROUPS is both the help panel and the render context.

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from business.models import Business
from core import trigger_tokens
from delivery.models import DeliveryTask
from fleet.models import Driver, DriverVehicle
from orders.models import Order


class TriggerTokenHelpersTests(TestCase):

    def test_unknown_tokens_ignores_known_and_control_words(self):
        body = 'Hi {customer_name} {if cod_amount}QAR {cod_amount}{else}-{endif} {made_up}'
        self.assertEqual(trigger_tokens.unknown_tokens(body), ['made_up'])

    def test_unknown_tokens_is_deduped_and_ordered(self):
        body = '{aaa} {bbb} {aaa}'
        self.assertEqual(trigger_tokens.unknown_tokens(body), ['aaa', 'bbb'])

    def test_money_blanks_zero(self):
        # A "QAR 0.00" line is noise in a customer's WhatsApp.
        self.assertEqual(trigger_tokens._money(0), '')
        self.assertEqual(trigger_tokens._money(None), '')
        self.assertEqual(trigger_tokens._money('150'), '150.00')


class TriggerTokenRenderTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        owner = User.objects.create_user(username='tok_owner', password='x')
        cls.business = Business.objects.create(
            business_id=990001, user=owner, business_name='Token Store',
            business_phone='97455500001', business_whatsapp='97455500002',
        )
        cls.order = Order.objects.create(
            order_number='TOK-0001', business=cls.business, client_order_code='SHOP-77',
            customer_name='Walid', customer_phone='97466600001',
            customer_address='Al Najma, Doha', cod_amount=250,
            package_description='Perfume box', package_qty=3,
            preferred_time_slot='evening',
        )

        driver_user = User.objects.create_user(username='tok_driver', password='x',
                                               first_name='Rahees', last_name='K')
        cls.driver = Driver.objects.create(
            driver_id=30001, user=driver_user, driver_code='TOKDRV', driver_phone='97460000001',
            driver_status='approved',
        )
        DriverVehicle.objects.create(driver=cls.driver, vehicle_type='car',
                                     vehicle_no='303450', vehicle_status='active')

        cls.task = DeliveryTask.objects.create(
            order=cls.order, business=cls.business, driver=cls.driver,
            dl_task_number='TOK-0001', dl_task_description='d',
            dl_task_status='delivered', dl_task_status_client='published',
            dl_task_date=datetime.date(2026, 9, 21), dl_speed='Same Day',
        )

    def test_every_advertised_token_resolves(self):
        """No token may be listed on the settings page and left unfilled."""
        body = '\n'.join('{%s}' % name for name in trigger_tokens.TOKEN_NAMES)
        out = trigger_tokens.render(body, self.order, task=self.task)
        self.assertNotIn('{', out, 'an advertised token was left unrendered')

    def test_order_and_delivery_values(self):
        body = ('{customer_name}|{client_order_code}|{cod_amount}|{payment_method}'
                '|{item_count}|{time_slot}|{delivery_speed}|{business_name}')
        self.assertEqual(
            trigger_tokens.render(body, self.order, task=self.task),
            'Walid|SHOP-77|250.00|Cash on Delivery|3|Evening (4 PM - 8 PM)|Same Day|Token Store',
        )

    def test_tracking_link_uses_the_task_token(self):
        out = trigger_tokens.render('{tracking_link}', self.order, task=self.task)
        self.assertTrue(self.task.tracking_token)
        self.assertTrue(out.endswith(f'/track/{self.task.tracking_token}/'), out)

    def test_conditional_block_hides_a_missing_value(self):
        self.order.cod_amount = 0
        body = 'Total due:{if cod_amount} QAR {cod_amount}{else} nothing{endif}'
        self.assertEqual(trigger_tokens.render(body, self.order, task=self.task),
                         'Total due: nothing')

    def test_prepaid_when_no_cod(self):
        self.order.cod_amount = 0
        self.assertEqual(trigger_tokens.render('{payment_method}', self.order), 'Prepaid')

    def test_driver_tokens_are_blank_without_a_task(self):
        # An order-only event (cancellation) has no driver yet — blank, not a crash.
        self.assertEqual(trigger_tokens.render('[{driver_name}][{driver_phone}]', self.order),
                         '[][]')

    def test_unknown_token_is_left_verbatim_not_dropped(self):
        out = trigger_tokens.render('Hi {customer_name} {not_a_token}', self.order, task=self.task)
        self.assertEqual(out, 'Hi Walid {not_a_token}')


class DefaultMessagePreviewTests(TestCase):
    """The settings page shows these as placeholders, so they must stay renderable.

    They come from _build_message() via a stub of {token} values — if someone adds
    a field to a default body and not to the stub, these fail rather than the page
    quietly showing an empty placeholder.
    """

    def test_every_live_trigger_has_a_preview(self):
        for status in trigger_tokens.TRIGGER_TO_EVENT:
            with self.subTest(status=status):
                preview = trigger_tokens.default_message(status)
                self.assertTrue(preview, f'{status} lost its default message')
                self.assertNotIn('None', preview)
                self.assertNotIn('<', preview)

    def test_preview_uses_only_advertised_tokens(self):
        # A default that mentions a token the reference panel does not list would
        # teach clients a placeholder we never document.
        for status in trigger_tokens.TRIGGER_TO_EVENT:
            with self.subTest(status=status):
                self.assertEqual(
                    trigger_tokens.unknown_tokens(trigger_tokens.default_message(status)), [])

    def test_dead_triggers_have_no_preview(self):
        # Picked Up / Start Ride are settings rows with no lifecycle event behind
        # them; the page says so rather than showing a message that never sends.
        for status in ('picked_up', 'start_ride'):
            with self.subTest(status=status):
                self.assertEqual(trigger_tokens.default_message(status), '')
