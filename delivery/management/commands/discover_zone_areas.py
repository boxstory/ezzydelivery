"""
Discover area/district names within zone polygons using HERE Maps reverse geocoding.

For each zone with a polygon, samples points inside the polygon and reverse geocodes
them to find Arabic district names. New areas are added as ZoneArea records.

Usage:
    python manage.py discover_zone_areas              # dry-run (shows what would be added)
    python manage.py discover_zone_areas --apply       # actually create ZoneArea records
    python manage.py discover_zone_areas --zone 53     # single zone only
"""
import time
import math
import requests
from django.core.management.base import BaseCommand
from decouple import config
from delivery.models import ZoneName, ZoneArea


class Command(BaseCommand):
    help = "Discover area names within zone polygons via HERE Maps reverse geocoding"

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually create ZoneArea records')
        parser.add_argument('--zone', type=int, help='Process only this zone number')

    def handle(self, *args, **options):
        here_key = config("HERE_MAP_API_KEY", default="")
        if not here_key:
            self.stderr.write(self.style.ERROR("HERE_MAP_API_KEY not set in .env"))
            return

        apply = options['apply']
        zone_num = options.get('zone')

        zones = ZoneName.objects.filter(is_active=True, polygon__isnull=False).exclude(polygon=[])
        if zone_num:
            zones = zones.filter(zone_number=zone_num)

        self.stdout.write(f"Processing {zones.count()} zones {'(DRY RUN)' if not apply else '(APPLYING)'}")
        self.stdout.write("")

        total_new = 0
        total_skipped = 0

        for zone in zones.order_by('zone_number'):
            polygon = zone.polygon
            if not polygon or len(polygon) < 3:
                continue

            # Get existing area names (Arabic) for this zone
            existing_arabic = set(
                ZoneArea.objects.filter(zone=zone, is_active=True)
                .exclude(area_name_arabic__isnull=True)
                .exclude(area_name_arabic='')
                .values_list('area_name_arabic', flat=True)
            )
            existing_english = set(
                ZoneArea.objects.filter(zone=zone, is_active=True)
                .values_list('area_name', flat=True)
            )

            # Sample points: center + evenly spaced polygon vertices
            points = []
            if zone.latitude and zone.longitude:
                points.append((float(zone.latitude), float(zone.longitude)))

            step = max(1, len(polygon) // 6)
            for i in range(0, len(polygon), step):
                pt = polygon[i]
                points.append((pt[0], pt[1]))

            # Also add midpoints between vertices for better interior coverage
            for i in range(0, len(polygon) - 1, max(1, len(polygon) // 3)):
                mid_lat = (polygon[i][0] + polygon[(i + len(polygon) // 2) % len(polygon)][0]) / 2
                mid_lng = (polygon[i][1] + polygon[(i + len(polygon) // 2) % len(polygon)][1]) / 2
                points.append((mid_lat, mid_lng))

            # Deduplicate nearby points (within 200m)
            unique_points = []
            for p in points:
                too_close = False
                for u in unique_points:
                    if math.sqrt((p[0] - u[0])**2 + (p[1] - u[1])**2) * 111000 < 200:
                        too_close = True
                        break
                if not too_close:
                    unique_points.append(p)

            # Reverse geocode each point
            discovered = {}  # arabic_name -> {lat, lng, english_hint}
            for lat, lng in unique_points[:12]:  # max 12 points per zone
                try:
                    resp = requests.get(
                        "https://revgeocode.search.hereapi.com/v1/revgeocode",
                        params={'at': f'{lat},{lng}', 'apiKey': here_key},
                        timeout=8,
                    )
                    if resp.status_code == 200:
                        items = resp.json().get('items', [])
                        if items:
                            addr = items[0].get('address', {})
                            district_ar = addr.get('district', '').strip()
                            if district_ar and district_ar not in discovered:
                                pos = items[0].get('position', {})
                                discovered[district_ar] = {
                                    'lat': pos.get('lat', lat),
                                    'lng': pos.get('lng', lng),
                                }
                    time.sleep(0.15)  # rate limiting
                except Exception as e:
                    self.stderr.write(f"  Error at ({lat},{lng}): {e}")

            # Now translate Arabic district names to English using HERE forward geocode
            new_areas = []
            for arabic_name, coords in discovered.items():
                if arabic_name in existing_arabic:
                    total_skipped += 1
                    continue

                # Try to get English name
                english_name = arabic_name  # fallback
                try:
                    resp = requests.get(
                        "https://geocode.search.hereapi.com/v1/geocode",
                        params={
                            'q': f'{arabic_name}, Qatar',
                            'in': 'countryCode:QAT',
                            'lang': 'en',
                            'limit': 1,
                            'apiKey': here_key,
                        },
                        timeout=8,
                    )
                    if resp.status_code == 200:
                        items = resp.json().get('items', [])
                        if items:
                            addr = items[0].get('address', {})
                            en_district = addr.get('district', '')
                            if en_district:
                                english_name = en_district
                    time.sleep(0.15)
                except Exception:
                    pass

                # Check if English name already exists
                if english_name in existing_english:
                    # Update Arabic name on existing record if missing
                    existing = ZoneArea.objects.filter(zone=zone, area_name=english_name).first()
                    if existing and not existing.area_name_arabic:
                        if apply:
                            existing.area_name_arabic = arabic_name
                            existing.save(update_fields=['area_name_arabic'])
                        self.stdout.write(f"  Zone {zone.zone_number}: Updated Arabic for '{english_name}' -> '{arabic_name}'")
                    total_skipped += 1
                    continue

                new_areas.append({
                    'english': english_name,
                    'arabic': arabic_name,
                    'lat': coords['lat'],
                    'lng': coords['lng'],
                })

            # Report
            if new_areas or discovered:
                existing_list = ', '.join(sorted(existing_english)[:5])
                self.stdout.write(
                    f"Zone {zone.zone_number:>2d} ({zone.zone_name:25s}): "
                    f"{len(discovered)} districts found, {len(new_areas)} NEW"
                )
                for area in new_areas:
                    self.stdout.write(
                        f"         + {area['english']} ({area['arabic']}) "
                        f"at ({area['lat']:.5f}, {area['lng']:.5f})"
                    )
                    if apply:
                        ZoneArea.objects.get_or_create(
                            zone=zone,
                            area_name=area['english'],
                            defaults={
                                'area_name_arabic': area['arabic'],
                                'latitude': area['lat'],
                                'longitude': area['lng'],
                                'is_active': True,
                            }
                        )
                    total_new += 1

        self.stdout.write("")
        self.stdout.write(f"{'WOULD ADD' if not apply else 'ADDED'}: {total_new} new areas, {total_skipped} already existed")
        if not apply and total_new > 0:
            self.stdout.write(self.style.WARNING("Run with --apply to actually create the records"))
