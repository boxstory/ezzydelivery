"""
Management command to fetch zone polygons from QNAS API and update ZoneName model.

Usage:
    python manage.py fetch_zone_polygons           # Fetch all zones
    python manage.py fetch_zone_polygons --zone=1  # Fetch specific zone
    python manage.py fetch_zone_polygons --dry-run # Preview without saving
"""
import time
import requests
from decouple import config

from django.core.management.base import BaseCommand
from delivery.models import ZoneName


class Command(BaseCommand):
    help = 'Fetch zone polygons from QNAS API and update ZoneName model'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zone',
            type=int,
            help='Fetch polygon for a specific zone number only',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving',
        )

    def handle(self, *args, **options):
        zone_number = options.get('zone')
        dry_run = options['dry_run']

        # QNAS API configuration
        base_url = "https://qnas.qa"
        token = config("QNAS_TOKEN", default="75f6618da1204809900d904de6e61b40")
        domain = config("QNAS_DOMAIN", default="ezzydelivery.qa")

        headers = {
            "X-Token": token,
            "X-Domain": domain,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://{domain}/",
            "Origin": f"https://{domain}",
        }

        # Get zones to process
        if zone_number:
            zones = ZoneName.objects.filter(zone_number=zone_number)
            if not zones.exists():
                self.stdout.write(self.style.ERROR(f'Zone {zone_number} not found'))
                return
        else:
            zones = ZoneName.objects.all().order_by('zone_number')

        self.stdout.write(f'Fetching polygons for {zones.count()} zones from QNAS API...')
        self.stdout.write('')

        updated = 0
        failed = 0
        skipped = 0

        for zone in zones:
            self.stdout.write(f'Zone {zone.zone_number} ({zone.zone_name})... ', ending='')

            try:
                # QNAS API endpoint: /get_zone_polygon/{zone_number}
                url = f"{base_url}/get_zone_polygon/{zone.zone_number}"
                resp = requests.get(url, headers=headers, timeout=15)

                if resp.status_code != 200:
                    self.stdout.write(self.style.WARNING(f'HTTP {resp.status_code}'))
                    failed += 1
                    time.sleep(1)
                    continue

                data = resp.json()

                # Check for API error response
                if data.get('status') == 'error':
                    self.stdout.write(self.style.WARNING(data.get('message', 'API error')))
                    skipped += 1
                    time.sleep(0.5)
                    continue

                # Extract polygon coordinates from QNAS response
                # Format: {"status": "success", "coordinates": [{"lat": x, "lng": y}, ...]}
                polygon = None
                if data.get('status') == 'success' and 'coordinates' in data:
                    coords = data['coordinates']
                    if isinstance(coords, list) and len(coords) >= 3:
                        # Convert from [{lat, lng}, ...] to [[lat, lng], ...]
                        polygon = [[p['lat'], p['lng']] for p in coords if 'lat' in p and 'lng' in p]

                if polygon and len(polygon) >= 3:
                    if dry_run:
                        self.stdout.write(self.style.SUCCESS(f'[DRY RUN] {len(polygon)} points'))
                    else:
                        zone.polygon = polygon
                        zone.save(update_fields=['polygon', 'updated_at'])
                        self.stdout.write(self.style.SUCCESS(f'{len(polygon)} points'))
                    updated += 1
                else:
                    self.stdout.write(self.style.WARNING('No polygon data'))
                    skipped += 1

                # Rate limiting to avoid "Too many IP requests"
                time.sleep(0.5)

            except requests.exceptions.Timeout:
                self.stdout.write(self.style.ERROR('Timeout'))
                failed += 1
                time.sleep(2)
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f'Request error: {e}'))
                failed += 1
                time.sleep(2)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error: {e}'))
                failed += 1

        # Summary
        self.stdout.write('')
        self.stdout.write('=' * 50)
        self.stdout.write(f'Updated: {updated}')
        self.stdout.write(f'Failed: {failed}')
        self.stdout.write(f'Skipped (no data): {skipped}')
        self.stdout.write('=' * 50)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('Done!'))
