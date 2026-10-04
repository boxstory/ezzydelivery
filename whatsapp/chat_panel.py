"""
Purpose: Data for the WAHA inbox's right-hand panel — who a chat is, which CRM leads it belongs to, and its media by kind.
Used by: whatsapp/wa_chats_view.py (?info=1, ?media=1, ?lead_search=1, link-lead/)
Notes: Lead data is only returned to a Django staff login with CRM access; the page itself is only htpasswd-gated. Never creates a lead (2026-09-22 rule) — it only links a chat to an existing one.
"""
import logging
import re

from django.db.models import Count, Q
from django.urls import reverse

from .models import WhatsAppContact, WhatsAppMessage

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)

# Tab key -> filter over the chat's WhatsAppMessage rows. Voice notes and audio
# files are both stored as message_type='audio'; WhatsApp's own raw type 'ptt'
# ("push to talk") is what tells a voice note apart.
_PTT = Q(raw_payload___data__type='ptt') | Q(raw_payload__payload___data__type='ptt')
MEDIA_KINDS = {
    'photos': Q(message_type='image'),
    'videos': Q(message_type='video'),
    'files': Q(message_type='document'),
    'links': Q(body__iregex=r'https?://') & ~Q(message_type__in=['image', 'video', 'document', 'audio', 'location']),
    'voice': Q(message_type='audio') & _PTT,
    'audio': Q(message_type='audio') & ~_PTT,
}
MEDIA_PAGE = 60


def split_chat_id(chat_id):
    """('digits', 'lid'|'c.us'|'g.us'|other) for a WAHA chat id."""
    digits, _, suffix = str(chat_id or '').partition('@')
    return digits, suffix


def _chat_rows(session, chat_id):
    """Every stored message of this chat — same match the message pane uses."""
    digits, _ = split_chat_id(chat_id)
    return WhatsAppMessage.objects.filter(session=session).filter(
        Q(from_number=digits) | Q(to_number=digits)
    )


def chat_phone(session, chat_id):
    """Real phone digits behind a chat, or '' when unknown (groups, unmapped lids)."""
    digits, suffix = split_chat_id(chat_id)
    if suffix == 'c.us':
        return digits
    if suffix != 'lid':
        return ''
    contact = WhatsAppContact.objects.filter(session=session, lid=digits).exclude(phone='').first()
    if contact:
        return contact.phone
    try:
        from .wa_chats_view import _lid_map, _waha_base
        from django.conf import settings
        return _lid_map(_waha_base(), session, getattr(settings, 'WAHA_API_KEY', '') or '').get(digits, '')
    except Exception:
        logger.exception('chat panel: lid lookup failed for %s', chat_id)
        return ''


def chat_identity(session, chat_id):
    """Who a chat is: phone, lid, saved name and WhatsApp (push) name.

    Shared by the panel and the conversation header, so both name a chat the
    same way.
    """
    digits, suffix = split_chat_id(chat_id)
    phone = chat_phone(session, chat_id)
    contact = None
    if suffix == 'lid':
        contact = WhatsAppContact.objects.filter(session=session, lid=digits).first()
    if contact is None and phone:
        contact = WhatsAppContact.objects.filter(session=session, phone=phone).first()
    rows = _chat_rows(session, chat_id)
    push_name = (contact.push_name if contact else '') or (
        '' if suffix == 'g.us' else _push_name(session, chat_id, rows, phone)
    )
    return {
        'phone': phone,
        'lid': digits if suffix == 'lid' else (contact.lid if contact else ''),
        'saved_name': contact.saved_name if contact else '',
        'push_name': push_name,
    }


def chat_info(session, chat_id):
    digits, suffix = split_chat_id(chat_id)
    who = chat_identity(session, chat_id)
    rows = _chat_rows(session, chat_id)
    stats = rows.aggregate(total=Count('pk'), inbound=Count('pk', filter=Q(direction='inbound')))
    first = rows.exclude(received_at=None).order_by('received_at').values_list('received_at', flat=True).first()
    last = rows.exclude(received_at=None).order_by('-received_at').values_list('received_at', flat=True).first()
    return {
        'chat_id': chat_id,
        'kind': 'group' if suffix == 'g.us' else 'person',
        **who,
        'messages': stats['total'],
        'inbound': stats['inbound'],
        'first_at': int(first.timestamp()) if first else 0,
        'last_at': int(last.timestamp()) if last else 0,
    }


