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
        }

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

        # Try to find area/zone from training data
        zone_match = self._find_zone_from_training_data(address)
        if zone_match:
            if not result['zone_number']:
                result['zone_number'] = zone_match['zone_number']
                result['confidence'] += 0.25
            result['zone_name'] = zone_match.get('zone_name')
            result['area_name'] = zone_match.get('area_name')
            result['parse_notes'].append(f"Matched area: {zone_match.get('area_name')}")

        # Try to find zone from ZoneName/ZoneArea models
        if not result['zone_number']:
            zone_from_db = self._find_zone_from_database(address)
            if zone_from_db:
                result['zone_number'] = zone_from_db['zone_number']
                result['zone_name'] = zone_from_db.get('zone_name')
                result['area_name'] = zone_from_db.get('area_name')
                result['confidence'] += 0.25
                result['parse_notes'].append(f"Matched from database: {zone_from_db.get('area_name')}")
                # Get coordinates if available
                if zone_from_db.get('latitude') and zone_from_db.get('longitude'):
                    result['coordinates']['latitude'] = zone_from_db['latitude']
                    result['coordinates']['longitude'] = zone_from_db['longitude']

        # Fetch zone name and coordinates if we have a zone number but missing details
        if result['zone_number']:
            zone_details = self._get_zone_details(result['zone_number'])
            if zone_details:
                # Set zone name if not already set
                if not result['zone_name']:
                    result['zone_name'] = zone_details.get('zone_name')
                    result['parse_notes'].append(f"Zone name: {zone_details.get('zone_name')}")

            # Try QNAS API for precise building-level coordinates
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
                    src = f"building {result.get('building_number')}" if qnas_coords.get('exact_match') else "street"
                    result['parse_notes'].append(f"QNAS precise coordinates from {src}")

            # Fallback to zone center if no QNAS coordinates
            if not result['coordinates']['latitude'] and zone_details and zone_details.get('latitude'):
                result['coordinates']['latitude'] = zone_details['latitude']
                result['coordinates']['longitude'] = zone_details['longitude']
                result['parse_notes'].append(f"Zone {result['zone_number']} center coordinates (approximate)")

        # AI Search fallback if no zone found
        if not result['zone_number']:
            ai_result = self._ai_search_zone(address)
            if ai_result:
                result['zone_number'] = ai_result.get('zone_number')
                result['zone_name'] = ai_result.get('zone_name')
                result['area_name'] = ai_result.get('area_name')
                result['confidence'] += 0.35
                result['parse_notes'].append(f"AI identified zone: {ai_result.get('zone_name')} (Zone {ai_result.get('zone_number')})")

                # Get coordinates for the AI-identified zone
                if result['zone_number']:
                    zone_details = self._get_zone_details(result['zone_number'])
                    if zone_details:
                        if not result['zone_name']:
                            result['zone_name'] = zone_details.get('zone_name')
                        if zone_details.get('latitude'):
                            result['coordinates']['latitude'] = zone_details['latitude']
                            result['coordinates']['longitude'] = zone_details['longitude']

        # Extract common landmarks
        landmarks = self._extract_landmarks(address)
        if landmarks:
            result['landmarks'] = landmarks
            result['confidence'] += 0.1
            result['parse_notes'].append(f"Landmarks: {', '.join(landmarks)}")

        # Cap confidence at 1.0
        result['confidence'] = min(1.0, result['confidence'])

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
            'rayyan': ['al rayyan', 'alrayyan'],
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
        search_terms = set(words)
        for word in words:
            word_clean = word.replace(',', '').strip()
            if word_clean in spelling_variants:
                search_terms.update(spelling_variants[word_clean])
            # Also check partial matches
            for key, variants in spelling_variants.items():
                if key in word_clean or word_clean in key:
                    search_terms.add(key)
                    search_terms.update(variants)

        # Search with all terms
        for term in search_terms:
            if len(term) < 3:
                continue

            # Search in ZoneArea
            area_match = ZoneArea.objects.filter(
                Q(area_name__icontains=term) |
                Q(area_name_arabic__icontains=term)
            ).select_related('zone').first()

            if area_match:
                return {
                    'zone_number': area_match.zone.zone_number,
                    'zone_name': area_match.zone.zone_name,
                    'area_name': area_match.area_name,
                    'latitude': float(area_match.zone.latitude) if area_match.zone.latitude else None,
                    'longitude': float(area_match.zone.longitude) if area_match.zone.longitude else None,
                }

            # Search in ZoneName
            zone_match = ZoneName.objects.filter(
                Q(zone_name__icontains=term) |
                Q(zone_name_arabic__icontains=term)
            ).first()

            if zone_match:
                return {
                    'zone_number': zone_match.zone_number,
                    'zone_name': zone_match.zone_name,
                    'area_name': zone_match.zone_name,
                    'latitude': float(zone_match.latitude) if zone_match.latitude else None,
                    'longitude': float(zone_match.longitude) if zone_match.longitude else None,
                }

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

    Examples:
    - lookup_zone(zone_number=44) -> West Bay zone details
    - lookup_zone(area_name="Al Sadd") -> Zone containing Al Sadd
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
            }
        },
    }

    def execute(
        self,
        zone_number: Optional[int] = None,
        area_name: Optional[str] = None
    ) -> Dict[str, Any]:
        from delivery.models import ZoneName, ZoneArea

        if not zone_number and not area_name:
            raise ToolError('Provide zone_number or area_name', 'MISSING_PARAM')

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


