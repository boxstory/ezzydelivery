# Purpose: Read an untriaged WhatsApp conversation, decide whether the sender is a driver applicant or a business prospect, and promote them onto the matching CRM board — only when the text actually says so.
# Used by: crm/management/commands/triage_wa_inbox.py (daily cron).
# Notes: Fails closed on purpose — no AI, thin conversation, low confidence or an unparseable answer all leave the sender in the inbox for a human. Anything already represented on a board (a lead in any stage, or a driver application) is skipped, never duplicated.

import json
import logging
import re

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from crm import services as crm_services
from crm.models import Lead, LeadActivity

logger = logging.getLogger(__name__)

# Below this the "conversation" is a greeting or a stray media caption — there is
# nothing to read, so no verdict is trustworthy.
MIN_TEXT_CHARS = 20
# Messages handed to the model. Newest matter most; the oldest are where the
# person usually says what they want.
MAX_MESSAGES = 40
DEFAULT_MIN_CONFIDENCE = 0.75
# A verdict is keyed on the conversation's last message, so it is recomputed the
# moment the sender writes again — but an unchanged chat is never paid for twice.
VERDICT_TTL = 60 * 60 * 24 * 45

CATEGORIES = {Lead.CATEGORY_DRIVER, Lead.CATEGORY_BUSINESS}

# Triage picks its own model rather than riding AI_CHAT_PROVIDER. The shared chat
# stack is pointed at a free router that rate-limits and goes down; a nightly job
# that silently classifies nothing is worse than no job. Whatever is configured
# here is tried first, then the ordinary chat service as a second chance.
TRIAGE_PROVIDER = getattr(settings, 'CRM_TRIAGE_AI_PROVIDER', 'groq')
TRIAGE_MODEL = getattr(settings, 'CRM_TRIAGE_AI_MODEL', 'openai/gpt-oss-120b')

PROMPT = """You triage inbound WhatsApp messages for EzzyDelivery, a delivery and \
logistics company in Qatar. Decide who this sender is, from what they actually wrote.

Answer "driver" if they are looking for delivery work: asking about a driver job, \
salary or per-delivery pay, how to join or register as a driver, vehicle or licence \
requirements, sending a CV, or following up on a driver application.

Answer "business" if they want us to deliver for them: a shop, restaurant or online \
seller asking about delivery pricing, coverage, cash on delivery, an account, a \
contract, a pickup, or sending a parcel.

Answer "unknown" for ANYTHING else, and whenever you are not sure: greetings with no \
request, wrong numbers, personal chat, spam, marketing sent to us, a question you \
cannot place, or a conversation too short to read. Guessing costs us more than \
leaving it for a human, so prefer "unknown".

Messages may be in English, Arabic, Hindi, Urdu, Malayalam or a mix.

Conversation (oldest first; "Them" is the sender, "Us" is EzzyDelivery):
{conversation}

Reply with ONLY a JSON object, no markdown fence and no other text:
{{"category": "driver" | "business" | "unknown", "confidence": <number between 0 and 1>, \
"reason": "<at most 15 words quoting what decided it>"}}"""


def conversation_text(session, from_number, limit=MAX_MESSAGES):
    """(rendered transcript, total inbound text length) for one sender's chat."""
    try:
        from whatsapp.models import WhatsAppMessage
        rows = list(
            WhatsAppMessage.objects
            .filter(session=session)
            .filter(from_number=from_number)
            .exclude(message_type='system')
            .order_by('-received_at')[:limit]
        )
    except Exception:
        logger.exception('crm: triage transcript fetch failed for %s', from_number)
        return '', 0
    rows.reverse()

    lines, inbound_chars = [], 0
    for m in rows:
        body = (m.body or '').strip()
        if m.direction == 'inbound':
            inbound_chars += len(body)
        who = 'Them' if m.direction == 'inbound' else 'Us'
        if not body:
            body = f'[{m.message_type or "media"} attachment]'
        ts = m.received_at.strftime('%d %b %H:%M') if m.received_at else ''
        lines.append(f'{who} ({ts}): {body[:400]}')
    return '\n'.join(lines), inbound_chars


