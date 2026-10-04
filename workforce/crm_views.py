# Purpose: Staff-facing CRM views — leads kanban board, list, detail, manual create, stage/field updates, WAHA inbox, link-lead-to-business, reports.
# Used by: workforce/urls.py (crm/... routes); templates in workforce/templates/workforce/crm/.
# Notes: Business logic lives in crm/services.py; JSON endpoints mirror the pricing_inquiry_update_status fetch-POST pattern.

import json
import logging
import os
import re
import threading
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.db.models import (Case, Count, Exists, F, IntegerField, Max,
                              OuterRef, Q, Subquery, Value, When)
from django.db.models.functions import Coalesce, Lower, NullIf, TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from core.decorators import staff_required
from crm import services as crm_services
from crm import wa_inbox
from crm import contact_tags as crm_contact_tags
from crm.contact_tags import CONTACT_TAGS, strip_tags
from crm import stage_rules as crm_stage_rules
from crm.models import STAGE_CACHE_KEY, InboxDismissal, Lead, LeadActivity, LeadStage
from core.validators import safe_int
from workforce.sorting import apply_sort

logger = logging.getLogger(__name__)

# Anything outside this set is collapsed to a dash in a ZIP member name, so a
# driver called with a slash or a right-to-left mark in their name cannot shape
# the path the archive unpacks to.
_ZIP_UNSAFE = re.compile(r'[^A-Za-z0-9._-]+')

# Board columns are LeadStage rows managed by staff at /workforce/crm/stages/ —
# label, order, colour, terminal-ness, how long a closed card lingers, and (on the
# driver board) which applicant condition auto-files a card there. Nothing about
# the funnel is hardcoded here any more.


def _staff_users():
    return User.objects.filter(is_staff=True).order_by('first_name', 'username')


def _parse_followup_date(raw):
    """(date_or_None, error) from a YYYY-MM-DD form value. Empty input is a
    valid 'no date'; anything unparseable returns an error instead of letting
    the raw string reach the DateField and 500 on save."""
    from django.utils.dateparse import parse_date
    raw = (raw or '').strip()
    if not raw:
        return None, ''
    try:
        parsed = parse_date(raw)
    except ValueError:
        parsed = None
    if parsed is None:
        return None, 'Invalid follow-up date — use the YYYY-MM-DD format.'
    return parsed, ''


def _search_terms(search):
    """The search box split on commas, blanks dropped. A box with no comma is a
    single term, which is exactly today's behaviour."""
    return [term.strip() for term in (search or '').split(',') if term.strip()]


def _search_term_q(term):
    """One search term as a lookup across the fields the box covers.

    A term that is mostly digits is treated as a phone number and matched on its
    last 8 (the Qatar local part), so '+974 3312 3456', '97433123456' and
    '33123456' all find the same card whichever form the row was stored in.

    Every WhatsApp number a card can be reached on is covered, not just the one
    typed into the lead: the manually linked numbers (crm.LeadWaLink, its legacy
    single-value predecessor), and — for a driver applicant — the WhatsApp and
    phone numbers on the application itself. A driver who applied from one number
    and chats from another was unfindable by the number staff had in hand; the two
    disagree on 46 of the 821 linked driver cards.

    Matched as a subquery per relation rather than a join: `driver__` is to-one and
    safe either way, but a joined match on the reverse wa_links would return the
    same lead once per matching row.
    """
    digits = crm_services.normalize_phone(term)
    if len(digits) >= 7 and re.sub(r'[\s()+.\-]', '', term).isdigit():
        from crm.models import LeadWaLink
        tail = digits[-8:]
        return (
            Q(phone__endswith=tail) | Q(phone_2__endswith=tail) | Q(wa_chat_override__endswith=tail)
            | Q(pk__in=LeadWaLink.objects.filter(identifier__endswith=tail).values('lead_id'))
            | Q(driver__driver_whatsapp__endswith=tail)
            | Q(driver__driver_phone__endswith=tail)
        )
    # A non-numeric term is a name, so the driver's own name fields join the box:
    # a card raised before the applicant filled in their contact name carries the
    # name only on the application behind it.
    return (
        Q(company_name__icontains=term) |
        Q(contact_name__icontains=term) |
        Q(phone__icontains=term) |
        Q(phone_2__icontains=term) |
        Q(product_category__icontains=term) |
        Q(driver__driver_code__icontains=term) |
        Q(driver__user__first_name__icontains=term) |
        Q(driver__user__last_name__icontains=term)
    )


def _filtered_leads(request, multi_facets=False):
    """Shared filter logic for board + list.

    `multi_facets` switches the source and assignee facets from one value to a
    list: the picker on those bars is a checkbox multi-select, so ?source=a&
    source=b has to read as "either", not as the last value alone. The two
    returned facet values become lists in that mode — the templates that opt in
    compare with `in` instead of `==`. Every other caller keeps the single-value
    behaviour, and a lone ?source=x works identically either way."""
    # Absorbed duplicates never appear on their own — they render inside their parent.
    leads = (Lead.objects.select_related('assigned_to', 'converted_business')
             .filter(merged_into__isnull=True)
             .prefetch_related('merged_children'))

    search = request.GET.get('search', '').strip()
    if search:
        # Commas make the box a list, not one string: paste a column of numbers
        # from a sheet and get exactly those cards back. Each term is matched on
        # its own and the results are OR'd, so one unknown number in the paste
        # never empties the page.
        matches = Q()
        for term in _search_terms(search):
            matches |= _search_term_q(term)
        leads = leads.filter(matches)

    if multi_facets:
        source_filter = [v.strip() for v in request.GET.getlist('source') if v.strip()]
        if source_filter:
            leads = leads.filter(source__in=source_filter)
    else:
        source_filter = request.GET.get('source', '').strip()
        if source_filter:
            leads = leads.filter(source=source_filter)

    category_filter = request.GET.get('category', '').strip()
    if category_filter in {c for c, _ in Lead.CATEGORY_CHOICES}:
        leads = leads.filter(category=category_filter)

    if multi_facets:
        assigned_filter = [v.strip() for v in request.GET.getlist('assigned') if v.strip()]
        # OR'd, not chained: two filters AND'd together would ask for a lead that
        # is both mine and unassigned, which is nothing.
        picks = Q()
        matched = False
        for value in assigned_filter:
            if value == 'me':
                picks |= Q(assigned_to=request.user)
            elif value == 'none':
                picks |= Q(assigned_to__isnull=True)
            else:
                try:
                    picks |= Q(assigned_to_id=int(value))
                except ValueError:
                    continue
            matched = True
        if matched:
            leads = leads.filter(picks)
        return leads, search, source_filter, assigned_filter, category_filter

    assigned_filter = request.GET.get('assigned', '').strip()
    if assigned_filter == 'me':
        leads = leads.filter(assigned_to=request.user)
    elif assigned_filter == 'none':
        leads = leads.filter(assigned_to__isnull=True)
    elif assigned_filter:
        try:
            leads = leads.filter(assigned_to_id=int(assigned_filter))
        except ValueError:
            pass

    return leads, search, source_filter, assigned_filter, category_filter


def _annotate_wa_chats(leads):
    """Bulk-set lead.has_wa_chat for leads whose phone has WhatsApp messages
    on record. Matches every identifier form the store may hold: bare digits
    with/without the 974 country code, @c.us JIDs, and anonymized @lid JIDs
    resolved via the synced WhatsAppContact directory. Three queries total.

    Deliberately spans every WAHA session: a lead counts as "has chat" whether
    they messaged our ops number or our marketing one. LID identifiers are the
    exception — a lid only means something relative to the session that issued
    it, so those are matched as (session, lid) pairs."""
    ident_map = {}   # message identifier -> [lead, ...]  (phone-based, session-independent)
    lid_map = {}     # (session, lid identifier) -> [lead, ...]
    phone_map = {}   # bare digit variant -> [lead, ...] (for lid lookup)
    from django.db.models import prefetch_related_objects
    leads = list(leads)
    prefetch_related_objects(leads, 'wa_links')
    for lead in leads:
        lead.has_wa_chat = False
        phone = crm_services.normalize_phone(lead.phone)
        variants = set()
        if phone:
            variants |= crm_services._phone_variants(phone)
        for override in [crm_services.normalize_phone(v) for v in lead.wa_link_values]:
            if not override:
                continue
            variants.add(override)
            # Only expand it as a phone when it is one: a lid's last 8 digits
            # make a plausible 974 number that belongs to somebody else.
            if not crm_services.is_lid_value(override):
                variants |= crm_services._phone_variants(override)
            # A manual override is an operator asserting "this identifier is
            # this lead" — honour it on any session.
            ident_map.setdefault(f'{override}@lid', []).append(lead)
        if not variants:
            continue
        for p in variants:
            phone_map.setdefault(p, []).append(lead)
            ident_map.setdefault(p, []).append(lead)
            ident_map.setdefault(f'{p}@c.us', []).append(lead)
    if not ident_map:
        return
    try:
        from whatsapp.models import WhatsAppContact, WhatsAppMessage
        lid_rows = (
            WhatsAppContact.objects
            .filter(phone__in=list(phone_map))
            .exclude(lid='')
            .values_list('session', 'lid', 'phone')
        )
        for sess, lid, phone in lid_rows:
            for ident in (lid, f'{lid}@lid'):
                lid_map.setdefault((sess, ident), []).extend(phone_map[phone])
        idents = list(ident_map) + [ident for _s, ident in lid_map]
        hits = set(
            WhatsAppMessage.objects.filter(from_number__in=idents)
            .values_list('session', 'from_number').distinct()
        ) | set(
            WhatsAppMessage.objects.filter(to_number__in=idents)
            .values_list('session', 'to_number').distinct()
        )
        for sess, ident in hits:
            for lead in ident_map.get(ident, ()):
                lead.has_wa_chat = True
            for lead in lid_map.get((sess, ident), ()):
                lead.has_wa_chat = True
    except Exception:
        logger.exception('crm: WA chat annotation failed')


# ── Vehicle facet (driver list) ─────────────────────────────────────────
# 'none' is the model's own "not stated" placeholder and never reads as a vehicle,
# so it is dropped from the options and its value reused for the question a
# recruiter actually asks: which applicants have no vehicle on file at all.
def _vehicle_labels():
    """Display names shared by the row's vehicle chip and the facet that filters on
    it. The two long names get a short form: the chip is a nowrap band on a narrow
    kanban card and the facet sits in a fixed-width track, so neither reads in full
    at the model's own wording."""
    from fleet.models import VEHICLE_CHOICES

    labels = dict(VEHICLE_CHOICES)
    labels.update({'pickup3ton': 'Pickup 3T', 'pickup_big': 'Pickup Big'})
    return labels


def _vehicle_filter_choices():
    from fleet.models import VEHICLE_CHOICES

    labels = _vehicle_labels()
    return [(key, labels[key]) for key, _label in VEHICLE_CHOICES if key != 'none']


def _apply_vehicle_filter(leads, vehicle_filter):
    """Narrow driver leads to the vehicle their application registered.

    `vehicle_filter` is a list of ticks — the facet is a checkbox multi-select on
    every page that offers it, and a recruiter reads "Bike + Car" as one pool, so
    the ticks are OR'd rather than forcing a second trip through the bar.

    Resolves to the SAME row the vehicle chip and the map pin show — newest
    registration wins — so filtering by Bike can never leave a lead labelled Car
    on the page. Values that are not vehicles are dropped: one typo in a
    hand-edited URL narrows nothing rather than emptying the page.
    """
    from fleet.models import DriverVehicle

    real_types = [key for key, _label in _vehicle_filter_choices()]
    # 'none' is not a vehicle, it is the absence of one, so it rides separately.
    picked = [v for v in vehicle_filter if v in real_types]
    want_none = 'none' in vehicle_filter
    if not picked and not want_none:
        return leads

    newest_vehicle = (DriverVehicle.objects
                      .filter(driver_id=OuterRef('driver_id'))
                      .exclude(vehicle_type='')
                      .exclude(vehicle_type='none')
                      .order_by('-created_at')
                      .values('vehicle_type')[:1])
    leads = leads.annotate(current_vehicle=Subquery(newest_vehicle))

    vehicle_q = Q(current_vehicle__in=picked) if picked else Q()
    if want_none:
        # No application bound to the card yet, or one carrying no usable vehicle
        # row — both read as "vehicle unknown" wherever the lead is drawn.
        vehicle_q |= Q(current_vehicle__isnull=True)
    return leads.filter(vehicle_q)


def _annotate_driver_vehicles(leads):
    """Bulk-set lead.vehicle_type / lead.vehicle_label for driver leads.

    Why: the card's driver chip used a fixed motorcycle icon for everyone, so a
    desk scanning the recruitment pipeline could not tell a car applicant from a
    bike one. One query for the whole page; leads with no application bound yet
    keep the generic chip.
    """
    from fleet.models import DriverVehicle

    labels = _vehicle_labels()
    driver_ids = {
        lead.driver_id for lead in leads
        if lead.category == Lead.CATEGORY_DRIVER and lead.driver_id
    }
    by_driver = {}
    if driver_ids:
        # Newest row wins: a driver who re-registered on a different vehicle is
        # shown as what they drive now, not what they first applied with.
        rows = (DriverVehicle.objects
                .filter(driver_id__in=driver_ids)
                .exclude(vehicle_type='')
                .exclude(vehicle_type='none')
                .order_by('driver_id', '-created_at')
                .values_list('driver_id', 'vehicle_type'))
        for driver_id, vehicle_type in rows:
            by_driver.setdefault(driver_id, vehicle_type)

    for lead in leads:
        vehicle_type = by_driver.get(getattr(lead, 'driver_id', None), '')
        lead.vehicle_type = vehicle_type
        lead.vehicle_label = labels.get(vehicle_type, '')


# ── Application facets (driver board) ───────────────────────────────────
# Everything a recruiter knows about an applicant beyond the card itself lives on
# the driver application behind it (fleet.Driver), so these facets all reach
# through Lead.driver. They deliberately reuse the keys, labels and semantics of
# the driver verification queue's bar (workforce.views._apply_driver_filters): a
# recruiter who filters "Part Time" there and here must get the same pool, and a
# URL is readable between the two pages.
#
# 'none' on a facet means "nothing recorded" — a card with no application bound
# yet, or one whose application left that question blank. It is offered because it
# is the question a recruiter actually asks (who still has to be chased), and it
# is never a value the applicant could have chosen.
DRIVER_FACET_NONE = 'none'

# Uploaded-documents state. The completeness rule is the public application's own
# (workforce.views._driver_application_sections): a selfie plus two distinct ID
# documents, each holding a real uploaded image rather than the placeholder the
# model ships with or a row carrying only a typed document number.
# Labels are one word because the facet track is a fixed 8.25rem and the control
# shows the chosen option's own label — "Docs complete" rendered as "Docs co…".
# What they are about is carried by the placeholder ("Any documents") and by the
# chip, which prints the facet name beside the value ("DOCUMENTS · Complete").
DOC_STATE_CHOICES = [
    ('complete', 'Complete'),
    ('partial', 'Partial'),
    ('none', 'Missing'),
]
DOC_ID_TYPES_REQUIRED = 2


def _job_type_choices():
    from fleet.models import DRIVER_JOB_TYPE_CHOICES

    return list(DRIVER_JOB_TYPE_CHOICES)


def _slab_choices():
    """Working-hours slabs, shortened. The model's labels carry the clock range
    ('Morning (6 AM – 12 PM)'), which a fixed-width facet track cannot show."""
    from fleet.models import WORK_TIME_SLAB_CHOICES

    return [(key, label.split(' (')[0]) for key, label in WORK_TIME_SLAB_CHOICES]


def _language_choices():
    from fleet.models import Driver

    return list(Driver.driver_languages_choices)


def _zone_group_choices():
    from delivery.models import ZoneGroup

    return [(str(pk), name) for pk, name in
            ZoneGroup.objects.filter(is_active=True).order_by('name').values_list('pk', 'name')]


def _driver_facet_picks(request, zone_choices):
    """The application facets as ticked on the bar, unknown values dropped.

    One typo in a hand-edited URL narrows nothing rather than emptying the page —
    the same contract the vehicle facet and the sort whitelist keep.

    `zone_choices` is passed in rather than fetched: it is the one choice list that
    costs a query, and the bar needs it three times per load (validating the ticks
    here, labelling the chips, filling the select).
    """
    def chosen(param, valid):
        allowed = set(valid) | {DRIVER_FACET_NONE}
        return [v for v in request.GET.getlist(param) if v in allowed]

    return {
        'job': chosen('job', dict(_job_type_choices())),
        'docs': [v for v in request.GET.getlist('docs') if v in dict(DOC_STATE_CHOICES)],
        'slab': chosen('slab', dict(_slab_choices())),
        'language': chosen('language', dict(_language_choices())),
        'zone': chosen('zone', dict(zone_choices)),
    }


def _doc_state_annotations():
    """The three reads the documents facet needs, as annotations on a Lead qs.

    Kept in one place because the chip, the filter and any later readout must
    agree on what "complete" means. Subqueries rather than joins: a driver holds
    up to five document rows, and a joined count would multiply the lead.
    """
    from django.db.models import Count
    from fleet.models import DriverDocument, docs_with_image

    real = docs_with_image(DriverDocument.objects.filter(driver_id=OuterRef('driver_id')))
    ids = (real.exclude(document_type='Selfie')
           .values('driver_id')
           .annotate(n=Count('document_type', distinct=True))
           .values('n')[:1])
    return {
        'doc_has_selfie': Exists(real.filter(document_type='Selfie')),
        'doc_has_any': Exists(real),
        # Coalesced: no matching row at all makes the subquery NULL, and NULL >= 2
        # is NULL, so an applicant with no documents would fall out of every
        # bucket instead of landing in "No docs".
        'doc_id_types': Coalesce(Subquery(ids, output_field=IntegerField()), Value(0)),
    }


def _apply_driver_facets(leads, picks):
    """Narrow driver leads by the application behind the card.

    Ticks within one facet are OR'd ("Full Time + Part Time" is one pool) and the
    facets are AND'd with each other, which is how every other staff bar reads.

    Returns (leads, needs_distinct). Preferred zones are a reverse many-to-many,
    so a driver who picked three zones would otherwise put three copies of the
    same card on the board; the caller applies the distinct.
    """
    needs_distinct = False

    job = picks['job']
    if job:
        named = [v for v in job if v != DRIVER_FACET_NONE]
        job_q = Q(driver__job_type__in=named) if named else Q()
        if DRIVER_FACET_NONE in job:
            # No application bound to the card yet, or one that left the question
            # blank — both read as "job type not stated" to a recruiter.
            job_q |= Q(driver__isnull=True) | Q(driver__job_type='')
        leads = leads.filter(job_q)

    docs = picks['docs']
    if docs:
        leads = leads.annotate(**_doc_state_annotations())
        complete = Q(doc_has_selfie=True, doc_id_types__gte=DOC_ID_TYPES_REQUIRED)
        docs_q = Q()
        if 'complete' in docs:
            docs_q |= complete
        if 'partial' in docs:
            # Something was uploaded but the set is short of the application's bar.
            docs_q |= Q(doc_has_any=True) & ~complete
        if 'none' in docs:
            docs_q |= Q(doc_has_any=False)
        leads = leads.filter(docs_q)

    slab = picks['slab']
    if slab:
        # Stored as a comma-joined list of slab keys. The keys never substring into
        # one another, so icontains per key is safe.
        named = [v for v in slab if v != DRIVER_FACET_NONE]
        slab_q = Q()
        for key in named:
            slab_q |= Q(driver__work_time_slabs__icontains=key)
        if DRIVER_FACET_NONE in slab:
            slab_q |= Q(driver__isnull=True) | Q(driver__work_time_slabs='')
        leads = leads.filter(slab_q)

    language = picks['language']
    if language:
        named = [v for v in language if v != DRIVER_FACET_NONE]
        lang_q = Q(driver__driver_languages__in=named) if named else Q()
        if DRIVER_FACET_NONE in language:
            lang_q |= Q(driver__isnull=True) | Q(driver__driver_languages='')
        leads = leads.filter(lang_q)

    zone = picks['zone']
    if zone:
        named = [int(v) for v in zone if v != DRIVER_FACET_NONE]
        zone_q = Q(driver__preferred_zone_groups__id__in=named) if named else Q()
        if DRIVER_FACET_NONE in zone:
            zone_q |= Q(driver__isnull=True) | Q(driver__preferred_zone_groups__isnull=True)
        leads = leads.filter(zone_q)
        needs_distinct = True

    return leads, needs_distinct


def _driver_facet_chip_specs(zone_choices):
    """(param, chip label, {value: display}, label for 'none') per application
    facet, for the removable chips on the right of the bar. Built from the same
    choice lists the selects render from, so a chip can never name a value the bar
    cannot show."""
    return [
        ('job', 'Job type', dict(_job_type_choices()), 'Not stated'),
        ('docs', 'Documents', dict(DOC_STATE_CHOICES), ''),
        ('slab', 'Hours', dict(_slab_choices()), 'Any time'),
        ('language', 'Language', dict(_language_choices()), 'Not stated'),
        ('zone', 'Zone', dict(zone_choices), 'No zone'),
    ]