def _notify_name(payload):
    """The sender's WhatsApp name as carried on an inbound message ('' if none)."""
    p = payload if isinstance(payload, dict) else {}
    for src in (p.get('payload'), p):
        data = src.get('_data') if isinstance(src, dict) and isinstance(src.get('_data'), dict) else {}
        name = (data.get('notifyName') or '').strip()
        if name:
            return name[:100]
    return ''


def remember_push_name(session, chat_id, name, phone=''):
    """Save a WhatsApp name onto the contact directory so the next page load
    reads it from the DB instead of asking WhatsApp again.

    Never overwrites a name already there (the daily sync owns those). A lid
    chat can only get a new row when its phone is known — the directory is
    keyed by (session, phone).
    """
    if not name:
        return
    digits, suffix = split_chat_id(chat_id)
    lid = digits if suffix == 'lid' else ''
    phone = phone or (digits if suffix == 'c.us' else '')
    row = None
    if lid:
        row = WhatsAppContact.objects.filter(session=session, lid=lid).first()
    if row is None and phone:
        row = WhatsAppContact.objects.filter(session=session, phone=phone).first()
    try:
        if row is not None:
            fields = []
            if not row.push_name:
                row.push_name = name
                fields.append('push_name')
            if lid and not row.lid:
                row.lid = lid
                fields.append('lid')
            if fields:
                row.save(update_fields=fields + ['updated_at'])
        elif phone:
            WhatsAppContact.objects.get_or_create(
                session=session, phone=phone,
                defaults={'lid': lid, 'push_name': name},
            )
    except Exception:
        logger.exception('chat panel: could not save WhatsApp name for %s/%s', session, chat_id)


def _push_name(session, chat_id, rows, phone=''):
    """The name the person set in WhatsApp, for chats the contact directory
    does not have yet: from their newest message (every inbound one carries it
    as notifyName), else one WAHA contact lookup. Whatever is found is saved to
    the directory, so this only ever reaches WhatsApp once per contact.
    """
    for payload in rows.filter(direction='inbound').order_by('-received_at').values_list('raw_payload', flat=True)[:5]:
        name = _notify_name(payload)
        if name:
            remember_push_name(session, chat_id, name, phone)
            return name
    name = _live_push_name(session, chat_id)
    remember_push_name(session, chat_id, name, phone)
    return name


def push_names(session, chat_ids):
    """{chat_id: WhatsApp name} for many chats at once — the chat list's labels.

    Reads the contact directory; for chats it lacks, takes the name from each
    one's newest inbound message and saves it into the directory. Makes NO
    WhatsApp API calls — a chat with no stored name simply maps to ''.
    """
    from django.core.cache import cache
    from .wa_chats_view import _lid_cache_key

    ids = [c for c in dict.fromkeys(chat_ids) if split_chat_id(c)[1] in ('lid', 'c.us')][:200]
    out = {c: '' for c in ids}
    by_digits = {split_chat_id(c)[0]: c for c in ids}

    lids = [d for d, c in by_digits.items() if c.endswith('@lid')]
    phones = [d for d, c in by_digits.items() if c.endswith('@c.us')]
    for lid, phone, name in (
        WhatsAppContact.objects.filter(session=session)
        .filter(Q(lid__in=lids) | Q(phone__in=phones)).exclude(push_name='')
        .values_list('lid', 'phone', 'push_name')
    ):
        cid = by_digits.get(lid) if lid in lids else by_digits.get(phone)
        if cid and not out[cid]:
            out[cid] = name.strip()[:100]

    missing = [d for d, c in by_digits.items() if not out[c]]
    if missing:
        # lid -> phone from the already-cached WAHA map only; never fetched here.
        lid_phones = cache.get(_lid_cache_key(session)) or {}
        rows = (
            WhatsAppMessage.objects.filter(session=session, direction='inbound', from_number__in=missing)
            .order_by('from_number', '-received_at').distinct('from_number')
            .values_list('from_number', 'raw_payload')
        )
        for num, payload in rows:
            name = _notify_name(payload)
            if name:
                cid = by_digits[num]
                out[cid] = name
                remember_push_name(session, cid, name, lid_phones.get(num, '') if cid.endswith('@lid') else num)
    return out


