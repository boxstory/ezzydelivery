# Purpose: Tests for delivery.geo — resolving the delivery area (neighbourhood) inside a zone.
# Used by: python manage.py test delivery.tests_geo
# Notes: The resolver is duck-typed on three attributes, so these use a stub rather than a real
#        Order — the real-Order path is covered by the signal tests in orders/tests.py. Every
#        test clears the cache first: a leaked zone-area map is the obvious cross-test flake.

from django.core.cache import cache
from django.test import TestCase, override_settings

from delivery import models as delivery_models
from delivery.geo import (
    ZONE_AREA_CACHE_KEY,
    apply_delivery_area,
    resolve_delivery_area,
    zone_area_map,
)

ZoneName = delivery_models.ZoneName
ZoneArea = delivery_models.ZoneArea


class StubOrder:
    """The three attributes the resolver reads, plus the two it writes."""

    def __init__(self, dl_zone=None, latitude=None, longitude=None):
        self.dl_zone = dl_zone
        self.latitude = latitude
        self.longitude = longitude
        self.delivery_area_name = ''
        self.delivery_area_source = ''


@override_settings(CACHES={'default': {
    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    'LOCATION': 'tests-geo',
}})
class DeliveryAreaResolverTest(TestCase):
    """Which neighbourhood a pin lands in, and how confident that answer is."""

    def setUp(self):
        cache.clear()

        # Many areas: the pin has to choose.
        self.many = ZoneName.objects.create(
            zone_number=9001, zone_name='Many Zone', is_active=True,
            latitude='25.2500000', longitude='51.5500000',
        )
        ZoneArea.objects.create(zone=self.many, area_name='North Area',
                                latitude='25.3000000', longitude='51.5000000')
        ZoneArea.objects.create(zone=self.many, area_name='South Area',
                                latitude='25.2000000', longitude='51.6000000')

        # Exactly one area — the branch that carries 40 of the 90 real mapped zones.
        self.single = ZoneName.objects.create(
            zone_number=9002, zone_name='Single Zone', is_active=True,
            latitude='25.2600000', longitude='51.5600000',
        )
        ZoneArea.objects.create(zone=self.single, area_name='Lone Area',
                                latitude='25.2600000', longitude='51.5600000')

        # No areas at all — 6 real active zones are in this state.
        self.empty = ZoneName.objects.create(
            zone_number=9003, zone_name='Empty Zone', is_active=True,
            latitude='25.2700000', longitude='51.5700000',
        )

        # The area name merely repeats the zone name, with different case/spacing.
        self.dup = ZoneName.objects.create(
            zone_number=9004, zone_name='Duplicate Zone', is_active=True,
            latitude='25.2800000', longitude='51.5800000',
        )
        ZoneArea.objects.create(zone=self.dup, area_name='  duplicate ZONE ',
                                latitude='25.2800000', longitude='51.5800000')

    def test_pin_picks_the_nearest_area(self):
        order = StubOrder(dl_zone=9001, latitude='25.2050000', longitude='51.5950000')
        self.assertEqual(resolve_delivery_area(order), ('South Area', 'pin'))

    def test_pin_picks_the_other_area_when_it_moves(self):
        order = StubOrder(dl_zone=9001, latitude='25.2950000', longitude='51.5050000')
        self.assertEqual(resolve_delivery_area(order), ('North Area', 'pin'))

    def test_single_area_zone_names_itself_without_a_pin(self):
        order = StubOrder(dl_zone=9002)
        self.assertEqual(resolve_delivery_area(order), ('Lone Area', 'only_area'))

    def test_many_areas_without_a_pin_is_unresolved(self):
        """Naming one of two areas with nothing to go on would be a guess."""
        order = StubOrder(dl_zone=9001)
        self.assertEqual(resolve_delivery_area(order), ('', 'unresolved'))

    def test_zone_with_no_areas_is_unresolved(self):
        order = StubOrder(dl_zone=9003, latitude='25.2700000', longitude='51.5700000')
        self.assertEqual(resolve_delivery_area(order), ('', 'unresolved'))

    def test_no_zone_is_unresolved(self):
        order = StubOrder(latitude='25.2700000', longitude='51.5700000')
        self.assertEqual(resolve_delivery_area(order), ('', 'unresolved'))

    def test_pin_outside_qatar_is_discarded(self):
        """lat 2.0 is the real corrupt value in production — a truncated 25.x.

        It must never be trusted enough to produce a 'pin' answer; the zone has
        two areas and no other way to choose, so the honest result is unresolved.
        """
        order = StubOrder(dl_zone=9001, latitude='2.0000000', longitude='51.5950000')
        self.assertEqual(resolve_delivery_area(order), ('', 'unresolved'))

    def test_area_repeating_the_zone_name_is_blanked(self):
        """Distinguishable from 'never computed' — the source says it was resolved."""
        order = StubOrder(dl_zone=9004, latitude='25.2800000', longitude='51.5800000')
        name, source = resolve_delivery_area(order)
        self.assertEqual(name, '')
        self.assertEqual(source, 'same_as_zone')

    def test_inactive_areas_are_ignored(self):
        ZoneArea.objects.filter(zone=self.single).update(is_active=False)
        cache.clear()
        order = StubOrder(dl_zone=9002, latitude='25.2600000', longitude='51.5600000')
        self.assertEqual(resolve_delivery_area(order), ('', 'unresolved'))

    def test_apply_reports_no_change_on_a_repeat_call(self):
        """This is what keeps a no-op order save from issuing a pointless UPDATE."""
        order = StubOrder(dl_zone=9001, latitude='25.2050000', longitude='51.5950000')
        self.assertTrue(apply_delivery_area(order))
        self.assertEqual(order.delivery_area_name, 'South Area')
        self.assertFalse(apply_delivery_area(order))

    def test_apply_reports_a_change_when_the_pin_moves(self):
        order = StubOrder(dl_zone=9001, latitude='25.2050000', longitude='51.5950000')
        apply_delivery_area(order)
        order.latitude, order.longitude = '25.2950000', '51.5050000'
        self.assertTrue(apply_delivery_area(order))
        self.assertEqual(order.delivery_area_name, 'North Area')

    def test_passing_the_map_avoids_a_query(self):
        area_map = zone_area_map()
        order = StubOrder(dl_zone=9001, latitude='25.2050000', longitude='51.5950000')
        with self.assertNumQueries(0):
            resolve_delivery_area(order, area_map)


