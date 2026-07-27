# Purpose: Generic fuzzy zone resolution (typo tolerance) + self-learning aliases.
# Used by: orders.signals._resolve_zone_number (Tier 2 fallback), workforce.views.update_order_zone (Tier 4 learn).
# Notes: Uses Postgres pg_trgm word_similarity so typos like "aziziyeh" -> "Al Aziziya" resolve
#        without hardcoding each variant. Guardrails (min score + margin over 2nd) keep it precise.

import logging
from django.db import connection

logger = logging.getLogger(__name__)

# Auto-fill only when the best match clears MIN_SIM *and* beats the runner-up by MARGIN.
# Tuned on real samples: real typos score ~0.6-0.85; junk (names/emails/numbers) stays <0.5
# or ties with a runner-up, so it is rejected instead of mis-filled.
DEFAULT_MIN_SIM = 0.55
DEFAULT_MARGIN = 0.12


def resolve_zone_fuzzy(text, min_sim=DEFAULT_MIN_SIM, margin=DEFAULT_MARGIN):
    """
    Fuzzily resolve free-text (an area name, or a whole messy address) to a zone number
    using trigram word-similarity against every active zone/area name (EN + AR).

    Returns (zone_number, score, matched_name) if a confident match is found, else
    (None, best_score, best_name) so callers can log near-misses.
    """
    if not text or len(str(text).strip()) < 3:
        return None, 0.0, None

    q = str(text).strip().lower()
    # One candidate set: area names + zone names, English + Arabic, each -> its zone number.
    sql = """
        WITH names AS (
            SELECT zn.zone_number AS zone_number, lower(za.area_name) AS name
            FROM delivery_zonearea za JOIN delivery_zonename zn ON zn.id = za.zone_id
            WHERE za.is_active AND za.area_name <> ''
            UNION ALL
            SELECT zn.zone_number, lower(za.area_name_arabic)
            FROM delivery_zonearea za JOIN delivery_zonename zn ON zn.id = za.zone_id
            WHERE za.is_active AND coalesce(za.area_name_arabic, '') <> ''
            UNION ALL
            SELECT zn.zone_number, lower(zn.zone_name)
            FROM delivery_zonename zn WHERE zn.is_active AND zn.zone_name <> ''
            UNION ALL
            SELECT zn.zone_number, lower(zn.zone_name_arabic)
            FROM delivery_zonename zn WHERE zn.is_active AND coalesce(zn.zone_name_arabic, '') <> ''
        )
        SELECT zone_number, name, word_similarity(name, %s) AS sim
        FROM names
        ORDER BY sim DESC
        LIMIT 2
    """
    with connection.cursor() as c:
        c.execute(sql, [q])
        rows = c.fetchall()

    if not rows:
        return None, 0.0, None

    top_zone, top_name, top_sim = rows[0]
    second_sim = rows[1][2] if len(rows) > 1 else 0.0

    if top_sim >= min_sim and (top_sim - second_sim) >= margin:
        logger.info(f"Fuzzy-resolved '{q[:40]}' -> zone {top_zone} ('{top_name}', sim={top_sim:.2f})")
        return top_zone, top_sim, top_name

    logger.debug(
        f"Fuzzy match for '{q[:40]}' below guardrails: best='{top_name}' "
        f"sim={top_sim:.2f} 2nd={second_sim:.2f} (min={min_sim}, margin={margin})"
    )
    return None, top_sim, top_name


def learn_alias(text, zone_number, verified=True):
    """
    Tier 4 self-learning: record a confirmed text -> zone mapping as a ZoneTrainingData
    alias so this exact spelling (and its trigram neighbours) resolves for free next time.
    Called when staff manually sets/corrects a task's zone. Best-effort, never raises.
    """
    if not text or not zone_number:
        return
    term = str(text).strip().lower()
    if len(term) < 3 or len(term) > 200:
        return
    try:
        from ai_agent.models import ZoneTrainingData
        from delivery.models import ZoneName
        zone = ZoneName.objects.filter(zone_number=zone_number, is_active=True).first()
        if not zone:
            return
        _, created = ZoneTrainingData.objects.get_or_create(
            zone=zone,
            text_input=term,
            defaults={
                'input_type': 'alias',
                'language': 'ar' if any('؀' <= ch <= 'ۿ' for ch in term) else 'en',
                'confidence': 1.0,
                'is_verified': verified,
            },
        )
        if created:
            logger.info(f"Learned zone alias '{term[:40]}' -> zone {zone_number}")
    except Exception as e:
        logger.warning(f"Failed to learn zone alias '{text}' -> {zone_number}: {e}")