def _live_push_name(session, chat_id):
    """WAHA's pushname for one chat, cached a day ('' cached too); '' on failure, not cached."""
    import requests
    from django.conf import settings
    from django.core.cache import cache

    try:
        resp = requests.get(
            f"{(getattr(settings, 'WAHA_BASE_URL', '') or '').rstrip('/')}/api/contacts",
            params={'contactId': chat_id, 'session': session},
            headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''},
            timeout=4,
        )
        if not (200 <= resp.status_code < 300):
            return ''
        name = ((resp.json() or {}).get('pushname') or '').strip()[:100]
    except Exception:
        return ''
    cache.set(f'wa_pushname:{session}:{chat_id}', name, 24 * 3600)
    return name


def media_counts(session, chat_id):
    rows = _chat_rows(session, chat_id)
    return rows.aggregate(**{k: Count('pk', filter=q) for k, q in MEDIA_KINDS.items()})


def media_items(session, chat_id, kind, offset=0):
    q = MEDIA_KINDS.get(kind)
    if q is None:
        return [], False
    rows = list(
        _chat_rows(session, chat_id).filter(q)
        .order_by('-received_at', '-pk')[offset:offset + MEDIA_PAGE + 1]
    )
    more = len(rows) > MEDIA_PAGE
    items = []
    for r in rows[:MEDIA_PAGE]:
        item = {
            'id': r.pk,
            'ts': int(r.received_at.timestamp()) if r.received_at else 0,
            'direction': r.direction,
            'caption': (r.body or '')[:300],
        }
        if kind == 'links':
            item['urls'] = _URL_RE.findall(r.body or '')[:5]
            item.pop('caption')
            item['text'] = (r.body or '')[:300]
        else:
            item['url'] = '/waha/wa-chats/media/%d/' % r.pk
            item['mime'] = r.media_mime or ''
            # False on a group file nobody has downloaded yet — the panel shows a
            # download tile instead of loading it.
            item['stored'] = bool(r.media_file)
            item['filename'] = _filename(r) if kind == 'files' else ''
            # A media message's body is often a base64 thumbnail, not a caption.
            if item['caption'] and ' ' not in item['caption'][:200]:
                item['caption'] = ''
        items.append(item)
    return items, more


def _filename(row):
    p = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    for src in (p.get('payload'), p):
        if not isinstance(src, dict):
            continue
        media = src.get('media') if isinstance(src.get('media'), dict) else {}
        data = src.get('_data') if isinstance(src.get('_data'), dict) else {}
        name = media.get('filename') or data.get('filename')
        if name:
            return str(name)[:120]
    return ''


# ---------------------------------------------------------------- CRM leads

def _lead_title(lead):
    return (lead.contact_name or lead.company_name or '').strip()[:100]


