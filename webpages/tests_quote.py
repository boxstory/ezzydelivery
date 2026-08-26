# Purpose: Cover the post-submission quote page — token access, agreement snapshot, status rules.
# Used by: manage.py test webpages.tests_quote
# Notes: WhatsApp and CRM side effects are patched out; they are best-effort in the view and must
#        never decide whether the customer's confirmation is recorded.

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from webpages.models import PricingEnquiry, PricingEnquiryActivity, PricingPlanOption


class QuotePageTests(TestCase):

    def setUp(self):
        # Migration 0010 already seeded these keys into the test database, so
        # pin the values this suite asserts on rather than creating duplicates.
        self.flat, _ = PricingPlanOption.objects.update_or_create(
            key='flat_48h',
            defaults=dict(name='Flat Rate — 48 Hour Delivery',
                          price_display='25', price_unit='QR per delivery',
                          price_value=Decimal('25.00'), is_custom_quote=False,
                          is_active=True, sort_order=1),
        )
        self.custom, _ = PricingPlanOption.objects.update_or_create(
            key='talk_to_sales',
            defaults=dict(name='Custom Plan',
                          price_display="Let's talk", price_unit='custom quote',
                          price_value=None, is_custom_quote=True,
                          is_active=True, sort_order=2),
        )
        PricingPlanOption.objects.exclude(
            key__in=['flat_48h', 'talk_to_sales']).update(is_active=False)
        self.inquiry = PricingEnquiry.objects.create(
            full_name='Sara', business_name='Aiwa Home',
            business_contact_number='97455512345', product_category='Home decor',
            is_complete=True,
        )

    def _url(self, inquiry=None):
        return reverse('webpages:inquiry_quote',
                       kwargs={'token': (inquiry or self.inquiry).quote_token})

    def _agree(self, plan_key, **extra):
        data = {'plan': plan_key, 'confirm_agree': 'on'}
        data.update(extra)
        return self.client.post(self._url(), data)

    # ── access ────────────────────────────────────────────────────────────────

    def test_page_renders_active_plans(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Flat Rate')
        self.assertContains(response, '25')
        self.assertContains(response, 'Custom Plan')

    def test_inactive_plan_is_not_offered(self):
        self.custom.is_active = False
        self.custom.save()
        response = self.client.get(self._url())
        self.assertNotContains(response, 'Custom Plan')
        # ...and cannot be agreed to by posting its key anyway
        self.assertEqual(self._agree('talk_to_sales').status_code, 200)
        self.inquiry.refresh_from_db()
        self.assertFalse(self.inquiry.has_agreed_plan)

    def test_unknown_token_is_404(self):
        response = self.client.get(
            reverse('webpages:inquiry_quote',
                    kwargs={'token': '00000000-0000-4000-8000-000000000000'})
        )
        self.assertEqual(response.status_code, 404)

    def test_incomplete_inquiry_is_404(self):
        partial = PricingEnquiry.objects.create(
            full_name='Half', business_name='Half Co',
            business_contact_number='974555', product_category='x', is_complete=False,
        )
        self.assertEqual(self.client.get(self._url(partial)).status_code, 404)

    # ── agreement ─────────────────────────────────────────────────────────────

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_agreeing_snapshots_the_price(self, _wa):
        response = self._agree('flat_48h')
        self.assertEqual(response.status_code, 302)
        self.inquiry.refresh_from_db()
        self.assertTrue(self.inquiry.has_agreed_plan)
        self.assertEqual(self.inquiry.selected_plan, self.flat)
        self.assertEqual(self.inquiry.agreed_plan_name, 'Flat Rate — 48 Hour Delivery')
        self.assertEqual(self.inquiry.agreed_price_display, '25')
        self.assertEqual(self.inquiry.agreed_price_value, Decimal('25.00'))
        self.assertEqual(self.inquiry.agreed_price_label, '25 QR per delivery')

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_snapshot_survives_a_later_catalogue_edit(self, _wa):
        self._agree('flat_48h')
        self.flat.price_display = '30'
        self.flat.price_value = Decimal('30.00')
        self.flat.save()
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.agreed_price_display, '25')
        self.assertEqual(self.inquiry.agreed_price_value, Decimal('25.00'))

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_custom_quote_records_no_price(self, _wa):
        self._agree('talk_to_sales')
        self.inquiry.refresh_from_db()
        self.assertTrue(self.inquiry.has_agreed_plan)
        self.assertIsNone(self.inquiry.agreed_price_value)
        self.assertEqual(self.inquiry.agreed_plan_name, 'Custom Plan')

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_note_is_stored(self, _wa):
        self._agree('flat_48h', plan_agreement_note='We ship 60 orders a week')
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.plan_agreement_note, 'We ship 60 orders a week')

    def test_unticked_confirmation_is_rejected(self):
        response = self.client.post(self._url(), {'plan': 'flat_48h'})
        self.assertEqual(response.status_code, 200)
        self.inquiry.refresh_from_db()
        self.assertFalse(self.inquiry.has_agreed_plan)

    def test_no_plan_chosen_is_rejected(self):
        response = self.client.post(self._url(), {'confirm_agree': 'on'})
        self.assertEqual(response.status_code, 200)
        self.inquiry.refresh_from_db()
        self.assertFalse(self.inquiry.has_agreed_plan)

    # ── CRM side ──────────────────────────────────────────────────────────────

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_new_lead_moves_to_quoted_and_logs_activity(self, _wa):
        self._agree('flat_48h')
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.crm_status, PricingEnquiry.STATUS_QUOTED)
        activity = PricingEnquiryActivity.objects.filter(inquiry=self.inquiry).first()
        self.assertIsNotNone(activity)
        self.assertIn('agreed to', activity.body)

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_converted_lead_is_not_dragged_back_to_quoted(self, _wa):
        self.inquiry.crm_status = PricingEnquiry.STATUS_CONVERTED
        self.inquiry.save()
        self._agree('flat_48h')
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.crm_status, PricingEnquiry.STATUS_CONVERTED)
        self.assertTrue(self.inquiry.has_agreed_plan)

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_changing_the_selection_keeps_both_in_the_timeline(self, _wa):
        self._agree('flat_48h')
        self._agree('talk_to_sales')
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.selected_plan, self.custom)
        self.assertEqual(PricingEnquiryActivity.objects.filter(inquiry=self.inquiry).count(), 2)

    @patch('core.whatsapp_utils.send_quote_agreement_notification',
           side_effect=RuntimeError('WAHA down'))
    def test_whatsapp_failure_does_not_lose_the_agreement(self, _wa):
        response = self._agree('flat_48h')
        self.assertEqual(response.status_code, 302)
        self.inquiry.refresh_from_db()
        self.assertTrue(self.inquiry.has_agreed_plan)

    # ── success page ──────────────────────────────────────────────────────────

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_success_page_shows_the_selection(self, _wa):
        self._agree('flat_48h')
        response = self.client.get(
            reverse('webpages:inquiry_success') + f'?t={self.inquiry.quote_token}'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Flat Rate')
        self.assertContains(response, '25 QR per delivery')

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_flat_rate_pops_the_congratulations_once(self, _wa):
        response = self.client.post(self._url(),
                                    {'plan': 'flat_48h', 'confirm_agree': 'on'},
                                    follow=True)
        self.assertContains(response, 'Congratulations')
        self.assertContains(response, '10 minutes')
        self.assertContains(response, reverse('account_signup'))
        # A reload must not replay it — the flag is one-shot.
        again = self.client.get(
            reverse('webpages:inquiry_success') + f'?t={self.inquiry.quote_token}'
        )
        self.assertNotContains(again, 'Congratulations')

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_custom_quote_gets_no_dashboard_promise(self, _wa):
        response = self.client.post(self._url(),
                                    {'plan': 'talk_to_sales', 'confirm_agree': 'on'},
                                    follow=True)
        self.assertNotContains(response, 'Congratulations')
        self.assertNotContains(response, '10 minutes')

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_flat_rate_receipt_keeps_a_signup_cta_after_dismissal(self, _wa):
        self._agree('flat_48h')
        response = self.client.get(
            reverse('webpages:inquiry_success') + f'?t={self.inquiry.quote_token}'
        )
        self.assertContains(response, 'Create my dashboard account')
        self.assertContains(response, reverse('account_signup'))

    @patch('core.whatsapp_utils.send_quote_agreement_notification')
    def test_agreement_attributes_a_later_signup_to_the_pricing_inquiry(self, _wa):
        from core import signup_origin
        self.client.post(self._url(), {'plan': 'flat_48h', 'confirm_agree': 'on'}, follow=True)
        self.assertEqual(
            self.client.session[signup_origin.SESSION_KEY]['source'],
            signup_origin.SOURCE_PRICING,
        )

    def test_success_page_without_token_is_the_plain_thank_you(self):
        response = self.client.get(reverse('webpages:inquiry_success'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Thank You')

    def test_success_page_ignores_a_malformed_token(self):
        response = self.client.get(reverse('webpages:inquiry_success') + '?t=not-a-uuid')
        self.assertEqual(response.status_code, 200)
