# Purpose: Tests for the Qatar-destination rule that keeps a GCC-wide store's foreign orders out of the import lists.
# Used by: manage.py test core.tests_destination
# Notes: The shape-matrix test is the point of this file — the same order must get the same
#        verdict whether it arrives as a raw Shopify dict, a shopify-lib object, a staged
#        row dict or a WooCommerce dict. No network, no DB: these are pure functions.
from types import SimpleNamespace as NS

from django.test import SimpleTestCase

from core.destination import (
    SERVICE_COUNTRY, canonical_country, destination_verdict, filter_deliverable,
    is_foreign, is_qatar_phone, order_country,
)


class CanonicalCountryTests(SimpleTestCase):
    def test_every_way_qatar_is_written(self):
        for value in ('QA', 'qa', ' qa ', 'Qatar', 'qatar ', 'QAT',
                      'State of Qatar', 'قطر'):
            self.assertEqual(canonical_country(value), SERVICE_COUNTRY, value)

    def test_foreign_codes_survive_for_the_log_line(self):
        # The code is kept rather than reduced to a bool so a skipped order can
        # say "ships to AE" instead of just "not Qatar".
        self.assertEqual(canonical_country('AE'), 'AE')
        self.assertEqual(canonical_country('bh'), 'BH')

    def test_unreadable_is_empty_not_foreign(self):
        for value in ('', None, '   '):
            self.assertEqual(canonical_country(value), '')


class QatarPhoneTests(SimpleTestCase):
    def test_accepts_every_qatar_format(self):
        for value in ('33445566', '55155556', '+974 5515 5556',
                      '974 33445566', '0097433445566'):
            self.assertTrue(is_qatar_phone(value), value)

    def test_rejects_gulf_neighbours(self):
        # Real numbers off the live store that must not read as Qatari: UAE and
        # Bahrain mobiles are 9-10 digits, so length alone separates them.
        for value in ('0542042944', '0507670213', '0558212796',
                      '0097339655967', '12345678', '47445566', '', None):
            self.assertFalse(is_qatar_phone(value), value)


def _shapes(country, phone=None):
    """One order expressed in all four shapes the import paths hand us."""
    ship = {'country_code': country}
    if phone:
        ship['phone'] = phone
    flat = {'order_id': '#1', 'shipping.country_code': country}
    if phone:
        flat['shipping.phone'] = phone
    woo_ship = {'country': country}
    if phone:
        woo_ship['phone'] = phone
    return {
        'raw shopify dict': {'name': '#1', 'shipping_address': dict(ship)},
        'shopify lib object': NS(name='#1', shipping_address=NS(**ship)),
        'staged row dict': flat,
        'woocommerce dict': {'number': '#1', 'shipping': woo_ship},
    }


class ShapeMatrixTests(SimpleTestCase):
    """One implementation, four input shapes — this is what stops them drifting."""

    def test_qatar_order_is_local_in_every_shape(self):
        for label, order in _shapes('QA').items():
            self.assertEqual(order_country(order), 'QA', label)
            self.assertEqual(destination_verdict(order), 'local', label)

    def test_foreign_order_is_foreign_in_every_shape(self):
        for label, order in _shapes('AE', '0542042944').items():
            self.assertEqual(order_country(order), 'AE', label)
            self.assertEqual(destination_verdict(order), 'foreign', label)


class VerdictTests(SimpleTestCase):
    def test_shipping_wins_over_billing(self):
        # Live order #1011 ships to Pakistan but bills to the UAE. Reading
        # billing would import a delivery we cannot make.
        order = {'shipping_address': {'country_code': 'PK'},
                 'billing_address': {'country_code': 'AE'}}
        self.assertEqual(destination_verdict(order), 'foreign')

    def test_qatari_phone_rescues_a_wrong_country_box(self):
        # Accepted trade-off: shoppers leave the store's default country set.
        order = {'shipping_address': {'country_code': 'AE', 'phone': '33445566'}}
        self.assertEqual(destination_verdict(order), 'local')

    def test_nothing_readable_is_unknown_and_is_kept(self):
        # Fails open on purpose. A wrongly hidden Qatar order is never delivered
        # and nobody finds out; a foreign order reaching a human can be refused.
        self.assertEqual(destination_verdict({}), 'unknown')
        self.assertFalse(is_foreign({}, NS(import_qatar_only=True)))


class SwitchTests(SimpleTestCase):
    """Nothing may be withheld unless the seller ticked the box."""

    foreign = {'name': '#1011', 'shipping_address': {'country_code': 'AE'}}

    def test_filter_is_inert_while_the_box_is_off(self):
        off = NS(import_qatar_only=False)
        self.assertFalse(is_foreign(self.foreign, off))
        kept, dropped = filter_deliverable([self.foreign], off)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])

    def test_filter_withholds_once_the_box_is_on(self):
        on = NS(import_qatar_only=True)
        self.assertTrue(is_foreign(self.foreign, on))
        kept, dropped = filter_deliverable([self.foreign], on)
        self.assertEqual(kept, [])
        self.assertEqual(dropped, ['#1011 -> AE'])

    def test_missing_field_defaults_to_off(self):
        # A caller holding something that is not a BusinessApiSettings must not
        # accidentally start hiding orders.
        self.assertFalse(is_foreign(self.foreign, NS()))

    def test_the_live_jm_auto_parts_order_set(self):
        """The 11 real orders on the connected store: every one is withheld."""
        live = ([{'name': f'#{n}', 'shipping_address': {'country_code': 'AE',
                                                        'phone': '0542042944'}}
                 for n in range(1001, 1010)]
                + [{'name': '#1009', 'shipping_address': {'country_code': 'BH',
                                                          'phone': '0097339655967'}},
                   {'name': '#1001', 'shipping_address': {'country_code': 'PK',
                                                          'phone': '0558212796'}}])
        kept, dropped = filter_deliverable(live, NS(import_qatar_only=True))
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 11)