def _render_leads_board(request, board_category, template):
    """Shared kanban builder behind the two board pages. The business sales pipeline
    and the driver recruitment pipeline are separate pages with their own URL, their
    own columns and their own help notes — this only assembles what they share."""
    # Every facet on this bar is a checkbox multi-select, the same as the tables:
    # "Manual + WhatsApp Inbound" is one pool, not two trips through the bar.
    leads, search, source_filter, assigned_filter, category_filter = _filtered_leads(
        request, multi_facets=True)
    leads = leads.filter(category=board_category)

    is_driver_board = board_category == Lead.CATEGORY_DRIVER

    # Vehicle is a recruitment question, so the facet exists only on the driver
    # board — a business lead has no application behind it to carry one.
    vehicle_filter = []
    driver_picks = {key: [] for key in ('job', 'docs', 'slab', 'language', 'zone')}
    zone_choices = _zone_group_choices() if is_driver_board else []
    if is_driver_board:
        vehicle_filter = [v.strip() for v in request.GET.getlist('vehicle') if v.strip()]
        leads = _apply_vehicle_filter(leads, vehicle_filter)

        # The rest of the application: job type, uploaded documents, working
        # hours, language, preferred zone. Same keys and meanings as the driver
        # verification queue's bar, so a URL reads the same on both pages.
        driver_picks = _driver_facet_picks(request, zone_choices)
        leads, needs_distinct = _apply_driver_facets(leads, driver_picks)
        if needs_distinct:
            leads = leads.distinct()

    # When the card was raised — a preset is one pick, so this facet is a single
    # select rather than a checklist.
    date_preset, date_from, date_to = _date_filter(request)
    leads = _apply_date_filter(leads, date_from, date_to)

    # Driver board mirrors the real applicant pool: ensure a card exists for every
    # driver application and each card's stage matches the driver's form status.
    if is_driver_board:
        try:
            crm_services.reconcile_driver_leads()
        except Exception:
            logger.exception('crm: driver lead reconcile failed')

    stage_rows = crm_services.board_stages(board_category)

    # Each terminal column decides for itself how long a closed card lingers
    # (hide_after_days); a blank one never ages a card out. Leads whose stage has
    # no column any more are always kept — they surface in the Unsorted lane.
    now = timezone.now()
    hide_map = {s.key: s.hide_after_days for s in stage_rows if s.hide_after_days}
    keep = Q(closed_at__isnull=True) | ~Q(stage__in=list(hide_map))
    for key, days in hide_map.items():
        keep |= Q(stage=key, closed_at__gte=now - timedelta(days=days))
    leads = list(leads.filter(keep).order_by('-created_at'))
    _annotate_wa_chats(leads)
    _annotate_driver_vehicles(leads)

    by_stage = {s.key: [] for s in stage_rows}
    for lead in leads:
        by_stage.setdefault(lead.stage, []).append(lead)

    # Once the first terminal column is reached the funnel is over — everything
    # from there on renders as a parked "bay" (no chevron, muted title) instead of
    # a flowing stage. Derived from the data so a new column styles itself.
    columns, in_bays = [], False
    for index, stage in enumerate(stage_rows):
        bucket = by_stage[stage.key]
        bay_start = stage.is_closed and not in_bays
        in_bays = in_bays or stage.is_closed
        columns.append({
            'key': stage.key,
            'label': stage.label,
            'leads': bucket,
            'count': len(bucket),
            'overdue': sum(1 for lead in bucket if lead.is_overdue),
            'swatch': stage.dot_swatch,
            'is_closed': stage.is_closed,
            'outcome': stage.outcome,
            'is_manual': stage.is_manual,
            'confirm_text': stage.confirm_text,
            'needs_reason': stage.needs_reason,
            'droppable': True,
            'is_first': index == 0,
            'in_bays': in_bays,
            'bay_start': bay_start,
        })

    # Cards stranded by a deleted or deactivated column — visible and draggable
    # out, never a drop target, so nothing silently disappears from the board.
    known = {s.key for s in stage_rows}
    orphans = [lead for lead in leads if lead.stage not in known]
    if orphans:
        columns.append({
            'key': '', 'label': 'Unsorted', 'leads': orphans, 'count': len(orphans),
            'overdue': sum(1 for lead in orphans if lead.is_overdue),
            'swatch': 'grey', 'is_closed': False, 'outcome': '', 'is_manual': True,
            'confirm_text': '', 'needs_reason': False, 'droppable': False,
            'is_first': not columns, 'in_bays': True, 'bay_start': False,
        })

    closed_keys = crm_services.closed_stage_keys(board_category)
    open_total = sum(c['count'] for c in columns if c['key'] not in closed_keys)
    overdue_total = sum(c['overdue'] for c in columns)

    # A kanban hides the effect of a filter — cards just quietly stop appearing.
    # The scope line under the controls says out loud how much of the board is on
    # screen, and each engaged filter gets a chip that carries its own removal URL.
    staff_users = _staff_users()
    board_total = sum(c['count'] for c in columns)
    driver_picks_on = any(driver_picks.values())
    filters_on = bool(search or source_filter or assigned_filter or vehicle_filter
                      or driver_picks_on or date_from or date_to)
    board_grand_total = board_total
    if filters_on:
        board_grand_total = (Lead.objects
                             .filter(merged_into__isnull=True, category=board_category)
                             .filter(keep).count())

    def _chip(param, label, display, tick=None):
        """One removable chip. `tick` drops just that value and leaves the facet's
        other ticks alone — with multi-selects a chip that cleared the whole param
        would throw away picks the staffer never pointed at. `param` may be several
        names, for a facet that spans more than one (the date range is a preset
        plus its two ends)."""
        params = request.GET.copy()
        names = [param] if isinstance(param, str) else list(param)
        if tick is None:
            for name in names:
                params.pop(name, None)
        else:
            params.setlist(names[0], [v for v in params.getlist(names[0]) if v != tick])
        query = params.urlencode()
        return {
            'label': label,
            'value': display,
            'remove_url': f'{request.path}?{query}' if query else request.path,
        }

    active_filters = []
    if search:
        active_filters.append(_chip('search', 'Search', search))

    source_labels = dict(Lead.SOURCE_CHOICES)
    for value in source_filter:
        active_filters.append(_chip('source', 'Source', source_labels.get(value, value), value))

    for value in assigned_filter:
        if value == 'me':
            assigned_label = 'Assigned to me'
        elif value == 'none':
            assigned_label = 'Unassigned'
        else:
            match = next((u for u in staff_users if str(u.pk) == value), None)
            assigned_label = (match.get_full_name() or match.username) if match else 'Assignee'
        active_filters.append(_chip('assigned', 'Assignee', assigned_label, value))

    vehicle_labels = dict(_vehicle_filter_choices())
    for value in vehicle_filter:
        active_filters.append(_chip(
            'vehicle', 'Vehicle', vehicle_labels.get(value, 'No vehicle'), value))

    # One chip per tick on the application facets, each dropping only its own tick.
    for param, chip_label, value_labels, none_label in _driver_facet_chip_specs(zone_choices):
        for value in driver_picks[param]:
            display = value_labels.get(value) or none_label or value
            active_filters.append(_chip(param, chip_label, display, value))

    if date_from or date_to:
        active_filters.append(_chip(
            ('datePreset', 'dateFrom', 'dateTo'), 'Created',
            _date_filter_label(date_preset, date_from, date_to)))

    # Headline outcome metric = the column this board calls a win (Won / Approved),
    # falling back to its leftmost terminal column if none declares an outcome.
    outcome = (next((c for c in columns if c.get('outcome') == 'won'), None)
               or next((c for c in columns if c['is_closed']), None))
    window_days = max(hide_map.values()) if hide_map else None

    context = {
        'page_title': 'Driver Leads Board' if is_driver_board else 'Leads Board',
        'board_category': board_category,
        'is_driver_board': is_driver_board,
        'columns': columns,
        'open_total': open_total,
        'overdue_total': overdue_total,
        'outcome_total': outcome['count'] if outcome else 0,
        'outcome_label': outcome['label'] if outcome else 'Closed',
        'search': search,
        'source_filter': source_filter,
        'assigned_filter': assigned_filter,
        'vehicle_filter': vehicle_filter,
        'vehicle_choices': _vehicle_filter_choices(),
        'date_preset': date_preset,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to else '',
        'date_preset_choices': DATE_PRESET_CHOICES,
        'category_filter': category_filter,
        'staff_users': staff_users,
        'source_choices': Lead.SOURCE_CHOICES,
        'category_choices': Lead.CATEGORY_CHOICES,
        # Application facets — only the driver board renders these, so the choice
        # lists are built only for that board (each is a query or an import).
        'driver_picks': driver_picks,
        'job_choices': _job_type_choices() if is_driver_board else [],
        'doc_state_choices': DOC_STATE_CHOICES if is_driver_board else [],
        'slab_choices': _slab_choices() if is_driver_board else [],
        'language_choices': _language_choices() if is_driver_board else [],
        'zone_choices': zone_choices,
        'closed_window_days': window_days,
        'today': timezone.localdate(),
        'board_total': board_total,
        'board_grand_total': board_grand_total,
        'column_total': len(columns),
        'filters_on': filters_on,
        'active_filters': active_filters,
    }
    return render(request, template, context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_board(request):
    """Business sales pipeline board."""
    return _render_leads_board(
        request, Lead.CATEGORY_BUSINESS, 'workforce/crm/leads_board.html')


@login_required(login_url='/accounts/login/')
@staff_required
def crm_driver_leads_board(request):
    """Driver recruitment pipeline board — its own page, not a tab of the business one."""
    return _render_leads_board(
        request, Lead.CATEGORY_DRIVER, 'workforce/crm/driver_leads_board.html')


# ── Created-date facet ──────────────────────────────────────────────
# Keys, labels and arithmetic are the shared staff-list ones (workforce.views.
# _resolve_print_label_dates and pgApplyPreset in workforce.js), so "Last 7 days"
# spans the same week here as on every other bar in the dashboard. Param names
# match them too: a URL copied between bars keeps meaning what it said.
DATE_PRESET_CHOICES = [
    ('today', 'Today'),
    ('yesterday', 'Yesterday'),
    ('3days', 'Last 3 days'),
    ('week', 'Last 7 days'),
    ('month', 'Last 30 days'),
    ('custom', 'Custom'),
]

# Days back from today, inclusive of today.
DATE_PRESET_SPANS = {'today': 0, '3days': 2, 'week': 6, 'month': 29}


def _parse_crm_date(raw):
    from datetime import date as _date

    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        return _date.fromisoformat(raw)
    except ValueError:
        return None


def _date_filter(request):
    """(preset, date_from, date_to) for the Created facet.

    A preset always resolves to the range it names: the dates on the URL are read
    only for 'custom', so a stale or hand-edited ?dateFrom= can never disagree
    with the option the bar is showing as selected. An unknown preset, or a custom
    range with neither end filled in, narrows nothing.

    Dates are Qatar dates — settings.TIME_ZONE is Asia/Qatar, so localdate() and
    the __date lookup below both read in the timezone the desk works in, not UTC.
    """
    preset = request.GET.get('datePreset', '').strip()

    if preset == 'custom':
        return (preset,
                _parse_crm_date(request.GET.get('dateFrom')),
                _parse_crm_date(request.GET.get('dateTo')))

    today = timezone.localdate()
    if preset == 'yesterday':
        day = today - timedelta(days=1)
        return preset, day, day
    if preset in DATE_PRESET_SPANS:
        return preset, today - timedelta(days=DATE_PRESET_SPANS[preset]), today
    return '', None, None


def _apply_date_filter(leads, date_from, date_to):
    """Narrow to cards raised inside the range, either end on its own being valid."""
    if date_from:
        leads = leads.filter(created_at__date__gte=date_from)
    if date_to:
        leads = leads.filter(created_at__date__lte=date_to)
    return leads


def _date_filter_label(preset, date_from, date_to):
    """What the applied-filter chip says. A custom range prints its own dates so
    the chip is readable without opening the picker."""
    if preset != 'custom':
        return dict(DATE_PRESET_CHOICES).get(preset, '')
    if date_from and date_to:
        return f'{date_from:%d %b} – {date_to:%d %b %Y}'
    if date_from:
        return f'From {date_from:%d %b %Y}'
    if date_to:
        return f'Until {date_to:%d %b %Y}'
    return 'Custom range'


def _facet_params(pairs):
    """Query string for a bar whose facets are multi-selects.

    urlencode on a dict would write ?stage=%5B%27new%27%5D for a list; every tick
    needs its own ?stage= so the link a sort header or a page button writes reads
    back as the same filter. Empty values and empty lists write nothing.
    """
    from urllib.parse import urlencode

    out = []
    for key, value in pairs:
        if isinstance(value, (list, tuple)):
            out.extend((key, item) for item in value if item)
        elif value:
            out.append((key, value))
    return urlencode(out)


def _render_leads_list(request, list_category):
    """Shared table builder behind the two list pages. The category is fixed by the
    URL, not by a tab — a business page never shows driver applicants and vice versa."""
    from workforce.views import paginate_queryset

    # Every facet on this bar is a checkbox multi-select, so each one reads its
    # ticks with getlist — including the two the shared helper owns. A URL
    # carrying a single ?source=x still reads identically.
    leads, search, source_filter, assigned_filter, _category_filter = _filtered_leads(
        request, multi_facets=True)
    category_filter = list_category
    leads = leads.filter(category=list_category)

    # Applied whenever one is given, not only when it matches a configured column:
    # an unrecognised stage falling through would show every lead, which reads as
    # "the filter did nothing".
    stage_filter = [v.strip() for v in request.GET.getlist('stage') if v.strip()]
    if stage_filter:
        leads = leads.filter(stage__in=stage_filter)

    overdue_filter = request.GET.get('overdue', '').strip()
    if overdue_filter == '1':
        leads = leads.filter(
            next_followup_at__lt=timezone.localdate()
        ).exclude(stage__in=crm_services.closed_stage_keys())

    # Vehicle is a recruitment question, so the facet only exists on the driver
    # page — a business lead has no application to carry one.
    vehicle_filter = []
    if list_category == Lead.CATEGORY_DRIVER:
        vehicle_filter = [v.strip() for v in request.GET.getlist('vehicle') if v.strip()]
        leads = _apply_vehicle_filter(leads, vehicle_filter)

    # When the card was raised. A preset is one pick, never several — "Today and
    # Last 30 days" is just Last 30 days — so this facet stays a single select.
    date_preset, date_from, date_to = _date_filter(request)
    leads = _apply_date_filter(leads, date_from, date_to)

    # Stage columns are this board's own, and they are needed twice: to rank a
    # stage sort in board order and to fill the stage filter below.
    stage_rows = crm_services.board_stages(list_category)

    # Column sorting. The whitelist is this page's contract with the URL — a
    # ?sort= naming anything else quietly falls back to newest-first.
    lead_name = Lower(Coalesce(
        NullIf('company_name', Value('')),
        NullIf('contact_name', Value('')),
        NullIf('phone', Value('')),
    ))
    leads, sort = apply_sort(leads, request.GET.get('sort'), {
        'id': (F('pk'),),
        'lead': (lead_name,),
        'phone': (NullIf('phone', Value('')),),
        'category': (Lower(NullIf('product_category', Value(''))),),
        'source': ('source',),
        # Board order, not the alphabet: "New before Won" is the only reading of
        # a pipeline column that means anything to the desk.
        'stage': (Case(
            *[When(stage=row.key, then=Value(index)) for index, row in enumerate(stage_rows)],
            default=Value(len(stage_rows)), output_field=IntegerField(),
        ),),
        'assignee': (Lower(Coalesce(
            NullIf('assigned_to__first_name', Value('')), 'assigned_to__username')),),
        'followup': ('next_followup_at',),
        'created': ('created_at',),
    }, default='-created')

    # Metrics scoped to the active category tab (All / Business / Drivers). The closed
    # keys are scoped to the same board: a terminal column that exists on only one
    # board would otherwise reclassify the other board's leads with the same key.
    scoped = Lead.objects.filter(category=list_category)
    scoped_closed = crm_services.closed_stage_keys(list_category)
    total_count = scoped.count()
    open_count = scoped.exclude(stage__in=scoped_closed).count()
    overdue_count = (
        scoped.filter(next_followup_at__lt=timezone.localdate())
        .exclude(stage__in=scoped_closed).count()
    )
    won_count = scoped.filter(
        stage__in=crm_services.outcome_stage_keys('won', list_category)
    ).count()

    # Stage filter options are this page's own board columns.
    stage_choices = [(row.key, row.label) for row in stage_rows]
    stage_choices = stage_choices or Lead.STAGE_CHOICES

    page_obj = paginate_queryset(request, leads, items_per_page=50)
    # Materialised so the per-lead vehicle set below survives into the template —
    # a sliced queryset would hand the loop fresh, un-annotated instances.
    page_obj.object_list = list(page_obj.object_list)
    _annotate_driver_vehicles(page_obj.object_list)

    # Two strings, deliberately: pagination has to carry the sort with it, while a
    # header cell writes its own sort and must not inherit the old one.
    facets = [
        ('search', search),
        ('stage', stage_filter),
        ('source', source_filter),
        ('assigned', assigned_filter),
        ('overdue', overdue_filter),
        ('vehicle', vehicle_filter),
        ('datePreset', date_preset),
        # Only a custom range carries its dates; a preset re-resolves server-side.
        ('dateFrom', date_from.isoformat() if date_preset == 'custom' and date_from else ''),
        ('dateTo', date_to.isoformat() if date_preset == 'custom' and date_to else ''),
        ('category', category_filter),
    ]
    sort_params = _facet_params(facets)
    filter_params = _facet_params(facets + [('sort', sort.value)])

    is_driver_list = list_category == Lead.CATEGORY_DRIVER
    # The shared column picker + row-tick contract (workforce/js/export-columns.js):
    # each page names its own registry, its own endpoint and its own remembered
    # column selection, so the two pipelines never overwrite each other's.
    from core.departments import can_access
    from workforce.views import export_columns_context

    context = {
        'page_title': 'Driver Leads' if is_driver_list else 'Business Leads',
        # Documents carry QID and licence scans, so the button only appears for the
        # desk that owns them — marketing works the same table without it.
        'can_download_documents': (
            is_driver_list and can_access(request.user, 'crm_driver_leads_documents')),
        # What the Documents dialog offers to pick from.
        'document_type_choices': _fleet_document_choices(),
        'document_driver_cap': MAX_DOCUMENT_DRIVERS,
        'list_category': list_category,
        'is_driver_list': is_driver_list,
        'page_obj': page_obj,
        'per_page': request.GET.get('per_page', '50'),
        'filter_params': filter_params,
        'sort': sort,
        'sort_params': sort_params,
        'sort_url': reverse('workforce:crm_driver_leads_list' if is_driver_list
                            else 'workforce:crm_leads_list'),
        'search': search,
        'source_filter': source_filter,
        'assigned_filter': assigned_filter,
        'stage_filter': stage_filter,
        'overdue_filter': overdue_filter,
        'vehicle_filter': vehicle_filter,
        'vehicle_choices': _vehicle_filter_choices(),
        'date_preset': date_preset,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to else '',
        'date_preset_choices': DATE_PRESET_CHOICES,
        'category_filter': category_filter,
        'staff_users': _staff_users(),
        'stage_choices': stage_choices,
        # The full column rows, not just (key, label): the bulk bar needs each
        # column's confirm text and reason flag so a bulk move prompts exactly
        # like a board drag into the same column.
        'stage_rows': stage_rows,
        'bulk_stage_cap': MAX_BULK_STAGE_LEADS,
        'source_choices': Lead.SOURCE_CHOICES,
        'category_choices': Lead.CATEGORY_CHOICES,
        'total_count': total_count,
        'open_count': open_count,
        'overdue_count': overdue_count,
        'won_count': won_count,
        'today': timezone.localdate(),
    }
    context.update(export_columns_context(
        CRM_DRIVER_LEAD_EXPORT_COLUMNS if is_driver_list else CRM_BUSINESS_LEAD_EXPORT_COLUMNS,
        url_name=('workforce:crm_driver_leads_export_csv' if is_driver_list
                  else 'workforce:crm_leads_export_csv'),
        storage_key=('wf_crm_driver_lead_cols' if is_driver_list
                     else 'wf_crm_lead_cols'),
    ))
    return render(request, 'workforce/crm/leads_list.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_list(request):
    """Business leads table."""
    return _render_leads_list(request, Lead.CATEGORY_BUSINESS)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_driver_leads_list(request):
    """Driver leads table."""
    return _render_leads_list(request, Lead.CATEGORY_DRIVER)


# Google CSV import wants these exact header names — anything else is ignored on
# import. Order does not matter to Google, only the spelling.
GOOGLE_CONTACTS_HEADERS = [
    'First Name', 'Last Name', 'Organization Name',
    'Phone 1 - Label', 'Phone 1 - Value', 'Notes', 'Labels',
]


def _google_phone(raw):
    """E.164 so the number matches an incoming call. Bare 8-digit numbers are Qatar
    local; anything already carrying a country code just gets the plus."""
    digits = re.sub(r'\D', '', raw or '')
    if not digits:
        return ''
    if len(digits) == 8:
        return f'+974{digits}'
    return f'+{digits}'


# A lead whose "name" is just its own phone number (WhatsApp inbound cards start
# that way) makes a useless address-book entry — and a leading '+' trips the CSV
# formula guard. Treat those as nameless and fall through to the next label.
_NAME_IS_PHONE_RE = re.compile(r'^[\d\s+()\-]+$')


def _split_name(name):
    """First token is the given name, the rest — tag included — is the family name,
    which is what puts ZyDrv / ZyBuz at the end of the last name in the phonebook."""
    parts = (name or '').strip().split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    return parts[0], ' '.join(parts[1:])


# ── Ticked-row downloads ─────────────────────────────────────────────────────
# Both downloads read the same selection the shared export-columns.js writes:
# ?ids=3,9,14 from the row checkboxes, and no ids at all meaning "everything the
# current filter matches". They are plain links, never htmx, so the file lands as
# a file instead of being swapped into the page.

# A driver's documents are photographs of a QID and a licence, ~1 MB each, so a
# whole-page download runs to hundreds of megabytes. The cap is what one desk can
# reasonably be handed in a single file; past it the operator narrows the ticks.
MAX_DOCUMENT_DRIVERS = 25


def _fleet_document_choices():
    from fleet.models import DriverDocument
    return DriverDocument.document_choices


# Offered in the Documents dialog, straight off the model so a new kind never has
# to be added in two places.
DOCUMENT_TYPES = [key for key, _label in _fleet_document_choices()]


def _lead_driver(lead):
    """The application behind a driver lead, or None.

    The FK is authoritative (crm.services._driver_for_lead) — a card not yet
    bound to an applicant exports blank driver columns rather than guessing from
    the phone number.
    """
    return lead.driver if lead.driver_id else None


def _driver_attr(getter):
    """Wrap a Driver getter so an unbound lead exports '' instead of raising."""
    def read(lead):
        driver = _lead_driver(lead)
        return getter(driver) if driver else ''
    return read


def _primary_vehicle(driver):
    return next(iter(driver.driver_vehicle.all()), None)


def _driver_documents_held(driver):
    """The document types actually uploaded — the placeholder image every row
    ships with is not a document (fleet.models.has_real_file)."""
    return ', '.join(sorted({
        doc.document_type for doc in driver.driver_document.all()
        if doc.has_real_file and doc.document_type
    }))


def _lead_assignee(lead):
    if not lead.assigned_to:
        return ''
    return lead.assigned_to.get_full_name() or lead.assigned_to.username


# (key, label, getter) in the order the modal offers them and the file writes them.
CRM_LEAD_BASE_COLUMNS = [
    ('lead_id',    'Lead #',     lambda l: l.pk),
    ('company',    'Company',    lambda l: l.company_name or ''),
    ('contact',    'Contact',    lambda l: strip_tags(l.contact_name) or ''),
    ('phone',      'Phone',      lambda l: l.phone or ''),
    ('phone_2',    '2nd mobile', lambda l: l.phone_2 or ''),
    ('stage',      'Stage',      lambda l: l.stage_label),
    ('source',     'Source',     lambda l: l.get_source_display()),
    ('assignee',   'Assignee',   _lead_assignee),
    ('followup',   'Follow-up',  lambda l: l.next_followup_at.strftime('%Y-%m-%d') if l.next_followup_at else ''),
    ('created',    'Created',    lambda l: timezone.localtime(l.created_at).strftime('%Y-%m-%d')),
    ('notes',      'Notes',      lambda l: l.notes or ''),
]

CRM_BUSINESS_LEAD_EXPORT_COLUMNS = CRM_LEAD_BASE_COLUMNS + [
    ('category',   'Category',   lambda l: l.product_category or ''),
    ('converted',  'Converted to', lambda l: l.converted_business.business_name if l.converted_business else ''),
]

# The recruitment desk works from the card AND the application behind it, so the
# driver columns ride along with the lead ones in one file.
CRM_DRIVER_LEAD_EXPORT_COLUMNS = CRM_LEAD_BASE_COLUMNS + [
    ('driver_code',  'Driver code',   _driver_attr(lambda d: d.driver_code or d.pk)),
    ('whatsapp',     'WhatsApp',      _driver_attr(lambda d: d.driver_whatsapp or '')),
    ('vehicle',      'Vehicle',       _driver_attr(
        lambda d: (_primary_vehicle(d).get_vehicle_type_display()
                   if _primary_vehicle(d) and _primary_vehicle(d).vehicle_type != 'none' else ''))),
    ('plate',        'Plate',         _driver_attr(
        lambda d: (_primary_vehicle(d).vehicle_no or '') if _primary_vehicle(d) else '')),
    ('application',  'Application',   _driver_attr(
        lambda d: d.profile.get_verification_status_display() if d.profile else '')),
    ('driver_status', 'Driver status', _driver_attr(lambda d: d.get_driver_status_display())),
    ('job_type',     'Job type',      _driver_attr(
        lambda d: d.get_job_type_display() if d.job_type else '')),
    ('zones',        'Zones',         _driver_attr(
        lambda d: ', '.join(zg.name for zg in d.preferred_zone_groups.all()))),
    ('nationality',  'Nationality',   _driver_attr(
        lambda d: (d.profile.nationlity or '') if d.profile else '')),
    ('area',         'Area',          _driver_attr(
        lambda d: (d.profile.zone_name or '') if d.profile else '')),
    ('licence',      'Licence no',    _driver_attr(lambda d: d.driver_license_number or '')),
    ('sponsor',      'Sponsor',       _driver_attr(lambda d: d.driver_sponsor or '')),
    ('documents',    'Documents held', _driver_attr(_driver_documents_held)),
]


def _export_leads_queryset(request, list_category):
    """The rows behind a download: the page's own filters re-applied.

    ?ids= is left to csv_columns_response, which narrows to the ticked rows —
    but only ever within this queryset, so a hand-written id can never reach
    across the category boundary into the other pipeline.
    """
    leads, *_ = _filtered_leads(request, multi_facets=True)
    leads = leads.filter(category=list_category)

    stage_filter = [v.strip() for v in request.GET.getlist('stage') if v.strip()]
    if stage_filter:
        leads = leads.filter(stage__in=stage_filter)
    if request.GET.get('overdue', '').strip() == '1':
        leads = leads.filter(
            next_followup_at__lt=timezone.localdate()
        ).exclude(stage__in=crm_services.closed_stage_keys())

    if list_category == Lead.CATEGORY_DRIVER:
        leads = _apply_vehicle_filter(
            leads, [v.strip() for v in request.GET.getlist('vehicle') if v.strip()])

    _preset, date_from, date_to = _date_filter(request)
    leads = _apply_date_filter(leads, date_from, date_to)

    return (leads
            .select_related('assigned_to', 'converted_business',
                            'driver', 'driver__user', 'driver__profile')
            .prefetch_related('driver__driver_document', 'driver__driver_vehicle',
                              'driver__preferred_zone_groups')
            .order_by('-created_at'))


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_export_csv(request):
    """Business leads table as a spreadsheet — ticked rows, else the whole filter."""
    from workforce.views import csv_columns_response

    return csv_columns_response(
        request, _export_leads_queryset(request, Lead.CATEGORY_BUSINESS),
        CRM_BUSINESS_LEAD_EXPORT_COLUMNS, 'ezzy_business_leads')


@login_required(login_url='/accounts/login/')
@staff_required
def crm_driver_leads_export_csv(request):
    """Driver leads table as a spreadsheet, application columns included."""
    from workforce.views import csv_columns_response

    return csv_columns_response(
        request, _export_leads_queryset(request, Lead.CATEGORY_DRIVER),
        CRM_DRIVER_LEAD_EXPORT_COLUMNS, 'ezzy_driver_leads')


@login_required(login_url='/accounts/login/')
@staff_required
def crm_driver_leads_documents(request):
    """The ticked applicants' uploaded documents, as chosen in the Documents dialog.

    ?types= picks the document kinds (blank = all of them) and ?format= picks the
    shape: `pdf` gives one captioned PDF per applicant, `images` the photographs
    themselves in a folder per applicant. Built on a temp file rather than in
    memory — a selection is hundreds of megabytes of photographs — and stored,
    not deflated, because JPEGs do not compress. Capped at MAX_DOCUMENT_DRIVERS:
    a whole-page download is not a file anyone can send on.
    """
    import tempfile
    import zipfile

    from core.exports import set_export_filename
    from django.http import FileResponse, HttpResponse

    # Back to the table the operator came from, filters intact — but without what
    # belongs to the download, which would otherwise sit in the address bar.
    params = request.GET.copy()
    for key in ('ids', 'types', 'format'):
        params.pop(key, None)
    query = params.urlencode()
    back_url = reverse('workforce:crm_driver_leads_list') + (f'?{query}' if query else '')

    ids = [value for value in (request.GET.get('ids', '') or '').split(',')
           if value.strip().isdigit()]
    if not ids:
        messages.warning(request, 'Tick the applicants whose documents you want, '
                                  'then press Documents again.')
        return redirect(back_url)

    wanted = {value for value in request.GET.getlist('types') if value in DOCUMENT_TYPES}
    as_pdf = request.GET.get('format') == 'pdf'

    leads = _export_leads_queryset(request, Lead.CATEGORY_DRIVER).filter(pk__in=ids)
    drivers = list({lead.driver_id: lead.driver
                    for lead in leads if lead.driver_id}.values())

    if not drivers:
        messages.warning(request, 'None of those leads has a driver application yet, '
                                  'so there are no documents to download.')
        return redirect(back_url)
    if len(drivers) > MAX_DOCUMENT_DRIVERS:
        messages.warning(
            request,
            f'{len(drivers)} applicants ticked — documents come {MAX_DOCUMENT_DRIVERS} '
            'at a time. Tick fewer rows, or narrow the filter first.')
        return redirect(back_url)

    index = [['Driver code', 'Name', 'Phone', 'Document', 'Number',
              'Issued from', 'Expiry', 'File in this download']]
    archive = tempfile.NamedTemporaryFile(suffix='.zip')
    written = 0
    single_pdf = None
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as bundle:
        for driver in drivers:
            scans = _selected_scans(driver, wanted)
            if not scans:
                continue
            folder = _driver_folder_name(driver)

            # An already-PDF upload cannot be drawn onto a page (no PDF library
            # here), so it rides along as itself rather than going missing.
            images = [scan for scan in scans if _is_image(scan[2])]
            originals = scans if not as_pdf else [s for s in scans if not _is_image(s[2])]

            if as_pdf and images:
                blob = _driver_documents_pdf(driver, images)
                if blob:
                    member = f'{folder}.pdf'
                    bundle.writestr(member, blob)
                    single_pdf = blob if len(drivers) == 1 else None
                    written += 1
                    for doc, side, _field in images:
                        index.append(_index_row(driver, doc, side, member))

            for doc, side, field in originals:
                member = (f'{folder} - {_scan_label(doc, side)}{_extension(field)}'
                          if as_pdf else
                          f'{folder}/{_scan_label(doc, side)}{_extension(field)}')
                try:
                    with field.open('rb') as handle:
                        bundle.writestr(member, handle.read())
                except (OSError, ValueError):
                    # A row pointing at a file that is no longer on disk must not
                    # cost the operator everyone else's documents.
                    logger.warning('crm: document file %s missing for driver %s',
                                   field.name, driver.pk)
                    continue
                written += 1
                index.append(_index_row(driver, doc, side, member))

        # Numbers and expiry dates live in the table, not on the photographs, so
        # the archive carries its own index rather than arriving as loose files.
        if written:
            bundle.writestr('index.csv', _index_csv(index))

    if not written:
        archive.close()
        messages.warning(
            request,
            'Nothing to download — those applicants have not uploaded '
            + ('any documents yet.' if not wanted else 'the document types you picked.'))
        return redirect(back_url)

    # One applicant asked for as one PDF is a PDF, not a one-item archive.
    if single_pdf is not None and written == 1:
        archive.close()
        response = HttpResponse(single_pdf, content_type='application/pdf')
        return set_export_filename(response, 'ezzy_driver_documents',
                                   code=drivers[0], ext='pdf')

    archive.seek(0)
    response = FileResponse(archive, content_type='application/zip')
    set_export_filename(
        response, 'ezzy_driver_documents',
        code=drivers[0] if len(drivers) == 1 else None, ext='zip')
    return response


def _selected_scans(driver, wanted):
    """[(doc, side, file field)] for one applicant, narrowed to the chosen types.

    `wanted` empty means every type. The placeholder image every DriverDocument
    row ships with is not a document, so only real uploads come back
    (fleet.models.has_real_file); a back side is only ever a real file.
    """
    scans = []
    for doc in driver.driver_document.all():
        if wanted and doc.document_type not in wanted:
            continue
        if doc.has_real_file:
            scans.append((doc, 'front', doc.document_file))
        back = doc.document_file_back
        if back and back.name:
            scans.append((doc, 'back', back))
    return scans


def _driver_folder_name(driver):
    """`CODE-Name` — what one applicant's files are filed under in the archive."""
    name = (driver.user.get_full_name() if driver.user else '') or ''
    return '-'.join(part for part in (
        _ZIP_UNSAFE.sub('-', str(driver.driver_code or driver.pk)).strip('-'),
        _ZIP_UNSAFE.sub('-', name).strip('-'),
    ) if part) or str(driver.pk)


def _scan_label(doc, side):
    label = _ZIP_UNSAFE.sub('-', doc.document_type or 'Document').strip('-')
    return f'{label}_back' if side == 'back' else label


def _extension(field):
    return os.path.splitext(field.name)[1].lower() or '.jpg'


def _is_image(field):
    """True when the upload can be drawn onto a PDF page. The field is an
    ImageField, but 16 rows predate that and hold a PDF."""
    return _extension(field) in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic'}


def _index_row(driver, doc, side, member):
    return [
        driver.driver_code or driver.pk,
        (driver.user.get_full_name() if driver.user else '') or '',
        driver.driver_phone or '',
        (doc.document_type or 'Document') + (' (back)' if side == 'back' else ''),
        doc.document_no or '',
        doc.document_issued_from or '',
        doc.document_expiry_date.strftime('%Y-%m-%d') if doc.document_expiry_date else '',
        member,
    ]


def _driver_documents_pdf(driver, scans):
    """One applicant's scans as a single A4 PDF, a captioned page each.

    The captions are the point: once the photographs leave the table they carry
    no name, no document number and no expiry date, and a pack of anonymous
    phone snaps is not something a desk can file.
    """
    import io

    from PIL import Image, ImageOps
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    name = (driver.user.get_full_name() if driver.user else '') or ''
    heading = ' · '.join(part for part in (
        str(driver.driver_code or driver.pk), name, driver.driver_phone or '') if part)

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    page.setTitle(f'EZZY driver documents — {heading}')
    width, height = A4
    margin = 15 * mm
    pages = 0

    for doc, side, field in scans:
        try:
            with field.open('rb') as handle:
                image = Image.open(handle)
                # Phone cameras record orientation in EXIF rather than in the
                # pixels; without this half the licences arrive on their side.
                image = ImageOps.exif_transpose(image)
                image = image.convert('RGB')
                image.load()
        except Exception:
            logger.warning('crm: could not render %s for driver %s',
                           field.name, driver.pk)
            continue

        # Re-encode as JPEG at print resolution and hand reportlab the encoded
        # bytes, not the pixels: given a raw image it stores every one of them
        # losslessly, which turned a 3 MB pack of photos into a 23 MB PDF.
        # A4 at 200 dpi is past what any of these scans actually resolve.
        image.thumbnail((1654, 2339), Image.LANCZOS)
        encoded = io.BytesIO()
        image.save(encoded, format='JPEG', quality=85, optimize=True)
        encoded.seek(0)

        page.setFont('Helvetica-Bold', 11)
        page.drawString(margin, height - margin, heading)
        page.setFont('Helvetica', 9.5)
        caption = (doc.document_type or 'Document') + (' — back' if side == 'back' else '')
        detail = ' · '.join(part for part in (
            doc.document_no or '',
            f'issued {doc.document_issued_from}' if doc.document_issued_from else '',
            f'expires {doc.document_expiry_date:%d %b %Y}' if doc.document_expiry_date else '',
        ) if part)
        page.drawString(margin, height - margin - 13, caption + (f'   ({detail})' if detail else ''))

        top = height - margin - 26
        page.drawImage(ImageReader(encoded), margin, margin,
                       width=width - 2 * margin, height=top - margin,
                       preserveAspectRatio=True, anchor='c', mask='auto')
        page.showPage()
        pages += 1

    if not pages:
        return None
    page.save()
    return buffer.getvalue()


def _index_csv(rows):
    """The archive's own index as CSV text, formula-guarded like every export."""
    import csv
    import io

    from core.exports import safe_csv_writer

    buffer = io.StringIO()
    writer = safe_csv_writer(buffer, quoting=csv.QUOTE_MINIMAL)
    for row in rows:
        writer.writerow(row)
    # Excel reads UTF-8 only with the BOM, and these rows carry Arabic names.
    return '﻿' + buffer.getvalue()

@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_export_google(request):
    """Google Contacts CSV for the current filter — import at contacts.google.com.

    Re-importing the same file updates the matching contacts rather than duplicating
    them, so this doubles as the sync until a People API push exists.
    """
    import csv

    from core.exports import safe_csv_writer, set_export_filename
    from django.http import HttpResponse

    # multi_facets: this link carries the list page's own query string, whose
    # facets each write one param per tick — read singly, ?source=a&source=b
    # would silently export only the last of the two.
    leads, _search, _source, _assigned, _category = _filtered_leads(
        request, multi_facets=True)
    # _filtered_leads prefetches for the table view; none of it is needed here.
    leads = (leads.exclude(phone='')
             .prefetch_related(None)
             .order_by('category', 'company_name', 'contact_name'))

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    set_export_filename(response, 'ezzy-google-contacts')
    # Google's importer reads UTF-8 only with the BOM present.
    response.write('\ufeff')
    writer = safe_csv_writer(response, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(GOOGLE_CONTACTS_HEADERS)

    label_for = {
        Lead.CATEGORY_DRIVER: f'* myContacts ::: EZZY Drivers ({CONTACT_TAGS["driver"]})',
        Lead.CATEGORY_BUSINESS: f'* myContacts ::: EZZY Business ({CONTACT_TAGS["business"]})',
    }
    for lead in leads.iterator():
        # A business lead with no named contact still deserves a phonebook entry —
        # the company carries the tag instead so the search still finds it.
        # …and a lead with neither still gets a findable, tagged entry rather than a
        # nameless phone number sitting in the address book.
        contact, company = lead.contact_name, lead.company_name
        if _NAME_IS_PHONE_RE.match(strip_tags(contact) or 'x'):
            contact = ''
        if _NAME_IS_PHONE_RE.match(company or 'x'):
            company = ''
        name = (contact
                or crm_contact_tags.apply_tag(company, lead.category)
                or crm_contact_tags.apply_tag(f'Lead {lead.pk}', lead.category))
        first, last = _split_name(name)
        writer.writerow([
            first,
            last,
            lead.company_name or '',
            'Mobile',
            _google_phone(lead.phone),
            f'EZZY lead #{lead.pk} — {lead.get_category_display()} · {lead.stage_label}',
            label_for.get(lead.category, '* myContacts'),
        ])
    return response


# Friendly icon + label per WAHA message_type for text-less preview rows
WA_MEDIA_LABELS = {
    'image': ('fa-image', 'Photo'),
    'sticker': ('fa-note-sticky', 'Sticker'),
    'video': ('fa-video', 'Video'),
    'audio': ('fa-microphone', 'Voice note'),
    'ptt': ('fa-microphone', 'Voice note'),
    'voice': ('fa-microphone', 'Voice note'),
    'document': ('fa-paperclip', 'Document'),
    'vcard': ('fa-address-card', 'Contact card'),
    'location': ('fa-location-dot', 'Location'),
}

_B64_BLOB_RE = re.compile(r'[A-Za-z0-9+/=\s]{80,}')


def _clean_wa_body(body):
    """Message text safe for previews. Some WAHA webhook payloads put the raw
    base64 media bytes in `body` — that renders as an endless garbage string,
    so treat it as no-text and let the media label speak instead."""
    body = (body or '').strip()
    if body.startswith('data:') or _B64_BLOB_RE.fullmatch(body):
        return ''
    return body


def _media_kind(mime, message_type):
    """Coarse media bucket for template rendering: image/audio/video/document/''."""
    m = (mime or '').lower()
    if m.startswith('image/'):
        return 'image'
    if m.startswith('audio/'):
        return 'audio'
    if m.startswith('video/'):
        return 'video'
    if m:
        return 'document'
    if message_type == 'sticker':
        return 'image'
    if message_type in ('image', 'audio', 'video', 'document'):
        return message_type
    return ''


def wa_identifiers_for(raw_phone, raw_override=''):
    """WhatsAppMessage from/to identifiers that can mean one phone number.

    Split out of _lead_wa_identifiers so surfaces that have a bare number rather
    than a Lead — the driver verification queue — can read the same thread
    without re-deriving the LID rules, which is exactly where a duplicate would
    go wrong (see the 974-invention trap below).

    Returns (idents, lid_pairs):
      idents    — phone-shaped identifiers (bare digits with/without the 974
                  country code, @c.us JIDs). Meaningful on any WAHA session.
      lid_pairs — {(session, lid identifier)}. A LID is issued per linked
                  device, so the same lid string on our other number belongs to
                  a different person and must only match within its session.
    """
    phone = crm_services.normalize_phone(raw_phone)
    # One override (legacy str) or every number linked to the lead (LeadWaLink).
    raw_list = [raw_override] if isinstance(raw_override, str) else list(raw_override or ())
    overrides = [o for o in (crm_services.normalize_phone(r or '') for r in raw_list) if o]
    idents = set()
    lid_pairs = set()
    if phone:
        idents |= crm_services._phone_variants(phone)
    for override in overrides:
        idents.add(override)
        # A manual override is an operator asserting the mapping — trust it on
        # any session rather than guessing which one they meant.
        idents.add(f'{override}@lid')
        # …but only read it as a phone when it is one. A lid expanded through
        # the phone variants invents '974' + its last 8 digits, which is a
        # perfectly plausible Qatar number belonging to a stranger.
        if not crm_services.is_lid_value(override):
            idents |= crm_services._phone_variants(override)
    if not idents:
        return set(), set()
    try:
        from whatsapp.models import WhatsAppContact
        rows = (
            WhatsAppContact.objects
            .filter(Q(phone__in=list(idents)) | Q(lid__in=list(idents)))
            .exclude(lid='')
            .values_list('session', 'lid')
        )
        for sess, lid in rows:
            lid_pairs.add((sess, lid))
            lid_pairs.add((sess, f'{lid}@lid'))
    except Exception:
        logger.exception('crm: lid lookup failed for phone %s', phone or overrides)
    for p in list(idents):
        if '@' not in p:
            idents.add(f'{p}@c.us')
    return idents, lid_pairs


def _lead_wa_identifiers(lead):
    """Identifiers for a Lead — the phone plus every manually linked number."""
    return wa_identifiers_for(lead.phone, lead.wa_link_values)


def _lead_wa_q(lead, session=''):
    """Q matching every WhatsAppMessage that belongs to this lead, or None.

    Unscoped it spans all WAHA sessions on purpose — one unified customer
    history whether they wrote to our ops or marketing number — while keeping
    lid matches inside the session that issued them.

    Pass `session` to narrow to a single number. That is an AND on top of the
    identifier match, not a replacement for the per-lid scoping above: a lid
    still only counts on the session that issued it.
    """
    idents, lid_pairs = _lead_wa_identifiers(lead)
    if not idents and not lid_pairs:
        return None
    q = None
    if idents:
        ident_list = list(idents)
        q = Q(from_number__in=ident_list) | Q(to_number__in=ident_list)
    for sess, lid in lid_pairs:
        clause = Q(session=sess) & (Q(from_number=lid) | Q(to_number=lid))
        q = clause if q is None else (q | clause)
    if session:
        q = q & Q(session=session)
    return q


def _lead_wa_session_stats(lead, user=None):
    """{session: {'count', 'last_at'}} for every number this lead has talked on.

    Feeds the number picker on the detail page: without the counts, switching
    lines is a guess, and a staff member who lands on an empty number cannot
    tell "wrong number picked" from "customer never replied".
    """
    # Same platform-account gate as the conversation itself — otherwise the
    # picker would leak "this number has 412 messages" for a blocked chat.
    if crm_services.wa_read_blocked(_lead_wa_identifiers(lead), user):
        return {}
    wa_q = _lead_wa_q(lead)
    if wa_q is None:
        return {}
    try:
        from whatsapp.models import WhatsAppMessage
        rows = (
            WhatsAppMessage.objects.filter(wa_q)
            .values('session')
            .annotate(count=Count('pk'), last_at=Max('received_at'))
        )
        return {r['session']: {'count': r['count'], 'last_at': r['last_at']} for r in rows}
    except Exception:
        logger.exception('crm: WA session stats failed for lead %s', lead.pk)
        return {}


def _lead_wa_conversation(lead, session='', user=None):
    """Full WhatsApp conversation for a lead's phone, oldest first, with media
    annotations (`media_kind`, `media_proxy`) on each row. Returns
    (messages, media_items) — media_items is the photo/video subset for the
    Media panel, newest first.

    `session` narrows the thread to one of our numbers; blank keeps the merged
    all-numbers view.

    Not gated on WAHA_ENABLED (that flag gates sending): the message table is
    filled by the webhook regardless, same as the CRM inbox."""
    if not lead.phone and not lead.wa_link_values:
        return [], []

    # A lead whose number belongs to a platform account must not expose that
    # account's conversation (it carries auth messages) — same gate as the inbox.
    # With `user`, a marketing-only chat stays hidden from other desks too.
    if crm_services.wa_read_blocked(_lead_wa_identifiers(lead), user):
        return [], []

    wa_q = _lead_wa_q(lead, session)
    if wa_q is None:
        return [], []

    try:
        from whatsapp.models import WhatsAppMessage
        from whatsapp.wa_chats_view import _extract_media

        rows = list(
            WhatsAppMessage.objects
            .filter(wa_q)
            .order_by('-received_at', '-created_at')[:200]
        )[::-1]
    except Exception:
        logger.exception('crm: failed to load WA messages for lead %s', lead.pk)
        return [], []

    messages, media_items = [], []
    for row in rows:
        media = None
        try:
            media = _extract_media(row)
        except Exception:
            pass
        has_source = bool(row.media_file) or bool((media or {}).get('url'))
        kind = (
            _media_kind(row.media_mime or (media or {}).get('mime', ''), row.message_type)
            if has_source else ''
        )
        row.media_kind = kind
        row.media_proxy = (
            reverse('workforce:crm_lead_wa_media', args=[lead.pk, row.pk])
            if kind and has_source else ''
        )
        row.body = _clean_wa_body(row.body)
        if not row.body and not row.media_proxy and row.message_type == 'text':
            continue  # empty text rows (reactions/protocol events) add noise
        messages.append(row)
        if row.media_proxy and kind in ('image', 'video'):
            media_items.append(row)

    media_items.reverse()
    return messages, media_items


def _lead_wa_session_choice(lead, requested, user=None):
    """Which number the lead page shows → (session, options, changed, explicit).

    `session` is '' for the merged all-numbers view, otherwise a WAHA session
    name. `options` is the picker payload. `changed` is True when `requested`
    is a new, valid choice the caller should persist onto the lead.

    `explicit` says whether a human chose this number or the page merely landed
    on it. Only an explicit choice may override which line a reply goes out
    from: the reading tab defaulting to the house number must not quietly move
    business-lead sends off the number configured on the Auto Triggers page —
    the client would see a different sender with nobody having asked for it.

    Precedence, and why:
      1. `requested` (?session= on the URL) — an explicit click always wins.
      2. `lead.wa_session` — the number this lead was last worked on. A driver
         switched to Ezzy6000 must still be on Ezzy6000 tomorrow.
      3. The default session (66451589) — the house number, per the ops rule.
      4. …unless the default has no messages for this lead and another number
         does. Landing on a blank panel while the real thread sits one tab away
         reads as "this lead never replied", which is the bug this picker is
         meant to end.
    """
    from whatsapp import sessions as wa_sessions

    stats = _lead_wa_session_stats(lead, user)
    live = wa_sessions.list_sessions()
    known = {s['name'] for s in live} | set(stats)
    default = wa_sessions.default_session()
    stored = (lead.wa_session or '').strip()

    def _valid(value):
        return value == Lead.WA_SESSION_ALL or (value in known and wa_sessions.is_valid(value))

    requested = (requested or '').strip()
    changed = bool(requested) and _valid(requested) and requested != stored
    picked = requested if (requested and _valid(requested)) else (stored if _valid(stored) else '')
    explicit = bool(picked)

    if not picked:
        if stats.get(default, {}).get('count'):
            picked = default
        elif stats:
            # Busiest-first, newest as the tiebreak — the thread most likely meant.
            # Sort on a float, not the datetime: `last_at` is None on rows that
            # never got a timestamp, and mixing None (or a naive fallback) into
            # a datetime comparison raises.
            picked = max(
                stats.items(),
                key=lambda kv: (
                    kv[1]['count'],
                    kv[1]['last_at'].timestamp() if kv[1]['last_at'] else 0.0,
                ),
            )[0]
        else:
            picked = default

    total = sum(s['count'] for s in stats.values())
    options = [{
        'name': Lead.WA_SESSION_ALL,
        'label': 'All numbers',
        'phone': '',
        'status': '',
        'count': total,
        'active': picked == Lead.WA_SESSION_ALL,
    }]
    seen = set()
    for s in live:
        seen.add(s['name'])
        options.append({
            'name': s['name'],
            'label': s['push_name'] or s['name'],
            'phone': s['phone'],
            'status': s['status'],
            'count': stats.get(s['name'], {}).get('count', 0),
            'active': picked == s['name'],
        })
    # Numbers we no longer host but still hold history for — hiding them would
    # make those messages unreachable from this page.
    for name in sorted(set(stats) - seen):
        options.append({
            'name': name,
            'label': name,
            'phone': '',
            'status': 'GONE',
            'count': stats[name]['count'],
            'active': picked == name,
        })

    return ('' if picked == Lead.WA_SESSION_ALL else picked), options, changed, explicit


def _lead_pricing_check(inquiry, user=None):
    """Everything the rate card read off this inquiry, and what it charged for it.

    Returned as flat rows rather than left to the template because the useful
    column is CHARGED: a requirement the engine normalises but no rule matches
    prices at zero, and that only becomes visible when it sits beside the answer
    that asked for it. `dimension=None` means the answer reaches no rule at all.

    Best-effort like every other panel on this page — a pricing failure must
    never take down a lead record staff are trying to read.
    """
    if inquiry is None:
        return None

    try:
        from webpages.pricing.engine import get_or_create_suggestion
        suggestion, _record = get_or_create_suggestion(inquiry, user=user)
    except Exception:
        logger.exception('crm: price suggestion failed for PricingEnquiry %s', inquiry.pk)
        return {'error': 'Could not compute a suggestion — see the error log.'}
    if not suggestion.available:
        return {'error': suggestion.reason or 'No suggestion available.'}

    inputs = suggestion.inputs or {}

    # What each dimension actually moved the price by. Summed, because special
    # handling and COD can both stack more than one line.
    charged = {}
    for line in suggestion.breakdown:
        try:
            charged[line['dimension']] = (charged.get(line['dimension'], Decimal('0'))
                                          + Decimal(line['delta']))
        except (InvalidOperation, TypeError, KeyError):
            continue

    # A dimension the active card carries no rule for is priced INTO the base by
    # design (v2 does this for same-day, COD, returns, home pickup and pickup
    # frequency). Read off the card rather than hardcoded, so adding a rule later
    # flips the row to a real charge on its own.
    carded = set(suggestion.ruleset.rules.filter(is_active=True)
                 .values_list('dimension', flat=True)) if suggestion.ruleset else set()

    def row(group, label, value, dimension, state='plain', note='', sets_base=False):
        return {
            'group': group, 'label': label, 'value': value or '—', 'state': state,
            # Volume and distance share one rule, so charging both rows would
            # print the base twice — they say "sets the base" and the breakdown
            # table below shows the single amount.
            'charged': None if sets_base else charged.get(dimension),
            'sets_base': sets_base,
            # "in the base" only answers "you asked for it, why is it free?" —
            # for a No it would be answering a question nobody asked.
            'in_base': (dimension is not None and dimension not in carded
                        and state != 'no'),
            'priced': dimension is not None,
            'note': note,
        }

    def yes_no(flag):
        return ('Yes', 'yes') if flag else ('No', 'no')

    handling = ', '.join(inputs.get('special_handling') or [])
    cod_value, cod_state = yes_no(inputs.get('cod_required'))
    if inputs.get('cod_required') and inputs.get('cod_share_mid') is not None:
        cod_value = f'Yes — {inquiry.cod_orders_share} of orders'
    sameday_value, sameday_state = yes_no(inputs.get('same_day_required'))
    returns_value, returns_state = yes_no(inputs.get('returns_required'))

    volume = inputs.get('monthly_orders')
    VOLUME_SOURCE = {
        'last_month': 'from last month’s orders',
        'expected_next_month': 'from what they EXPECT next month, not history',
        'last_week_scaled': 'from last week, scaled ×4.33',
    }

    rows = [
        row('Service required', 'Delivery speed promised',
            inquiry.speed_delivery_offer_to_customers, 'speed',
            'unknown' if inputs.get('speed_rank') is None else 'plain'),
        row('Service required', 'Same-day pick & deliver', sameday_value,
            'same_day_pickup', sameday_state),
        row('Service required', 'Special handling',
            handling or ('Yes — unspecified' if inquiry.is_special_handling_required else 'No'),
            'special_handling', 'yes' if handling else 'no'),
        row('Service required', 'Return logistics', returns_value, 'returns', returns_state),
        row('Service required', 'Cash on delivery', cod_value, 'cod', cod_state),
        row('Service required', 'Parcel size', inquiry.typical_package_size, 'size',
            'unknown' if inputs.get('size_rank') is None else 'plain'),
        row('Service required', 'Parcel weight', inquiry.average_package_weight, 'weight',
            'unknown' if inputs.get('weight_mid_kg') is None else 'plain'),

        row('Pickup', 'Where we collect from', inquiry.type_of_pickup_location, 'pickup_type',
            'unknown' if inputs.get('pickup_type_rank') is None else 'plain'),
        row('Pickup', 'Pickup area', inquiry.pickup_Location_area_name, None,
            'unknown' if not inquiry.pickup_Location_area_name else 'plain',
            'never reaches the rate card'),
        row('Pickup', 'How many pickup points',
            inquiry.number_of_pickup_locations or 'Single point', 'pickup_locations'),
        row('Pickup', 'Pickups per day', inquiry.number_of_pickup_times_in_day,
            'pickups_per_day'),
        row('Pickup', 'Pickup slot → delivery window',
            ' → '.join(p for p in (inquiry.pickup_location_time_slab,
                                   inquiry.preferred_delivery_time_window) if p),
            None, 'plain', 'never reaches the rate card'),

        row('Sets the base rate', 'Orders per month',
            f'{volume:.0f}' if volume is not None else '',
            'volume_distance_base',
            'unknown' if volume is None else 'plain',
            VOLUME_SOURCE.get(inputs.get('volume_source'), ''), sets_base=True),
        row('Sets the base rate', 'Typical delivery distance',
            inquiry.typical_delivery_distance, 'volume_distance_base',
            'unknown' if inputs.get('distance_km') is None else 'plain', sets_base=True),
        row('Sets the base rate', 'Delivery coverage', inquiry.delivery_coverage, None,
            'unknown' if inputs.get('coverage_rank') is None else 'plain',
            'never reaches the rate card'),
    ]

    agreed_gap = None
    if inquiry.agreed_price_value is not None:
        try:
            agreed_gap = (Decimal(str(inquiry.agreed_price_value))
                          - Decimal(str(suggestion.suggested_price)))
        except (InvalidOperation, TypeError, ValueError):
            agreed_gap = None

    return {
        'suggestion': suggestion,
        'rows': rows,
        'agreed_gap': agreed_gap,
        'unpriced': [r for r in rows if not r['priced']],
        'error': '',
    }


def _lead_reminder(lead, driver):
    """The "what is still missing" reminder the WhatsApp composer offers, or None.

    Returns ``{'label': ..., 'body': ...}``. The label carries the count so the
    picker reads "Reminder — 2 details missing" rather than a generic entry that
    might hold nothing.

    Two different questions, one chip:
      • Driver lead — the applicant's own form. Reuses the exact body the driver
        profile page sends (``_build_driver_reminder``), so a reminder chased
        from the CRM and one chased from the application read identically.
      • Business lead — the answers we still need before a quote can go out:
        the lead's own blanks first, then the pricing form's, plus that form's
        resume link when they abandoned it half-way.

    Nothing missing → None, and the composer simply does not offer the option:
    a "you still owe us" message with an empty list is worse than no chip.
    """
    # A closed card is not chased. Won/approved has nothing outstanding that a
    # message can fix, and lost/rejected must never get a "we still need…" nudge.
    # Read off LeadStage.is_closed, not the key: both boards name their own
    # terminal columns.
    if lead.stage in crm_services.closed_stage_keys(lead.category) or lead.converted_business_id:
        return None

    if lead.category == Lead.CATEGORY_DRIVER:
        if not driver:
            return None
        from workforce.views import _build_driver_reminder
        _phone, body, missing, error = _build_driver_reminder(driver)
        if error or not body:
            return None
        # Short on purpose: this label is a chip in the composer's paste row, not
        # a sentence.
        return {'label': f'Reminder · {len(missing)} missing', 'body': body}

    return _business_lead_reminder(lead)


def _business_lead_reminder(lead):
    """Reminder body for a business lead — the details a quote still waits on."""
    missing = []
    if not lead.company_name:
        missing.append('your business / store name')
    if not lead.contact_name:
        missing.append('your name')
    if not lead.product_category:
        missing.append('what you sell (product category)')

    pe = lead.pricing_enquiry
    resume_url = ''
    if pe:
        if not (pe.email or '').strip():
            missing.append('an email address to send the quotation to')
        if not (pe.avarage_number_of_order_done_last_month
                or pe.avarage_number_of_order_last_week):
            missing.append('how many orders you ship in a month')
        if not (pe.pickup_Location_area_name or '').strip():
            missing.append('the area we would collect from')
        if not (pe.delivery_coverage or '').strip():
            missing.append('where you deliver — Doha only or all Qatar')
        if not (pe.typical_package_size or '').strip():
            missing.append('the size of a typical parcel')
        if not pe.is_complete and pe.quote_token:
            base = (getattr(settings, 'SITE_URL', '') or 'https://ezzydelivery.qa').rstrip('/')
            resume_url = f'{base}/3pl/inquiry/resume/{pe.quote_token}/'
    else:
        # No pricing form behind this lead, so nothing was ever asked. These are
        # the three answers sales cannot quote without.
        missing.append('how many orders you ship in a week')
        missing.append('the area we would collect from')
        missing.append('whether you need Cash on Delivery')

    if not missing:
        return None

    greeting = strip_tags(lead.contact_name) or lead.company_name or 'there'
    lines = '\n'.join(f'• {item}' for item in missing)
    tail = (
        f'\nYour answers are saved — you can finish the form here:\n{resume_url}\n'
        if resume_url else ''
    )
    body = (
        f'Hello {greeting}, this is *EZZY Delivery* 👋\n\n'
        f'To prepare your delivery pricing we still need a few details:\n'
        f'{lines}\n'
        f'{tail}\n'
        f'Just reply here with the answers and we will send your rates on this chat.\n\n'
        f'*EZZY Delivery* 🚚'
    )
    return {'label': f'Reminder · {len(missing)} missing', 'body': body}


def _ai_summary_available():
    """True when the ai_agent unified provider stack has a usable provider."""
    try:
        from ai_agent.services.unified_service import get_chat_service
        return get_chat_service('chat').is_available()[0]
    except Exception:
        logger.exception('crm: AI availability check failed')
        return False


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_detail(request, lead_id):
    """Lead detail: source summary, editors, activity timeline, full WA
    conversation, shared-media gallery, AI summary."""
    lead = get_object_or_404(
        Lead.objects.select_related(
            'assigned_to', 'converted_business', 'pricing_enquiry', 'whatsapp_inquiry',
            # The Quote panel reads the agreed plan and who quoted it.
            'pricing_enquiry__selected_plan', 'pricing_enquiry__quoted_by',
        ),
        pk=lead_id,
    )

    # Which of our numbers this conversation runs on. Persisted with .update()
    # so remembering a tab never touches updated_at — that field drives the
    # follow-up digests and must keep meaning "the lead moved".
    wa_session, wa_session_options, wa_session_changed, wa_session_explicit = (
        _lead_wa_session_choice(lead, request.GET.get('session'), request.user))
    if wa_session_changed:
        stored = wa_session or Lead.WA_SESSION_ALL
        Lead.objects.filter(pk=lead.pk).update(wa_session=stored)
        lead.wa_session = stored

    wa_messages, wa_media = _lead_wa_conversation(lead, wa_session, request.user)

    from fleet.models import DriverDocument

    # Driver leads: keep the pipeline stage in sync with the applicant's real
    # form status (the timeline) and show driver-funnel labels + the timeline.
    driver = None
    driver_sections = None
    driver_documents = []
    stage_rows = crm_services.board_stages(lead.category)
    if lead.category == Lead.CATEGORY_DRIVER:
        driver = crm_services._driver_for_lead(lead)
        if driver:
            # Cards in a manual column, or pinned by staff, stay put — same rule as the
            # board. `user=None` because this mirror is automatic: attributing it to
            # whoever opened the page put false actors in the timeline.
            manual = crm_stage_rules.manual_stage_keys(stage_rows)
            target = crm_services.driver_lead_target_stage(driver, stage_rows)
            if (target and target != lead.stage and lead.stage not in manual
                    and not lead.stage_pinned):
                crm_services.set_lead_stage(lead, target, None)
            from workforce.views import (
                LEAD_DOC_EXPIRY_SOON_DAYS, _driver_application_sections, driver_document_cards,
            )
            driver_sections = _driver_application_sections(driver)
            # The scans themselves, not just the "6/7 sections" tally — the desk
            # reads an ID here to decide the stage, and used to have to open the
            # driver record in another tab to see one.
            driver_documents = driver_document_cards(driver, soon_days=LEAD_DOC_EXPIRY_SOON_DAYS)
    # LeadStage rows, not (key, label) tuples — the template needs each column's
    # confirm_text / needs_reason so the chips can prompt like the board does.
    stage_choices = stage_rows

    # Starter text for the "Send from EZZY" composer. Driver leads get the fleet
    # wording, business leads the sales one; editable on the AI Config Messages
    # tab, and '' (blank composer) when that template is switched off.
    from core.message_templates import (
        CRM_DRIVER_LEAD_MANUAL, CRM_LEAD_MANUAL, render_template,
    )
    wa_send_message = render_template(
        CRM_DRIVER_LEAD_MANUAL if lead.category == Lead.CATEGORY_DRIVER else CRM_LEAD_MANUAL,
        lead_name=strip_tags(lead.contact_name) or lead.company_name or 'there',
        company=lead.company_name or '',
        staff_name=request.user.get_full_name() or request.user.username,
    ) or ''

    # The second body the composer offers: what this record is still short of.
    # Built here rather than in the modal because only the page knows whether it
    # is looking at a driver application or a quote request.
    wa_reminder = _lead_reminder(lead, driver)

    # What the rate card makes of this inquiry — the requirement-by-requirement
    # check, so the desk can see WHY the number is what it is before quoting.
    pricing_check = _lead_pricing_check(lead.pricing_enquiry, user=request.user)

    # "Two cards in one": what has been absorbed here, and where each absorbed card
    # disagrees with this one (the merge kept this card's value without asking).
    merged_children = list(
        lead.merged_children.select_related('merged_by', 'assigned_to').order_by('created_at')
    )
    for child in merged_children:
        child.merge_diffs = crm_services.merge_differences(lead, child)

    context = {
        'page_title': f'Lead – {lead.company_name or lead.contact_name or lead.phone}',
        'lead': lead,
        # Absorbed cards' entries are folded in, tagged with their card number in the
        # template (activity.lead_id != lead.pk), so one timeline tells the whole story.
        'activities': LeadActivity.objects.filter(
            lead_id__in=[lead.pk] + [c.pk for c in merged_children]
        ).select_related('created_by').order_by('-created_at'),
        'staff_users': _staff_users(),
        'stage_choices': stage_choices,
        # Untagged name for the WhatsApp composer — the customer never sees "ZyDrv".
        'lead_wa_name': strip_tags(lead.contact_name) or lead.company_name or '',
        'driver': driver,
        'driver_sections': driver_sections,
        'driver_documents': driver_documents,
        'document_type_choices': DriverDocument.document_choices,
        # "Two cards in one": what has been absorbed here, and what still could be.
        'merged_children': merged_children,
        'duplicate_candidates': crm_services.duplicate_candidates(lead),
        'wa_messages': wa_messages,
        'wa_media': wa_media,
        'wa_session': wa_session,
        'wa_session_options': wa_session_options,
        'wa_numbers': crm_services.lead_wa_numbers(lead),
        # Only a chosen number overrides the composer. Blank = keep the section
        # route from the Auto Triggers page, i.e. exactly today's behaviour.
        'wa_send_session': wa_session if wa_session_explicit else '',
        'wa_send_message': wa_send_message,
        'wa_reminder_message': wa_reminder['body'] if wa_reminder else '',
        'wa_reminder_label': wa_reminder['label'] if wa_reminder else '',
        # Across every number — lets the empty state say "the thread is on
        # another line" instead of the flatly wrong "this lead never wrote".
        'wa_total_messages': wa_session_options[0]['count'] if wa_session_options else 0,
        'pricing_check': pricing_check,
        # The summary is read from the conversation, so it is hidden with it.
        'ai_summary': '' if crm_services.wa_read_blocked(_lead_wa_identifiers(lead), request.user) else lead.ai_summary,
        'ai_available': _ai_summary_available(),
        'today': timezone.localdate(),
        # One URL serves both pipelines, so the sidebar cannot tell from the
        # url_name which menu owns it — a driver card opened from the driver
        # board used to light up CRM Business. The card's own board decides.
        'crm_sidebar_board': lead.category,
    }
    return render(request, 'workforce/crm/lead_detail.html', context)


def _wa_chat_id(ident):
    """A stored identifier ('97455…', '1234567890@lid') as a WAHA chatId."""
    ident = (ident or '').strip()
    if not ident:
        return ''
    if '@' in ident:
        return ident
    if crm_services.is_lid_value(ident):
        return f'{ident}@lid'
    return f'{ident}@c.us'


def _lead_wa_chat_targets(lead, session=''):
    """[(session, chatId)] — the WAHA chats holding this lead's thread.

    Read off the lead's newest stored messages, because those rows already name
    the identifier WhatsApp actually routes on (a phone JID on one number, a
    per-device @lid on the other) rather than a guess built from the phone.
    Falls back to the phone when nothing is stored yet — a lead the webhook
    never delivered is exactly what the Refresh button is for.
    """
    from whatsapp import sessions as wa_sessions

    idents, lid_pairs = _lead_wa_identifiers(lead)
    lid_values = {lid for _sess, lid in lid_pairs}
    targets, seen = [], set()

    wa_q = _lead_wa_q(lead, session)
    if wa_q is not None:
        try:
            from whatsapp.models import WhatsAppMessage
            rows = list(
                WhatsAppMessage.objects.filter(wa_q)
                .order_by('-received_at')
                .values_list('session', 'from_number', 'to_number')[:100]
            )
        except Exception:
            logger.exception('crm: chat target lookup failed for lead %s', lead.pk)
            rows = []
        for sess, from_number, to_number in rows:
            for cand in (from_number, to_number):
                # Whichever side of the row is the LEAD — our own number is never
                # in the identifier set, so this picks the counterpart.
                if not cand or (cand not in idents and cand not in lid_values):
                    continue
                key = (sess, _wa_chat_id(cand))
                if key[1] and key not in seen:
                    seen.add(key)
                    targets.append(key)

    if not targets:
        fallback_session = session or wa_sessions.default_session()
        # The first linked number stands in when the lead's own phone is blank.
        links = lead.wa_link_values
        override = crm_services.normalize_phone(links[0]) if links else ''
        phone = crm_services.normalize_phone(lead.phone or '')
        if override and crm_services.is_lid_value(override):
            # A lid addresses a chat only on the session whose device issued it;
            # the same string elsewhere is a different person. So it is a target
            # only where this lead's lid is known, and the plain phone carries
            # the fallback on every other number.
            base = override if (fallback_session, override) in lid_pairs else phone
        else:
            base = override or phone
        if base and crm_services.is_lid_value(base):
            targets.append((fallback_session, _wa_chat_id(base)))
        elif base:
            # WhatsApp routes on the full international number.
            variants = crm_services._phone_variants(base)
            full = next((v for v in sorted(variants) if v.startswith('974')), base)
            targets.append((fallback_session, _wa_chat_id(full)))
    return targets


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_chat_refresh(request, lead_id):
    """POST: pull this lead's chat straight from WAHA, then hand back the
    re-rendered message bubbles.

    The conversation panel is fed by the webhook, so a message that arrived
    while the bridge was down never appears no matter how often staff reload.
    This does what the inbox Resync does, scoped to one lead's chat(s) so it
    stays inside a request: fetch → upsert → re-render.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    lead = get_object_or_404(Lead, pk=lead_id)

    # Same gate as the panel itself — a platform account's thread carries auth
    # messages and must not be pulled into view here.
    if crm_services.wa_read_blocked(_lead_wa_identifiers(lead), request.user):
        return JsonResponse({'success': False, 'error': 'This chat is not readable here'}, status=403)

    # Resolve the same way the page does, but never persist: refreshing a panel
    # is not the staff member choosing a number.
    requested = request.POST.get('session') or request.GET.get('session') or ''
    wa_session, _options, _changed, _explicit = _lead_wa_session_choice(lead, requested, request.user)

    pulled = 0
    pull_error = ''
    fetched_any = False
    if getattr(settings, 'WAHA_API_KEY', ''):
        import time as _time
        from whatsapp.management.commands.backfill_waha import upsert_message, waha_get

        started = _time.monotonic()
        budget_s = 20  # nginx cuts the response off at 60s — stay well inside it
        for sess, chat_id in _lead_wa_chat_targets(lead, wa_session)[:3]:
            if _time.monotonic() - started > budget_s:
                break
            try:
                body = waha_get(
                    f'/api/{sess}/chats/{quote(chat_id, safe="")}/messages',
                    params={'limit': 50, 'downloadMedia': 'true'},
                    timeout=12,
                )
            except Exception as exc:
                logger.warning('crm: chat refresh failed for lead %s (%s/%s): %s',
                               lead.pk, sess, chat_id, exc)
                # A bridge that is down and a chat WAHA will not open are
                # different problems: the first is ours to fix, the second means
                # we asked this number for a thread it does not have. Saying
                # "bridge did not answer" for both sends staff chasing an
                # outage that is not happening.
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                pull_error = (
                    f'no WhatsApp thread for this lead on {sess}'
                    if status else 'WhatsApp bridge did not answer'
                )
                continue
            fetched_any = True
            if isinstance(body, dict) and isinstance(body.get('messages'), list):
                msgs = body['messages']
            elif isinstance(body, list):
                msgs = body
            else:
                msgs = []
            for m in msgs:
                if not isinstance(m, dict) or not m.get('id'):
                    continue
                try:
                    _obj, created = upsert_message(m, sess, chat_id)
                except Exception:
                    logger.exception('crm: chat refresh upsert failed for lead %s', lead.pk)
                    continue
                if created:
                    pulled += 1
    else:
        pull_error = 'WhatsApp bridge is not configured'

    # One target failing while another answered is not worth an error banner —
    # the panel below already has the messages.
    if fetched_any:
        pull_error = ''

    # Media bodies are downloaded by the per-minute archive_wa_media cron, so a
    # brand-new photo can land here as a link before its local copy exists.
    wa_messages, _wa_media = _lead_wa_conversation(lead, wa_session, request.user)
    html = render_to_string(
        'workforce/crm/parts/_lead_chat_messages.html',
        {'wa_messages': wa_messages, 'lead': lead},
        request=request,
    )
    return JsonResponse({
        'success': True,
        'html': html,
        'count': len(wa_messages),
        'new': pulled,
        'error': pull_error,
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_ai_summary(request, lead_id):
    """POST: generate the AI summary of the lead's conversation and persist it
    on the Lead. force=1 regenerates; otherwise an existing summary is returned."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    lead = get_object_or_404(Lead, pk=lead_id)

    if request.POST.get('force') != '1' and lead.ai_summary:
        return JsonResponse({'success': True, 'summary': lead.ai_summary, 'cached': True})

    wa_messages, _ = _lead_wa_conversation(lead, user=request.user)
    summary, error = crm_services.generate_lead_ai_summary(lead, wa_messages)
    if error:
        return JsonResponse({'success': False, 'error': error})

    lead.ai_summary = summary
    lead.ai_summary_at = timezone.now()
    lead.save(update_fields=['ai_summary', 'ai_summary_at', 'updated_at'])
    return JsonResponse({'success': True, 'summary': summary, 'cached': False})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_wa_media(request, lead_id, msg_id):
    """Stream a WAHA media file for a message in this lead's conversation.

    The nginx /waha/ proxy is htpasswd-gated for ops only, so CRM staff get
    media through this Django-auth proxy instead. The WAHA API key stays
    server-side."""
    from django.http import Http404

    lead = get_object_or_404(Lead, pk=lead_id)
    if not lead.phone and not lead.wa_link_values:
        raise Http404

    from whatsapp.models import WhatsAppMessage

    wa_q = _lead_wa_q(lead)
    if wa_q is None:
        raise Http404
    if crm_services.wa_read_blocked(_lead_wa_identifiers(lead), request.user):
        raise Http404
    msg = get_object_or_404(WhatsAppMessage.objects.filter(wa_q), pk=msg_id)
    return _stream_wa_media(msg)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_contact_search(request):
    """GET ?q=: typeahead search across the synced WhatsAppContact directory (phone or
    name), used by the lead-detail 'Link WhatsApp Chat' widget when auto-matching by
    the lead's stored phone missed a real chat (e.g. enquiry phone != WhatsApp number,
    or the chat is indexed by WhatsApp LID)."""
    q = request.GET.get('q', '').strip()
    if len(q) < 3:
        return JsonResponse({'results': []})

    from whatsapp.models import WhatsAppContact

    contacts = (
        WhatsAppContact.objects
        .filter(Q(phone__icontains=q) | Q(saved_name__icontains=q) | Q(push_name__icontains=q))
        .exclude(lid='')
        .order_by('-updated_at')[:15]
    )
    # `session` rides along so the link-chat POST can resolve the lid against
    # the number that actually issued it.
    results = [
        {'phone': c.phone, 'lid': c.lid, 'name': c.display_name, 'session': c.session}
        for c in contacts
    ]
    return JsonResponse({'results': results})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_link_chat(request, lead_id):
    """POST identifier=<phone|lid>: manually connect a lead to a WhatsApp chat when
    auto-matching by the lead's stored phone failed or picked the wrong number.
    Adds the number as one of the lead's linked numbers (LeadWaLink, optional
    `label` such as Owner/Office), then immediately pulls that chat's history in
    from WAHA (rather than waiting on the resync/cron sweep) so the conversation
    panel populates right away."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    lead = get_object_or_404(Lead, pk=lead_id)
    raw_identifier = request.POST.get('identifier', '').strip()
    identifier = crm_services.normalize_phone(raw_identifier)
    if not identifier:
        return JsonResponse({'success': False, 'error': 'A phone number or contact is required'}, status=400)

    from whatsapp.models import WhatsAppContact
    from whatsapp.waha_backfill import pull_chat_history
    from whatsapp import sessions as wa_sessions

    # Which number this chat lives on. The typeahead sends back the session of
    # the row the operator picked; a hand-typed phone falls back to the default.
    session = wa_sessions.normalize(request.POST.get('session'))
    # Adds a number rather than replacing one: a company can reach us from the
    # owner's phone, the office phone and more, each its own chat.
    label = (request.POST.get('label') or '').strip()[:40]
    crm_services.add_wa_link(lead, identifier, session=session, label=label, user=request.user)

    variants = crm_services._phone_variants(identifier)
    contact = (
        WhatsAppContact.objects
        .filter(session=session)
        .filter(Q(phone__in=list(variants)) | Q(lid=identifier))
        .exclude(lid='')
        .first()
    )
    chat_id_candidates = []
    if contact:
        chat_id_candidates.append(f'{contact.lid}@lid')
    elif len(identifier) >= 12:
        # Long digit string with no directory match is most likely a raw lid, not a phone.
        chat_id_candidates.append(f'{identifier}@lid')
    best_variant = next((v for v in variants if len(v) in (8, 11)), identifier)
    chat_id_candidates.append(f'{best_variant}@c.us')

    seen = inserted = 0
    counterparties = set()
    for chat_id in chat_id_candidates:
        try:
            seen, inserted, counterparties = pull_chat_history(chat_id, session=session)
        except Exception:
            logger.exception('crm: manual link backfill failed for lead %s via %s', lead.pk, chat_id)
            continue
        if seen:
            break

    # A phone-based chatId can resolve fine in WAHA while every message inside is
    # stamped with a privacy LID we have no directory entry for yet (see lead #2,
    # 2026-07-19) — if so, re-point the override at that LID so has_wa_chat actually
    # matches, instead of leaving it pointed at a phone the stored messages don't use.
    lid_counterparties = {c for c in counterparties if c.endswith('@lid')}
    if lid_counterparties:
        resolved_lid = next(iter(lid_counterparties)).replace('@lid', '')
        if resolved_lid and resolved_lid != identifier:
            crm_services.repoint_wa_link(lead, identifier, resolved_lid)

    LeadActivity.objects.create(
        lead=lead, activity_type=LeadActivity.TYPE_NOTE,
        body=(
            f'WhatsApp chat linked ({raw_identifier}{" — " + label if label else ""})'
            + (f' — {seen} message(s) pulled in' if seen else ' — no messages found on WhatsApp yet')
        ),
        created_by=request.user,
    )

    if not seen:
        return JsonResponse({
            'success': True, 'connected': False,
            'message': 'Saved, but no WhatsApp messages were found for that number yet.',
        })

    return JsonResponse({
        'success': True, 'connected': True,
        'messages_found': seen, 'messages_inserted': inserted,
        'message': f'Connected — {seen} message(s) pulled in.',
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_unlink_chat(request, lead_id):
    """POST identifier=<phone|lid>: detach one linked WhatsApp number from a lead."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    identifier = crm_services.normalize_phone(request.POST.get('identifier', ''))
    if not identifier:
        return JsonResponse({'success': False, 'error': 'Which number?'}, status=400)
    if not crm_services.remove_wa_link(lead, identifier):
        return JsonResponse({'success': False, 'error': 'That number is not linked to this lead.'}, status=404)
    LeadActivity.objects.create(
        lead=lead, activity_type=LeadActivity.TYPE_NOTE,
        body=f'WhatsApp number {identifier} unlinked', created_by=request.user,
    )
    return JsonResponse({'success': True})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_media(request, msg_id):
    """Stream WAHA media for any message — used by the inbox chat preview, where no
    lead exists yet. Staff-gated, and refuses attachments from a platform account's
    own conversation: a bare pk is otherwise enough to walk the whole media table."""
    from django.http import Http404

    from whatsapp.models import WhatsAppMessage
    msg = get_object_or_404(WhatsAppMessage, pk=msg_id)
    if crm_services.wa_read_blocked([msg.from_number, msg.to_number], request.user):
        logger.warning('crm: blocked WA media read for platform account by user %s', request.user.pk)
        raise Http404
    return _stream_wa_media(msg)


# A WhatsApp sender picks the mimetype of what they send us, and it is stored raw
# at whatsapp/waha_views.py:586. Echoing it back as the response Content-Type lets
# an outsider serve text/html or image/svg+xml from our own origin, where the CSP
# allows 'unsafe-inline' — script then runs in a staff session that reaches the
# payout and COD consoles. Only these types are ever served as themselves.
_WA_MEDIA_INLINE_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'audio/mpeg', 'audio/ogg', 'audio/opus', 'audio/mp4', 'audio/aac', 'audio/amr',
    'video/mp4', 'video/webm', 'video/3gpp',
    'application/pdf',
})


def _safe_media_type(raw_mime):
    """Map a sender-supplied mimetype onto something safe to serve.

    Anything not explicitly allowed — notably text/html, image/svg+xml and
    application/xhtml+xml — collapses to application/octet-stream so the browser
    downloads it instead of rendering it on our origin.
    """
    mime = (raw_mime or '').split(';')[0].strip().lower()
    return mime if mime in _WA_MEDIA_INLINE_TYPES else 'application/octet-stream'


def _stream_wa_media(msg):
    """Serve a message's media: local archive first, live WAHA fetch fallback."""
    import requests as http
    from django.http import Http404, StreamingHttpResponse

    from whatsapp.wa_chats_view import _extract_media, _waha_base

    msg_id = msg.pk
    # Local archive first — WAHA purges its own media copies within minutes,
    # so the live fetch below only works for very fresh messages.
    if msg.media_file:
        try:
            from django.http import FileResponse
            served_type = _safe_media_type(msg.media_mime)
            resp = FileResponse(
                msg.media_file.open('rb'),
                content_type=served_type,
                # Anything we would not render inline is forced to download.
                as_attachment=(served_type == 'application/octet-stream'),
            )
            resp['Cache-Control'] = 'private, max-age=86400'
            resp['X-Content-Type-Options'] = 'nosniff'
            return resp
        except Exception:
            logger.exception('crm: archived media read failed for msg %s', msg_id)

    media = _extract_media(msg) or {}
    url = media.get('url') or ''
    if not url:
        raise Http404
    # _extract_media rewrites to same-origin /waha/...; undo that for the
    # server-side fetch straight to the WAHA container. Any other host is
    # refused — the URL comes from webhook payload data, and fetching it
    # server-side with the API key attached would be an SSRF hole.
    if url.startswith('/waha/'):
        url = _waha_base() + url[len('/waha'):]
    elif not url.startswith(_waha_base() + '/'):
        logger.warning('crm: refusing non-WAHA media URL for msg %s', msg_id)
        raise Http404

    try:
        upstream = http.get(
            url,
            headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''},
            stream=True,
            timeout=30,
        )
    except Exception:
        logger.exception('crm: WAHA media fetch failed for msg %s', msg_id)
        raise Http404
    if upstream.status_code != 200:
        raise Http404

    served_type = _safe_media_type(
        media.get('mime') or upstream.headers.get('Content-Type', '')
    )
    resp = StreamingHttpResponse(upstream.iter_content(chunk_size=64 * 1024),
                                 content_type=served_type)
    if upstream.headers.get('Content-Length'):
        resp['Content-Length'] = upstream.headers['Content-Length']
    resp['Cache-Control'] = 'private, max-age=86400'
    resp['X-Content-Type-Options'] = 'nosniff'
    if served_type == 'application/octet-stream':
        resp['Content-Disposition'] = f'attachment; filename="wa-media-{msg_id}"'
    return resp


