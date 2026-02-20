"""
Script to create dummy warehouse data - can be run in Django shell.

Matches the exact structure shown in the UI:
- 2 ZONES (HL, AL)
- 10 RACKS (5 per zone: A, B, C, D, E)
- 50 SHELVES (5 per rack)
- 200 BINS (4 per shelf)
- 262 TOTAL locations

Example: Zone HL → Rack H → Shelf H-S1 → Bins H-S1-B01, H-S1-B02, H-S1-B03, H-S1-B04

Usage:
    python manage.py shell < create_dummy_warehouse.py

Or on production:
    ssh root@ezzydelivery.qa
    cd /opt/ezzydelivery
    source venv/bin/activate
    python manage.py shell < create_dummy_warehouse.py
"""

from django.db import transaction
from warehouse.models import Warehouse, StorageLocation

warehouse_code = 'WH-001-SDN'
warehouse_name = 'EZZYDELIVERY FULFILLMENT CENTER - SUDAN'

# Check if warehouse already exists
if Warehouse.objects.filter(code=warehouse_code).exists():
    print(f'❌ Warehouse {warehouse_code} already exists.')
    print(f'To recreate, first delete it:')
    print(f'  Warehouse.objects.filter(code="{warehouse_code}").delete()')
else:
    print(f'Creating {warehouse_name}...')

    with transaction.atomic():
        # Create warehouse
        warehouse = Warehouse.objects.create(
            name=warehouse_name,
            code=warehouse_code,
            description='Main fulfillment center in Sudan with automated storage system',
            address='Sudan Street, Industrial Area',
            city='Khartoum',
            state='Khartoum State',
            postal_code='11111',
            country='Sudan',
            latitude=15.5007,
            longitude=32.5599,
            phone='+249123456789',
            email='sudan@ezzydelivery.qa',
            total_zones=2,
            racks_per_zone=5,  # 5 racks per zone
            shelves_per_rack=5,  # 5 shelves per rack
            bins_per_shelf=4,  # 4 bins per shelf
            zone_naming_pattern='HL,AL',
            rack_naming_pattern='alpha',  # A, B, C, D, E
            shelf_naming_pattern='numeric',  # 1, 2, 3, 4, 5
            bin_naming_pattern='numeric',  # 01, 02, 03, 04
            is_capacity_configured=True,
            is_active=True,
            is_default=False,
        )

        print(f'✓ Created warehouse: {warehouse}')

        # Configuration - matching the screenshot structure
        zones = ['HL', 'AL']  # Zone HL and AL
        racks_per_zone = 5  # 5 racks per zone: A, B, C, D, E
        shelves_per_rack = 5  # 5 shelves per rack
        bins_per_shelf = 4  # 4 bins per shelf

        zone_count = 0
        rack_count = 0
        shelf_count = 0
        bin_count = 0

        # Create zones
        for zone_name in zones:
            zone = StorageLocation.objects.create(
                warehouse=warehouse,
                parent=None,
                name=f'Zone {zone_name}',
                code=zone_name,
                barcode=f'LOC-{warehouse_code}-{zone_name}',
                location_type='zone',
                is_pickable=False,
                is_active=True,
            )
            zone_count += 1
            print(f'  ✓ Zone {zone_name}')

            # Create racks (A, B, C, D, E for 5 racks per zone)
            for rack_num in range(1, racks_per_zone + 1):
                rack_letter = chr(64 + rack_num)  # A=65, so 64+1=A
                rack_code = rack_letter  # Just the letter (H, not HL-H)

                rack = StorageLocation.objects.create(
                    warehouse=warehouse,
                    parent=zone,
                    name=f'Rack {rack_letter}',
                    code=rack_code,
                    barcode=f'LOC-{warehouse_code}-{rack_code}',
                    location_type='rack',
                    is_pickable=False,
                    is_active=True,
                )
                rack_count += 1

                # Create shelves (naming: H-S1, H-S2, etc.)
                for shelf_num in range(1, shelves_per_rack + 1):
                    shelf_code = f'{rack_letter}-S{shelf_num}'  # A-S1, not A-S01

                    shelf = StorageLocation.objects.create(
                        warehouse=warehouse,
                        parent=rack,
                        name=f'Rack {rack_letter} Shelf {shelf_num}',
                        code=shelf_code,
                        barcode=f'LOC-{warehouse_code}-{shelf_code}',
                        location_type='shelf',
                        width_cm=50,
                        length_cm=200,
                        height_cm=50,
                        max_weight_kg=100,
                        is_pickable=False,
                        is_active=True,
                    )
                    shelf_count += 1

                    # Create bins (naming: H-S1-B01, H-S1-B02, etc.)
                    for bin_num in range(1, bins_per_shelf + 1):
                        bin_code = f'{shelf_code}-B{bin_num:02d}'  # A-S1-B01

                        StorageLocation.objects.create(
                            warehouse=warehouse,
                            parent=shelf,
                            name=f'{bin_num:02d}',  # Just "01", "02", etc.
                            code=bin_code,
                            barcode=f'LOC-{warehouse_code}-{bin_code}',
                            location_type='bin',
                            width_cm=50,
                            length_cm=50,
                            height_cm=50,
                            max_weight_kg=25,
                            is_pickable=True,
                            is_active=True,
                        )
                        bin_count += 1

        total_locations = zone_count + rack_count + shelf_count + bin_count

        # Summary
        print('\n' + '='*60)
        print('WAREHOUSE CREATION COMPLETE')
        print('='*60)
        print(f'Warehouse: {warehouse.name}')
        print(f'Code: {warehouse.code}')
        print(f'\nStructure:')
        print(f'  • Zones: {zone_count}')
        print(f'  • Racks: {rack_count} ({racks_per_zone} per zone)')
        print(f'  • Shelves: {shelf_count} ({shelves_per_rack} per rack)')
        print(f'  • Bins: {bin_count} ({bins_per_shelf} per shelf)')
        print(f'  • Total locations: {total_locations}')
        print(f'\nCalculated capacity: {warehouse.total_capacity} bins')

        # Example locations
        print(f'\nExample locations (matching screenshot):')
        example_bins = StorageLocation.objects.filter(
            warehouse=warehouse,
            location_type='bin',
            code__startswith='A-S1'  # Rack A, Shelf 1 bins
        ).order_by('code')[:4]

        for bin_obj in example_bins:
            print(f'  • {bin_obj.code} ({bin_obj.width_cm}×{bin_obj.length_cm}×{bin_obj.height_cm} cm)')

        print('\n✓ Dummy warehouse created successfully!')
        print(f'\nUI Display:')
        print(f'  {zone_count} ZONES | {rack_count} RACKS | {shelf_count} SHELVES | {bin_count} BINS | {total_locations} TOTAL')
