# Purpose: Cover the suggested-price engine — band parsing, the rate matrix, clamps, and the staff quote.
# Used by: manage.py test webpages.tests_pricing
# Notes: Never assume the rate card seeded by migration 0013 is present — a TransactionTestCase
#        elsewhere in the suite truncates every table and migration data does not come back.
#        Call ensure_rate_card() in setUp instead.

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from webpages.models import (
    PricingEnquiry, PricingEnquiryActivity, PricingRule, PricingRuleSet, PricingSuggestion,
)
from webpages.pricing import bands
from webpages.pricing.engine import get_or_create_suggestion, suggest_price


def ensure_rate_card():
    """Return the seeded rate card, re-seeding it if the table is empty.

    Migration 0013 creates it, but a TransactionTestCase anywhere else in the
    suite truncates every table on teardown and migration-created rows do not
    come back — so depending on the seed makes these tests order-dependent and
    flaky. Re-runs the migration's own seed function so the two cannot drift.
    """
    import importlib
    ruleset = PricingRuleSet.objects.filter(code='rate_card_v1').first()
    if ruleset is not None:
        return ruleset

    module = importlib.import_module('webpages.migrations.0013_seed_rate_card_v1')

    class _Apps:
        @staticmethod
        def get_model(app_label, model_name):
            return {'PricingRuleSet': PricingRuleSet, 'PricingRule': PricingRule}[model_name]

    module.seed(_Apps, None)
    # 0014 corrects the COD rules so they stack; apply it here too.
    PricingRule.objects.filter(dimension='cod', label='Cash on delivery').update(stop_on_match=False)
    return PricingRuleSet.objects.get(code='rate_card_v1')


class BandParsingTests(TestCase):
    """Every value the live form can post must parse, or be explicitly unknown."""

    # Straight from the data-value attributes in delivery_pricing_inquiry.html.
    NUMERIC = [
        '1-10', '11-30', '31-100', '101-300', '300+',
        '1-25', '26-100', '301-1000', '1000+',
        'Below 100', '100-500', '500-1000', '1000-3000', '3000+',
        'Below 50', '50-100', '100-300', '300-500', 'Above 1000',
        'Under 1 kg', '1-5 kg', '5-15 kg', '15+ kg',
        'Below 10 QAR', '10-15 QAR', '15-20 QAR', '20-30 QAR', '30+ QAR',
        '2-3', '4-5', '6-10', '10+', '1-3', '3-5',
    ]
    UNKNOWN = ['', None, 'Not sure', 'Mixed', 'Mixed Sizes', 'None', 'Any', 'garbage text']

    def test_every_live_numeric_band_parses(self):
        for value in self.NUMERIC:
            with self.subTest(value=value):
                parsed = bands.parse_band(value)
                self.assertTrue(parsed.known, f'{value!r} should parse')
                self.assertIsNotNone(parsed.mid)

    def test_unknown_values_have_no_midpoint(self):
        # A 0 here would silently price the lead as if they had answered.
        for value in self.UNKNOWN:
            with self.subTest(value=value):
                parsed = bands.parse_band(value)
                self.assertFalse(parsed.known)
                self.assertIsNone(parsed.mid)

    def test_en_dash_from_a_pasted_label(self):
        self.assertEqual(bands.parse_band('50 – 100').mid, Decimal('75'))

    def test_percentages_cap_at_100(self):
        parsed = bands.parse_band('Above 75%', cap=100)
        self.assertEqual((parsed.low, parsed.high, parsed.mid),
                         (Decimal('75'), Decimal('100'), Decimal('87.5')))

    def test_open_top_without_a_cap_uses_the_factor(self):
        self.assertEqual(bands.parse_band('300+').mid, Decimal('300') * bands.OPEN_TOP_FACTOR)

    def test_ordinal_tables_keep_their_unit_words(self):
        # These keys contain words the numeric cleaner strips ("pallets", "km"),
        # so they must be looked up on the un-stripped text.
        self.assertEqual(bands.rank_of('1-5 pallets', bands.STORAGE_RANK), 2)
        self.assertEqual(bands.distance_km('Over 30 km'), Decimal('35'))

    def test_distance_bands_land_in_their_matrix_row(self):
        self.assertEqual(bands.distance_km('Under 10 km'), Decimal('5'))
        self.assertEqual(bands.distance_km('10-15 km'), Decimal('12.5'))
        self.assertEqual(bands.distance_km('15-25 km'), Decimal('20'))
        self.assertEqual(bands.distance_km('25-30 km'), Decimal('27.5'))
        self.assertIsNone(bands.distance_km('Not sure'))

    def test_staff_typed_free_text_still_parses(self):
        # pricing_inquiry_edit lets staff type into these fields.
        self.assertEqual(bands.distance_km('12 km'), Decimal('12'))
        self.assertEqual(bands.parse_band('20').mid, Decimal('20'))


