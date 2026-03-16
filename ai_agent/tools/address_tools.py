"""
Address Tools

Tools for parsing Qatar addresses, looking up zones, and validating addresses.
"""

import re
import logging
from typing import Any, Dict, List, Optional

from django.db.models import Q

from ai_agent.tools.base import BaseTool, ToolError, register_tool
from ai_agent.models import ZoneTrainingData

logger = logging.getLogger(__name__)


# Qatar address patterns
QATAR_PATTERNS = {
    'zone': [
        r'zone\s*[#:]?\s*(\d{1,3})',
        r'منطقة\s*(\d{1,3})',
        r'z\s*(\d{1,3})\b',
        r'\bzone(\d{1,3})\b',
    ],
    'street': [
        r'street\s*[#:]?\s*(\d{1,4})',
        r'شارع\s*(\d{1,4})',
        r'st\.?\s*(\d{1,4})',
        r'\bstreet(\d{1,4})\b',
    ],
    'building': [
        r'building\s*[#:]?\s*(\d{1,4})',
        r'bldg\.?\s*[#:]?\s*(\d{1,4})',
        r'مبنى\s*(\d{1,4})',
        r'\bbuilding(\d{1,4})\b',
        r'villa\s*[#:]?\s*(\d{1,4})',
        r'house\s*[#:]?\s*(\d{1,4})',
    ],
    'unit': [
        r'(?:unit|apt|apartment|flat)\s*[#:]?\s*(\w+)',
        r'شقة\s*(\w+)',
    ],
}

# Google Maps link patterns — extract lat/lng from various URL formats
GOOGLE_MAPS_PATTERNS = [
    # https://maps.google.com/?q=25.3548,51.4218
    r'maps\.google\.com/?\?[^"\s]*q=([-\d.]+),([-\d.]+)',
    # https://www.google.com/maps?q=25.3548,51.4218
    r'google\.com/maps\?[^"\s]*q=([-\d.]+),([-\d.]+)',
    # https://www.google.com/maps/place/.../@25.3548,51.4218,17z
    r'google\.com/maps/[^"\s]*@([-\d.]+),([-\d.]+)',
    # https://maps.app.goo.gl/... (short links — can't extract coords, but detect presence)
    # https://goo.gl/maps/...
    # https://www.google.com/maps/search/25.3548,51.4218
    r'google\.com/maps/search/([-\d.]+),([-\d.]+)',
    # Plain Google Maps with ll= parameter
    r'maps\.google\.com[^"\s]*ll=([-\d.]+),([-\d.]+)',
]

# Raw lat/lng patterns in text (Qatar region: lat ~24-27, lng ~50-52)
RAW_COORDS_PATTERNS = [
    # 25.3548, 51.4218 or 25.3548,51.4218
    r'(2[4-6]\.\d{3,8})\s*[,\s]\s*(5[0-2]\.\d{3,8})',
]

# Full Google Maps URL extraction (to save the link itself)
GOOGLE_LINK_PATTERN = r'(https?://(?:www\.)?(?:maps\.google\.com|google\.com/maps|maps\.app\.goo\.gl|goo\.gl/maps)[^\s"<>]*)'


def extract_coords_from_text(text: str):
    """Extract latitude/longitude from Google Maps links or raw coordinates in text.
    Returns (lat, lng, source, link) or (None, None, None, None).
    """
    if not text:
        return None, None, None, None

    # 1. Try Google Maps links
    for pattern in GOOGLE_MAPS_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            lat, lng = float(match.group(1)), float(match.group(2))
            # Validate Qatar region
            if 24.0 <= lat <= 27.0 and 50.0 <= lng <= 52.5:
                # Extract full link
                link_match = re.search(GOOGLE_LINK_PATTERN, text, re.IGNORECASE)
                link = link_match.group(1) if link_match else None
                return lat, lng, 'google_maps', link

    # 2. Try raw coordinates
    for pattern in RAW_COORDS_PATTERNS:
        match = re.search(pattern, text)
        if match:
            lat, lng = float(match.group(1)), float(match.group(2))
            if 24.0 <= lat <= 27.0 and 50.0 <= lng <= 52.5:
                return lat, lng, 'raw_coordinates', None

    # 3. Detect Google short link — resolve server-side to get actual URL with coords
    link_match = re.search(GOOGLE_LINK_PATTERN, text, re.IGNORECASE)
    if link_match:
        short_url = link_match.group(1)
        resolved = _resolve_google_short_link(short_url)
        if resolved:
            resolved_lat, resolved_lng, resolved_url = resolved
            if resolved_lat and resolved_lng:
                return resolved_lat, resolved_lng, 'google_maps', resolved_url or short_url
        return None, None, 'google_link_unresolved', short_url

    return None, None, None, None