def lead_names(session, chat_ids):
    """{chat_id: connected lead's name} for many chats — the chat list's labels.

    Same two ways a lead belongs to a chat as connected_leads() (a linked
    number, or the lead's own phone ending in the chat's 8 digits), done in a
    couple of queries for the whole page instead of one per row. Only call it
    for a user who may see leads (can_see_leads).
    """
    from django.core.cache import cache
    from django.db.models import F, Func, Value
    from django.db.models.functions import Right

    from crm import services as crm_services
    from crm.models import Lead, LeadWaLink
    from .wa_chats_view import _lid_cache_key

    ids = [c for c in dict.fromkeys(chat_ids) if split_chat_id(c)[1] in ('lid', 'c.us')][:200]
    if not ids:
        return {}
    digits_of = {c: split_chat_id(c)[0] for c in ids}
    lids = [d for c, d in digits_of.items() if c.endswith('@lid')]
    lid_phone = dict(cache.get(_lid_cache_key(session)) or {})
    for lid, phone in (WhatsAppContact.objects.filter(session=session, lid__in=lids)
                       .exclude(phone='').values_list('lid', 'phone')):
        lid_phone[lid] = phone
    phone_of = {c: (d if c.endswith('@c.us') else lid_phone.get(d, '')) for c, d in digits_of.items()}

    # identifier -> chats it names. A lid is only ever itself — never run
    # through _phone_variants (that would invent a 974 number).
    by_ident = {}
    for c, d in digits_of.items():
        by_ident.setdefault(d, set()).add(c)
        if phone_of[c]:
            for v in crm_services._phone_variants(crm_services.normalize_phone(phone_of[c])):
                by_ident.setdefault(v, set()).add(c)
    by_last8 = {}
    for c, ph in phone_of.items():
        if len(ph) >= 8:
            by_last8.setdefault(ph[-8:], set()).add(c)

    found = {}  # chat -> lead (newest wins)

    def take(chats, lead):
        card = lead.merged_into if lead.merged_into_id else lead
        for c in chats:
            held = found.get(c)
            if held is None or card.updated_at > held.updated_at:
                found[c] = card

    base = Lead.objects.select_related('merged_into')
    for link in LeadWaLink.objects.filter(identifier__in=list(by_ident)).select_related('lead', 'lead__merged_into'):
        take(by_ident.get(link.identifier, ()), link.lead)
    for lead in base.filter(wa_chat_override__in=list(by_ident)):
        take(by_ident.get(lead.wa_chat_override, ()), lead)
    if by_last8:
        digits_only = Func(F('phone'), Value(r'\D'), Value(''), Value('g'), function='regexp_replace')
        for lead in (base.exclude(phone='').annotate(last8=Right(digits_only, 8))
                     .filter(last8__in=list(by_last8))):
            take(by_last8.get(lead.last8, ()), lead)
    return {c: _lead_title(l) for c, l in found.items() if _lead_title(l)}


def can_see_leads(user):
    from core.departments import can_access
    return bool(getattr(user, 'is_authenticated', False) and user.is_staff
                and can_access(user, 'crm_lead_detail'))


def can_link_leads(user):
    from core.departments import can_access
    return bool(getattr(user, 'is_authenticated', False) and user.is_staff
                and can_access(user, 'crm_lead_link_chat'))


def can_save_driver_docs(user):
    """Filing a chat photo onto a driver's documents is the documents desk's
    write, so it needs that right on top of working the lead."""
    from core.departments import can_access
    return can_link_leads(user) and can_access(user, 'driver_document_edit')


# ---------------------------------------------------------------- driver documents

# The driver application's own rule (core.views.join_driver): a selfie plus at
# least two of the ID documents.
DRIVER_DOC_TYPES = ['Selfie', 'QID', 'Passport', 'Driving License', 'Istimara']
DRIVER_IDS_REQUIRED = 2
# Side -> (image field, where a staff crop parked the pre-crop original).
DOC_SIDES = {
    'front': ('document_file', 'document_file_original'),
    'back': ('document_file_back', 'document_file_back_original'),
}
DOC_MAX_BYTES = 8 * 1024 * 1024  # DriverDocument's own image_validators(max_mb=8)
_PIL_EXT = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp'}


def _doc_rows(driver):
    """One row per document type: the one holding a real photo, else the newest."""
    rows = {}
    for doc in driver.driver_document.filter(document_type__in=DRIVER_DOC_TYPES).order_by('-updated_at', '-pk'):
        held = rows.get(doc.document_type)
        if held is None or (doc.has_real_file and not held.has_real_file):
            rows[doc.document_type] = doc
    return rows


def _file_url(f):
    try:
        return f.url if f and f.name else ''
    except ValueError:
        return ''