@register_tool
class ValidateAddressTool(BaseTool):
    """
    Validate a structured address for completeness and correctness.
    """

    name = 'validate_address'
    description = '''Validate a Qatar address for completeness and correctness.

    Checks:
    - Zone number is valid (exists in system)
    - Street number format is valid
    - Building number is provided
    - All required fields are present

    Returns validation status and any issues found.
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'zone_number': {
                'type': 'integer',
                'description': 'Zone number'
            },
            'street_number': {
                'type': 'integer',
                'description': 'Street number'
            },
            'building_number': {
                'type': 'integer',
                'description': 'Building/villa number'
            },
            'area_name': {
                'type': 'string',
                'description': 'Area name (optional)'
            }
        },
        'required': ['zone_number']
    }

    def execute(
        self,
        zone_number: int,
        street_number: Optional[int] = None,
        building_number: Optional[int] = None,
        area_name: Optional[str] = None
    ) -> Dict[str, Any]:
        from delivery.models import ZoneName

        issues = []
        warnings = []
        is_valid = True

        # Validate zone
        try:
            zone = ZoneName.objects.get(zone_number=zone_number, is_active=True)
            zone_info = {
                'zone_number': zone.zone_number,
                'zone_name': zone.zone_name,
            }
        except ZoneName.DoesNotExist:
            is_valid = False
            issues.append({
                'field': 'zone_number',
                'issue': f'Zone {zone_number} not found in system',
                'suggestion': 'Please verify the zone number'
            })
            zone_info = None

        # Validate street number
        if street_number:
            if street_number < 1 or street_number > 9999:
                warnings.append({
                    'field': 'street_number',
                    'issue': f'Street number {street_number} seems unusual',
                    'suggestion': 'Qatar streets are typically 1-999'
                })
        else:
            warnings.append({
                'field': 'street_number',
                'issue': 'Street number not provided',
                'suggestion': 'Adding street number improves delivery accuracy'
            })

        # Validate building number
        if not building_number:
            is_valid = False
            issues.append({
                'field': 'building_number',
                'issue': 'Building number is required for delivery',
                'suggestion': 'Please provide building or villa number'
            })

        # Calculate completeness score
        fields_provided = sum([
            zone_number is not None,
            street_number is not None,
            building_number is not None,
            bool(area_name),
        ])
        completeness = fields_provided / 4.0

        return {
            'is_valid': is_valid,
            'completeness_score': completeness,
            'zone_info': zone_info,
            'issues': issues,
            'warnings': warnings,
            'formatted_address': self._format_address(
                zone_number, street_number, building_number, area_name, zone_info
            ) if is_valid else None
        }

    def _format_address(
        self,
        zone_number: int,
        street_number: Optional[int],
        building_number: Optional[int],
        area_name: Optional[str],
        zone_info: Optional[Dict]
    ) -> str:
        """Format address into standard Qatar format."""
        parts = []

        if building_number:
            parts.append(f'Building {building_number}')

        if street_number:
            parts.append(f'Street {street_number}')

        parts.append(f'Zone {zone_number}')

        if zone_info and zone_info.get('zone_name'):
            parts.append(zone_info['zone_name'])
        elif area_name:
            parts.append(area_name)

        return ', '.join(parts)


@register_tool
class SuggestZoneTool(BaseTool):
    """
    Suggest possible zones based on partial or ambiguous input.
    """

    name = 'suggest_zone'
    description = '''Suggest possible Qatar zones based on partial input.

    Useful when the exact zone is unclear. Returns a list of possible
    matches with confidence scores.

    Example: "west" -> suggests West Bay (Zone 44), West Doha zones, etc.
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'query': {
                'type': 'string',
                'description': 'Partial zone name, area name, or landmark'
            },
            'limit': {
                'type': 'integer',
                'description': 'Maximum number of suggestions (default 5)',
                'default': 5
            }
        },
        'required': ['query']
    }

    def execute(self, query: str, limit: int = 5) -> Dict[str, Any]:
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
                # Avoid duplicates
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