class EngineTests(TestCase):

    def setUp(self):
        self.ruleset = ensure_rate_card()
        self.ruleset.is_active = True
        self.ruleset.save()

    def _enquiry(self, **kwargs):
        defaults = dict(
            full_name='Sara', business_name='Aiwa Home', business_contact_number='97455512345',
            product_category='Home decor', is_complete=True,
            typical_package_size='Small (Envelopes / Packets)',
            speed_delivery_offer_to_customers='48 Hours',
            delivery_coverage='Doha Only',
        )
        defaults.update(kwargs)
        return PricingEnquiry.objects.create(**defaults)

    # ── the matrix ────────────────────────────────────────────────────────────

    def test_matrix_prices_fall_as_volume_rises(self):
        """The whole point of the corrected card — a bigger customer never pays more."""
        for distance in ('Under 10 km', '10-15 km', '15-25 km'):
            prices = []
            for volume in ('1-25', '101-300', '1000+'):   # low, mid, high
                result = suggest_price(
                    self._enquiry(avarage_number_of_order_done_last_month=volume,
                                  typical_delivery_distance=distance),
                    with_comparables=False)
                prices.append(result.suggested_price)
            with self.subTest(distance=distance):
                self.assertEqual(prices, sorted(prices, reverse=True),
                                 f'{distance}: {prices} should fall as volume rises')

    def test_known_matrix_cells(self):
        cases = [
            ('1000+', 'Under 10 km', Decimal('15.00')),
            ('1000+', '10-15 km', Decimal('19.00')),
            ('101-300', 'Under 10 km', Decimal('20.00')),
            ('101-300', '10-15 km', Decimal('25.00')),
            ('1-25', 'Under 10 km', Decimal('25.00')),
            ('1-25', '15-25 km', Decimal('30.00')),
        ]
        for volume, distance, expected in cases:
            with self.subTest(volume=volume, distance=distance):
                result = suggest_price(
                    self._enquiry(avarage_number_of_order_done_last_month=volume,
                                  typical_delivery_distance=distance),
                    with_comparables=False)
                self.assertEqual(result.suggested_price, expected)

    def test_over_30km_is_flagged_not_invented(self):
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='101-300',
                          typical_delivery_distance='Over 30 km'),
            with_comparables=False)
        self.assertIn('outside_rate_card', result.flags)
        self.assertEqual(result.base_price, self.ruleset.base_price_default)

    def test_missing_distance_falls_back_and_says_so(self):
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='101-300',
                          typical_delivery_distance='Not sure'),
            with_comparables=False)
        self.assertIn('base_defaulted', result.flags)
        self.assertIn('typical_delivery_distance', result.missing)

    # ── adjustments ───────────────────────────────────────────────────────────

    def test_adjustments_stack_onto_the_base(self):
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='101-300',
                          typical_delivery_distance='10-15 km',
                          average_package_weight='5-15 kg',
                          is_required_COD_service=True, cod_orders_share='Below 25%'),
            with_comparables=False)
        # 25 base + 5 weight + 2 COD
        self.assertEqual(result.suggested_price, Decimal('32.00'))

    def test_high_cod_share_surcharge_can_actually_fire(self):
        """The base COD fee must not stop the loop before the >75% surcharge."""
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='101-300',
                          typical_delivery_distance='10-15 km',
                          is_required_COD_service=True, cod_orders_share='Above 75%'),
            with_comparables=False)
        # 25 base + 2 COD + 1 high cash share
        self.assertEqual(result.suggested_price, Decimal('28.00'))
        labels = [line['label'] for line in result.breakdown]
        self.assertIn('Mostly COD (over 75% of orders)', labels)

    def test_special_handling_rules_stack(self):
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='1-25',
                          typical_delivery_distance='15-25 km',
                          is_special_handling_required=True,
                          special_handling_detail='Fragile, Chilled / Frozen'),
            with_comparables=False)
        # 30 base + 8 frozen + 3 fragile
        self.assertEqual(result.suggested_price, Decimal('41.00'))

    def test_unknown_weight_adds_nothing(self):
        priced = lambda **kw: suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='101-300',
                          typical_delivery_distance='10-15 km', **kw),
            with_comparables=False).suggested_price
        self.assertEqual(priced(average_package_weight='Mixed'), priced())

    def test_breakdown_arithmetic_reconciles(self):
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='1-25',
                          typical_delivery_distance='15-25 km',
                          average_package_weight='15+ kg',
                          is_return_logistics_required=True),
            with_comparables=False)
        total = sum(Decimal(line['delta']) for line in result.breakdown)
        self.assertEqual(total, result.suggested_price)

    def test_deterministic_across_runs(self):
        enquiry = self._enquiry(avarage_number_of_order_done_last_month='101-300',
                                typical_delivery_distance='10-15 km',
                                average_package_weight='5-15 kg')
        first = suggest_price(enquiry, with_comparables=False)
        second = suggest_price(enquiry, with_comparables=False)
        self.assertEqual(first.suggested_price, second.suggested_price)
        self.assertEqual([l['label'] for l in first.breakdown],
                         [l['label'] for l in second.breakdown])

    # ── guards ────────────────────────────────────────────────────────────────

    def test_no_active_rate_card_declines_instead_of_guessing(self):
        PricingRuleSet.objects.update(is_active=False)
        result = suggest_price(self._enquiry(), with_comparables=False)
        self.assertFalse(result.available)
        self.assertIsNone(result.suggested_price)
        self.assertEqual(PricingSuggestion.objects.count(), 0)

    def test_floor_is_applied_and_labelled_as_configured(self):
        self.ruleset.min_price_floor = Decimal('40.00')
        self.ruleset.save()
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='1000+',
                          typical_delivery_distance='Under 10 km'),
            with_comparables=False)
        self.assertEqual(result.suggested_price, Decimal('40.00'))
        self.assertIn('floor_applied', result.flags)
        self.assertTrue(any(l['dimension'] == 'floor' for l in result.breakdown))

    def test_margin_is_never_reported_while_the_floor_is_a_guess(self):
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='101-300',
                          typical_delivery_distance='10-15 km'),
            with_comparables=False)
        self.assertFalse(self.ruleset.can_report_margin)
        self.assertIsNone(result.margin)

    def test_uplift_is_clamped(self):
        self.ruleset.max_total_uplift_pct = Decimal('10')
        self.ruleset.save()
        result = suggest_price(
            self._enquiry(avarage_number_of_order_done_last_month='1-25',
                          typical_delivery_distance='15-25 km',
                          is_special_handling_required=True,
                          special_handling_detail='Oversized / Heavy'),
            with_comparables=False)
        self.assertIn('clamped_uplift', result.flags)
        self.assertEqual(result.suggested_price, Decimal('33.00'))  # 30 + 10%

    def test_only_one_rate_card_can_be_active(self):
        other = PricingRuleSet.objects.create(code='rate_card_v2', name='v2', is_active=True)
        self.ruleset.refresh_from_db()
        self.assertTrue(other.is_active)
        self.assertFalse(self.ruleset.is_active)

    # ── persistence ───────────────────────────────────────────────────────────

    def test_reopening_the_page_does_not_pile_up_rows(self):
        enquiry = self._enquiry(avarage_number_of_order_done_last_month='101-300',
                                typical_delivery_distance='10-15 km')
        get_or_create_suggestion(enquiry)
        get_or_create_suggestion(enquiry)
        self.assertEqual(PricingSuggestion.objects.filter(inquiry=enquiry).count(), 1)

    def test_changed_answers_produce_a_new_suggestion(self):
        enquiry = self._enquiry(avarage_number_of_order_done_last_month='101-300',
                                typical_delivery_distance='10-15 km')
        get_or_create_suggestion(enquiry)
        enquiry.typical_delivery_distance = '15-25 km'
        enquiry.save()
        get_or_create_suggestion(enquiry)
        self.assertEqual(PricingSuggestion.objects.filter(inquiry=enquiry).count(), 2)

    def test_editing_a_rate_supersedes_the_stored_suggestion(self):
        """A rule edit changes the price for unchanged answers, so the old row
        must not be reused — otherwise the panel and the record disagree and an
        accept is logged as an override of a number nobody was shown."""
        enquiry = self._enquiry(avarage_number_of_order_done_last_month='101-300',
                                typical_delivery_distance='10-15 km')
        _result, first = get_or_create_suggestion(enquiry)

        rule = self.ruleset.rules.get(dimension='volume_distance_base',
                                      label='Mid volume (150+/mo) — 10-15 km')
        rule.amount = Decimal('27.00')
        rule.save()

        _result, second = get_or_create_suggestion(enquiry)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.suggested_price, Decimal('27.00'))
        enquiry.refresh_from_db()
        self.assertEqual(enquiry.suggested_price_value, Decimal('27.00'))
        self.assertEqual(enquiry.latest_suggestion_id, second.pk)

    def test_denormalised_price_lands_on_the_inquiry(self):
        enquiry = self._enquiry(avarage_number_of_order_done_last_month='1000+',
                                typical_delivery_distance='Under 10 km')
        get_or_create_suggestion(enquiry)
        enquiry.refresh_from_db()
        self.assertEqual(enquiry.suggested_price_value, Decimal('15.00'))
        self.assertIsNotNone(enquiry.latest_suggestion)