def driver_documents(driver):
    """The driver's documents as their profile holds them, against the application rule."""
    from django.utils import timezone

    today = timezone.localdate()
    rows = _doc_rows(driver)
    items = []
    for doc_type in DRIVER_DOC_TYPES:
        doc = rows.get(doc_type)
        front = _file_url(doc.document_file) if doc and doc.has_real_file else ''
        items.append({
            'type': doc_type,
            'required': doc_type == 'Selfie',
            'front': front,
            'back': _file_url(doc.document_file_back) if doc else '',
            'number': (doc.document_no or '') if doc else '',
            'expiry': doc.document_expiry_date.isoformat() if doc and doc.document_expiry_date else '',
            'expired': bool(doc and doc.document_expiry_date and doc.document_expiry_date < today),
            'url': reverse('workforce:driver_document_detail', args=[doc.pk]) if doc else '',
        })
    selfie = bool(items[0]['front'])
    ids = sum(1 for i in items[1:] if i['front'])
    return {
        'items': items,
        'selfie_ok': selfie,
        'ids_have': ids,
        'ids_need': DRIVER_IDS_REQUIRED,
        'complete': selfie and ids >= DRIVER_IDS_REQUIRED,
        'driver_url': reverse('workforce:driver_detail', args=[driver.pk]),
    }


def save_chat_photo_to_driver(lead, msg, doc_type, side, user):
    """File one chat photo onto the lead's driver as `doc_type` (`side` of it).

    Raises ValueError with an operator-facing reason. Replaces that side's photo
    only — the number, expiry and the other side stay as they were. A previous
    crop's parked original belonged to the old photo, so it is dropped.
    """
    import io

    from django.core.files.base import ContentFile
    from django.db import transaction
    from PIL import Image

    from crm.models import LeadActivity
    from fleet.models import DriverDocument

    if doc_type not in DRIVER_DOC_TYPES or side not in DOC_SIDES:
        raise ValueError('Unknown document type or side.')
    if msg.message_type != 'image':
        raise ValueError('Only a photo can be saved as a document.')
    if not msg.media_file:
        from .media_archive import archive_message_media
        try:
            archive_message_media(msg)
        except Exception:
            logger.exception('save doc: archive failed for msg %s', msg.pk)
    if not msg.media_file:
        raise ValueError('This photo is no longer available to save.')
    with msg.media_file.open('rb') as fh:
        data = fh.read(DOC_MAX_BYTES + 1)
    if len(data) > DOC_MAX_BYTES:
        raise ValueError('The photo is larger than 8 MB.')
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.verify()
    except Exception:
        raise ValueError('The file is not a readable image.')
    ext = _PIL_EXT.get(fmt)
    if not ext:
        raise ValueError('Only JPEG, PNG or WebP photos can be saved.')

    field, original = DOC_SIDES[side]
    with transaction.atomic():
        doc = _doc_rows(lead.driver).get(doc_type)
        if doc is None:
            doc = DriverDocument(driver=lead.driver, document_type=doc_type, document_no='')
        else:
            doc = DriverDocument.objects.select_for_update().get(pk=doc.pk)
        replaced = bool(doc.pk and (doc.has_real_file if side == 'front' else getattr(doc, field)))
        getattr(doc, field).save(f'{doc_type}{ext}', ContentFile(data), save=False)
        setattr(doc, original, None)
        doc.save()
        LeadActivity.objects.create(
            lead=lead, activity_type=LeadActivity.TYPE_NOTE,
            body=f'{"Replaced" if replaced else "Saved"} driver {doc_type}'
                 f'{" (back)" if side == "back" else ""} from a WhatsApp photo (message #{msg.pk})',
            created_by=user,
        )
    return doc


def _phone_regex(phone):
    """Postgres regex matching a free-text phone field ending in these 8 digits."""
    last8 = re.sub(r'\D', '', phone)[-8:]
    if len(last8) < 8:
        return None
    return r'\D*'.join(last8) + r'\D*$'


def _surviving(leads):
    """Swap absorbed (merged) cards for their parent and de-duplicate."""
    out, seen = [], set()
    for lead in leads:
        card = lead.merged_into if lead.merged_into_id else lead
        if card.pk not in seen:
            seen.add(card.pk)
            out.append(card)
    return out