def _wa_sender_identifiers(raw_sender, session=None):
    """Identifier set for an inbox sender string (digits, JID, or @lid alias):
    all phone variants, @c.us JIDs, and the lid mapping both ways via the
    WhatsAppContact directory.

    `session` scopes the lid lookups: a lid is issued per linked device, so
    resolving one against the wrong session would attach a stranger's phone to
    this sender. None means the default session.
    """
    raw = (raw_sender or '').strip()
    digits = raw.split('@', 1)[0]
    if not digits:
        return set()
    idents = {raw, digits} if raw else {digits}

    try:
        from whatsapp.models import WhatsAppContact
        from whatsapp import sessions as wa_sessions
        scoped = WhatsAppContact.objects.filter(session=wa_sessions.normalize(session))
        phones = set()
        if raw.endswith('@lid'):
            idents.add(f'{digits}@lid')
            contact = scoped.filter(lid=digits).first()
            if contact and contact.phone:
                phones.update(crm_services._phone_variants(contact.phone))
        else:
            phones.update(crm_services._phone_variants(crm_services.normalize_phone(digits)))
            # Bare digits can be a phone OR an unsuffixed lid — try both.
            contact = (
                scoped.filter(phone__in=list(phones)).exclude(lid='').first()
                or scoped.filter(lid=digits).first()
            )
            if contact:
                if contact.lid:
                    idents.update({contact.lid, f'{contact.lid}@lid'})
                if contact.phone:
                    phones.update(crm_services._phone_variants(contact.phone))
        for p in phones:
            idents.update({p, f'{p}@c.us'})
    except Exception:
        logger.exception('crm: sender ident expansion failed for %s', raw_sender)
    return idents


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_chat_preview(request):
    """JSON conversation preview for an inbox sender (before any lead exists).

    GET ?sender=<from_number as shown in the inbox row>&session=<name> — returns
    the last 100 messages both directions with media annotations for the modal.
    Scoped to one session: the inbox row came from a specific number, and an
    @lid sender means nothing outside the session that issued it."""
    from whatsapp.models import WhatsAppMessage
    from whatsapp.wa_chats_view import _extract_media
    from whatsapp import sessions as wa_sessions

    session = wa_sessions.from_request(request)
    idents = _wa_sender_identifiers(request.GET.get('sender', ''), session=session)
    if not idents:
        return JsonResponse({'success': False, 'error': 'sender is required'}, status=400)

    # AUTHORIZATION, not filtering: `sender` comes straight from the query string, so
    # without this any CRM-capable staff member could read a platform user's own
    # conversation — including the password-reset codes we send them.
    blocked = crm_services.wa_read_blocked(idents, request.user)
    if blocked:
        logger.warning('crm: blocked WA chat read for platform account by user %s', request.user.pk)
        return JsonResponse({'success': False, 'error': blocked}, status=403)

    rows = list(
        WhatsAppMessage.objects
        .filter(session=session)
        .filter(Q(from_number__in=idents) | Q(to_number__in=idents))
        .order_by('-received_at', '-created_at')[:100]
    )[::-1]

    messages = []
    for row in rows:
        media = None
        try:
            media = _extract_media(row)
        except Exception:
            pass
        has_source = bool(row.media_file) or bool((media or {}).get('url'))
        kind = (
            _media_kind(row.media_mime or (media or {}).get('mime', ''), row.message_type)
            if has_source else ''
        )
        body = _clean_wa_body(row.body)
        if not body and not kind and row.message_type == 'text':
            continue
        messages.append({
            'direction': row.direction,
            'body': body,
            'type': row.message_type,
            'media_kind': kind,
            'media_url': reverse('workforce:crm_wa_media', args=[row.pk]) if kind else '',
            'time': (
                timezone.localtime(row.received_at).strftime('%d %b, %H:%M')
                if row.received_at else ''
            ),
        })
    return JsonResponse({'success': True, 'messages': messages})


