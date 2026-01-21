"""
Management command to clean up zone polygon points that are too close together.

This removes redundant points on the same polygon line while preserving the shape.

Usage:
    python manage.py cleanup_polygon_points              # Check all zones (dry run)
    python manage.py cleanup_polygon_points --apply      # Actually remove points
    python manage.py cleanup_polygon_points --zone=41    # Check specific zone
    python manage.py cleanup_polygon_points --min-distance=5  # Set minimum distance (meters)
"""
import math
from django.core.management.base import BaseCommand
from delivery.models import ZoneName


class Command(BaseCommand):
    help = 'Clean up zone polygon points that are too close together'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zone',
            type=int,
            help='Check/clean specific zone number only',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually apply the changes (default is dry run)',
        )
        parser.add_argument(
            '--min-distance',
            type=float,
            default=5.0,
            help='Minimum distance between points in meters (default: 5)',
        )

    def haversine_distance(self, lat1, lng1, lat2, lng2):
        """Calculate distance between two points in meters using Haversine formula."""
        R = 6371000  # Earth's radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def clean_polygon(self, polygon, min_distance):
        """
        Remove points that are too close together.
        Returns cleaned polygon and list of removed points.
        """
        if not polygon or len(polygon) < 3:
            return polygon, []

        # Check if polygon is closed (last point equals first)
        is_closed = (polygon[0][0] == polygon[-1][0] and polygon[0][1] == polygon[-1][1])

        # Process all points except closing point if polygon is closed
        points_to_process = polygon[:-1] if is_closed else polygon

        cleaned = [points_to_process[0]]  # Always keep first point
        removed = []

        for i in range(1, len(points_to_process)):
            current = points_to_process[i]
            last_kept = cleaned[-1]

            dist = self.haversine_distance(
                last_kept[0], last_kept[1],
                current[0], current[1]
            )

            if dist >= min_distance:
                cleaned.append(current)
            else:
                removed.append({
                    'index': i,
                    'point': current,
                    'distance': round(dist, 2)
                })

        # Ensure polygon is still valid (at least 3 points)
        if len(cleaned) < 3:
            self.stdout.write(self.style.WARNING(
                f'  Cannot clean - would result in less than 3 points'
            ))
            return polygon, []

        # Ensure polygon is closed
        if cleaned[0] != cleaned[-1]:
            # Check if last point is close to first
            dist_to_start = self.haversine_distance(
                cleaned[-1][0], cleaned[-1][1],
                cleaned[0][0], cleaned[0][1]
            )
            if dist_to_start < min_distance:
                # Last point is close to first, remove it and close
                pass
            cleaned.append(cleaned[0][:])  # Close the polygon

        return cleaned, removed

    def handle(self, *args, **options):
        zone_number = options.get('zone')
        apply_changes = options['apply']
        min_distance = options['min_distance']

        self.stdout.write(f'Checking polygon points (min distance: {min_distance}m)')
        self.stdout.write(f'Mode: {"APPLY CHANGES" if apply_changes else "DRY RUN"}')
        self.stdout.write('')

        # Get zones to process
        if zone_number:
            zones = ZoneName.objects.filter(zone_number=zone_number)
            if not zones.exists():
                self.stdout.write(self.style.ERROR(f'Zone {zone_number} not found'))
                return
        else:
            zones = ZoneName.objects.exclude(
                polygon__isnull=True
            ).exclude(
                polygon=[]
            ).order_by('zone_number')

        total_zones = 0
        zones_cleaned = 0
        total_points_removed = 0

        for zone in zones:
            if not zone.polygon or len(zone.polygon) < 3:
                continue

            total_zones += 1
            original_count = len(zone.polygon)

            cleaned_polygon, removed_points = self.clean_polygon(
                zone.polygon, min_distance
            )

            if removed_points:
                zones_cleaned += 1
                points_removed = len(removed_points)
                total_points_removed += points_removed

                self.stdout.write(
                    f'Zone {zone.zone_number} ({zone.zone_name}): '
                    f'{original_count} → {len(cleaned_polygon)} points '
                    f'({points_removed} removed)'
                )

                # Show details of removed points
                for r in removed_points[:5]:  # Show first 5
                    self.stdout.write(
                        f'  - Point {r["index"]}: [{r["point"][0]:.6f}, {r["point"][1]:.6f}] '
                        f'(only {r["distance"]}m from previous)'
                    )
                if len(removed_points) > 5:
                    self.stdout.write(f'  ... and {len(removed_points) - 5} more')

                if apply_changes:
                    zone.polygon = cleaned_polygon
                    zone.save(update_fields=['polygon', 'updated_at'])
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Saved'))
                else:
                    self.stdout.write(self.style.WARNING(f'  (dry run - not saved)'))

                self.stdout.write('')

        # Summary
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write(f'Total zones checked: {total_zones}')
        self.stdout.write(f'Zones with close points: {zones_cleaned}')
        self.stdout.write(f'Total points to remove: {total_points_removed}')
        self.stdout.write('=' * 60)

        if not apply_changes and total_points_removed > 0:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'This was a DRY RUN. Run with --apply to actually remove points.'
            ))
