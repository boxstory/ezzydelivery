# Purpose: Staff-facing CRM views — leads kanban board, list, detail, manual create, stage/field updates, WAHA inbox, convert-to-business, reports.
# Used by: workforce/urls.py (crm/... routes); templates in workforce/templates/workforce/crm/.
# Notes: Business logic lives in crm/services.py; JSON endpoints mirror the pricing_inquiry_update_status fetch-POST pattern.

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.decorators import staff_required
from crm import services as crm_services
from crm.models import InboxDismissal, Lead, LeadActivity

logger = logging.getLogger(__name__)

BOARD_CLOSED_WINDOW_DAYS = 30


def _staff_users():
    return User.objects.filter(is_staff=True).order_by('first_name', 'username')


def _filtered_leads(request):
    """Shared filter logic for board + list."""
    leads = Lead.objects.select_related('assigned_to', 'converted_business')

    search = request.GET.get('search', '').strip()
    if search:
        leads = leads.filter(
            Q(company_name__icontains=search) |
            Q(contact_name__icontains=search) |
            Q(phone__icontains=search) |
            Q(product_category__icontains=search)
        )

    source_filter = request.GET.get('source', '').strip()
    if source_filter:
        leads = leads.filter(source=source_filter)

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

    return leads, search, source_filter, assigned_filter


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_board(request):
    """Kanban pipeline board grouped by stage."""
    leads, search, source_filter, assigned_filter = _filtered_leads(request)

    closed_cutoff = timezone.now() - timedelta(days=BOARD_CLOSED_WINDOW_DAYS)
    leads = leads.filter(
        Q(closed_at__isnull=True) | Q(closed_at__gte=closed_cutoff)
    ).order_by('-created_at')

    by_stage = {key: [] for key, _ in Lead.STAGE_CHOICES}
    for lead in leads:
        by_stage.setdefault(lead.stage, []).append(lead)

    columns = [
        {'key': key, 'label': label, 'leads': by_stage[key], 'count': len(by_stage[key])}
        for key, label in Lead.STAGE_CHOICES
    ]

    context = {
        'page_title': 'Leads Board',
        'columns': columns,
        'search': search,
        'source_filter': source_filter,
        'assigned_filter': assigned_filter,
        'staff_users': _staff_users(),
        'source_choices': Lead.SOURCE_CHOICES,
        'closed_window_days': BOARD_CLOSED_WINDOW_DAYS,
        'today': timezone.localdate(),
    }
    return render(request, 'workforce/crm/leads_board.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_list(request):
    """Filterable table of all leads."""
    from workforce.views import paginate_queryset

    leads, search, source_filter, assigned_filter = _filtered_leads(request)

    stage_filter = request.GET.get('stage', '').strip()
    if stage_filter:
        leads = leads.filter(stage=stage_filter)

    overdue_filter = request.GET.get('overdue', '').strip()
    if overdue_filter == '1':
        leads = leads.filter(
            next_followup_at__lt=timezone.localdate()
        ).exclude(stage__in=Lead.CLOSED_STAGES)

    leads = leads.order_by('-created_at')

    total_count = Lead.objects.count()
    open_count = Lead.objects.exclude(stage__in=Lead.CLOSED_STAGES).count()
    overdue_count = (
        Lead.objects.filter(next_followup_at__lt=timezone.localdate())
        .exclude(stage__in=Lead.CLOSED_STAGES).count()
    )
    won_count = Lead.objects.filter(stage=Lead.STAGE_WON).count()

    page_obj = paginate_queryset(request, leads, items_per_page=50)

    context = {
        'page_title': 'Leads',
        'page_obj': page_obj,
        'search': search,
        'source_filter': source_filter,
        'assigned_filter': assigned_filter,
        'stage_filter': stage_filter,
        'overdue_filter': overdue_filter,
        'staff_users': _staff_users(),
        'stage_choices': Lead.STAGE_CHOICES,
        'source_choices': Lead.SOURCE_CHOICES,
        'total_count': total_count,
        'open_count': open_count,
        'overdue_count': overdue_count,
        'won_count': won_count,
        'today': timezone.localdate(),
    }
    return render(request, 'workforce/crm/leads_list.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_detail(request, lead_id):
    """Lead detail: source summary, editors, activity timeline, WA chat snippet."""
    lead = get_object_or_404(
        Lead.objects.select_related(
            'assigned_to', 'converted_business', 'pricing_enquiry', 'whatsapp_inquiry'
        ),
        pk=lead_id,
    )

    wa_messages = []
    if getattr(settings, 'WAHA_ENABLED', False) and lead.phone:
        try:
            from whatsapp.models import WhatsAppMessage
            wa_messages = list(
                WhatsAppMessage.objects
                .filter(Q(from_number=lead.phone) | Q(to_number=lead.phone))
                .exclude(body='')
                .order_by('-received_at', '-created_at')[:10]
            )[::-1]
        except Exception:
            logger.exception('crm: failed to load WA messages for lead %s', lead.pk)

    context = {
        'page_title': f'Lead – {lead.company_name or lead.contact_name or lead.phone}',
        'lead': lead,
        'activities': lead.activities.select_related('created_by').order_by('-created_at'),
        'staff_users': _staff_users(),
        'stage_choices': Lead.STAGE_CHOICES,
        'wa_messages': wa_messages,
        'today': timezone.localdate(),
    }
    return render(request, 'workforce/crm/lead_detail.html', context)


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
            }
            return render(request, 'workforce/crm/lead_form.html', context)

        lead = Lead.objects.create(
            source=Lead.SOURCE_MANUAL,
            company_name=company_name[:200],
            contact_name=contact_name[:100],
            phone=phone[:50],
            product_category=request.POST.get('product_category', '').strip()[:200],
            notes=request.POST.get('notes', '').strip(),
            next_followup_at=request.POST.get('next_followup_at') or None,
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

    context = {'page_title': 'New Lead', 'staff_users': _staff_users()}
    return render(request, 'workforce/crm/lead_form.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_update_stage(request, lead_id):
    """AJAX: move a lead to a new pipeline stage (board drag-drop + detail page)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    new_stage = request.POST.get('stage', '').strip()
    try:
        crm_services.set_lead_stage(lead, new_stage, request.user)
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({
        'success': True,
        'stage': lead.stage,
        'stage_display': lead.get_stage_display(),
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
        raw = request.POST.get('next_followup_at', '').strip()
        new_date = raw or None
        old_date = lead.next_followup_at.isoformat() if lead.next_followup_at else None
        if new_date != old_date:
            lead.next_followup_at = new_date
            changes.append((
                'followup',
                f'Follow-up date set to {new_date}' if new_date else 'Follow-up date cleared',
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

    if 'phone' in request.POST:
        phone = crm_services.normalize_phone(request.POST.get('phone', ''))[:50]
        if phone != lead.phone:
            lead.phone = phone
            changes.append(('note', 'Phone updated'))

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
def crm_lead_convert(request, lead_id):
    """AJAX: convert a lead into a pending Business account."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    if lead.converted_business_id:
        return JsonResponse({
            'success': False,
            'error': f'Already converted to Business #{lead.converted_business_id}',
        }, status=400)
    try:
        business, created = crm_services.convert_lead_to_business(lead, None)
    except Exception:
        logger.exception('crm: convert failed for lead %s', lead.pk)
        return JsonResponse({'success': False, 'error': 'Conversion failed'}, status=500)
    return JsonResponse({
        'success': True,
        'business_id': business.business_id,
        'business_name': business.business_name,
        'business_url': reverse('workforce:seller_detail', args=[business.business_id]),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_whatsapp_inbox(request):
    """Inbound WAHA senders not yet known: promote to lead or dismiss."""
    from workforce.views import paginate_queryset

    waha_enabled = getattr(settings, 'WAHA_ENABLED', False)
    rows, known_lead_map = [], {}
    search = request.GET.get('search', '').strip()

    try:
        from whatsapp.models import WhatsAppMessage
        grouped = (
            WhatsAppMessage.objects
            .filter(direction='inbound')
            .exclude(from_number='')
            .values('from_number')
            .annotate(last_at=Max('received_at'), msg_count=Count('id'))
            .order_by('-last_at')
        )
        if search:
            grouped = grouped.filter(from_number__icontains=search)

        business_numbers = set(
            WhatsAppMessage.objects
            .filter(direction='inbound', business__isnull=False)
            .values_list('from_number', flat=True).distinct()
        )
        dismissed_numbers = set(InboxDismissal.objects.values_list('phone', flat=True))

        from core.models import Profile
        profile_numbers = set()
        for phone, whatsapp in Profile.objects.exclude(
            phone='', whatsapp=''
        ).values_list('phone', 'whatsapp'):
            for value in (phone, whatsapp):
                normalized = crm_services.normalize_phone(value)
                if normalized:
                    profile_numbers.add(normalized)

        open_leads = dict(
            Lead.objects.exclude(stage__in=Lead.CLOSED_STAGES)
            .exclude(phone='').values_list('phone', 'pk')
        )

        for row in grouped:
            number = row['from_number']
            if number in business_numbers or number in dismissed_numbers:
                continue
            if crm_services.normalize_phone(number) in profile_numbers:
                continue
            row['existing_lead_id'] = open_leads.get(crm_services.normalize_phone(number))
            rows.append(row)
    except Exception:
        logger.exception('crm: WA inbox query failed')

    page_obj = paginate_queryset(request, rows, items_per_page=25)

    from whatsapp.models import WhatsAppMessage as _WM
    for row in page_obj:
        last = (
            _WM.objects.filter(direction='inbound', from_number=row['from_number'])
            .order_by('-received_at').first()
        )
        row['last_body'] = (last.body[:160] if last and last.body else '')
        row['last_type'] = last.message_type if last else ''

    context = {
        'page_title': 'WhatsApp Inbox',
        'page_obj': page_obj,
        'search': search,
        'waha_enabled': waha_enabled,
    }
    return render(request, 'workforce/crm/whatsapp_inbox.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_promote(request):
    """AJAX: create (or reuse) a lead from an inbound WhatsApp number."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    phone = request.POST.get('phone', '').strip()
    try:
        lead, created = crm_services.create_lead_from_wa_number(phone, request.user)
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
def crm_wa_dismiss(request):
    """AJAX: mark an inbound WhatsApp number as not-a-lead (hidden from inbox)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    phone = request.POST.get('phone', '').strip()
    if not phone:
        return JsonResponse({'success': False, 'error': 'Phone required'}, status=400)
    InboxDismissal.objects.get_or_create(
        phone=phone, defaults={'dismissed_by': request.user},
    )
    return JsonResponse({'success': True})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_reports(request):
    """Funnel and conversion stats across the leads pipeline."""
    today = timezone.localdate()

    stage_counts = {
        row['stage']: row['n']
        for row in Lead.objects.values('stage').annotate(n=Count('id'))
    }
    stage_data = [
        {'key': key, 'label': label, 'count': stage_counts.get(key, 0)}
        for key, label in Lead.STAGE_CHOICES
    ]

    twelve_months_ago = (today.replace(day=1) - timedelta(days=365))
    monthly = (
        Lead.objects.filter(created_at__date__gte=twelve_months_ago)
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

    per_staff = []
    staff_rows = (
        Lead.objects.filter(assigned_to__isnull=False)
        .values('assigned_to__id', 'assigned_to__first_name',
                'assigned_to__last_name', 'assigned_to__username')
        .annotate(
            total=Count('id'),
            won=Count('id', filter=Q(stage=Lead.STAGE_WON)),
            lost=Count('id', filter=Q(stage=Lead.STAGE_LOST)),
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
        Lead.objects.values('source')
        .annotate(total=Count('id'), won=Count('id', filter=Q(stage=Lead.STAGE_WON)))
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

    closed_leads = Lead.objects.filter(closed_at__isnull=False)
    avg_days_to_close = None
    durations = [
        (lead.closed_at - lead.created_at).days
        for lead in closed_leads.only('created_at', 'closed_at')
    ]
    if durations:
        avg_days_to_close = round(sum(durations) / len(durations), 1)

    total = Lead.objects.count()
    won = stage_counts.get(Lead.STAGE_WON, 0)
    lost = stage_counts.get(Lead.STAGE_LOST, 0)
    context = {
        'page_title': 'CRM Reports',
        'total_count': total,
        'open_count': total - won - lost,
        'won_count': won,
        'lost_count': lost,
        'win_rate': round(won * 100 / (won + lost)) if (won + lost) else None,
        'avg_days_to_close': avg_days_to_close,
        'stage_data': stage_data,
        'monthly_chart': monthly_chart,
        'per_staff': per_staff,
        'per_source': per_source,
    }
    return render(request, 'workforce/crm/crm_reports.html', context)