def _resolve_google_short_link(short_url: str):
    """Follow a Google Maps short link redirect to get the full URL with coordinates.
    Returns (lat, lng, full_url) or None.
    """
    import requests as http_requests

    try:
        resp = http_requests.head(short_url, allow_redirects=True, timeout=5,
                                   headers={'User-Agent': 'EzzyDelivery/1.0'})
        final_url = resp.url
        if not final_url or final_url == short_url:
            # Try GET if HEAD didn't redirect
            resp = http_requests.get(short_url, allow_redirects=True, timeout=5,
                                      headers={'User-Agent': 'EzzyDelivery/1.0'},
                                      stream=True)
            final_url = resp.url
            resp.close()

        if final_url:
            # Try extracting coords from the resolved URL
            for pattern in GOOGLE_MAPS_PATTERNS:
                match = re.search(pattern, final_url, re.IGNORECASE)
                if match:
                    lat, lng = float(match.group(1)), float(match.group(2))
                    if 24.0 <= lat <= 27.0 and 50.0 <= lng <= 52.5:
                        return lat, lng, final_url
            # Also try raw coords in URL
            for pattern in RAW_COORDS_PATTERNS:
                match = re.search(pattern, final_url)
                if match:
                    lat, lng = float(match.group(1)), float(match.group(2))
                    if 24.0 <= lat <= 27.0 and 50.0 <= lng <= 52.5:
                        return lat, lng, final_url
    except Exception as e:
        logger.warning(f"Failed to resolve Google short link {short_url}: {e}")

    return None


def extract_pattern(text: str, patterns: List[str]) -> Optional[str]:
    """Extract first matching pattern from text."""
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