def _parse_verdict(text):
    """Model output -> (category, confidence, reason). Anything we cannot read
    becomes 'unknown', which leaves the sender in the inbox."""
    raw = (text or '').strip()
    if not raw:
        return '', 0.0, 'empty AI response'
    # Models still fence JSON now and then despite being told not to.
    fenced = re.search(r'\{.*\}', raw, re.S)
    if not fenced:
        return '', 0.0, 'AI response was not JSON'
    try:
        data = json.loads(fenced.group(0))
    except (ValueError, TypeError):
        return '', 0.0, 'AI response was not valid JSON'
    if not isinstance(data, dict):
        return '', 0.0, 'AI response was not an object'

    category = str(data.get('category', '')).strip().lower()
    if category not in CATEGORIES:
        category = ''
    try:
        confidence = float(data.get('confidence', 0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(data.get('reason', '') or '').strip()[:200]
    return category, confidence, reason


def _services():
    """The models to try, in order: the triage-specific one, then the shared chat
    stack. Either may be missing or misconfigured — that is not fatal here."""
    from ai_agent.services.unified_service import _build_service, get_chat_service

    built = []
    if TRIAGE_PROVIDER:
        try:
            svc = _build_service(TRIAGE_PROVIDER, TRIAGE_MODEL)
            if svc is not None:
                built.append(svc)
        except Exception:
            logger.exception('crm: triage provider %s unavailable', TRIAGE_PROVIDER)
    try:
        built.append(get_chat_service('chat'))
    except Exception:
        logger.exception('crm: triage fallback chat service unavailable')
    return built


def _ask(prompt):
    """(content, error). Tries each service until one answers with text."""
    from ai_agent.services.unified_service import GeminiService, OpenAICompatService

    services = _services()
    if not services:
        return '', 'AI unavailable (no chat service could be built)'

    last_error = 'AI unavailable (no service answered)'
    for service in services:
        try:
            available, msg = service.is_available()
            if not available:
                last_error = f'AI unavailable ({msg})'
                continue
            # Reasoning models spend tokens before the answer and truncate to empty
            # content on the default budget. Built per call, so this leaks nowhere.
            for svc in (service, getattr(service, 'primary', None),
                        getattr(service, 'fallback', None)):
                if isinstance(svc, (OpenAICompatService, GeminiService)):
                    svc.max_tokens = 1200
            result = service.chat(messages=[{'role': 'user', 'content': prompt}])
            if result.get('error'):
                last_error = f"AI error ({result.get('message', 'unknown')})"
                continue
            content = (result.get('content') or '').strip()
            if not content:
                last_error = 'AI error (empty response)'
                continue
            return content, ''
        except Exception:
            logger.exception('crm: triage call failed on %s', type(service).__name__)
            last_error = 'AI error (call raised — see logs)'
    return '', last_error


def classify(session, from_number, last_at=None, use_cache=True):
    """Read the chat and decide. Returns a dict with ``category`` ('' when it
    could not be decided), ``confidence``, ``reason`` and ``cached``.

    The verdict is cached against the conversation's last message, so a sender who
    has not written since is never re-read, and one who has is re-read at once.
    """
    key = f'crm:watriage:{session}:{from_number}:{last_at.isoformat() if last_at else ""}'
    if use_cache:
        hit = cache.get(key)
        if hit:
            return {**hit, 'cached': True}

    convo, inbound_chars = conversation_text(session, from_number)
    if inbound_chars < MIN_TEXT_CHARS:
        verdict = {
            'category': '', 'confidence': 0.0,
            'reason': f'only {inbound_chars} characters of text from this sender',
        }
        cache.set(key, verdict, VERDICT_TTL)
        return {**verdict, 'cached': False}

    try:
        content, error = _ask(PROMPT.format(conversation=convo))
        if error:
            # Not cached: the next run should try again once AI is back.
            return {'category': '', 'confidence': 0.0, 'reason': error, 'cached': False}
        category, confidence, reason = _parse_verdict(content)
    except Exception:
        logger.exception('crm: triage classify failed for %s', from_number)
        return {'category': '', 'confidence': 0.0,
                'reason': 'classification raised — see logs', 'cached': False}

    verdict = {'category': category, 'confidence': confidence, 'reason': reason}
    cache.set(key, verdict, VERDICT_TTL)
    return {**verdict, 'cached': False}


def driver_phone_keys():
    """{last-8-digit key: driver id} for every driver application on file.

    Built once per run: matching each sender against the driver table one query at
    a time turned a 200-sender pass into 200 full-table scans. ``None`` means the
    lookup failed, which callers must treat as "cannot prove it is safe".
    """
    try:
        from fleet.models import Driver
        keys = {}
        for pk, phone, whatsapp in Driver.objects.values_list(
            'driver_id', 'driver_phone', 'driver_whatsapp',
        ):
            for key in crm_services._driver_match_keys(phone, whatsapp):
                keys.setdefault(key, pk)
        return keys
    except Exception:
        logger.exception('crm: triage driver key map failed')
        return None


def promotable_phone(raw):
    """Digits we can actually hang a lead on, or ''.

    A sender id that never resolved past its @lid, or a stray '0' from the lid map,
    normalizes to something no human could ring back — those stay in the inbox.
    Same 8-13 digit window ``_driver_match_keys`` trusts as a real phone.
    """
    digits = crm_services.normalize_phone(raw)
    return digits if 8 <= len(digits) <= 13 else ''


def existing_board_record(phone, driver_keys=None):
    """Why this number must NOT be promoted again, or ''.

    Two things already own a card. A Lead in ANY stage — including a closed Won /
    Approved / Rejected one, which ``create_lead_from_wa_number`` would happily
    duplicate — and a driver application, whose card the driver board creates and
    maintains itself on every load via ``reconcile_driver_leads``.
    """
    normalized = crm_services.normalize_phone(phone)
    if not normalized:
        return 'no usable phone number'

    variants = crm_services._phone_variants(normalized)
    lead = (Lead.objects
            .filter(phone__in=variants, merged_into__isnull=True)
            .order_by('-created_at').first())
    if lead:
        return (f'lead #{lead.pk} already on the '
                f'{lead.get_category_display()} board ({lead.stage_label})')

    if driver_keys is None:
        driver_keys = driver_phone_keys()
    keys = crm_services._driver_match_keys(normalized)
    if keys:
        if driver_keys is None:
            # Unverified means unsafe: refuse rather than risk a second card.
            return 'driver lookup failed — left for a human'
        for key in keys:
            if key in driver_keys:
                return (f'driver application #{driver_keys[key]} exists — the driver '
                        f'board builds that card itself')
    return ''


def _unregistered_driver_stage():
    """The driver column meaning "no driver record matches this number yet".

    A WhatsApp enquiry is someone who has not filled the form at all. The board's
    fallback column is "Incomplete" — registered but never submitted — which reads
    as a half-finished application that does not exist. The column staff bound to
    the `no_driver` rule is the honest one, and it is where reconcile would put
    them the moment they do apply.
    """
    from crm import stage_rules
    for stage in crm_services.board_stages(Lead.CATEGORY_DRIVER):
        if stage_rules.RULE_NO_DRIVER in (stage.auto_rules or []):
            return stage.key
    return ''


def promote(phone, category, verdict, session='', from_number=''):
    """Create the lead and record how it was decided. Returns (lead, created).

    Also pins the card to the conversation it came from — the sender id and which
    of our numbers received it — so the detail page opens on the right thread
    instead of re-guessing from the phone number.
    """
    lead, created = crm_services.create_lead_from_wa_number(phone, None, category=category)
    if not created:
        return lead, False

    fields = []
    if category == Lead.CATEGORY_DRIVER:
        stage = _unregistered_driver_stage()
        if stage and stage != lead.stage:
            lead.stage = stage
            lead.stage_changed_at = timezone.now()
            fields += ['stage', 'stage_changed_at']

    sender = crm_services.normalize_phone(from_number)
    if sender and sender != crm_services.normalize_phone(phone):
        lead.wa_chat_override = sender[:50]
        fields.append('wa_chat_override')
    if session and not lead.wa_session:
        lead.wa_session = session[:64]
        fields.append('wa_session')

    # create_lead_from_wa_number copies the chat in by phone, which finds nothing
    # when the sender is only known by an @lid. We already have the transcript.
    if not (lead.notes or '').strip() and session and from_number:
        convo, _ = conversation_text(session, from_number, limit=8)
        if convo:
            lead.notes = f'Recent WhatsApp conversation:\n{convo}'[:4000]
            fields.append('notes')

    if fields:
        lead.save(update_fields=fields + ['updated_at'])

    crm_services._log_activity(
        lead, LeadActivity.TYPE_NOTE,
        'Filed on the {board} board automatically from the WhatsApp inbox '
        '(confidence {conf:.0%}) — {reason}. Triaged {when}.'.format(
            board=lead.get_category_display(),
            conf=verdict.get('confidence', 0.0),
            reason=verdict.get('reason') or 'no reason given',
            when=timezone.localtime().strftime('%d %b %Y %H:%M'),
        ),
    )
    return lead, True