def _lead_category(value):
    """A posted/queried category narrowed to a real one.

    Also what the sidebar reads (`crm_sidebar_board`) to decide whether CRM
    Business or CRM Driver owns a page that both pipelines share.
    """
    value = (value or '').strip()
    return value if value in {c for c, _ in Lead.CATEGORY_CHOICES} else Lead.CATEGORY_BUSINESS


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_create(request):
    """Manual lead creation form."""
    if request.method == 'POST':
        company_name = request.POST.get('company_name', '').strip()
        contact_name = request.POST.get('contact_name', '').strip()
        phone = crm_services.normalize_phone(request.POST.get('phone', ''))
        if not (company_name or contact_name or phone):
            context = {
                'page_title': 'New Lead',
                'staff_users': _staff_users(),
                'error': 'Provide at least a company, contact name, or phone number.',
                'form_data': request.POST,
                'category_choices': Lead.CATEGORY_CHOICES,
                'initial_category': _lead_category(request.POST.get('category')),
                'crm_sidebar_board': _lead_category(request.POST.get('category')),
            }
            return render(request, 'workforce/crm/lead_form.html', context)

        followup, date_error = _parse_followup_date(request.POST.get('next_followup_at'))
        if date_error:
            context = {
                'page_title': 'New Lead',
                'staff_users': _staff_users(),
                'error': date_error,
                'form_data': request.POST,
                'category_choices': Lead.CATEGORY_CHOICES,
                'initial_category': _lead_category(request.POST.get('category')),
                'crm_sidebar_board': _lead_category(request.POST.get('category')),
            }
            return render(request, 'workforce/crm/lead_form.html', context)

        category = request.POST.get('category', '').strip()
        if category not in {c for c, _ in Lead.CATEGORY_CHOICES}:
            category = Lead.CATEGORY_BUSINESS
        lead = Lead.objects.create(
            source=Lead.SOURCE_MANUAL,
            category=category,
            # Explicit, not the model default: the boards no longer share keys, so
            # falling back to 'new' would strand a driver card in Unsorted.
            stage=crm_services.initial_stage_key(category),
            company_name=company_name[:200],
            contact_name=contact_name[:100],
            phone=phone[:50],
            phone_2=crm_services.normalize_phone(request.POST.get('phone_2', ''))[:50],
            product_category=request.POST.get('product_category', '').strip()[:200],
            notes=request.POST.get('notes', '').strip(),
            next_followup_at=followup,
        )
        assigned_to_id = request.POST.get('assigned_to', '').strip()
        if assigned_to_id:
            try:
                lead.assigned_to = User.objects.get(pk=int(assigned_to_id))
                lead.save(update_fields=['assigned_to', 'updated_at'])
            except (User.DoesNotExist, ValueError):
                pass
        LeadActivity.objects.create(
            lead=lead, activity_type=LeadActivity.TYPE_NOTE,
            body='Lead created manually', created_by=request.user,
        )
        return redirect('workforce:crm_lead_detail', lead.pk)

    initial_category = _lead_category(request.GET.get('category'))
    context = {
        'page_title': 'New Lead',
        'staff_users': _staff_users(),
        'category_choices': Lead.CATEGORY_CHOICES,
        'initial_category': initial_category,
        'crm_sidebar_board': initial_category,
    }
    return render(request, 'workforce/crm/lead_form.html', context)