class RequiredPricingAnswersTests(TestCase):
    """The answers the rate card needs are enforced server-side too — the form's
    JavaScript can simply be skipped."""

    URL = '/3pl/inquiry/'

    STEP2_OK = {
        'typical_delivery_distance': '10-15 km',
        'delivery_coverage': 'Doha Only',
    }
    STEP3_OK = {
        'speed_delivery_offer_to_customers': '48 Hours',
        'typical_package_size': 'Small (Envelopes / Packets)',
        'average_package_weight': '1-5 kg',
    }

    def _post_step(self, step, data, button='next_step'):
        payload = dict(data)
        payload[button] = '1'
        return self.client.post(f'{self.URL}?step={step}', payload)

    def test_step2_blocks_a_missing_distance(self):
        response = self._post_step(2, {'delivery_coverage': 'Doha Only'})
        self.assertEqual(response.status_code, 200)   # re-rendered, not advanced
        self.assertContains(response, 'typical delivery distance')

    def test_step2_blocks_a_missing_coverage(self):
        response = self._post_step(2, {'typical_delivery_distance': '10-15 km'})
        self.assertContains(response, 'delivery coverage')

    def test_step2_advances_when_answered(self):
        response = self._post_step(2, self.STEP2_OK)
        self.assertEqual(response.status_code, 302)

    def test_cod_share_is_required_only_when_cod_was_chosen(self):
        without_cod = dict(self.STEP2_OK, is_required_COD_service='False')
        self.assertEqual(self._post_step(2, without_cod).status_code, 302)

        with_cod = dict(self.STEP2_OK, is_required_COD_service='True')
        blocked = self._post_step(2, with_cod)
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, 'share of your orders are COD')

        answered = dict(with_cod, cod_orders_share='Below 25%')
        self.assertEqual(self._post_step(2, answered).status_code, 302)

    def test_final_submit_blocks_missing_weight_size_or_speed(self):
        from django.test import Client
        for field in ('speed_delivery_offer_to_customers', 'typical_package_size',
                      'average_package_weight'):
            with self.subTest(missing=field):
                # A fresh client per case: the view accumulates answers in the
                # session across steps, so a shared one would carry the previous
                # iteration's value and mask the omission.
                self.client = Client()
                data = {k: v for k, v in self.STEP3_OK.items() if k != field}
                response = self._post_step(3, data, button='submit_final')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(PricingEnquiry.objects.filter(is_complete=True).count(), 0)

    def test_handling_detail_is_required_only_when_handling_was_chosen(self):
        needs_detail = dict(self.STEP3_OK, is_special_handling_required='True')
        blocked = self._post_step(3, needs_detail, button='submit_final')
        self.assertContains(blocked, 'special handling')

    def test_going_back_a_step_is_never_blocked(self):
        # prev_step must not validate, or a customer can get stuck on a step
        # they cannot complete and cannot leave.
        response = self._post_step(2, {}, button='prev_step')
        self.assertEqual(response.status_code, 302)