@override_settings(CACHES={'default': {
    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    'LOCATION': 'tests-geo-cache',
}})
class ZoneAreaCacheTest(TestCase):
    """The map is cached because it is read on every order save, not once per page."""

    def setUp(self):
        cache.clear()
        self.zone = ZoneName.objects.create(
            zone_number=9010, zone_name='Cache Zone', is_active=True,
            latitude='25.2500000', longitude='51.5500000',
        )
        self.area = ZoneArea.objects.create(
            zone=self.zone, area_name='Cached Area',
            latitude='25.2500000', longitude='51.5500000',
        )

    def test_second_call_hits_the_cache(self):
        zone_area_map()
        with self.assertNumQueries(0):
            zone_area_map()

    def test_saving_an_area_invalidates_the_map(self):
        """delivery.signals.zonearea_saved calls invalidate_zone_cache for us."""
        self.assertEqual(zone_area_map()[9010][0][0], 'Cached Area')

        self.area.area_name = 'Renamed Area'
        self.area.save()

        self.assertIsNone(cache.get(ZONE_AREA_CACHE_KEY))
        self.assertEqual(zone_area_map()[9010][0][0], 'Renamed Area')

    def test_moving_an_area_pin_invalidates_the_map(self):
        zone_area_map()
        self.area.latitude = '25.3500000'
        self.area.save()

        self.assertIsNone(cache.get(ZONE_AREA_CACHE_KEY))
        self.assertAlmostEqual(zone_area_map()[9010][0][1], 25.35, places=4)

    def test_areas_without_coordinates_are_excluded(self):
        ZoneArea.objects.create(zone=self.zone, area_name='Unpinned Area')
        cache.clear()
        names = [a[0] for a in zone_area_map()[9010]]
        self.assertEqual(names, ['Cached Area'])
