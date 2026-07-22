# Purpose: Reusable "pull one chat's full message history from WAHA into WhatsAppMessage" helper.
# Used by: crm management command backfill_lead_wa_chats, CRM manual-link-chat view (workforce/crm_views.py).
# Notes: Caller supplies the exact chatId to try (e.g. "<lid>@lid" or "<phone>@c.us") — WhatsApp's LID
#        privacy mode means some contacts' chats are indexed by lid, not phone JID, so callers should try
#        both forms and keep whichever actually returns messages.

import logging

from django.conf import settings

from whatsapp.management.commands.backfill_waha import _strip_jid, upsert_message, waha_get

logger = logging.getLogger(__name__)


def pull_chat_history(chat_id, session=None, page_size=100, max_pages=5):
    """Fetch up to max_pages*page_size messages for chat_id from WAHA and upsert
    them into WhatsAppMessage (deduped on waha_message_id). Returns
    (total_seen, total_inserted, counterparties) — counterparties is the set of
    customer-side identifiers (bare digits or "<lid>@lid") actually seen in the
    payloads. Querying a chat by phone JID doesn't guarantee the messages come
    back tagged with that same phone: some contacts' chats are privacy-LID-indexed,
    so WAHA can resolve the phone-based chatId fine but every message inside is
    stamped with a LID the caller has no other way of discovering."""
    session = session or settings.WAHA_DEFAULT_SESSION
    total_seen = 0
    total_inserted = 0
    counterparties = set()
    offset = 0
    for _ in range(max_pages):
        msgs = waha_get(
            f'/api/{session}/chats/{chat_id}/messages',
            params={'limit': page_size, 'offset': offset, 'downloadMedia': 'true'},
            timeout=120,
        )
        if not msgs:
            break
        for m in msgs:
            if not m.get('id'):
                continue
            total_seen += 1
            counterparty = _strip_jid(m.get('to')) if m.get('fromMe') else _strip_jid(m.get('from'))
            if counterparty:
                counterparties.add(counterparty)
            try:
                _obj, created = upsert_message(m, session, chat_id)
            except Exception:
                logger.exception('waha_backfill: upsert failed for %s', m.get('id'))
                continue
            if created:
                total_inserted += 1
        if len(msgs) < page_size:
            break
        offset += page_size
    return total_seen, total_inserted, counterparties
