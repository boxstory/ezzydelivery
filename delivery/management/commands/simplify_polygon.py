"""
Management command to simplify zone polygons by removing unnecessary points.

This removes:
1. Points that are too close together
2. Collinear points (points on a straight line that don't define shape)

Usage:
    python manage.py simplify_polygon --zone=37           # Check specific zone (dry run)
    python manage.py simplify_polygon --zone=37 --apply   # Apply to specific zone
    python manage.py simplify_polygon --apply             # Apply to all zones
    python manage.py simplify_polygon --tolerance=0.00001 # Set collinearity tolerance
"""
import math
from django.core.management.base import BaseCommand
from delivery.models import ZoneName


class Command(BaseCommand):
    help = 'Simplify zone polygons by removing unnecessary points'

    def add_arguments(self, parser):
        parser.add_argument(
            '--zone',
            type=int,
            help='Simplify specific zone number only',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually apply the changes (default is dry run)',
        )
        parser.add_argument(
            '--min-distance',
            type=float,
            default=3.0,
            help='Minimum distance between points in meters (default: 3)',
        )
        parser.add_argument(
            '--tolerance',
            type=float,
            default=0.000005,
            help='Collinearity tolerance in degrees (default: 0.000005 ~ 0.5m)',
        )
        parser.add_argument(
            '--simplify-distance',
            type=float,
            default=0.0,
            help='Remove points within this distance (meters) if no major corner (default: 0 = disabled)',
        )
        parser.add_argument(
            '--corner-angle',
            type=float,
            default=15.0,
            help='Minimum angle (degrees) to consider a point as a corner (default: 15)',
        )

    def haversine_distance(self, lat1, lng1, lat2, lng2):
        """Calculate distance between two points in meters."""
        R = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lng2 - lng1)

        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def point_to_line_distance(self, px, py, x1, y1, x2, y2):
        """
        Calculate perpendicular distance from point (px, py) to line defined by (x1,y1)-(x2,y2).
        Returns distance in degrees (approximate).
        """
        # Line vector
        dx = x2 - x1
        dy = y2 - y1

        # If line is a point, return distance to that point
        if dx == 0 and dy == 0:
            return math.sqrt((px - x1) ** 2 + (py - y1) ** 2)

        # Calculate perpendicular distance using cross product
        # Area of triangle = 0.5 * |cross product|
        # Distance = Area * 2 / base_length
        cross = abs((py - y1) * dx - (px - x1) * dy)
        base = math.sqrt(dx ** 2 + dy ** 2)

        return cross / base

    def is_collinear(self, p1, p2, p3, tolerance):
        """Check if three points are collinear within tolerance."""
        dist = self.point_to_line_distance(p2[0], p2[1], p1[0], p1[1], p3[0], p3[1])
        return dist < tolerance

    def calculate_angle(self, p1, p2, p3):
        """
        Calculate the angle at p2 formed by p1-p2-p3.
        Returns angle in degrees (0-180).
        """
        # Vectors
        v1 = (p1[0] - p2[0], p1[1] - p2[1])
        v2 = (p3[0] - p2[0], p3[1] - p2[1])

        # Dot product
        dot = v1[0] * v2[0] + v1[1] * v2[1]

        # Magnitudes
        mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
        mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

        if mag1 == 0 or mag2 == 0:
            return 180  # Points are the same

        # Angle
        cos_angle = max(-1, min(1, dot / (mag1 * mag2)))
        angle = math.degrees(math.acos(cos_angle))

        return angle

    def point_to_line_distance_meters(self, px, py, x1, y1, x2, y2):
        """
        Calculate perpendicular distance from point to line in meters.
        """
        # Project point onto line and find nearest point
        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            return self.haversine_distance(px, py, x1, y1)

        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        nearest_x = x1 + t * dx
        nearest_y = y1 + t * dy

        return self.haversine_distance(px, py, nearest_x, nearest_y)

    def simplify_polygon(self, polygon, min_distance, tolerance):
        """
        Simplify polygon by removing:
        1. Points too close together
        2. Collinear points
        Returns simplified polygon and details of removed points.
        """
        if not polygon or len(polygon) < 4:
            return polygon, [], []

        # Check if polygon is closed
        is_closed = (polygon[0][0] == polygon[-1][0] and polygon[0][1] == polygon[-1][1])
        points = polygon[:-1] if is_closed else polygon[:]

        # First pass: remove points too close together
        close_removed = []
        after_distance = [points[0]]

        for i in range(1, len(points)):
            current = points[i]
            last_kept = after_distance[-1]

            dist = self.haversine_distance(
                last_kept[0], last_kept[1],
                current[0], current[1]
            )

            if dist >= min_distance:
                after_distance.append(current)
            else:
                close_removed.append({
                    'index': i,
                    'point': current,
                    'reason': f'too close ({dist:.1f}m)'
                })

        # Second pass: remove collinear points
        if len(after_distance) < 3:
            # Close the polygon
            after_distance.append(after_distance[0][:])
            return after_distance, close_removed, []

        collinear_removed = []
        simplified = [after_distance[0]]

        for i in range(1, len(after_distance) - 1):
            prev = simplified[-1]
            current = after_distance[i]
            next_pt = after_distance[i + 1]

            if not self.is_collinear(prev, current, next_pt, tolerance):
                simplified.append(current)
            else:
                collinear_removed.append({
                    'index': i,
                    'point': current,
                    'reason': 'collinear'
                })

        # Always keep the last point before closing
        simplified.append(after_distance[-1])

        # Ensure at least 3 points
        if len(simplified) < 3:
            simplified = after_distance[:]

        # Close the polygon
        simplified.append(simplified[0][:])

        return simplified, close_removed, collinear_removed

    def simplify_by_distance_and_angle(self, polygon, simplify_distance, corner_angle):
        """
        Remove points within simplify_distance if they don't form a major corner.
        A major corner is where the angle deviation from straight (180°) exceeds corner_angle.
        """
        if not polygon or len(polygon) < 4:
            return polygon, []

        # Check if polygon is closed
        is_closed = (polygon[0][0] == polygon[-1][0] and polygon[0][1] == polygon[-1][1])
        points = polygon[:-1] if is_closed else polygon[:]

        removed = []
        simplified = [points[0]]

        i = 1
        while i < len(points) - 1:
            prev = simplified[-1]
            current = points[i]
            next_pt = points[i + 1]

            # Calculate distance from previous kept point
            dist_from_prev = self.haversine_distance(
                prev[0], prev[1], current[0], current[1]
            )

            # Calculate angle at current point
            angle = self.calculate_angle(prev, current, next_pt)
            angle_deviation = abs(180 - angle)  # How far from straight line

            # Calculate perpendicular distance from current point to line prev-next
            perp_dist = self.point_to_line_distance_meters(
                current[0], current[1],
                prev[0], prev[1],
                next_pt[0], next_pt[1]
            )

            # Keep the point if:
            # 1. It's far from the prev-next line (perp distance > threshold)
            # 2. OR it forms a significant corner (angle deviation > corner_angle)
            # 3. OR it's beyond the simplify distance
            keep_point = (
                perp_dist > simplify_distance * 0.1 or  # 10% of simplify distance as perp threshold
                angle_deviation > corner_angle or
                dist_from_prev > simplify_distance
            )

            if keep_point:
                simplified.append(current)
            else:
                removed.append({
                    'index': i,
                    'point': current,
                    'reason': f'no corner (angle={angle:.1f}°, perp={perp_dist:.1f}m)'
                })

            i += 1

        # Always keep the last point
        simplified.append(points[-1])

        # Ensure at least 3 points
        if len(simplified) < 3:
            return polygon, []

        # Close the polygon
        simplified.append(simplified[0][:])

        return simplified, removed

    def handle(self, *args, **options):
        zone_number = options.get('zone')
        apply_changes = options['apply']
        min_distance = options['min_distance']
        tolerance = options['tolerance']
        simplify_distance = options['simplify_distance']
        corner_angle = options['corner_angle']

        self.stdout.write(f'Simplifying polygons')
        self.stdout.write(f'  Min distance: {min_distance}m')
        self.stdout.write(f'  Collinearity tolerance: {tolerance} degrees')
        if simplify_distance > 0:
            self.stdout.write(f'  Simplify distance: {simplify_distance}m')
            self.stdout.write(f'  Corner angle threshold: {corner_angle}°')
        self.stdout.write(f'  Mode: {"APPLY CHANGES" if apply_changes else "DRY RUN"}')
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
        zones_simplified = 0
        total_close_removed = 0
        total_collinear_removed = 0
        total_angle_removed = 0

        for zone in zones:
            if not zone.polygon or len(zone.polygon) < 4:
                continue

            total_zones += 1
            original_count = len(zone.polygon)

            # First pass: basic simplification
            simplified, close_removed, collinear_removed = self.simplify_polygon(
                zone.polygon, min_distance, tolerance
            )

            # Second pass: distance and angle based simplification (if enabled)
            angle_removed = []
            if simplify_distance > 0 and len(simplified) > 4:
                simplified, angle_removed = self.simplify_by_distance_and_angle(
                    simplified, simplify_distance, corner_angle
                )

            total_removed = len(close_removed) + len(collinear_removed) + len(angle_removed)

            if total_removed > 0:
                zones_simplified += 1
                total_close_removed += len(close_removed)
                total_collinear_removed += len(collinear_removed)
                total_angle_removed += len(angle_removed)

                self.stdout.write(
                    f'Zone {zone.zone_number} ({zone.zone_name}): '
                    f'{original_count} → {len(simplified)} points'
                )
                removed_parts = []
                if len(close_removed) > 0:
                    removed_parts.append(f'{len(close_removed)} too close')
                if len(collinear_removed) > 0:
                    removed_parts.append(f'{len(collinear_removed)} collinear')
                if len(angle_removed) > 0:
                    removed_parts.append(f'{len(angle_removed)} no corner')
                self.stdout.write(f'  Removed: {", ".join(removed_parts)}')

                # Show some examples
                all_removed = close_removed + collinear_removed + angle_removed
                for r in all_removed[:5]:
                    self.stdout.write(
                        f'    - Point {r["index"]}: {r["reason"]}'
                    )
                if len(all_removed) > 5:
                    self.stdout.write(f'    ... and {len(all_removed) - 5} more')

                if apply_changes:
                    zone.polygon = simplified
                    zone.save(update_fields=['polygon', 'updated_at'])
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Saved'))
                else:
                    self.stdout.write(self.style.WARNING(f'  (dry run - not saved)'))

                self.stdout.write('')

        # Summary
        total_all_removed = total_close_removed + total_collinear_removed + total_angle_removed
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write(f'Total zones checked: {total_zones}')
        self.stdout.write(f'Zones simplified: {zones_simplified}')
        self.stdout.write(f'Points removed (too close): {total_close_removed}')
        self.stdout.write(f'Points removed (collinear): {total_collinear_removed}')
        if total_angle_removed > 0:
            self.stdout.write(f'Points removed (no corner): {total_angle_removed}')
        self.stdout.write(f'Total points removed: {total_all_removed}')
        self.stdout.write('=' * 60)

        if not apply_changes and total_all_removed > 0:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'This was a DRY RUN. Run with --apply to actually simplify.'
            ))
