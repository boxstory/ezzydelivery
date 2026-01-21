"""
Management command to import zone data from CSV file.
Reads media/qnas_complete_zone_names.csv and updates ZoneName and ZoneArea models.
"""
import csv
import re
from decimal import Decimal
from urllib.parse import urlparse, parse_qs

from django.core.management.base import BaseCommand
from django.conf import settings

from delivery.models import ZoneName, ZoneArea


class Command(BaseCommand):
    help = 'Import zone data from CSV file to ZoneName and ZoneArea models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without saving',
        )

    def extract_lat_long(self, google_link):
        """Extract latitude and longitude from Google Maps link."""
        try:
            parsed = urlparse(google_link)
            query_params = parse_qs(parsed.query)
            if 'query' in query_params:
                coords = query_params['query'][0]
                lat, lng = coords.split(',')
                return Decimal(lat.strip()), Decimal(lng.strip())
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Failed to parse coords from {google_link}: {e}'))
        return None, None

    def parse_zone_name(self, zone_name_raw):
        """
        Parse zone name to extract English and Arabic names.
        Format: "NUMBER - English Name - العربية"
        Handles cases where English name contains hyphens.
        """
        # First, remove the zone number prefix (e.g., "90 - ")
        parts = zone_name_raw.split(' - ', 1)
        if len(parts) < 2:
            return zone_name_raw.strip(), ''

        # Remaining text after zone number
        remaining = parts[1].strip()

        # Find the position where Arabic text starts
        # Arabic Unicode range: \u0600-\u06FF
        arabic_match = re.search(r'[\u0600-\u06FF]', remaining)

        if arabic_match:
            arabic_start = arabic_match.start()
            # Find the separator before Arabic text (usually " - ")
            # Look for " - " before the Arabic text
            separator_pos = remaining.rfind(' - ', 0, arabic_start)
            if separator_pos > 0:
                english_name = remaining[:separator_pos].strip()
                arabic_name = remaining[separator_pos + 3:].strip()
            else:
                # No separator found, all is English before Arabic
                english_name = remaining[:arabic_start].strip().rstrip(' -')
                arabic_name = remaining[arabic_start:].strip()
        else:
            # No Arabic text found
            english_name = remaining.strip()
            arabic_name = ''

        return english_name, arabic_name

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        csv_path = settings.BASE_DIR / 'media' / 'qnas_complete_zone_names.csv'

        if not csv_path.exists():
            self.stdout.write(self.style.ERROR(f'CSV file not found: {csv_path}'))
            return

        # Dictionary to collect zone data (first occurrence per zone number)
        zone_data = {}
        # List to collect ALL areas from CSV
        all_areas = []

        self.stdout.write(f'Reading CSV from: {csv_path}')

        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            for row in reader:
                zone_number = int(row['zone_number'])
                zone_name_raw = row['zone_name']
                google_link = row['google_link']

                english_name, arabic_name = self.parse_zone_name(zone_name_raw)
                lat, lng = self.extract_lat_long(google_link)

                # Track all areas
                all_areas.append({
                    'zone_number': zone_number,
                    'english': english_name,
                    'arabic': arabic_name,
                    'lat': lat,
                    'lng': lng,
                })

                # Use first occurrence as the main zone data
                if zone_number not in zone_data:
                    zone_data[zone_number] = {
                        'english_name': english_name,
                        'arabic_name': arabic_name,
                        'latitude': lat,
                        'longitude': lng,
                        'areas': [],
                    }

                # Add area to zone's area list
                zone_data[zone_number]['areas'].append({
                    'english': english_name,
                    'arabic': arabic_name,
                    'lat': lat,
                    'lng': lng,
                })

        self.stdout.write(f'Found {len(zone_data)} unique zones')
        self.stdout.write(f'Found {len(all_areas)} total areas')

        # Calculate center point for zones with multiple areas
        for zone_number, data in zone_data.items():
            areas = data['areas']
            if len(areas) > 1:
                # Calculate average lat/lng from all areas with valid coordinates
                valid_coords = [(a['lat'], a['lng']) for a in areas if a['lat'] and a['lng']]
                if valid_coords:
                    avg_lat = sum(c[0] for c in valid_coords) / len(valid_coords)
                    avg_lng = sum(c[1] for c in valid_coords) / len(valid_coords)
                    data['latitude'] = Decimal(str(round(avg_lat, 7)))
                    data['longitude'] = Decimal(str(round(avg_lng, 7)))
                    self.stdout.write(
                        f'Zone {zone_number}: calculated center from {len(valid_coords)} areas'
                    )

        # Import/update zones
        zone_created_count = 0
        zone_updated_count = 0
        area_created_count = 0
        area_updated_count = 0
        skipped_zone_count = 0

        for zone_number, data in sorted(zone_data.items()):
            # Skip zone 0 as it's unassigned areas
            if zone_number == 0:
                self.stdout.write(f'Skipping zone 0 (unassigned areas) - {len(data["areas"])} areas')
                skipped_zone_count += len(data['areas'])
                continue

            if dry_run:
                self.stdout.write(
                    f'[DRY RUN] Zone {zone_number}: {data["english_name"]} - {data["arabic_name"]} '
                    f'({data["latitude"]}, {data["longitude"]}) - {len(data["areas"])} areas'
                )
                continue

            # Create/update the zone
            zone, created = ZoneName.objects.update_or_create(
                zone_number=zone_number,
                defaults={
                    'zone_name': data['english_name'],
                    'zone_name_arabic': data['arabic_name'],
                    'latitude': data['latitude'],
                    'longitude': data['longitude'],
                    'is_active': True,
                }
            )

            if created:
                zone_created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Created zone {zone_number}: {data["english_name"]}'
                ))
            else:
                zone_updated_count += 1

            # Create/update all areas for this zone
            for area_data in data['areas']:
                area, area_created = ZoneArea.objects.update_or_create(
                    zone=zone,
                    area_name=area_data['english'],
                    defaults={
                        'area_name_arabic': area_data['arabic'],
                        'latitude': area_data['lat'],
                        'longitude': area_data['lng'],
                        'is_active': True,
                    }
                )
                if area_created:
                    area_created_count += 1
                else:
                    area_updated_count += 1

            self.stdout.write(
                f'Zone {zone_number}: {data["english_name"]} - {len(data["areas"])} areas'
            )

        # Print summary
        self.stdout.write('')
        self.stdout.write('=' * 50)
        self.stdout.write('Import Summary:')
        self.stdout.write(f'  Zones created: {zone_created_count}')
        self.stdout.write(f'  Zones updated: {zone_updated_count}')
        self.stdout.write(f'  Areas created: {area_created_count}')
        self.stdout.write(f'  Areas updated: {area_updated_count}')
        self.stdout.write(f'  Skipped (zone 0): {skipped_zone_count} areas')
        self.stdout.write('=' * 50)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes were made'))
        else:
            self.stdout.write(self.style.SUCCESS('Import completed successfully!'))
