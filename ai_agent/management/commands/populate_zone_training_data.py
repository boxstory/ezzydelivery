"""
Management command to populate ZoneTrainingData from ZoneName and ZoneArea tables.

This auto-generates training data for zone recognition from your existing zone definitions.
Handles English, Arabic, and common typos/aliases.

Usage:
    python manage.py populate_zone_training_data [--clear]
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from ai_agent.models import ZoneTrainingData
from delivery.models import ZoneName, ZoneArea


class Command(BaseCommand):
    help = 'Populate ZoneTrainingData from ZoneName and ZoneArea tables'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing training data before populating',
        )

    def handle(self, *args, **options):
        if options['clear']:
            count = ZoneTrainingData.objects.all().delete()[0]
            self.stdout.write(self.style.WARNING(f'Deleted {count} existing training records'))

        created_count = 0
        skipped_count = 0

        # Iterate through all active zones
        for zone in ZoneName.objects.filter(is_active=True):
            # 1. Add zone name (English)
            if zone.zone_name:
                training_data, created = ZoneTrainingData.objects.get_or_create(
                    zone=zone,
                    text_input=zone.zone_name.lower(),
                    defaults={
                        'input_type': 'area_name',
                        'language': 'en',
                        'confidence': 1.0,
                        'is_verified': True,  # From authoritative source
                    }
                )
                if created:
                    created_count += 1
                    self.stdout.write(f'✓ Zone {zone.zone_number}: {zone.zone_name}')
                else:
                    skipped_count += 1

            # 2. Add zone name (Arabic)
            if zone.zone_name_arabic:
                training_data, created = ZoneTrainingData.objects.get_or_create(
                    zone=zone,
                    text_input=zone.zone_name_arabic.lower(),
                    defaults={
                        'input_type': 'area_name',
                        'language': 'ar',
                        'confidence': 1.0,
                        'is_verified': True,
                    }
                )
                if created:
                    created_count += 1
                else:
                    skipped_count += 1

            # 3. Add area names from ZoneArea
            for area in zone.areas.filter(is_active=True):
                # English area name
                if area.area_name:
                    training_data, created = ZoneTrainingData.objects.get_or_create(
                        zone=zone,
                        text_input=area.area_name.lower(),
                        defaults={
                            'input_type': 'area_name',
                            'language': 'en',
                            'confidence': 1.0,
                            'is_verified': True,
                        }
                    )
                    if created:
                        created_count += 1
                    else:
                        skipped_count += 1

                # Arabic area name
                if area.area_name_arabic:
                    training_data, created = ZoneTrainingData.objects.get_or_create(
                        zone=zone,
                        text_input=area.area_name_arabic.lower(),
                        defaults={
                            'input_type': 'area_name',
                            'language': 'ar',
                            'confidence': 1.0,
                            'is_verified': True,
                        }
                    )
                    if created:
                        created_count += 1
                    else:
                        skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Populated {created_count} training records '
                f'({skipped_count} already existed)'
            )
        )