def connected_leads(session, chat_id):
    """Leads whose conversation already includes this chat.

    Returns [(lead, how, label)] — how is 'phone' (the lead's own number is this
    chat's) or 'linked' (staff linked this number to the lead; `label` says who
    it is, e.g. Office). One chat can belong to a lead through either.
    """
    from crm.models import Lead, LeadWaLink
    from crm import services as crm_services

    digits, suffix = split_chat_id(chat_id)
    if suffix == 'g.us' or not digits:
        return []
    phone = chat_phone(session, chat_id)
    overrides = {digits}
    if phone:
        overrides |= crm_services._phone_variants(crm_services.normalize_phone(phone))

    base = Lead.objects.select_related('merged_into', 'assigned_to', 'converted_business', 'driver')
    found = {}
    labels = dict(
        LeadWaLink.objects.filter(identifier__in=list(overrides)).values_list('lead_id', 'label')
    )
    for lead in base.filter(Q(pk__in=list(labels)) | Q(wa_chat_override__in=list(overrides))):
        found[lead.pk] = (lead, 'linked', labels.get(lead.pk) or '')
    rx = _phone_regex(phone) if phone else None
    if rx:
        for lead in base.filter(phone__regex=rx):
            found.setdefault(lead.pk, (lead, 'phone', 'Primary'))
    meta_by_pk = {}
    for lead, how, label in found.values():
        card = lead.merged_into if lead.merged_into_id else lead
        meta_by_pk.setdefault(card.pk, (how, label))
    return [(card,) + meta_by_pk[card.pk] for card in _surviving([l for l, _, _ in found.values()])]


def suggested_leads(session, chat_id, chat_name='', exclude=()):
    """Unconnected leads whose contact/company name resembles this chat's name."""
    from crm.models import Lead

    digits, _ = split_chat_id(chat_id)
    names = {chat_name.strip()}
    contact = WhatsAppContact.objects.filter(session=session).filter(Q(lid=digits) | Q(phone=digits)).first()
    if contact:
        names |= {contact.saved_name.strip(), contact.push_name.strip()}
    names = {n for n in names if n and not n.lstrip('+').isdigit() and n.lower() != 'unknown number'}
    # A lone word ("Ahmed") matches half the board — only multi-word names suggest.
    names = {n for n in names if len([t for t in re.split(r'\W+', n) if len(t) >= 3]) >= 2}
    if not names:
        return []
    q = Q()
    for n in names:
        q |= Q(contact_name__icontains=n) | Q(company_name__icontains=n)
        tokens = [t for t in re.split(r'\W+', n) if len(t) >= 3]
        if len(tokens) >= 2:
            tq = Q()
            for t in tokens[:3]:
                tq &= Q(contact_name__icontains=t) | Q(company_name__icontains=t)
            q |= tq
    leads = Lead.objects.select_related('merged_into', 'assigned_to').filter(q).exclude(pk__in=list(exclude))
    return _surviving(leads.order_by('-updated_at')[:10])[:6]


def search_leads(term, limit=8):
    from crm.models import Lead

    term = (term or '').strip()
    if len(term) < 2:
        return []
    q = Q(contact_name__icontains=term) | Q(company_name__icontains=term)
    digits = re.sub(r'\D', '', term)
    if len(digits) >= 4:
        q |= Q(phone__regex=r'\D*'.join(digits[-8:]))
    if term.isdigit():
        q |= Q(pk=int(term))
    leads = Lead.objects.select_related('merged_into', 'assigned_to').filter(q).order_by('-updated_at')[:limit * 2]
    return _surviving(leads)[:limit]


def lead_dict(lead, how='', detail=False, stage_cache=None, label=''):
    d = {
        'id': lead.pk,
        'name': lead.contact_name or lead.company_name or f'Lead #{lead.pk}',
        'company': lead.company_name if lead.contact_name else '',
        'phone': lead.phone,
        'category': lead.get_category_display(),
        'stage': lead.stage_label,
        'swatch': lead.stage_swatch,
        'sources': ', '.join(b['label'] for b in lead.source_badges),
        'assigned': (lead.assigned_to.get_full_name() or lead.assigned_to.username) if lead.assigned_to_id else '',
        'followup': lead.next_followup_at.isoformat() if lead.next_followup_at else '',
        'created': lead.created_at.date().isoformat() if lead.created_at else '',
        'links': lead.wa_link_values,
        'how': how,
        'this_label': label,
        'url': reverse('workforce:crm_lead_detail', args=[lead.pk]),
    }
    if detail:
        d.update(_lead_detail(lead, stage_cache if stage_cache is not None else {}))
    return d