class P2PRoutingTests(TestCase):
    """Spotting the one-off personal sender who filled in the business form."""

    def _enquiry(self, **kwargs):
        defaults = dict(
            full_name='Rotinie', business_name='Aiwa Home',
            business_contact_number='97455512345', product_category='Fashion & Clothing',
            is_complete=True,
        )
        defaults.update(kwargs)
        return PricingEnquiry.objects.create(**defaults)

    def test_the_real_personal_lead_is_flagged(self):
        """Modelled on inquiry #146, which prompted this: business name
        'Personal', a note saying it is not a business, no trading history,
        13 orders a month and pickup from home."""
        from webpages.pricing.routing import p2p_signals
        enquiry = self._enquiry(
            business_name='Personal',
            additional_notes='This is for personal gift delivery only not a business.',
            business_operating_age='New (not started yet)',
            avarage_number_of_order_expect_next_month='1-25',
            type_of_pickup_location='Home',
        )
        signals = p2p_signals(enquiry)
        self.assertTrue(signals['is_likely_p2p'])
        self.assertGreaterEqual(len(signals['reasons']), 3)

    def test_a_real_early_stage_business_is_not_flagged(self):
        """New + low volume + home pickup is an ordinary home-run startup. It
        scores 3 and must stay below the line — these are exactly the leads
        sales does want."""
        from webpages.pricing.routing import p2p_signals
        enquiry = self._enquiry(
            business_name='House of Hikayat',
            business_operating_age='New (not started yet)',
            avarage_number_of_order_expect_next_month='1-25',
            type_of_pickup_location='Home',
        )
        signals = p2p_signals(enquiry)
        self.assertFalse(signals['is_likely_p2p'])
        self.assertEqual(signals['score'], 3)

    def test_a_florist_is_not_flagged_for_selling_gifts(self):
        """'gift' as a bare word would flag every gift shop, so only whole
        phrases like 'not a business' count."""
        from webpages.pricing.routing import p2p_signals
        enquiry = self._enquiry(
            business_name='Gifts by Layali', product_category='Gifts & Flowers',
            additional_notes='We send gift boxes daily and need same-day delivery.',
            avarage_number_of_order_done_last_month='101-300',
        )
        self.assertFalse(p2p_signals(enquiry)['is_likely_p2p'])

    def test_an_established_business_is_never_flagged(self):
        from webpages.pricing.routing import p2p_signals
        enquiry = self._enquiry(
            business_name='Aiwa Home', business_operating_age='More than 3 years',
            avarage_number_of_order_done_last_month='301-1000',
            type_of_pickup_location='Store',
        )
        signals = p2p_signals(enquiry)
        self.assertFalse(signals['is_likely_p2p'])
        self.assertEqual(signals['score'], 0)

    def test_the_quote_page_offers_the_p2p_link(self):
        enquiry = self._enquiry(
            business_name='Personal',
            additional_notes='personal use, one-off',
            business_operating_age='New (not started yet)',
            type_of_pickup_location='Home',
        )
        response = self.client.get(
            reverse('webpages:inquiry_quote', kwargs={'token': enquiry.quote_token}))
        self.assertContains(response, 'one-off or personal parcel')
        self.assertContains(response, reverse('webpages:p2p_pricing'))
        # An offer, never a block — the plans are still there to choose from.
        self.assertContains(response, 'Available plans')

    def test_an_ordinary_business_sees_no_p2p_nudge(self):
        enquiry = self._enquiry(avarage_number_of_order_done_last_month='101-300')
        response = self.client.get(
            reverse('webpages:inquiry_quote', kwargs={'token': enquiry.quote_token}))
        self.assertNotContains(response, 'one-off or personal parcel')