# ── Stage moves ──────────────────────────────────────────────────────────────
# One card or fifty, a stage move is the same act: it can rewrite a real driver's
# verification status and WhatsApp them. Both entry points below go through
# _apply_lead_stage so the department gate, the write-back and the pin rule can
# never drift apart between the board and the list's bulk bar.


def _write_back_denied(user, lead, target_stage):
    """The reason this user may not move a card into this column, or ''.

    A column that rewrites the driver's real verification status is the same
    privilege as the ops-only verification page (it activates vehicles and
    WhatsApps the applicant). The stage routes are reachable by Marketing, so the
    desk is re-checked here rather than letting a board or a bulk bar be a way
    around the department gate.
    """
    if lead.category != Lead.CATEGORY_DRIVER or not (target_stage and target_stage.write_back):
        return ''
    from core.departments import ADMIN, OPS, user_departments
    if user_departments(user) & {OPS, ADMIN}:
        return ''
    return (
        f'"{target_stage.label}" changes the driver\'s real application status '
        'and notifies them, so it needs the Operations desk. Ask ops to make '
        'this decision, or move the card to a column that does not write back.'
    )


def _apply_lead_stage(lead, new_stage, user, rejection_reason=''):
    """Move one lead into a column and run everything that goes with it.

    Returns {'ok': bool, 'error': str, 'status': int, 'warning': str,
             'synced_driver': str|None}. The caller decides how to report it —
    a JSON body for one card, a tally for a bulk run.
    """
    target_stage = crm_services.get_stage(lead.category, new_stage)

    denied = _write_back_denied(user, lead, target_stage)
    if denied:
        return {'ok': False, 'error': denied, 'status': 403, 'warning': '',
                'synced_driver': None}

    try:
        crm_services.set_lead_stage(lead, new_stage, user)
    except ValueError as exc:
        return {'ok': False, 'error': str(exc), 'status': 400, 'warning': '',
                'synced_driver': None}

    # Driver leads: moving into a decision column updates the real applicant
    synced_driver = None
    sync_failed = False
    try:
        driver = crm_services.sync_driver_status_from_lead(
            lead, user, rejection_reason=rejection_reason
        )
        synced_driver = driver.driver_id if driver else None
    except Exception:
        logger.exception('crm: driver status sync failed for lead %s', lead.pk)
        sync_failed = True

    # Staff were told "this will approve this driver" — if the write-back reached
    # nobody, say so instead of reporting a success that changed nothing.
    if target_stage and target_stage.write_back and not synced_driver:
        note = (
            'the driver record could not be updated (see server logs)' if sync_failed
            else 'no driver record matches this number, so nothing was sent to an applicant'
        )
        warning_prefix = f'The card moved, but {note}. '
    else:
        warning_prefix = ''

    # A manual move only needs pinning when it DISAGREES with the driver's application
    # status — checked after the write-back, so a column that just set the driver to
    # match (Approved, Rejected, back-to-queue) keeps auto-filing instead of freezing.
    conflict = crm_services.stage_move_conflict(lead, target_stage)
    warning = ''
    if conflict:
        crm_services.pin_lead_stage(lead, user, conflict)
        warning = (
            f'{conflict} The card is pinned here and will stay put — use "Resume '
            'auto-filing" on the lead page to hand it back to the application status.'
        )
    elif lead.stage_pinned:
        # It agrees again, so there is nothing left to protect it from.
        crm_services.unpin_lead_stage(lead, user)

    return {
        'ok': True,
        'error': '',
        'status': 200,
        'warning': f'{warning_prefix}{warning}'.strip(),
        'synced_driver': synced_driver,
    }


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_update_stage(request, lead_id):
    """AJAX: move a lead to a new pipeline stage (board drag-drop + detail page)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)

    result = _apply_lead_stage(
        lead,
        request.POST.get('stage', '').strip(),
        request.user,
        rejection_reason=request.POST.get('rejection_reason', '').strip(),
    )
    if not result['ok']:
        return JsonResponse({'success': False, 'error': result['error']},
                            status=result['status'])

    return JsonResponse({
        'success': True,
        'stage': lead.stage,
        'stage_display': lead.stage_label,
        'stage_swatch': lead.stage_swatch,
        'synced_driver': result['synced_driver'],
        'pinned': lead.stage_pinned,
        'warning': result['warning'],
    })


# A bulk move is deliberately capped. The bar acts on ticked rows only (never on
# "everything matching the filter" — see workforce/js/export-columns.js), and a
# page holds 50, so this is one page's worth with room for a wider per_page —
# not a lever that re-files the whole pipeline, or WhatsApps hundreds of drivers,
# in one click.
MAX_BULK_STAGE_LEADS = 100


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_bulk_stage(request):
    """AJAX: move every ticked lead on a list page into one stage.

    Same act as a board drag, repeated: it runs the identical helper per lead, so
    a write-back column still needs the Operations desk and still messages each
    matched applicant. Leads are looked up inside the posted category, so a
    hand-written id can never reach across into the other pipeline.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Malformed request'}, status=400)

    new_stage = str(data.get('stage') or '').strip()
    category = str(data.get('category') or '').strip()
    rejection_reason = str(data.get('rejection_reason') or '').strip()[:500]
    raw_ids = data.get('ids') or []
    if not isinstance(raw_ids, list):
        return JsonResponse({'success': False, 'error': 'Malformed request'}, status=400)

    if category not in {key for key, _label in Lead.CATEGORY_CHOICES}:
        return JsonResponse({'success': False, 'error': 'Unknown lead category'}, status=400)
    if not new_stage:
        return JsonResponse({'success': False, 'error': 'Pick a stage first.'}, status=400)
    if crm_services.get_stage(category, new_stage) is None:
        return JsonResponse({
            'success': False,
            'error': 'That stage is not a column on this board.',
        }, status=400)

    # Counted before anything is parsed: the message has to name what was actually
    # sent, and an unbounded list should not be walked just to reject it.
    if len(raw_ids) > MAX_BULK_STAGE_LEADS:
        return JsonResponse({
            'success': False,
            'error': (f'{len(raw_ids)} leads is more than one bulk move may carry — '
                      f'do it in batches of {MAX_BULK_STAGE_LEADS} or fewer.'),
        }, status=400)
    ids = {pk for pk in (safe_int(value, default=0) for value in raw_ids) if pk}
    if not ids:
        return JsonResponse({'success': False, 'error': 'Tick the leads you want to move.'}, status=400)

    leads = list(Lead.objects.filter(pk__in=ids, category=category))
    if not leads:
        return JsonResponse({'success': False, 'error': 'None of those leads are on this board.'},
                            status=404)

    moved, unchanged, notified = 0, 0, 0
    warnings, errors = [], []
    for lead in leads:
        if lead.stage == new_stage:
            unchanged += 1
            continue
        result = _apply_lead_stage(lead, new_stage, request.user,
                                  rejection_reason=rejection_reason)
        if not result['ok']:
            # One refusal applies to every lead in the run (the department gate is
            # about the column, not the card), so say it once and stop rather than
            # repeating it per row.
            if result['status'] == 403:
                return JsonResponse({'success': False, 'error': result['error']}, status=403)
            errors.append(f'#{lead.pk}: {result["error"]}')
            continue
        moved += 1
        if result['synced_driver']:
            notified += 1
        if result['warning']:
            warnings.append(f'#{lead.pk}: {result["warning"]}')

    label = crm_services.get_stage(category, new_stage).label
    parts = [f'{moved} lead{"" if moved == 1 else "s"} moved to “{label}”']
    if unchanged:
        parts.append(f'{unchanged} already there')
    if notified:
        parts.append(f'{notified} applicant{"" if notified == 1 else "s"} updated and notified')
    if errors:
        parts.append(f'{len(errors)} failed')

    return JsonResponse({
        'success': True,
        'message': ', '.join(parts) + '.',
        'moved': moved,
        'unchanged': unchanged,
        'notified': notified,
        # Capped: a pinned-card note per lead is the same sentence fifty times over.
        'warnings': warnings[:5],
        'warning_count': len(warnings),
        'errors': errors[:5],
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_unpin_stage(request, lead_id):
    """AJAX: hand a pinned driver card back to automatic filing."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    crm_services.unpin_lead_stage(lead, request.user)

    # Tell staff where it is about to go, so "resume" is not a blind action.
    moves_to = ''
    if lead.category == Lead.CATEGORY_DRIVER:
        stages = crm_services.board_stages(Lead.CATEGORY_DRIVER)
        driver = crm_services._driver_for_lead(lead)
        target = crm_stage_rules.target_stage_key(driver, stages) if driver else None
        if target and target != lead.stage:
            moves_to = next((s.label for s in stages if s.key == target), target)

    return JsonResponse({'success': True, 'pinned': False, 'moves_to': moves_to})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_move_board(request, lead_id):
    """POST category=business|driver: re-file a card on the other pipeline.

    The two boards share no stage keys, so the category can never move on its own —
    a business lead flipped to `driver` keeps a business stage and lands in the grey
    Unsorted lane. Re-homing the stage to the target board's entry column is part of
    the same write.

    Deliberately NOT routed through crm_services.set_lead_stage: that fires the
    marketing auto-flows, and filing a card on the right board is housekeeping the
    lead must not hear about. No driver write-back happens either — both entry
    columns carry a blank `write_back`.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)

    target = (request.POST.get('category') or '').strip()
    if target not in {c for c, _ in Lead.CATEGORY_CHOICES}:
        return JsonResponse({'success': False, 'error': 'Pick a board to move to.'}, status=400)
    if target == lead.category:
        return JsonResponse({'success': False, 'error': 'This card is already on that board.'},
                            status=400)

    # A converted client is not a driver applicant, and a merged card is not on a
    # board at all — both would make the move meaningless rather than wrong.
    if lead.converted_business_id:
        return JsonResponse({
            'success': False,
            'error': (f'This lead is already linked to Business #{lead.converted_business_id}, '
                      'so it belongs on the Business board. Unlink it first.'),
        }, status=400)
    if lead.merged_into_id:
        return JsonResponse({
            'success': False,
            'error': (f'This card is merged into #{lead.merged_into_id} and does not appear on a '
                      'board on its own. Un-merge it first, or move the card it sits inside.'),
        }, status=400)

    old_label = dict(Lead.CATEGORY_CHOICES).get(lead.category, lead.category)
    new_label = dict(Lead.CATEGORY_CHOICES)[target]
    old_stage_label = lead.stage_label

    lead.category = target
    lead.stage = crm_services.initial_stage_key(target)
    lead.stage_changed_at = timezone.now()
    lead.closed_at = None          # both boards' entry columns are open stages
    # Pinning only ever protects a driver card from its own auto-filing. A card that
    # has just arrived must follow the application status it now tracks.
    lead.stage_pinned = False
    lead.stage_pinned_at = None
    if target == Lead.CATEGORY_BUSINESS:
        # `driver` is the binding a driver card is *about*; on the business board it
        # would be a dangling claim on a real applicant.
        lead.driver = None
    # Full save, not update_fields: Lead.save() re-tags contact_name ZyBuz ⇄ ZyDrv so
    # the synced phone address book keeps matching the board.
    lead.save()

    # Absorbed cards render inside this one, so they follow it across rather than
    # keeping the old board's tag and a stage label from a pipeline they left.
    for child in lead.merged_children.all():
        child.category = target
        child.stage = lead.stage
        child.save()

    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_STAGE_CHANGE,
        body=(f'Moved from the {old_label} board to the {new_label} board — '
              f'{old_stage_label} → {lead.stage_label}'),
        created_by=request.user,
    )

    return JsonResponse({
        'success': True,
        'category': lead.category,
        'stage': lead.stage,
        'stage_display': lead.stage_label,
        'redirect': reverse('workforce:crm_lead_detail', args=[lead.pk]),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_update(request, lead_id):
    """AJAX: update assignee, follow-up date, notes, and contact fields."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)

    changes = []

    if 'assigned_to' in request.POST:
        assigned_to_id = request.POST.get('assigned_to', '').strip()
        if assigned_to_id == '':
            if lead.assigned_to_id is not None:
                lead.assigned_to = None
                changes.append(('assignment', 'Assignment cleared'))
        else:
            try:
                user = User.objects.get(pk=int(assigned_to_id))
                if lead.assigned_to_id != user.pk:
                    lead.assigned_to = user
                    changes.append((
                        'assignment',
                        f'Assigned to {user.get_full_name() or user.username}',
                    ))
            except (User.DoesNotExist, ValueError):
                pass

    if 'next_followup_at' in request.POST:
        new_date, date_error = _parse_followup_date(request.POST.get('next_followup_at'))
        if date_error:
            return JsonResponse({'success': False, 'error': date_error}, status=400)
        if new_date != lead.next_followup_at:
            lead.next_followup_at = new_date
            changes.append((
                'followup',
                f'Follow-up date set to {new_date.isoformat()}' if new_date else 'Follow-up date cleared',
            ))

    if 'notes' in request.POST:
        notes = request.POST.get('notes', '').strip()
        if notes != (lead.notes or ''):
            lead.notes = notes
            changes.append(('note', 'Notes updated'))

    for field, max_len in (('company_name', 200), ('contact_name', 100),
                           ('product_category', 200)):
        if field in request.POST:
            value = request.POST.get(field, '').strip()[:max_len]
            if value != getattr(lead, field):
                setattr(lead, field, value)
                changes.append(('note', f'{field.replace("_", " ").title()} updated'))

    for field, label in (('phone', 'Phone'), ('phone_2', '2nd mobile')):
        if field in request.POST:
            phone = crm_services.normalize_phone(request.POST.get(field, ''))[:50]
            if phone != getattr(lead, field):
                setattr(lead, field, phone)
                changes.append(('note', f'{label} updated'))

    if changes:
        lead.save()
        activity_type = changes[0][0] if len(changes) == 1 else LeadActivity.TYPE_NOTE
        if activity_type not in {t for t, _ in LeadActivity.TYPE_CHOICES}:
            activity_type = LeadActivity.TYPE_NOTE
        LeadActivity.objects.create(
            lead=lead, activity_type=activity_type,
            body='; '.join(body for _, body in changes),
            created_by=request.user,
        )

    return JsonResponse({
        'success': True,
        'changes': len(changes),
        'assigned_to': (lead.assigned_to.get_full_name() or lead.assigned_to.username)
                       if lead.assigned_to else '',
        'next_followup_at': lead.next_followup_at.isoformat() if lead.next_followup_at else '',
        # Echoed back so the contact card can repaint from what was stored rather
        # than from what was typed — the phone is normalised on the way in, so the
        # two differ whenever staff paste a +974 / spaced number.
        'contact': {
            'company_name': lead.company_name or '',
            'contact_name': lead.contact_name or '',
            'phone': lead.phone or '',
            'phone_2': lead.phone_2 or '',
            'product_category': lead.product_category or '',
        },
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_add_activity(request, lead_id):
    """AJAX: append a note/follow-up to the lead timeline."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'success': False, 'error': 'Activity text is required'}, status=400)
    activity_type = request.POST.get('activity_type', LeadActivity.TYPE_NOTE)
    if activity_type not in {t for t, _ in LeadActivity.TYPE_CHOICES}:
        activity_type = LeadActivity.TYPE_NOTE
    activity = LeadActivity.objects.create(
        lead=lead, activity_type=activity_type, body=body, created_by=request.user,
    )
    return JsonResponse({
        'success': True,
        'activity': {
            'id': activity.pk,
            'type': activity.activity_type,
            'type_display': activity.get_activity_type_display(),
            'body': activity.body,
            'created_by': request.user.get_full_name() or request.user.username,
            'created_at': timezone.localtime(activity.created_at).strftime('%d %b, %H:%M'),
        },
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_delete_activity(request, lead_id, activity_id):
    """AJAX: delete an activity (creator or superadmin only)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    activity = get_object_or_404(LeadActivity, pk=activity_id, lead_id=lead_id)
    is_superadmin = getattr(getattr(request.user, 'profile', None), 'is_superadmin', False)
    if activity.created_by_id != request.user.pk and not is_superadmin:
        return JsonResponse({'success': False, 'error': 'Not allowed'}, status=403)
    activity.delete()
    return JsonResponse({'success': True})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_link_business(request):
    """AJAX (business verification page): attach an open CRM lead to a real
    Business account. Marks the lead Won and logs who linked it."""
    from business.models import Business

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        lead_id = safe_int(request.POST.get('lead_id'), default=0, minimum=0)
        business_id = safe_int(request.POST.get('business_id'), default=0, minimum=0)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'lead_id and business_id are required'}, status=400)

    lead = get_object_or_404(Lead, pk=lead_id)
    business = get_object_or_404(Business, pk=business_id)
    if lead.category != Lead.CATEGORY_BUSINESS:
        return JsonResponse({'success': False, 'error': 'Driver leads cannot be linked to a business'}, status=400)

    try:
        linked, error = crm_services.link_lead_to_business(lead, business, request.user)
    except Exception:
        logger.exception('crm: link failed for lead %s -> business %s', lead_id, business_id)
        return JsonResponse({'success': False, 'error': 'Linking failed'}, status=500)
    if not linked:
        return JsonResponse({'success': False, 'error': error}, status=400)
    return JsonResponse({
        'success': True,
        'lead_id': lead.pk,
        'lead_url': reverse('workforce:crm_lead_detail', args=[lead.pk]),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_whatsapp_inbox(request):
    """Inbound WAHA senders not yet known: send them a form link, or dismiss.

    A conversation is deliberately NOT a lead here. The primary action sends the
    driver join form or the pricing enquiry link, and the CRM card is created by
    the submission itself — so a board column means "this person applied", not
    "this person said hello".
    """
    from workforce.views import paginate_queryset
    from whatsapp import sessions as wa_sessions

    waha_enabled = getattr(settings, 'WAHA_ENABLED', False)

    # Which of our numbers to show. Defaults to ALL of them: any number can
    # produce a lead, and hiding one behind a tab would silently lose them.
    # ?session=<name> narrows to one.
    wa_session_list = wa_sessions.list_sessions()
    requested = (request.GET.get('session', '') or '').strip()
    session_filter = (
        wa_sessions.normalize(requested)
        if requested and requested.lower() != 'all'
        else ''
    )

    # Live session status banner — which number the WAHA bridge is connected to
    waha_session = None
    try:
        from whatsapp.waha_views import fetch_waha_session_status
        waha_session = fetch_waha_session_status(session=session_filter or None)
    except Exception:
        logger.exception('crm: WAHA session status fetch failed')

    search = request.GET.get('search', '').strip()
    rows = wa_inbox.collect_senders(
        session_filter=session_filter, search=search, wa_session_list=wa_session_list,
    )

    page_obj = paginate_queryset(request, rows, items_per_page=25)

    from whatsapp.models import WhatsAppMessage as _WM
    for row in page_obj:
        last = (
            _WM.objects.filter(
                direction='inbound',
                session=row['session'],
                from_number=row['from_number'],
            )
            .order_by('-received_at').first()
        )
        row['last_body'] = _clean_wa_body(last.body)[:160] if last else ''
        row['last_type'] = last.message_type if last else ''
        icon_label = WA_MEDIA_LABELS.get(row['last_type'])
        if not row['last_body'] and icon_label:
            row['last_media_icon'], row['last_media_label'] = icon_label

    from urllib.parse import urlencode
    filter_params = {k: v for k, v in (('search', search), ('session', session_filter)) if v}
    context = {
        'page_title': 'WhatsApp Inbox',
        'page_obj': page_obj,
        'search': search,
        'waha_enabled': waha_enabled,
        'waha_session': waha_session,
        # Tab strip is only worth rendering once a second number is linked.
        'wa_sessions': wa_session_list if len(wa_session_list) > 1 else [],
        'wa_session_filter': session_filter,
        'per_page': request.GET.get('per_page', '25'),
        'filter_params': urlencode(filter_params) if filter_params else '',
    }
    return render(request, 'workforce/crm/whatsapp_inbox.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_promote(request):
    """AJAX: create (or reuse) a lead from an inbound WhatsApp number."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    phone = request.POST.get('phone', '').strip()
    category = (
        Lead.CATEGORY_DRIVER
        if request.POST.get('category') == Lead.CATEGORY_DRIVER
        else Lead.CATEGORY_BUSINESS
    )
    try:
        lead, created = crm_services.create_lead_from_wa_number(
            phone, request.user, category=category,
        )
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({
        'success': True,
        'created': created,
        'lead_id': lead.pk,
        'lead_url': reverse('workforce:crm_lead_detail', args=[lead.pk]),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_send_link(request):
    """AJAX: WhatsApp the driver join form or the pricing enquiry link to an inbound sender.

    The intended answer to an unknown sender, in place of filing them as a lead:
    a conversation is not an application. Sending the link creates nothing — the
    CRM card appears only when they actually submit the form, so the boards hold
    real applicants and real enquiries rather than everyone who ever said hello.

    Replies on the SAME number the sender wrote to. Routing by message section
    would answer a fleet-number enquiry from the marketing number, which reads to
    the recipient as a different company.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    from core import message_templates as msg_templates
    from crm import wa_triage
    from whatsapp import sessions as wa_sessions
    from whatsapp.waha_views import send_waha_text

    kind = 'driver' if request.POST.get('kind') == 'driver' else 'business'
    template_key = (
        msg_templates.CRM_WA_DRIVER_LINK if kind == 'driver'
        else msg_templates.CRM_WA_PRICING_LINK
    )

    # promotable_phone is the house rule for "digits we can actually ring back".
    # A sender still known only by an @lid normalizes to something that is not a
    # phone number at all, and sending there would invent a stranger's number.
    phone = wa_triage.promotable_phone(request.POST.get('phone', '').strip())
    if not phone:
        return JsonResponse({
            'success': False,
            'error': 'No callable number behind this sender — open the chat in WhatsApp '
                     'and send the link by hand.',
        }, status=400)

    body = msg_templates.render_template(
        template_key, contact_name=_wa_link_greeting_name(phone),
    )
    if body is None:
        label = msg_templates.get_template(template_key)['label']
        return JsonResponse({
            'success': False,
            'error': f'"{label}" is switched off on the Messages page — turn it back '
                     f'on to send it.',
        }, status=400)

    session = wa_sessions.normalize(request.POST.get('session', ''))
    ok, info = send_waha_text(phone, body, session=session)
    if not ok:
        return JsonResponse({
            'success': False,
            'error': info.get('error') or 'WhatsApp send failed',
        }, status=502)

    return JsonResponse({
        'success': True,
        'kind': kind,
        'sent_from': wa_sessions.sender_number(session),
    })


def _wa_link_greeting_name(phone):
    """First name to greet an inbox sender by, or '' to greet them plainly.

    A WhatsApp push name is whatever the sender typed into their own phone, so it
    is often a shop name, an emoji or a full sentence. Anything that does not read
    as a name is dropped rather than pasted into the greeting.
    """
    contact = crm_services._wa_contact_for_phone(phone)
    name = ((contact.display_name if contact else '') or '').strip()
    if not name or len(name) > 40:
        return ''
    first = name.split()[0]
    return first if first.replace('-', '').replace("'", '').isalpha() else ''


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_dismiss(request):
    """AJAX: mark an inbound WhatsApp number as not-a-lead (hidden from inbox)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    phone = request.POST.get('phone', '').strip()
    if not phone:
        return JsonResponse({'success': False, 'error': 'Phone required'}, status=400)
    # Store the digits-only form so '974...@c.us' and '+974 ...' variants all
    # collapse to one dismissal (lid-only senders keep their raw string).
    normalized = crm_services.normalize_phone(phone) or phone
    InboxDismissal.objects.get_or_create(
        phone=normalized[:50], defaults={'dismissed_by': request.user},
    )
    return JsonResponse({'success': True})


# The contact-directory refresh is far too slow to run inside a request: WAHA
# takes ~80s just to serialise the main number's ~22k-row directory, and nginx
# cuts the response off at 60s. The browser then receives an HTML 504 page and
# the Resync button dies on `r.json()` with "Unexpected token '<'". So it runs
# in a daemon thread and the JSON answer goes back immediately; the daily
# sync_wa_contacts cron remains the freshness backstop.
#
# The lock is per gunicorn worker (3 of them), so at worst three sweeps overlap
# — they are idempotent upserts, and it beats stacking one per click.
_CONTACT_SYNC_LOCK = threading.Lock()


def _contact_sync_worker(session_names):
    from django.db import connections
    try:
        from whatsapp.contacts import sync_contacts
        for session in session_names:
            try:
                res = sync_contacts(session=session)
                logger.info(
                    'crm resync: contacts %s -> %s new, %s updated',
                    session, res['created'], res['updated'],
                )
            except Exception:
                logger.exception('crm resync: contact sync failed for %s', session)
    finally:
        # A thread gets its own DB connection; leaving it open leaks a backend.
        connections.close_all()
        _CONTACT_SYNC_LOCK.release()


def _spawn_contact_sync(session_names):
    """Kick off the directory refresh off-request. Returns a status string."""
    if not _CONTACT_SYNC_LOCK.acquire(blocking=False):
        return 'already running'
    try:
        threading.Thread(
            target=_contact_sync_worker,
            args=(list(session_names),),
            name='crm-wa-contact-sync',
            daemon=True,
        ).start()
    except Exception:
        _CONTACT_SYNC_LOCK.release()
        logger.exception('crm resync: could not start contact sync thread')
        return 'failed to start'
    return 'running in background'


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_resync(request):
    """AJAX: pull recent WAHA chats into WhatsAppMessage so the inbox picks up
    senders whose messages never arrived via webhook (bridge downtime, etc.)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    # Like the webhook, this only needs the bridge configured — WAHA_ENABLED
    # gates order-notification routing, not the inbox.
    if not getattr(settings, 'WAHA_API_KEY', ''):
        return JsonResponse({'success': False, 'error': 'WAHA bridge is not configured'}, status=400)

    import time as _time
    from whatsapp.management.commands.backfill_waha import upsert_message, waha_get
    from whatsapp import sessions as wa_sessions

    # Sweeps every linked number: the inbox spans all of them, so resyncing
    # only one would leave the other's senders invisible. ?session=<name>
    # narrows it when an operator is chasing one number.
    requested = (request.POST.get('session') or request.GET.get('session') or '').strip()
    if requested and requested.lower() != 'all':
        session_names = [wa_sessions.normalize(requested)]
    else:
        session_names = [s['name'] for s in wa_sessions.list_sessions()]

    started = _time.monotonic()
    budget_s = 20  # nginx cuts the response off at 60s — stay well inside it

    scanned = 0
    inserted = 0
    partial = False
    listed_any = False
    for session in session_names:
        if _time.monotonic() - started > budget_s:
            partial = True
            break
        try:
            chats = waha_get(f'/api/{session}/chats', params={'limit': 40}, timeout=15)
            listed_any = True
        except Exception as exc:
            logger.warning('crm resync: chat list failed for %s: %s', session, exc)
            continue

        for chat in chats if isinstance(chats, list) else []:
            cid = chat.get('id') if isinstance(chat, dict) else None
            if isinstance(cid, dict):
                cid = cid.get('_serialized')
            if not cid or str(cid).endswith('@g.us'):
                continue  # inbox tracks direct senders only
            if _time.monotonic() - started > budget_s:
                partial = True
                break
            try:
                msgs = waha_get(
                    f'/api/{session}/chats/{cid}/messages',
                    params={'limit': 15, 'downloadMedia': 'false'},
                    timeout=10,
                )
            except Exception:
                continue
            scanned += 1
            for m in msgs if isinstance(msgs, list) else []:
                if not isinstance(m, dict) or not m.get('id'):
                    continue
                try:
                    _obj, created = upsert_message(m, session, cid)
                    if created:
                        inserted += 1
                except Exception:
                    logger.exception('crm resync: upsert failed for %s', m.get('id'))

    if not listed_any:
        return JsonResponse(
            {'success': False, 'error': 'WAHA unreachable — could not list chats'},
            status=502,
        )

    # Refresh the contact directory too, but never inside this request — see
    # _spawn_contact_sync for why. Messages (what the operator clicked for) are
    # already saved above; names catch up a minute later.
    contacts_sync = _spawn_contact_sync(session_names)

    return JsonResponse({
        'success': True,
        'chats_scanned': scanned,
        'new_messages': inserted,
        'partial': partial,
        'contacts_sync': contacts_sync,
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_contacts(request):
    """Synced WhatsApp contact directory — phone ↔ lid ↔ name reference.

    Defaults to rows with a name or address-book membership; ?all=1 shows the
    full directory (thousands of bare lid mappings).
    """
    from workforce.views import paginate_queryset
    from whatsapp.models import WhatsAppContact

    search = request.GET.get('search', '').strip()
    show_all = request.GET.get('all') == '1'

    qs = WhatsAppContact.objects.all()
    if search:
        qs = qs.filter(
            Q(phone__icontains=search) | Q(lid__icontains=search) |
            Q(saved_name__icontains=search) | Q(push_name__icontains=search)
        )
    elif not show_all:
        qs = qs.filter(
            Q(is_my_contact=True) | ~Q(saved_name='') | ~Q(push_name='')
        )
    qs = qs.order_by('-is_my_contact', '-updated_at')

    page_obj = paginate_queryset(request, qs, items_per_page=50)
    last_sync = (
        WhatsAppContact.objects.exclude(synced_at=None)
        .order_by('-synced_at').values_list('synced_at', flat=True).first()
    )

    from urllib.parse import urlencode
    params = {}
    if search:
        params['search'] = search
    if show_all:
        params['all'] = '1'
    context = {
        'page_title': 'WhatsApp Contacts',
        'page_obj': page_obj,
        'search': search,
        'show_all': show_all,
        # Only worth labelling the session once more than one number is linked.
        'wa_multi_session': (
            WhatsAppContact.objects.values('session').distinct().count() > 1
        ),
        'total_count': WhatsAppContact.objects.count(),
        'last_sync': last_sync,
        'per_page': request.GET.get('per_page', '50'),
        'filter_params': urlencode(params),
    }
    return render(request, 'workforce/crm/contacts.html', context)


def _render_crm_reports(request, category, template):
    """Scorecard for ONE pipeline. Every figure on the page — tiles, funnel, monthly
    intake, per-staff and per-source — is filtered to `category`, and the outcome
    keys are read off that board's own terminal columns, because the two boards name
    their outcomes differently ("Won"/"Lost" vs "Approved"/"Rejected") and used to be
    added together into a number that meant nothing."""
    today = timezone.localdate()
    leads = Lead.objects.filter(category=category)

    stage_counts = {
        row['stage']: row['n']
        for row in leads.values('stage').annotate(n=Count('id'))
    }
    rows = [
        {
            'key': stage.key,
            'label': stage.label,
            'count': stage_counts.get(stage.key, 0),
            'is_closed': stage.is_closed,
        }
        for stage in LeadStage.board_columns(category)
    ]
    if not rows:
        # Unseeded DB — fall back to the legacy business keys so the page still draws.
        rows = [
            {'key': key, 'label': label, 'count': stage_counts.get(key, 0), 'is_closed': False}
            for key, label in Lead.STAGE_CHOICES
        ]
    funnel = {
        'category': category,
        'rows': rows,
        'total': sum(r['count'] for r in rows),
        'peak': max((r['count'] for r in rows), default=0),
    }

    twelve_months_ago = (today.replace(day=1) - timedelta(days=365))
    monthly = (
        leads.filter(created_at__date__gte=twelve_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month', 'source')
        .annotate(n=Count('id'))
        .order_by('month')
    )
    months = sorted({row['month'].strftime('%Y-%m') for row in monthly})
    source_labels = dict(Lead.SOURCE_CHOICES)
    counts_by_source = {}
    for row in monthly:
        counts_by_source.setdefault(row['source'], {})[row['month'].strftime('%Y-%m')] = row['n']
    # Series in fixed SOURCE_CHOICES order so colors stay stable across filters
    monthly_chart = {
        'months': months,
        'series': [
            {'name': label,
             'data': [counts_by_source.get(key, {}).get(m, 0) for m in months]}
            for key, label in Lead.SOURCE_CHOICES
            if counts_by_source.get(key)
        ],
    }

    # This board's own outcome columns — the driver board calls them Approved and
    # Rejected, so neither the keys nor the words can be hardcoded.
    won_keys = crm_services.outcome_stage_keys('won', category)
    lost_keys = crm_services.outcome_stage_keys('lost', category)
    outcome_labels = {
        stage.outcome: stage.label
        for stage in reversed(LeadStage.board_columns(category)) if stage.outcome
    }
    won_label = outcome_labels.get('won', 'Won')
    lost_label = outcome_labels.get('lost', 'Lost')

    per_staff = []
    staff_rows = (
        leads.filter(assigned_to__isnull=False)
        .values('assigned_to__id', 'assigned_to__first_name',
                'assigned_to__last_name', 'assigned_to__username')
        .annotate(
            total=Count('id'),
            won=Count('id', filter=Q(stage__in=won_keys)),
            lost=Count('id', filter=Q(stage__in=lost_keys)),
        )
        .order_by('-total')
    )
    for row in staff_rows:
        closed = row['won'] + row['lost']
        name = (f"{row['assigned_to__first_name']} {row['assigned_to__last_name']}".strip()
                or row['assigned_to__username'])
        per_staff.append({
            'name': name,
            'total': row['total'],
            'won': row['won'],
            'lost': row['lost'],
            'win_rate': round(row['won'] * 100 / closed) if closed else None,
        })

    source_rows = (
        leads.values('source')
        .annotate(total=Count('id'), won=Count('id', filter=Q(stage__in=won_keys)))
        .order_by('-total')
    )
    per_source = [
        {
            'label': source_labels.get(row['source'], row['source']),
            'total': row['total'],
            'won': row['won'],
            'rate': round(row['won'] * 100 / row['total']) if row['total'] else 0,
        }
        for row in source_rows
    ]

    avg_days_to_close = None
    durations = [
        (lead.closed_at - lead.created_at).days
        for lead in leads.filter(closed_at__isnull=False).only('created_at', 'closed_at')
    ]
    if durations:
        avg_days_to_close = round(sum(durations) / len(durations), 1)

    total = leads.count()
    won = sum(n for key, n in stage_counts.items() if key in won_keys)
    lost = sum(n for key, n in stage_counts.items() if key in lost_keys)
    is_driver_report = category == Lead.CATEGORY_DRIVER
    context = {
        'page_title': 'Driver Reports' if is_driver_report else 'Business Reports',
        'report_category': category,
        'is_driver_report': is_driver_report,
        'won_label': won_label,
        'lost_label': lost_label,
        'total_count': total,
        'open_count': total - won - lost,
        'won_count': won,
        'lost_count': lost,
        'win_rate': round(won * 100 / (won + lost)) if (won + lost) else None,
        'avg_days_to_close': avg_days_to_close,
        'funnel': funnel,
        'monthly_chart': monthly_chart,
        'per_staff': per_staff,
        'per_source': per_source,
    }
    return render(request, template, context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_reports(request):
    """Business sales pipeline scorecard."""
    return _render_crm_reports(
        request, Lead.CATEGORY_BUSINESS, 'workforce/crm/crm_reports.html')


@login_required(login_url='/accounts/login/')
@staff_required
def crm_driver_reports(request):
    """Driver recruitment scorecard — its own page, its own numbers."""
    return _render_crm_reports(
        request, Lead.CATEGORY_DRIVER, 'workforce/crm/driver_reports.html')


# ── Driver map ──────────────────────────────────────────────────────────────
#: Where the pipeline actually is on the ground. The pin comes from the location the
#: applicant's browser captured when they submitted at /join_us/driver/, which lives
#: on the Driver row as driver_meta['registration_location'].
QATAR_BBOX = (24.4, 50.6, 26.3, 51.8)   # lat_min, lng_min, lat_max, lng_max
DRIVER_MAP_PIN_LIMIT = 800


def _lead_map_point(lead, stage_labels, stage_outcomes):
    """One pin, or None when this lead has no usable location.

    Leads are bound to their Driver row by FK, never by phone — see the driver
    identity notes. No driver bound means no registration capture to plot.
    """
    driver = lead.driver
    if not driver:
        return None
    loc = (driver.driver_meta or {}).get('registration_location') or {}
    try:
        lat, lng = float(loc.get('lat')), float(loc.get('lng'))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None

    profile = getattr(driver, 'profile', None)
    name = (strip_tags(lead.contact_name)
            or (profile.user.get_full_name() if profile and profile.user else '')
            or lead.phone or driver.driver_code or '—')
    in_qatar = (QATAR_BBOX[0] <= lat <= QATAR_BBOX[2]
                and QATAR_BBOX[1] <= lng <= QATAR_BBOX[3])

    return {
        'lat': lat,
        'lng': lng,
        'in_qatar': in_qatar,
        'name': name,
        'phone': lead.phone or '',
        'code': driver.driver_code or '',
        'stage': lead.stage,
        'stage_label': stage_labels.get(lead.stage, lead.stage),
        # Set in bulk by _annotate_driver_vehicles — one query for the whole map.
        'vehicle': getattr(lead, 'vehicle_label', '') or '',
        # Colour axis: still live, hired, or gone. The stage itself is in the popup.
        'outcome': stage_outcomes.get(lead.stage, ''),
        'account': driver.get_driver_status_display(),
        'assigned': (lead.assigned_to.get_full_name() or lead.assigned_to.username)
                    if lead.assigned_to else '',
        'captured_at': (loc.get('captured_at') or '')[:10],
        'accuracy_m': str(loc.get('accuracy_m') or ''),
        'url': reverse('workforce:crm_lead_detail', args=[lead.id]),
    }


@login_required(login_url='/accounts/login/')
@staff_required
def crm_driver_map(request):
    """Live map of the driver pipeline — one pin per applicant, where they signed up.

    Built from the whole filtered set rather than a page of it, so the map answers
    "where are my applicants" instead of "where is page 1".
    """
    from fleet.models import DRIVER_STATUS_CHOICES

    # Every facet on this bar is a checkbox multi-select, so each one reads its
    # values with getlist — including the two the shared helper owns.
    leads, search, source_filter, assigned_filter, _category = _filtered_leads(
        request, multi_facets=True)
    leads = leads.filter(category=Lead.CATEGORY_DRIVER)

    stages = list(crm_services.board_stages(Lead.CATEGORY_DRIVER))
    stage_labels = {st.key: st.label for st in stages}
    stage_outcomes = {st.key: (st.outcome or '') for st in stages}

    # Applied whenever one is given, not only when it matches a configured column:
    # validating against the board made an unrecognised stage fall through and show
    # every lead, which reads as "the filter did nothing".
    # getlist, not get: the picker is a multi-select, so "Uploads Done + Applied"
    # is one map rather than two trips. A single ?stage=x still works unchanged.
    stage_filters = [v.strip() for v in request.GET.getlist('stage') if v.strip()]
    if stage_filters:
        leads = leads.filter(stage__in=stage_filters)

    # Vehicle and account status: the two things a recruiter narrows by before
    # asking "where are they". Vehicle resolves to the SAME row the pin popup and
    # the board chip show — newest registration wins — so filtering by Bike can
    # never leave a pin labelled Car on the map.
    vehicle_filter = [v.strip() for v in request.GET.getlist('vehicle') if v.strip()]
    account_filter = [v.strip() for v in request.GET.getlist('account') if v.strip()]

    # Shared with the driver leads table (_apply_vehicle_filter): "No vehicle on
    # file" is a pick like any other, so Bike + none is one OR'd question rather
    # than two impossible AND'd ones.
    leads = _apply_vehicle_filter(leads, vehicle_filter)

    if account_filter:
        leads = leads.filter(driver__driver_status__in=account_filter)

    # Only leads bound to a driver can carry a registration capture at all.
    leads = (leads.select_related('driver', 'driver__profile', 'driver__profile__user')
             .order_by('-created_at'))

    total = leads.count()
    plotted = list(leads[:DRIVER_MAP_PIN_LIMIT])
    # Same source as the board chip and the list column, so a pin, a card and a row
    # never disagree about what someone drives.
    _annotate_driver_vehicles(plotted)

    points, no_driver, no_location = [], 0, 0
    for lead in plotted:
        if not lead.driver_id:
            no_driver += 1
            continue
        point = _lead_map_point(lead, stage_labels, stage_outcomes)
        if point is None:
            no_location += 1
            continue
        points.append(point)

    outside = sum(1 for p in points if not p['in_qatar'])

    context = {
        'map_points': points,
        'pin_count': len(points),
        'lead_total': total,
        'no_driver_count': no_driver,
        'no_location_count': no_location,
        'outside_count': outside,
        'truncated': total > DRIVER_MAP_PIN_LIMIT,
        'pin_limit': DRIVER_MAP_PIN_LIMIT,
        'stages': stages,
        'stage_filters': stage_filters,
        'vehicle_filter': vehicle_filter,
        'account_filter': account_filter,
        'vehicle_choices': _vehicle_filter_choices(),
        'account_choices': DRIVER_STATUS_CHOICES,
        'search': search,
        'source_filter': source_filter,
        'assigned_filter': assigned_filter,
        'source_choices': Lead.SOURCE_CHOICES,
    }
    return render(request, 'workforce/crm/driver_map.html', context)


# ── Board columns (LeadStage) — staff-managed pipeline configuration ─────────
# Adding a column used to mean editing DRIVER_STAGE_LABELS + a migration. These
# four views let ops do it from the UI: label, order, colour, terminal-ness, how
# long closed cards linger, and (driver board) which applicant condition files a
# card there automatically.

def _stage_board(request):
    """Which board is being configured. Defaults to the business pipeline."""
    board = (request.GET.get('board') or request.POST.get('board') or '').strip()
    valid = {c for c, _ in Lead.CATEGORY_CHOICES}
    return board if board in valid else Lead.CATEGORY_BUSINESS


# Each board configures its columns on its own page, so a save/delete/reorder
# posted from one desk never bounces staff onto the other one.
STAGE_PAGE_BY_BOARD = {
    Lead.CATEGORY_BUSINESS: 'workforce:crm_stages_manage',
    Lead.CATEGORY_DRIVER: 'workforce:crm_driver_stages_manage',
}


def _stages_redirect(board):
    return redirect(reverse(STAGE_PAGE_BY_BOARD.get(board, 'workforce:crm_stages_manage')))


def _clean_stage_key(raw, label):
    """Slugified, <=20 chars (Lead.stage's max_length). Falls back to the label."""
    from django.utils.text import slugify
    key = slugify(raw or label or '').replace('-', '_')[:20].strip('_')
    return key


@login_required(login_url='/accounts/login/')
@staff_required
def crm_stages_manage(request):
    """Business board columns — /workforce/crm/stages/."""
    return _stages_manage(request, Lead.CATEGORY_BUSINESS)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_driver_stages_manage(request):
    """Driver board columns — /workforce/crm/driver/stages/.

    A separate page, not a tab: recruitment columns carry auto-file rules and a
    write-back to the driver's real verification status, none of which exist on
    the sales board, so the two consoles show different controls entirely.
    """
    return _stages_manage(request, Lead.CATEGORY_DRIVER)


def _stages_manage(request, board):
    """Configure one board's kanban columns: list every column with its rules and
    lead count, plus the add form."""
    stages = list(LeadStage.objects.filter(category=board).order_by('position', 'pk'))

    counts = {
        row['stage']: row['n']
        for row in Lead.objects.filter(category=board).values('stage').annotate(n=Count('id'))
    }
    known = {s.key for s in stages}
    rows = [
        {
            'stage': stage,
            'lead_count': counts.get(stage.key, 0),
            'rule_labels': [crm_stage_rules.RULE_LABELS.get(r, r) for r in (stage.auto_rules or [])],
        }
        for stage in stages
    ]
    orphan_count = sum(n for key, n in counts.items() if key not in known)

    is_driver_board = board == Lead.CATEGORY_DRIVER
    context = {
        'page_title': 'Driver Board Columns' if is_driver_board else 'Sales Board Columns',
        'board': board,
        'is_driver_board': is_driver_board,
        'rows': rows,
        'orphan_count': orphan_count,
        'rule_groups': crm_stage_rules.RULE_GROUPS,
        'swatch_choices': LeadStage.SWATCH_CHOICES,
        'outcome_choices': LeadStage.OUTCOME_CHOICES,
        'write_back_choices': LeadStage.WRITE_BACK_CHOICES,
        'next_position': (stages[-1].position + 1) if stages else 1,
        'move_targets': [(s.key, s.label) for s in stages],
    }
    template = ('workforce/crm/driver_stages_manage.html' if is_driver_board
                else 'workforce/crm/stages_manage.html')
    return render(request, template, context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_stage_save(request):
    """POST: create a column, or update an existing one (stage_id present)."""
    board = _stage_board(request)
    if request.method != 'POST':
        return _stages_redirect(board)

    stage_id = (request.POST.get('stage_id') or '').strip()
    label = (request.POST.get('label') or '').strip()
    if not label:
        messages.error(request, 'A column needs a name.')
        return _stages_redirect(board)

    stage = None
    if stage_id:
        stage = LeadStage.objects.filter(pk=stage_id, category=board).first()
        if stage is None:
            messages.error(request, 'That column no longer exists.')
            return _stages_redirect(board)

    rules = [r for r in request.POST.getlist('auto_rules') if r in crm_stage_rules.VALID_RULES]
    write_back = (request.POST.get('write_back') or '').strip()
    if write_back not in {c for c, _ in LeadStage.WRITE_BACK_CHOICES}:
        write_back = ''
    swatch = (request.POST.get('dot_swatch') or 'grey').strip()
    if swatch not in {c for c, _ in LeadStage.SWATCH_CHOICES}:
        swatch = 'grey'

    # Only a terminal column can be a win or a loss — an in-progress column that
    # kept a stale outcome would be counted in the win rate while still open.
    outcome = (request.POST.get('outcome') or '').strip()
    if outcome not in {c for c, _ in LeadStage.OUTCOME_CHOICES}:
        outcome = ''
    if request.POST.get('is_closed') != '1':
        outcome = ''

    hide_after = (request.POST.get('hide_after_days') or '').strip()
    try:
        hide_after_days = int(hide_after) if hide_after else None
        if hide_after_days is not None and hide_after_days < 1:
            hide_after_days = None
    except ValueError:
        hide_after_days = None

    try:
        position = safe_int(request.POST.get('position'), default=0, minimum=0, maximum=100000)
    except ValueError:
        position = 0

    confirm_text = (request.POST.get('confirm_text') or '').strip()[:120]
    # A column that rewrites a driver's real status (and messages them) must always
    # prompt — the board's guard is driven by this text, so a blank one would approve
    # or reject a real applicant on a stray drag with no dialog at all.
    if write_back and not confirm_text:
        confirm_text = f'move this driver to "{label[:60]}"'

    fields = {
        'label': label[:60],
        'position': max(position, 0),
        'is_closed': request.POST.get('is_closed') == '1',
        'hide_after_days': hide_after_days,
        'is_fallback': request.POST.get('is_fallback') == '1',
        'auto_rules': rules,
        'write_back': write_back,
        'confirm_text': confirm_text,
        'needs_reason': request.POST.get('needs_reason') == '1',
        'outcome': outcome,
        'dot_swatch': swatch,
        'is_active': request.POST.get('is_active') == '1',
    }
    # Only the business form carries crm_status; a driver form must not blank it.
    if 'crm_status' in request.POST:
        fields['crm_status'] = (request.POST.get('crm_status') or '').strip()[:20]

    if stage is None:
        key = _clean_stage_key(request.POST.get('key'), label)
        if not key:
            messages.error(request, 'Could not build a key from that name — use letters or numbers.')
            return _stages_redirect(board)
        if LeadStage.objects.filter(category=board, key=key).exists():
            messages.error(request, f'A column with the key "{key}" already exists on this board.')
            return _stages_redirect(board)

        # Rules are evaluated right-to-left, so a column created at the far end would
        # silently outrank Approved/Rejected. Land new columns just BEFORE the first
        # outcome column instead, and say so, rather than handing staff maximum
        # precedence by default.
        if not fields['is_closed']:
            first_closed = (
                LeadStage.objects.filter(category=board, is_closed=True)
                .order_by('position').first()
            )
            if first_closed and fields['position'] >= first_closed.position:
                fields['position'] = first_closed.position
                LeadStage.objects.filter(
                    category=board, position__gte=first_closed.position
                ).update(position=models.F('position') + 1)
                messages.info(
                    request,
                    f'Placed "{label}" before "{first_closed.label}" — columns are matched '
                    'from the right, so anything after an outcome column would outrank it. '
                    'Use the arrows to move it if you meant somewhere else.',
                )

        stage = LeadStage.objects.create(category=board, key=key, **fields)
        cache.delete(STAGE_CACHE_KEY)
        messages.success(request, f'Column "{stage.label}" added.')
    else:
        # The key is what Lead.stage stores, so it is never editable — renaming a
        # column changes its label only and no card has to move.
        for name, value in fields.items():
            setattr(stage, name, value)
        stage.save()
        messages.success(request, f'Column "{stage.label}" updated.')

    # Exactly one fallback per board, or reconcile has nowhere to put an
    # unmatched driver.
    if stage.is_fallback:
        LeadStage.objects.filter(category=board).exclude(pk=stage.pk).update(is_fallback=False)
        cache.delete(STAGE_CACHE_KEY)
    elif board == Lead.CATEGORY_DRIVER and not LeadStage.objects.filter(
        category=board, is_fallback=True, is_active=True
    ).exists():
        # Without an active catch-all, an unmatched driver silently lands in whatever
        # column happens to be leftmost. Put it back rather than leave the board in
        # that state.
        stage.is_fallback = True
        stage.save(update_fields=['is_fallback', 'updated_at'])
        messages.warning(
            request,
            f'"{stage.label}" has been kept as the catch-all — every driver board needs '
            'exactly one, or applicants that match no column would be filed at random. '
            'Set the catch-all on another column first if you want to move it.',
        )
    return _stages_redirect(board)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_stage_delete(request):
    """POST: delete a staff-created column, optionally moving its cards first."""
    board = _stage_board(request)
    if request.method != 'POST':
        return _stages_redirect(board)

    stage = LeadStage.objects.filter(pk=(request.POST.get('stage_id') or '').strip(),
                                     category=board).first()
    if stage is None:
        messages.error(request, 'That column no longer exists.')
        return _stages_redirect(board)
    if stage.is_system:
        messages.error(
            request,
            f'"{stage.label}" is a built-in column and cannot be deleted. '
            'Untick "Show on board" to hide it instead.',
        )
        return _stages_redirect(board)

    occupied = Lead.objects.filter(category=board, stage=stage.key)
    move_to = (request.POST.get('move_to') or '').strip()
    count = occupied.count()
    if count:
        target = LeadStage.objects.filter(category=board, key=move_to).exclude(pk=stage.pk).first()
        if target is None:
            messages.error(
                request,
                f'"{stage.label}" still holds {count} lead(s). Pick a column to move them to first.',
            )
            return _stages_redirect(board)
        now = timezone.now()
        occupied.update(
            stage=target.key,
            stage_changed_at=now,
            closed_at=now if target.is_closed else None,
            updated_at=now,
        )
        messages.info(request, f'Moved {count} lead(s) to "{target.label}".')

    label = stage.label
    stage.delete()
    messages.success(request, f'Column "{label}" deleted.')
    return _stages_redirect(board)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_stage_reorder(request):
    """POST: persist a new left-to-right column order (order=<id>,<id>,...)."""
    board = _stage_board(request)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    raw = (request.POST.get('order') or '').strip()
    ids = [part for part in raw.split(',') if part.strip().isdigit()]
    if not ids:
        return JsonResponse({'success': False, 'error': 'No order supplied'}, status=400)

    stages = {str(s.pk): s for s in LeadStage.objects.filter(category=board)}
    changed = []
    for index, pk in enumerate(ids, start=1):
        stage = stages.get(pk)
        if stage and stage.position != index:
            stage.position = index
            changed.append(stage)
    if changed:
        LeadStage.objects.bulk_update(changed, ['position'])
        cache.delete(STAGE_CACHE_KEY)
    return JsonResponse({'success': True, 'moved': len(changed)})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_merge(request, lead_id):
    """POST duplicate_id=<pk>: fold another card for the same prospect into this one.

    Both rows survive — the absorbed card keeps its own source, inquiry link and
    timeline and renders inside this one, so a wrong merge can be undone."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    primary = get_object_or_404(Lead, pk=lead_id)
    duplicate = Lead.objects.filter(pk=(request.POST.get('duplicate_id') or '').strip()).first()
    if duplicate is None:
        return JsonResponse({'success': False, 'error': 'Pick a lead to merge.'}, status=400)

    ok, error = crm_services.merge_leads(primary, duplicate, request.user)
    if not ok:
        return JsonResponse({'success': False, 'error': error}, status=400)
    return JsonResponse({
        'success': True,
        'merged_id': duplicate.pk,
        'children': primary.merged_children.count(),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_merge_adopt(request, lead_id):
    """POST child_id=<pk>, field=<name>: take one value from an absorbed card onto this one."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    parent = get_object_or_404(Lead, pk=lead_id)
    child = parent.merged_children.filter(pk=(request.POST.get('child_id') or '').strip()).first()
    if child is None:
        return JsonResponse({'success': False, 'error': 'That card is not merged into this one.'},
                            status=400)
    ok, error = crm_services.adopt_merged_value(
        parent, child, (request.POST.get('field') or '').strip(), request.user)
    if not ok:
        return JsonResponse({'success': False, 'error': error}, status=400)
    return JsonResponse({'success': True})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_unmerge(request, lead_id):
    """POST child_id=<pk>: put an absorbed card back on the board on its own."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    parent = get_object_or_404(Lead, pk=lead_id)
    child = parent.merged_children.filter(pk=(request.POST.get('child_id') or '').strip()).first()
    if child is None:
        return JsonResponse({'success': False, 'error': 'That card is not merged into this one.'},
                            status=400)

    ok, error = crm_services.unmerge_lead(child, request.user)
    if not ok:
        return JsonResponse({'success': False, 'error': error}, status=400)
    return JsonResponse({'success': True, 'child_id': child.pk})
