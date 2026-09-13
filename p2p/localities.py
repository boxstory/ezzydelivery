# Purpose: The Qatar locality list (name → coordinates) both the public calculator and the staff booking desk pick from.
# Used by: webpages.views.p2p_pricing, workforce.views.wf_p2p_new
# Notes: Names are deduplicated on first sight, so the hardcoded extras below win over a DB row of
#        the same name. One list, because a place the public can book from must also be one ops can.

# Well-known areas that are absent from the zone tables, or whose DB coordinates sit
# somewhere less useful than the spot a customer means by the name.
EXTRAS = [
    {'name': 'West Bay',      'zone': 'Doha',       'lat': 25.3272, 'lng': 51.5310},
    {'name': 'Al Wakrah',     'zone': 'South',      'lat': 25.1719, 'lng': 51.5989},
    {'name': 'Abu Hamour',    'zone': 'Doha',       'lat': 25.2390, 'lng': 51.4654},
    {'name': 'Garaffa',       'zone': 'Al Rayyan',  'lat': 25.2900, 'lng': 51.4400},
    {'name': 'Al Rayyan',     'zone': 'Al Rayyan',  'lat': 25.2546, 'lng': 51.4225},
    {'name': 'Al Khor City',  'zone': 'North',      'lat': 25.6839, 'lng': 51.5037},
    {'name': 'Education City','zone': 'Al Rayyan',  'lat': 25.3152, 'lng': 51.4249},
    {'name': 'Corniche',      'zone': 'Doha',       'lat': 25.3068, 'lng': 51.5352},
]

# The chips shown before anyone types, in display order.
POPULAR_NAMES = [
    'West Bay', 'The Pearl', 'The Pearl Island', 'Lusail', 'Al Sadd',
    'Mushaireb', 'Industrial Area', 'Al Khor', 'Al Khor City', 'Old Airport',
    'Al Waab', 'Al Gharrafa', 'Gharrafat Al Rayyan', 'Muaither', 'Al Thumama',
    'Duhail', 'Hamad International Airport', 'Al Wakrah', 'Abu Hamour',
    'Education City', 'Al Rayyan', 'Corniche', 'Madinat Khalifa North',
    'Madinat Khalifa South', 'Fereej Bin Omran', 'Al Mansoura', 'Najma',
    'Al Aziziya', 'Mesaieed', 'Al Daayen', 'Nuaija', 'Onaiza',
    'Fereej Al Nasr', 'Al Dafna', 'Wholesale Market',
    'Fereej Al Soudan', 'Al Sailiya', 'Bu Sidra', 'Fereej Al Manaseer',
    'Fereej Al Murra', 'Al Ghanim Al Jadeed',
]


def localities():
    """Every place a P2P job can be booked from or to, with a pin for each.

    Zone names first, then areas — a row without coordinates is no use to a distance
    calculation and is left out rather than quoted at 0 km.
    """
    from delivery.models import ZoneArea, ZoneName

    seen = {e['name'] for e in EXTRAS}
    rows = list(EXTRAS)

    for z in (ZoneName.objects
              .filter(is_active=True, latitude__isnull=False)
              .order_by('zone_number')):
        if z.zone_name not in seen:
            seen.add(z.zone_name)
            rows.append({'name': z.zone_name, 'zone': f'Zone {z.zone_number}',
                         'lat': float(z.latitude), 'lng': float(z.longitude)})

    for a in (ZoneArea.objects
              .filter(is_active=True, latitude__isnull=False)
              .select_related('zone').order_by('area_name')):
        if a.area_name not in seen:
            seen.add(a.area_name)
            rows.append({'name': a.area_name, 'zone': a.zone.zone_name,
                         'lat': float(a.latitude), 'lng': float(a.longitude)})

    return rows


def popular(rows=None):
    """The subset shown as chips. Silently drops a name the database does not have."""
    index = {row['name']: row for row in (rows if rows is not None else localities())}
    return [index[name] for name in POPULAR_NAMES if name in index]