class SeedIdempotenceTests(TestCase):

    def test_reseeding_neither_duplicates_nor_overwrites(self):
        from webpages.migrations import __name__ as _  # noqa: F401
        import importlib
        module = importlib.import_module('webpages.migrations.0013_seed_rate_card_v1')

        ruleset = ensure_rate_card()
        rule = ruleset.rules.filter(dimension='volume_distance_base').first()
        rule.amount = Decimal('99.00')
        rule.save()
        before = ruleset.rules.count()

        class _Apps:
            @staticmethod
            def get_model(app_label, model_name):
                return {'PricingRuleSet': PricingRuleSet, 'PricingRule': PricingRule}[model_name]

        module.seed(_Apps, None)

        self.assertEqual(ruleset.rules.count(), before)
        rule.refresh_from_db()
        self.assertEqual(rule.amount, Decimal('99.00'), 'a staff-edited rate must survive reseeding')


class StaffQuoteTests(TestCase):

    def setUp(self):
        self.ruleset = ensure_rate_card()
        self.ruleset.is_active = True
        self.ruleset.save()
        self.user = User.objects.create_user('sales', 'sales@example.com', 'pw', is_staff=True)
        # Pricing inquiries sit in the marketing department, and
        # StaffDepartmentMiddleware fails closed — a staff user with no
        # department is redirected away from every /workforce/ page.
        from core import models as core_models
        core_models.Profile.objects.create(
            user=self.user, first_name='Sales', last_name='Desk', phone=55500222,
            is_staff=True, dept_marketing=True,
        )
        self.client.force_login(self.user)
        self.inquiry = PricingEnquiry.objects.create(
            full_name='Sara', business_name='Aiwa Home', business_contact_number='97455512345',
            product_category='Home decor', is_complete=True,
            avarage_number_of_order_done_last_month='101-300',
            typical_delivery_distance='10-15 km',
        )
        get_or_create_suggestion(self.inquiry)
        self.inquiry.refresh_from_db()
        self.url = reverse('workforce:pricing_inquiry_quote_price',
                           kwargs={'inquiry_id': self.inquiry.pk})

    def test_accepting_writes_the_staff_quote_not_the_customer_agreement(self):
        response = self.client.post(self.url, {'price': '25.00'})
        self.assertEqual(response.status_code, 200)
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.quoted_price_value, Decimal('25.00'))
        self.assertEqual(self.inquiry.quoted_by, self.user)
        # The customer's own record stays untouched.
        self.assertIsNone(self.inquiry.plan_agreed_at)
        self.assertIsNone(self.inquiry.agreed_price_value)

    def test_accepting_logs_an_activity_and_lifts_a_new_lead(self):
        self.client.post(self.url, {'price': '25.00'})
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.crm_status, PricingEnquiry.STATUS_QUOTED)
        activity = PricingEnquiryActivity.objects.filter(inquiry=self.inquiry).first()
        self.assertIn('accepted the suggested rate', activity.body)

    def test_override_is_recorded_as_an_override(self):
        self.client.post(self.url, {'price': '22.00', 'note': 'matching their courier'})
        suggestion = PricingSuggestion.objects.filter(inquiry=self.inquiry).first()
        self.assertEqual(suggestion.staff_action, PricingSuggestion.ACTION_OVERRIDDEN)
        self.assertEqual(suggestion.staff_price, Decimal('22.00'))

    def test_below_floor_needs_a_reason(self):
        response = self.client.post(self.url, {'price': '5.00'})
        self.assertEqual(response.status_code, 400)
        self.inquiry.refresh_from_db()
        self.assertIsNone(self.inquiry.quoted_price_value)

        ok = self.client.post(self.url, {'price': '5.00', 'note': 'strategic logo client'})
        self.assertEqual(ok.status_code, 200)
        activity = PricingEnquiryActivity.objects.filter(inquiry=self.inquiry).first()
        self.assertIn('BELOW the configured floor', activity.body)

    def test_quoting_after_the_customer_agreed_is_a_counter_offer(self):
        from django.utils import timezone
        self.inquiry.plan_agreed_at = timezone.now()
        self.inquiry.agreed_plan_name = 'Flat Rate — 48 Hour Delivery'
        self.inquiry.agreed_price_value = Decimal('25.00')
        self.inquiry.save()

        response = self.client.post(self.url, {'price': '22.00'})
        self.assertTrue(response.json()['counter_offer'])
        self.inquiry.refresh_from_db()
        # Their agreement survives; the staff number sits alongside it.
        self.assertEqual(self.inquiry.agreed_price_value, Decimal('25.00'))
        self.assertEqual(self.inquiry.quoted_price_value, Decimal('22.00'))

    def test_rubbish_price_is_rejected(self):
        for value in ('', 'abc', '-5', '0'):
            with self.subTest(value=value):
                self.assertEqual(self.client.post(self.url, {'price': value}).status_code, 400)

    def test_detail_page_survives_a_broken_engine(self):
        with patch('webpages.pricing.engine.get_or_create_suggestion',
                   side_effect=RuntimeError('boom')):
            response = self.client.get(
                reverse('workforce:pricing_inquiry_detail', kwargs={'inquiry_id': self.inquiry.pk}))
        self.assertEqual(response.status_code, 200)

    def test_panel_shows_the_breakdown_and_no_margin(self):
        response = self.client.get(
            reverse('workforce:pricing_inquiry_detail', kwargs={'inquiry_id': self.inquiry.pk}))
        self.assertContains(response, 'Suggested Rate')
        self.assertContains(response, 'How we got here')
        self.assertContains(response, 'configured, not a measured cost')
        self.assertNotContains(response, 'Margin')
