# Purpose: The staff P2P rate card page — the box-tier editor and the matrix's box dimension.
# Used by: manage.py test workforce.tests_p2p_rate_card
# Notes: Kept out of tests_views.py, which is large and carries known failures of its own.

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from p2p.models import P2PBoxTier, P2PRateBand, P2PVehicleBoxLimit, P2PVehicleCapacity
from workforce.tests_views import WorkforceTestMixin


class P2PRateCardBoxTierTests(WorkforceTestMixin, TestCase):
    """Boxes are the fifth pricing dimension, and ops edit them on the same page."""

    def setUp(self):
        self.user, _profile = self.create_staff_user()
        self.client.login(username='staffuser', password='Staff@123')
        self.url = reverse('workforce:wf_p2p_rate_card')
        P2PRateBand.objects.all().delete()
        P2PRateBand.objects.create(min_boxes=1, up_to_km=None, price=Decimal('40'))
        P2PBoxTier.objects.all().delete()
        self.one = P2PBoxTier.objects.create(min_boxes=1, max_boxes=1, uplift=Decimal('0'))
        self.few = P2PBoxTier.objects.create(min_boxes=2, max_boxes=3, uplift=Decimal('10'))
        self.many = P2PBoxTier.objects.create(min_boxes=4, max_boxes=None, needs_quote=True)

    def _matrix_prices(self, response, tier=None):
        return {cell['price'] for row in response.context['matrix'] for cell in row['cells']
                if cell['price'] is not None
                and (tier is None or cell['tier_id'] == tier.id)}

    def test_every_box_tier_is_a_column_group(self):
        """All three counts are on screen at once, each carrying its own uplift."""
        resp = self.client.get(self.url)
        self.assertEqual([t.id for t in resp.context['matrix_tiers']],
                         [self.one.id, self.few.id, self.many.id])
        self.assertEqual(self._matrix_prices(resp, self.one), {Decimal('40')})
        self.assertEqual(self._matrix_prices(resp, self.few), {Decimal('50')})
        # One group per tier, each as wide as speeds × distance columns.
        cells = resp.context['matrix'][0]['cells']
        self.assertEqual(len(cells),
                         resp.context['matrix_tier_cols'] * len(resp.context['matrix_tiers']))
        self.assertEqual(resp.context['matrix_total_cols'], len(cells))

    def test_a_quote_tier_prices_nothing_in_its_own_group_only(self):
        """A tier that needs a quote must not take the priced groups with it."""
        resp = self.client.get(self.url)
        self.assertEqual(self._matrix_prices(resp, self.many), set())
        self.assertTrue(all(cell['needs_quote']
                            for row in resp.context['matrix'] for cell in row['cells']
                            if cell['tier_id'] == self.many.id))
        self.assertTrue(self._matrix_prices(resp, self.one))

    def _post(self, **overrides):
        """The whole page posts as one form — both formsets, or neither saves."""
        bands = list(P2PRateBand.objects.all())
        caps = list(P2PVehicleCapacity.objects.all().order_by('capacity_cbm', 'id'))
        limits = list(P2PVehicleBoxLimit.objects.all().order_by('vehicle', 'size', 'id'))
        data = {
            'form-TOTAL_FORMS': str(len(bands) + 1),
            'form-INITIAL_FORMS': str(len(bands)),
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'tiers-TOTAL_FORMS': '4',
            'tiers-INITIAL_FORMS': '3',
            'tiers-MIN_NUM_FORMS': '0',
            'tiers-MAX_NUM_FORMS': '1000',
            'caps-TOTAL_FORMS': str(len(caps) + 1),
            'caps-INITIAL_FORMS': str(len(caps)),
            'caps-MIN_NUM_FORMS': '0',
            'caps-MAX_NUM_FORMS': '1000',
            'limits-TOTAL_FORMS': str(len(limits) + 1),
            'limits-INITIAL_FORMS': str(len(limits)),
            'limits-MIN_NUM_FORMS': '0',
            'limits-MAX_NUM_FORMS': '1000',
        }
        for i, limit in enumerate(limits):
            data.update({
                f'limits-{i}-id': str(limit.id),
                f'limits-{i}-vehicle': limit.vehicle,
                f'limits-{i}-size': limit.size,
                f'limits-{i}-max_boxes': ('' if limit.max_boxes is None
                                          else str(limit.max_boxes)),
                f'limits-{i}-is_active': 'on',
            })
        for i, cap in enumerate(caps):
            data.update({
                f'caps-{i}-id': str(cap.id),
                f'caps-{i}-vehicle': cap.vehicle,
                f'caps-{i}-min_cbm': str(cap.min_cbm),
                f'caps-{i}-capacity_cbm': str(cap.capacity_cbm),
                f'caps-{i}-is_active': 'on',
            })
        for i, band in enumerate(bands):
            data.update({
                f'form-{i}-id': str(band.id),
                f'form-{i}-min_boxes': str(band.min_boxes),
                f'form-{i}-max_boxes': '',
                f'form-{i}-size': band.size,
                f'form-{i}-up_to_kg': '',
                f'form-{i}-vehicle': band.vehicle,
                f'form-{i}-speed': band.speed,
                f'form-{i}-up_to_km': '',
                f'form-{i}-price': str(band.price),
                f'form-{i}-priority': str(band.priority),
                f'form-{i}-is_active': 'on',
            })
        for i, tier in enumerate([self.one, self.few, self.many]):
            data.update({
                f'tiers-{i}-id': str(tier.id),
                f'tiers-{i}-min_boxes': str(tier.min_boxes),
                f'tiers-{i}-max_boxes': '' if tier.max_boxes is None else str(tier.max_boxes),
                f'tiers-{i}-up_to_kg': '' if tier.up_to_kg is None else str(tier.up_to_kg),
                f'tiers-{i}-uplift': str(tier.uplift),
                f'tiers-{i}-is_active': 'on',
            })
            if tier.needs_quote:
                data[f'tiers-{i}-needs_quote'] = 'on'
        data.update(overrides)
        return self.client.post(self.url, data, follow=True)

    def test_an_uplift_edit_saves_and_moves_the_price(self):
        resp = self._post(**{'tiers-1-uplift': '18'})
        self.assertEqual(resp.status_code, 200)
        self.few.refresh_from_db()
        self.assertEqual(self.few.uplift, Decimal('18'))
        after = self.client.get(self.url)
        self.assertEqual(self._matrix_prices(after, self.few), {Decimal('58')})

    def test_adding_a_band_with_a_new_ceiling_adds_a_column(self):
        """End to end, through the page: the chart's shape follows the card, so a new
        distance bracket needs no code change to appear."""
        before = self.client.get(self.url)
        self.assertNotIn('≤ 55 km', before.context['matrix_km'])

        blank = P2PRateBand.objects.count()
        self._post(**{
            f'form-{blank}-min_boxes': '1',
            f'form-{blank}-up_to_km': '55',
            f'form-{blank}-price': '70',
            f'form-{blank}-priority': '0',
            f'form-{blank}-is_active': 'on',
        })
        after = self.client.get(self.url)
        self.assertIn('≤ 55 km', after.context['matrix_km'])
        self.assertEqual(
            len(after.context['matrix'][0]['cells']),
            len(after.context['matrix_km']) * len(after.context['matrix_speeds'])
            * len(after.context['matrix_tiers']))

    def test_the_editor_is_folded_away_until_it_is_asked_for(self):
        """The page is read far more often than it is edited, so it opens on the chart."""
        resp = self.client.get(self.url)
        self.assertFalse(resp.context['editor_open'])
        self.assertContains(resp, 'id="workforce_ratecard_editor" hidden')
        self.assertContains(resp, 'Edit rate card')
        # Folded, not gone: every row is still in the DOM and still posts.
        self.assertContains(resp, 'workforce_ratecard_table_bands')

    def test_a_failed_save_comes_back_with_the_editor_open(self):
        """The errors are inside the fold. A page that looked untouched would read as
        "nothing happened" rather than "nothing saved"."""
        resp = self._post(**{'form-0-price': '', 'form-0-needs_quote': ''})
        self.assertTrue(resp.context['editor_open'])
        self.assertNotContains(resp, 'id="workforce_ratecard_editor" hidden')
        self.assertContains(resp, 'Set a price, or tick')
        self.assertContains(resp, 'Close editor')

    def test_a_row_added_on_the_page_saves(self):
        """The Add button clones the spare row and bumps TOTAL_FORMS; this is that POST.
        A count that disagrees with the rows sent is rejected wholesale, so the contract
        is worth a test even though the button itself is three lines of JS."""
        resp = self._post(**{
            'tiers-TOTAL_FORMS': '5',
            'tiers-4-min_boxes': '21',
            'tiers-4-max_boxes': '40',
            'tiers-4-up_to_kg': '500',
            'tiers-4-uplift': '75',
            'tiers-4-is_active': 'on',
        })
        self.assertContains(resp, 'Rate card updated')
        added = P2PBoxTier.objects.get(min_boxes=21)
        self.assertEqual(added.uplift, Decimal('75'))
        self.assertEqual(added.up_to_kg, Decimal('500'))

    def test_the_trailing_blank_tier_row_does_not_block_a_save(self):
        """The extra row posts the model defaults back; treating that as a real edit
        would fail the formset and discard every band edit on the page with it."""
        resp = self._post(**{
            'tiers-3-min_boxes': '1', 'tiers-3-max_boxes': '', 'tiers-3-uplift': '0',
        })
        self.assertEqual(P2PBoxTier.objects.count(), 3)
        self.assertContains(resp, 'Rate card updated')