@register_tool
class ParseAddressTool(BaseTool):
    """
    Parse free-text Qatar address into structured components.

    Extracts zone, street, building, and area information from
    various address formats including Arabic text.
    """

    name = 'parse_address'
    description = '''Parse a Qatar address from free text into structured components.

    Extracts:
    - Zone number (1-99)
    - Street number
    - Building/villa number
    - Unit/apartment number
    - Area/neighborhood name

    Supports both English and Arabic input, common misspellings, and landmarks.

    Example inputs:
    - "Zone 44, Street 850, Building 12, West Bay"
    - "الدفنة قرب سيتي سنتر"
    - "delivery to al sadd near sports city"
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'address': {
                'type': 'string',
                'description': 'Free-text address to parse'
            }
        },
        'required': ['address']
    }

    def execute(self, address: str) -> Dict[str, Any]:
        if not address or len(address.strip()) < 3:
            raise ToolError('Address is too short', 'INVALID_INPUT')

        result = {
            'original_address': address,
            'zone_number': None,
            'zone_name': None,
            'street_number': None,
            'building_number': None,
            'unit_number': None,
            'area_name': None,
            'landmarks': [],
            'confidence': 0.0,
            'parse_notes': [],
            'coordinates': {
                'latitude': None,
                'longitude': None,
            },
            'geocode_source': None,
            'location_link': None,
        }

        # Extract coordinates from Google Maps links or raw lat/lng in text
        text_lat, text_lng, coord_source, google_link = extract_coords_from_text(address)
        if text_lat and text_lng:
            result['coordinates']['latitude'] = text_lat
            result['coordinates']['longitude'] = text_lng
            result['geocode_source'] = coord_source
            # Google Maps pin = high-confidence exact location
            if coord_source == 'google_maps':
                result['confidence'] += 0.7
                result['parse_notes'].append(f'Exact coordinates from Google Maps: {text_lat:.6f}, {text_lng:.6f}')
            else:
                result['confidence'] += 0.5
                result['parse_notes'].append(f'Coordinates from {coord_source}: {text_lat:.6f}, {text_lng:.6f}')
        if google_link:
            result['location_link'] = google_link
            if not text_lat:
                result['parse_notes'].append('Google Maps link found (could not extract coordinates)')

        # Extract zone number
        zone_num = extract_pattern(address, QATAR_PATTERNS['zone'])
        if zone_num:
            result['zone_number'] = int(zone_num)
            result['confidence'] += 0.3
            result['parse_notes'].append(f'Zone {zone_num} found in text')

        # Extract street number
        street_num = extract_pattern(address, QATAR_PATTERNS['street'])
        if street_num:
            result['street_number'] = int(street_num)
            result['confidence'] += 0.2
            result['parse_notes'].append(f'Street {street_num} found')

        # Extract building number
        building_num = extract_pattern(address, QATAR_PATTERNS['building'])
        if building_num:
            result['building_number'] = int(building_num)
            result['confidence'] += 0.2
            result['parse_notes'].append(f'Building {building_num} found')

        # Extract unit number
        unit = extract_pattern(address, QATAR_PATTERNS['unit'])
        if unit:
            result['unit_number'] = unit
            result['confidence'] += 0.1

        # Step 1: Training data lookup
        zone_match = self._find_zone_from_training_data(address)
        if zone_match:
            if not result['zone_number']:
                result['zone_number'] = zone_match['zone_number']
                result['confidence'] += 0.25
            result['zone_name'] = zone_match.get('zone_name')
            result['area_name'] = zone_match.get('area_name')
            result['parse_notes'].append(f"Matched area: {zone_match.get('area_name')}")

        # Step 2: ZoneName/ZoneArea DB lookup (fuzzy)
        if not result['zone_number']:
            zone_from_db = self._find_zone_from_database(address)
            if zone_from_db:
                result['zone_number'] = zone_from_db['zone_number']
                result['zone_name'] = zone_from_db.get('zone_name')
                result['area_name'] = zone_from_db.get('area_name')
                result['confidence'] += 0.25
                result['parse_notes'].append(f"Matched from database: {zone_from_db.get('area_name')}")
                # Only set zone_center coords if we don't already have better coords (google/raw)
                if not result['coordinates']['latitude'] and zone_from_db.get('latitude') and zone_from_db.get('longitude'):
                    result['coordinates']['latitude'] = zone_from_db['latitude']
                    result['coordinates']['longitude'] = zone_from_db['longitude']
                    result['geocode_source'] = 'zone_center'

        # Step 3: AI search for typo handling (moved earlier — runs before geocoding)
        if not result['zone_number']:
            ai_result = self._ai_search_zone(address)
            if ai_result:
                result['zone_number'] = ai_result.get('zone_number')
                result['zone_name'] = ai_result.get('zone_name')
                result['area_name'] = ai_result.get('area_name')
                result['confidence'] += 0.35
                result['geocode_source'] = 'ai_estimate'
                result['parse_notes'].append(f"AI identified zone: {ai_result.get('zone_name')} (Zone {ai_result.get('zone_number')})")

        # Step 4: Enrich with zone details + QNAS/geocoding
        if result['zone_number']:
            zone_details = self._get_zone_details(result['zone_number'])
            if zone_details:
                if not result['zone_name']:
                    result['zone_name'] = zone_details.get('zone_name')
                    result['parse_notes'].append(f"Zone name: {zone_details.get('zone_name')}")

            # Step 4a: QNAS lookup if we have zone + street
            if result['street_number']:
                qnas_coords = self._lookup_qnas_building(
                    result['zone_number'],
                    result['street_number'],
                    result.get('building_number')
                )
                if qnas_coords:
                    result['coordinates']['latitude'] = qnas_coords['latitude']
                    result['coordinates']['longitude'] = qnas_coords['longitude']
                    result['confidence'] += 0.15
                    if qnas_coords.get('exact_match'):
                        result['geocode_source'] = 'qnas_exact'
                        result['parse_notes'].append(f"QNAS precise coordinates from building {result.get('building_number')}")
                    else:
                        result['geocode_source'] = 'qnas_street'
                        result['parse_notes'].append("QNAS precise coordinates from street")

            # Step 4b: Landmark geocoding if zone but no street (better than zone center)
            if not result['coordinates']['latitude'] and not result['street_number']:
                # Pass zone center as hint for picking best geocode result
                hint_lat = zone_details.get('latitude') if zone_details else None
                hint_lng = zone_details.get('longitude') if zone_details else None
                landmark_coords = self._geocode_landmark(address, hint_lat, hint_lng)
                if landmark_coords:
                    result['coordinates']['latitude'] = landmark_coords['latitude']
                    result['coordinates']['longitude'] = landmark_coords['longitude']
                    result['geocode_source'] = 'landmark'
                    result['confidence'] += 0.1
                    result['parse_notes'].append(f"Landmark/area geocoded via {landmark_coords.get('provider', 'geocoder')}")

            # Step 4c: Fallback to zone center if still no coordinates
            if not result['coordinates']['latitude'] and zone_details and zone_details.get('latitude'):
                result['coordinates']['latitude'] = zone_details['latitude']
                result['coordinates']['longitude'] = zone_details['longitude']
                if not result['geocode_source'] or result['geocode_source'] == 'ai_estimate':
                    # Keep ai_estimate if that's how we found the zone
                    if result['geocode_source'] != 'ai_estimate':
                        result['geocode_source'] = 'zone_center'
                result['parse_notes'].append(f"Zone {result['zone_number']} center coordinates (approximate)")

        # Step 5: If still no zone and no coords, try landmark geocoding alone
        if not result['zone_number'] and not result['coordinates']['latitude']:
            landmark_coords = self._geocode_landmark(address)
            if landmark_coords:
                result['coordinates']['latitude'] = landmark_coords['latitude']
                result['coordinates']['longitude'] = landmark_coords['longitude']
                result['geocode_source'] = 'landmark'
                result['confidence'] += 0.15
                result['parse_notes'].append(f"Address geocoded via {landmark_coords.get('provider', 'geocoder')} (no zone identified)")

        # Extract common landmarks
        landmarks = self._extract_landmarks(address)
        if landmarks:
            result['landmarks'] = landmarks
            result['confidence'] += 0.1
            result['parse_notes'].append(f"Landmarks: {', '.join(landmarks)}")

        # Cap confidence at 1.0
        result['confidence'] = min(1.0, result['confidence'])

        # Inline validation (merged from ValidateAddressTool)
        issues = []
        warnings = []
        is_valid = True

        if not result['zone_number']:
            is_valid = False
            issues.append({
                'field': 'zone_number',
                'issue': 'Zone number not identified',
                'suggestion': 'Include zone number (1-99) in the address'
            })

        if not result['building_number']:
            is_valid = False
            issues.append({
                'field': 'building_number',
                'issue': 'Building number is required for delivery',
                'suggestion': 'Please provide building or villa number'
            })

        if not result['street_number']:
            warnings.append({
                'field': 'street_number',
                'issue': 'Street number not provided',
                'suggestion': 'Adding street number improves delivery accuracy'
            })

        # Completeness score
        fields_provided = sum([
            result['zone_number'] is not None,
            result['street_number'] is not None,
            result['building_number'] is not None,
            bool(result['area_name']),
        ])
        result['is_valid'] = is_valid
        result['completeness_score'] = fields_provided / 4.0
        result['issues'] = issues
        result['warnings'] = warnings

        # Formatted address if valid
        if is_valid:
            parts = []
            if result['building_number']:
                parts.append(f"Building {result['building_number']}")
            if result['street_number']:
                parts.append(f"Street {result['street_number']}")
            if result['zone_number']:
                parts.append(f"Zone {result['zone_number']}")
            if result['zone_name']:
                parts.append(result['zone_name'])
            elif result['area_name']:
                parts.append(result['area_name'])
            result['formatted_address'] = ', '.join(parts)

        return result

    def _find_zone_from_training_data(self, address: str) -> Optional[Dict[str, Any]]:
        """Search training data for zone matches."""
        address_lower = address.lower()

        # Search for matches in ZoneTrainingData
        training_matches = ZoneTrainingData.objects.filter(
            Q(text_input__icontains=address_lower[:50]) |  # Partial match
            Q(text_input__in=address_lower.split())  # Word match
        ).select_related('zone').order_by('-confidence')[:5]

        if training_matches.exists():
            best_match = training_matches.first()
            return {
                'zone_number': best_match.zone.zone_number,
                'zone_name': best_match.zone.zone_name,
                'area_name': best_match.text_input,
                'confidence': best_match.confidence,
            }

        return None

    def _find_zone_from_database(self, address: str) -> Optional[Dict[str, Any]]:
        """Search ZoneName and ZoneArea models for matches with fuzzy matching."""
        from delivery.models import ZoneName, ZoneArea

        address_lower = address.lower()
        words = address_lower.split()

        # Common Qatar area spelling variations
        spelling_variants = {
            'musheireb': ['mushaireb', 'msheireb', 'musheirib'],
            'mushaireb': ['musheireb', 'msheireb', 'musheirib'],
            'lusail': ['luseil', 'lusayl', 'lussail'],
            'wakra': ['wakrah', 'al wakra', 'al wakrah'],
            'khor': ['al khor', 'alkhor', 'khawr'],
            'sadd': ['al sadd', 'alsadd'],
            'duhail': ['al duhail', 'duheil'],
            'rayyan': ['al rayyan', 'alrayyan', 'rayan', 'al rayan'],
            'rayan': ['rayyan', 'al rayyan', 'alrayyan'],
            'gharafa': ['al gharafa', 'algharafa', 'gharrafa'],
            'markhiya': ['al markhiya', 'markhiyya'],
            'messila': ['al messila', 'messilah'],
            'thumama': ['al thumama', 'thumamah'],
            'waab': ['al waab', 'wab'],
            'aziziya': ['al aziziya', 'aziziyah'],
            'mansoura': ['al mansoura', 'mansourah'],
            'najma': ['al najma', 'nejmah'],
            'nasr': ['al nasr'],
            'hilal': ['al hilal'],
            'sailiya': ['al sailiya', 'sailiyah'],
            'dafna': ['al dafna', 'dafnah', 'west bay'],
            'westbay': ['west bay', 'dafna', 'al dafna'],
            'downtown': ['mushaireb', 'msheireb', 'souq waqif'],
            'corniche': ['doha corniche', 'al corniche'],
            'pearl': ['the pearl', 'pearl qatar'],
            'katara': ['katara cultural village'],
        }

        # Build search terms including variants
        # Clean words: strip commas, punctuation
        clean_words = [w.replace(',', '').replace('.', '').strip() for w in words if w.strip()]
        clean_words = [w for w in clean_words if w]

        search_terms = set(clean_words)
        # Full address as search term
        search_terms.add(address_lower.replace(',', ' ').strip())

        # Build multi-word n-grams (bigrams, trigrams, 4-grams) to catch
        # area names like "Umm Salal Ali", "Al Wakrah", "West Bay" etc.
        for n in range(2, min(5, len(clean_words) + 1)):
            for i in range(len(clean_words) - n + 1):
                ngram = ' '.join(clean_words[i:i + n])
                search_terms.add(ngram)

        for word in clean_words:
            if word in spelling_variants:
                search_terms.update(spelling_variants[word])
            # Partial matches only for words long enough to be meaningful (>3 chars)
            if len(word) > 3:
                for key, variants in spelling_variants.items():
                    if key in word or word in key:
                        search_terms.add(key)
                        search_terms.update(variants)

        # Sort search terms: longer/more specific first for better matching
        sorted_terms = sorted(
            [t for t in search_terms if len(t) >= 3],
            key=lambda t: -len(t)
        )

        # Search with all terms — collect candidates and pick best match
        candidates = []
        seen_areas = set()  # avoid duplicate DB hits
        for term in sorted_terms:
            # Search in ZoneArea
            area_matches = ZoneArea.objects.filter(
                Q(area_name__icontains=term) |
                Q(area_name_arabic__icontains=term)
            ).select_related('zone')[:5]

            for area_match in area_matches:
                if area_match.id in seen_areas:
                    continue
                seen_areas.add(area_match.id)
                # Score: how much of the area name is covered by our search
                area_lower = area_match.area_name.lower()
                score = len(term) / max(len(area_lower), 1)
                # Bonus if area name appears in the address text
                if area_lower in address_lower:
                    score += 0.8
                elif address_lower in area_lower:
                    score += 0.5
                candidates.append((score, {
                    'zone_number': area_match.zone.zone_number,
                    'zone_name': area_match.zone.zone_name,
                    'area_name': area_match.area_name,
                    'latitude': float(area_match.latitude) if area_match.latitude else (float(area_match.zone.latitude) if area_match.zone.latitude else None),
                    'longitude': float(area_match.longitude) if area_match.longitude else (float(area_match.zone.longitude) if area_match.zone.longitude else None),
                }))

            # Search in ZoneName
            zone_matches = ZoneName.objects.filter(
                Q(zone_name__icontains=term) |
                Q(zone_name_arabic__icontains=term)
            )[:5]

            for zone_match in zone_matches:
                zone_lower = zone_match.zone_name.lower()
                score = len(term) / max(len(zone_lower), 1)
                if zone_lower in address_lower:
                    score += 0.8
                elif address_lower in zone_lower:
                    score += 0.5
                candidates.append((score, {
                    'zone_number': zone_match.zone_number,
                    'zone_name': zone_match.zone_name,
                    'area_name': zone_match.zone_name,
                    'latitude': float(zone_match.latitude) if zone_match.latitude else None,
                    'longitude': float(zone_match.longitude) if zone_match.longitude else None,
                }))

        # Reverse search: check if any ZoneArea area_name exists within the address
        if not candidates:
            all_areas = ZoneArea.objects.select_related('zone').filter(is_active=True)
            for area in all_areas:
                area_lower = area.area_name.lower()
                if len(area_lower) >= 4 and area_lower in address_lower:
                    score = len(area_lower) / max(len(address_lower), 1) + 0.8
                    candidates.append((score, {
                        'zone_number': area.zone.zone_number,
                        'zone_name': area.zone.zone_name,
                        'area_name': area.area_name,
                        'latitude': float(area.latitude) if area.latitude else (float(area.zone.latitude) if area.zone.latitude else None),
                        'longitude': float(area.longitude) if area.longitude else (float(area.zone.longitude) if area.zone.longitude else None),
                    }))

        if candidates:
            # Return highest-scoring match
            candidates.sort(key=lambda x: -x[0])
            return candidates[0][1]

        return None

    def _lookup_qnas_building(
        self,
        zone_number: int,
        street_number: int,
        building_number: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Look up precise coordinates from QNAS API for zone/street/building."""
        import requests
        from decouple import config

        token = config("QNAS_TOKEN", default="")
        domain = config("QNAS_DOMAIN", default="ezzydelivery.qa")

        if not token:
            return None

        headers = {
            "X-Token": token,
            "X-Domain": domain,
            "Accept": "application/json",
            "User-Agent": "EzzyDelivery/1.0",
            "Referer": f"https://{domain}/",
            "Origin": f"https://{domain}",
        }

        try:
            url = f"https://qnas.qa/get_buildings/{zone_number}/{street_number}"
            resp = requests.get(url, headers=headers, timeout=10)

            if resp.status_code != 200:
                return None

            buildings = resp.json()
            if not isinstance(buildings, list) or not buildings:
                return None

            # Try exact building match first
            if building_number:
                building_str = str(building_number)
                for b in buildings:
                    if str(b.get("building_number", "")) == building_str:
                        return {
                            'latitude': float(b["x"]),
                            'longitude': float(b["y"]),
                            'exact_match': True,
                        }

            # Fallback to first building on the street
            first = buildings[0]
            if first.get("x") and first.get("y"):
                return {
                    'latitude': float(first["x"]),
                    'longitude': float(first["y"]),
                    'exact_match': False,
                }

        except Exception as e:
            logger.warning(f"QNAS lookup error for zone={zone_number}, street={street_number}: {e}")

        return None

    def _get_zone_coordinates(self, zone_number: int) -> Optional[Dict[str, float]]:
        """Get coordinates for a zone by zone number."""
        from delivery.models import ZoneName

        try:
            zone = ZoneName.objects.get(zone_number=zone_number, is_active=True)
            if zone.latitude and zone.longitude:
                return {
                    'latitude': float(zone.latitude),
                    'longitude': float(zone.longitude),
                }
        except ZoneName.DoesNotExist:
            pass
        return None

    def _get_zone_details(self, zone_number: int) -> Optional[Dict[str, Any]]:
        """Get full zone details (name and coordinates) by zone number."""
        from delivery.models import ZoneName

        try:
            zone = ZoneName.objects.get(zone_number=zone_number, is_active=True)
            return {
                'zone_number': zone.zone_number,
                'zone_name': zone.zone_name,
                'latitude': float(zone.latitude) if zone.latitude else None,
                'longitude': float(zone.longitude) if zone.longitude else None,
            }
        except ZoneName.DoesNotExist:
            pass
        return None

    def _ai_search_zone(self, address: str) -> Optional[Dict[str, Any]]:
        """Use AI to identify the zone from address text."""
        from delivery.models import ZoneName
        import json

        try:
            from ai_agent.services.claude_service import get_claude_service
            claude = get_claude_service()

            # Check if service is available
            available, msg = claude.is_available()
            if not available:
                logger.warning(f"AI service not available for zone search: {msg}")
                return None

            # Get list of available zones for context
            zones = list(ZoneName.objects.filter(is_active=True).values('zone_number', 'zone_name')[:100])
            zones_list = "\n".join([f"Zone {z['zone_number']}: {z['zone_name']}" for z in zones])

            # Create prompt for Claude
            system_prompt = """You are a Qatar address expert. Given an address or location text, identify the most likely Qatar zone number and name.

Available Qatar zones:
""" + zones_list + """

Respond ONLY with a valid JSON object in this exact format:
{"zone_number": <number>, "zone_name": "<name>", "area_name": "<area if different>", "confidence": <0.0-1.0>}

If you cannot identify the zone, respond with: {"zone_number": null}
Do not include any other text, only the JSON."""

            messages = [
                {"role": "user", "content": f"Identify the Qatar zone for this address: {address}"}
            ]

            response = claude.chat(messages=messages, system=system_prompt)

            if response.get('error'):
                logger.warning(f"AI zone search error: {response.get('message')}")
                return None

            content = response.get('content', '')
            if not content:
                return None

            # Parse JSON response
            try:
                # Clean up response - extract JSON if wrapped in markdown
                content = content.strip()
                if content.startswith('```'):
                    content = content.split('\n', 1)[1] if '\n' in content else content
                    content = content.rsplit('```', 1)[0] if '```' in content else content
                content = content.strip()

                result = json.loads(content)
                if result.get('zone_number') is not None:
                    zone_num = int(result['zone_number'])
                    # Verify zone exists
                    zone = ZoneName.objects.filter(zone_number=zone_num, is_active=True).first()
                    if zone:
                        return {
                            'zone_number': zone.zone_number,
                            'zone_name': zone.zone_name,
                            'area_name': result.get('area_name', zone.zone_name),
                        }
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.warning(f"AI zone search JSON parse error: {e}, content: {content[:200]}")

        except Exception as e:
            logger.error(f"AI zone search error: {e}")

        return None

    def _geocode_landmark(
        self,
        address: str,
        zone_lat: Optional[float] = None,
        zone_lng: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Geocode an address/landmark via HERE Maps (Geocode + Discover APIs).

        Uses zone center coordinates as a hint to pick the best result when
        both APIs return different locations. Fallback to Nominatim.
        """
        import math
        import requests
        from decouple import config

        def _dist(lat1, lng1, lat2, lng2):
            return math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2) * 111

        # Strip zone/street/building numbers from query (confuses geocoders)
        cleaned = re.sub(r'\b(?:zone|z)\s*[#:]?\s*\d+', '', address, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:street|st\.?)\s*[#:]?\s*\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:building|bldg\.?|house|villa)\s*[#:]?\s*\d+', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(?:منطقة|شارع|مبنى)\s*\d+', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip().strip(',').strip()
        query = cleaned if cleaned and len(cleaned) >= 3 else address

        here_key = config("HERE_MAP_API_KEY", default="")
        geo_result = None
        disc_result = None

        # 1) HERE Geocode API (good for area/neighborhood names)
        if here_key:
            try:
                resp = requests.get(
                    "https://geocode.search.hereapi.com/v1/geocode",
                    params={
                        'q': f"{address}, Qatar",
                        'in': 'countryCode:QAT',
                        'limit': 1,
                        'apiKey': here_key,
                    },
                    timeout=8,
                )
                if resp.status_code == 200:
                    items = resp.json().get('items', [])
                    if items:
                        pos = items[0].get('position', {})
                        if pos.get('lat') and pos.get('lng'):
                            geo_result = (round(pos['lat'], 8), round(pos['lng'], 8))
            except Exception as e:
                logger.warning(f"HERE Geocode error for '{address}': {e}")

            # 2) HERE Discover API (good for landmarks/places)
            try:
                resp = requests.get(
                    "https://discover.search.hereapi.com/v1/discover",
                    params={
                        'q': query,
                        'in': 'circle:25.3,51.5;r=80000',
                        'limit': 1,
                        'apiKey': here_key,
                    },
                    timeout=8,
                )
                if resp.status_code == 200:
                    items = resp.json().get('items', [])
                    if items:
                        pos = items[0].get('position', {})
                        if pos.get('lat') and pos.get('lng'):
                            disc_result = (round(pos['lat'], 8), round(pos['lng'], 8))
            except Exception as e:
                logger.warning(f"HERE Discover error for '{address}': {e}")

        # 3) Pick best result
        if geo_result and disc_result:
            if zone_lat and zone_lng:
                # Use zone center as hint — pick whichever is closer
                g_dist = _dist(geo_result[0], geo_result[1], zone_lat, zone_lng)
                d_dist = _dist(disc_result[0], disc_result[1], zone_lat, zone_lng)
                if d_dist < g_dist - 0.3:
                    return {'latitude': disc_result[0], 'longitude': disc_result[1], 'provider': 'HERE Discover'}
            return {'latitude': geo_result[0], 'longitude': geo_result[1], 'provider': 'HERE'}
        elif geo_result:
            return {'latitude': geo_result[0], 'longitude': geo_result[1], 'provider': 'HERE'}
        elif disc_result:
            return {'latitude': disc_result[0], 'longitude': disc_result[1], 'provider': 'HERE Discover'}

        # 4) Fallback: Nominatim (free, no key needed)
        try:
            from geopy.geocoders import Nominatim
            geo = Nominatim(user_agent="EzzyDelivery/1.0", timeout=8)
            location = geo.geocode(
                f"{address}, Qatar",
                viewbox=[(24.47, 50.75), (26.18, 51.67)],
                bounded=True,
            )
            if location:
                return {
                    'latitude': round(location.latitude, 8),
                    'longitude': round(location.longitude, 8),
                    'provider': 'Nominatim',
                }
        except Exception as e:
            logger.warning(f"Nominatim geocode error for '{address}': {e}")

        return None

    def _extract_landmarks(self, address: str) -> List[str]:
        """Extract known landmarks from address."""
        address_lower = address.lower()
        landmarks = []

        landmark_patterns = [
            (r'city\s*center', 'City Center Mall'),
            (r'سيتي\s*سنتر', 'City Center Mall'),
            (r'villaggio', 'Villaggio Mall'),
            (r'villagio', 'Villaggio Mall'),
            (r'landmark\s*mall', 'Landmark Mall'),
            (r'mall\s*of\s*qatar', 'Mall of Qatar'),
            (r'the\s*pearl', 'The Pearl Qatar'),
            (r'pearl\s*qatar', 'The Pearl Qatar'),
            (r'lusail', 'Lusail'),
            (r'لوسيل', 'Lusail'),
            (r'souq\s*waqif', 'Souq Waqif'),
            (r'سوق\s*واقف', 'Souq Waqif'),
            (r'katara', 'Katara Cultural Village'),
            (r'كتارا', 'Katara Cultural Village'),
            (r'aspire', 'Aspire Zone'),
            (r'hamad\s*airport', 'Hamad International Airport'),
            (r'corniche', 'Doha Corniche'),
            (r'كورنيش', 'Doha Corniche'),
            (r'education\s*city', 'Education City'),
            (r'industrial\s*area', 'Industrial Area'),
        ]

        for pattern, name in landmark_patterns:
            if re.search(pattern, address_lower):
                if name not in landmarks:
                    landmarks.append(name)

        return landmarks


@register_tool
class LookupZoneTool(BaseTool):
    """
    Look up zone details by zone number or area name.
    """

    name = 'lookup_zone'
    description = '''Look up a Qatar zone by number or area name.

    Returns zone details including:
    - Zone number
    - Zone name (English and Arabic)
    - All area names within the zone
    - Zone group (e.g., West Doha, Industrial Area)
    - Neighboring zones

    Set fuzzy_match=true (with area_name) to get multiple suggestions
    when the exact zone is unclear. Returns ranked matches with confidence.

    Examples:
    - lookup_zone(zone_number=44) -> West Bay zone details
    - lookup_zone(area_name="Al Sadd") -> Zone containing Al Sadd
    - lookup_zone(area_name="west", fuzzy_match=true) -> suggests West Bay, West Doha zones
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'zone_number': {
                'type': 'integer',
                'description': 'Zone number (1-99)'
            },
            'area_name': {
                'type': 'string',
                'description': 'Area or neighborhood name to search'
            },
            'fuzzy_match': {
                'type': 'boolean',
                'description': 'Return multiple suggestions instead of exact match (default false)',
                'default': False,
            },
            'limit': {
                'type': 'integer',
                'description': 'Max suggestions when fuzzy_match=true (default 5)',
                'default': 5,
            },
        },
    }

    def execute(
        self,
        zone_number: Optional[int] = None,
        area_name: Optional[str] = None,
        fuzzy_match: bool = False,
        limit: int = 5,
    ) -> Dict[str, Any]:
        from delivery.models import ZoneName, ZoneArea, ZoneGroup

        if not zone_number and not area_name:
            raise ToolError('Provide zone_number or area_name', 'MISSING_PARAM')

        # Fuzzy suggestion mode (merged from SuggestZoneTool)
        if fuzzy_match and area_name:
            return self._fuzzy_search(area_name, limit)

        zone = None

        # Lookup by zone number
        if zone_number:
            try:
                zone = ZoneName.objects.prefetch_related('areas', 'zone_groups').get(
                    zone_number=zone_number,
                    is_active=True
                )
            except ZoneName.DoesNotExist:
                raise ToolError(f'Zone {zone_number} not found', 'NOT_FOUND')

        # Lookup by area name
        if not zone and area_name:
            area = ZoneArea.objects.filter(
                Q(area_name__icontains=area_name) |
                Q(area_name_arabic__icontains=area_name),
                is_active=True
            ).select_related('zone').first()

            if area:
                zone = area.zone
            else:
                # Try zone name directly
                zone = ZoneName.objects.filter(
                    Q(zone_name__icontains=area_name) |
                    Q(zone_name_arabic__icontains=area_name),
                    is_active=True
                ).prefetch_related('areas', 'zone_groups').first()

            if not zone:
                raise ToolError(f'Area "{area_name}" not found', 'NOT_FOUND')

        # Ensure prefetch for zone found via area
        if zone and not hasattr(zone, '_prefetched_objects_cache'):
            zone = ZoneName.objects.prefetch_related('areas', 'zone_groups').get(pk=zone.pk)

        # Build response
        areas = list(zone.areas.filter(is_active=True).values('area_name', 'area_name_arabic'))
        zone_groups = list(zone.zone_groups.filter(is_active=True).values('name', 'description'))
        neighbors = list(zone.neighbour_zones.filter(is_active=True).values('zone_number', 'zone_name'))

        return {
            'zone_number': zone.zone_number,
            'zone_name': zone.zone_name,
            'zone_name_arabic': zone.zone_name_arabic,
            'areas': areas,
            'zone_groups': zone_groups,
            'neighbor_zones': neighbors,
            'coordinates': {
                'latitude': float(zone.latitude) if zone.latitude else None,
                'longitude': float(zone.longitude) if zone.longitude else None,
            },
            'has_polygon': bool(zone.polygon),
        }

    def _fuzzy_search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Fuzzy search for zone suggestions (merged from SuggestZoneTool)."""
        from delivery.models import ZoneName, ZoneArea, ZoneGroup

        if len(query.strip()) < 2:
            raise ToolError('Query must be at least 2 characters', 'INVALID_INPUT')

        suggestions = []
        query_lower = query.lower()

        # Search zones by name
        zones = ZoneName.objects.filter(
            Q(zone_name__icontains=query_lower) |
            Q(zone_name_arabic__icontains=query),
            is_active=True
        ).prefetch_related('areas')[:limit]

        for zone in zones:
            suggestions.append({
                'zone_number': zone.zone_number,
                'zone_name': zone.zone_name,
                'match_type': 'zone_name',
                'confidence': 0.9,
            })

        # Search areas
        if len(suggestions) < limit:
            areas = ZoneArea.objects.filter(
                Q(area_name__icontains=query_lower) |
                Q(area_name_arabic__icontains=query),
                is_active=True
            ).select_related('zone')[:limit - len(suggestions)]

            for area in areas:
                if not any(s['zone_number'] == area.zone.zone_number for s in suggestions):
                    suggestions.append({
                        'zone_number': area.zone.zone_number,
                        'zone_name': area.zone.zone_name,
                        'area_name': area.area_name,
                        'match_type': 'area_name',
                        'confidence': 0.85,
                    })

        # Search zone groups
        if len(suggestions) < limit:
            groups = ZoneGroup.objects.filter(
                Q(name__icontains=query_lower) |
                Q(description__icontains=query_lower),
                is_active=True
            ).prefetch_related('zones')[:limit - len(suggestions)]

            for group in groups:
                for zone in group.zones.filter(is_active=True)[:3]:
                    if not any(s['zone_number'] == zone.zone_number for s in suggestions):
                        suggestions.append({
                            'zone_number': zone.zone_number,
                            'zone_name': zone.zone_name,
                            'zone_group': group.name,
                            'match_type': 'zone_group',
                            'confidence': 0.7,
                        })
                        if len(suggestions) >= limit:
                            break

        # Search training data
        if len(suggestions) < limit:
            training = ZoneTrainingData.objects.filter(
                text_input__icontains=query_lower
            ).select_related('zone').order_by('-confidence')[:limit - len(suggestions)]

            for data in training:
                if not any(s['zone_number'] == data.zone.zone_number for s in suggestions):
                    suggestions.append({
                        'zone_number': data.zone.zone_number,
                        'zone_name': data.zone.zone_name,
                        'matched_text': data.text_input,
                        'match_type': 'training_data',
                        'confidence': data.confidence * 0.8,
                    })

        # Sort by confidence
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)

        return {
            'query': query,
            'suggestions': suggestions[:limit],
            'count': len(suggestions[:limit]),
        }