def _lead_detail(lead, stage_cache):
    """Extra fields + action URLs for a connected lead's working card.

    The actions post to the CRM's own endpoints (stage, follow-up/assignee,
    notes) so stage sync, driver write-back and activity logging stay in one
    place — the panel adds no second write path.
    """
    from django.utils import timezone
    from crm import services as crm_services
    from crm.models import Lead

    if lead.category not in stage_cache:
        stage_cache[lead.category] = [
            {'key': st.key, 'label': st.label, 'swatch': st.dot_swatch}
            for st in crm_services.board_stages(lead.category)
        ]
    today = timezone.localdate()
    acts = list(lead.activities.select_related('created_by').order_by('-created_at')[:4])
    since = lead.stage_changed_at or lead.created_at
    return {
        'category_key': lead.category,
        'stage_key': lead.stage,
        'stages': stage_cache[lead.category],
        'assigned_id': lead.assigned_to_id or '',
        'overdue': bool(lead.next_followup_at and lead.next_followup_at < today and lead.is_open),
        'is_open': lead.is_open,
        'stage_days': (timezone.now() - since).days if since else None,
        'age_days': (timezone.now() - lead.created_at).days if lead.created_at else None,
        'product': lead.product_category,
        'notes': (lead.notes or '')[:400],
        'ai_summary': (lead.ai_summary or '')[:500],
        'business': lead.converted_business.business_name if lead.converted_business_id else '',
        'driver': str(getattr(lead.driver, 'driver_id', '') or '') if lead.driver_id else '',
        'pinned': lead.stage_pinned,
        'docs': driver_documents(lead.driver)
                if lead.category == Lead.CATEGORY_DRIVER and lead.driver_id else None,
        'activity_count': lead.activities.count(),
        # Every number the lead talks from, labelled, with the account on it.
        'numbers': crm_services.lead_wa_numbers(lead),
        'activities': [{
            'type': a.get_activity_type_display(),
            'body': a.body[:240],
            'by': (a.created_by.get_full_name() or a.created_by.username) if a.created_by_id else 'System',
            'at': int(a.created_at.timestamp()),
        } for a in acts],
        'urls': {
            'stage': reverse('workforce:crm_lead_update_stage', args=[lead.pk]),
            'update': reverse('workforce:crm_lead_update', args=[lead.pk]),
            'note': reverse('workforce:crm_lead_add_activity', args=[lead.pk]),
        },
    }


def staff_options():
    from django.contrib.auth.models import User
    return [
        {'id': u.pk, 'name': u.get_full_name() or u.username}
        for u in User.objects.filter(is_staff=True, is_active=True).order_by('first_name', 'username')
    ]


def link_lead(lead, session, chat_id, user, label=''):
    """Add this chat's number to the lead's linked numbers. Returns the identifier.

    Stores the chat's own digits: a lid for @lid chats (lids are only readable
    on the number that issued them, which is the session the operator is on),
    the phone for @c.us chats. Adds — never replaces — so an owner's and an
    office's chat can both belong to one lead.
    """
    from crm.models import LeadActivity
    from crm import services as crm_services

    digits, _ = split_chat_id(chat_id)
    crm_services.add_wa_link(lead, digits, session=session, label=label, user=user)
    LeadActivity.objects.create(
        lead=lead, activity_type=LeadActivity.TYPE_NOTE,
        body=f'WhatsApp chat linked from the WAHA inbox ({session} · {chat_id}'
             + (f' · {label}' if label else '') + ')',
        created_by=user,
    )
    return digits


def unlink_lead(lead, session, chat_id, user):
    """Detach this chat's number from the lead — only when it is a linked one."""
    from crm.models import LeadActivity
    from crm import services as crm_services

    digits, _ = split_chat_id(chat_id)
    if digits not in lead.wa_link_values or not crm_services.remove_wa_link(lead, digits):
        return False
    LeadActivity.objects.create(
        lead=lead, activity_type=LeadActivity.TYPE_NOTE,
        body=f'WhatsApp chat unlinked from the WAHA inbox ({session} · {chat_id})',
        created_by=user,
    )
    return True
