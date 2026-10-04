"""
Purpose: Super-admin settings page — tick which WhatsApp labels, per number, are marketing-only.
Used by: workforce/urls.py (workforce:whatsapp_label_access)
Notes: Enforcement lives in whatsapp/label_access.py; this page only edits RestrictedChatLabel rows.
"""
import logging

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.decorators import staff_required
from whatsapp import sessions as wa_sessions
from whatsapp.models import RestrictedChatLabel

logger = logging.getLogger(__name__)


def _number_labels(session):
    """This number's labels from WAHA, or None when WAHA cannot be reached."""
    base = (getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000') or '').rstrip('/')
    try:
        resp = requests.get(f'{base}/api/{session}/labels',
                            headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''}, timeout=10)
        body = resp.json() if resp.status_code == 200 else None
    except (requests.exceptions.RequestException, ValueError):
        return None
    if not isinstance(body, list):
        return None
    return [{'id': str(l['id']), 'name': l.get('name') or str(l['id']), 'color': l.get('colorHex') or ''}
            for l in body if isinstance(l, dict) and l.get('id')]


@login_required(login_url='/accounts/login/')
@staff_required
@require_http_methods(['GET', 'POST'])
def whatsapp_label_access(request):
    if request.method == 'POST':
        session = (request.POST.get('session') or '').strip()
        if not wa_sessions.is_valid(session):
            messages.error(request, 'Unknown WhatsApp number.')
            return redirect('workforce:whatsapp_label_access')
        labels = _number_labels(session)
        if labels is None:
            messages.error(request, 'Could not read this number\'s labels from WhatsApp — nothing was changed.')
            return redirect('workforce:whatsapp_label_access')
        names = {l['id']: l['name'] for l in labels}
        existing = {r.label_id: r for r in RestrictedChatLabel.objects.filter(session=session)}
        chosen = set(request.POST.getlist('label'))
        # A label deleted on the phone can still be un-ticked, never newly ticked.
        chosen &= set(names) | set(existing)
        with transaction.atomic():
            RestrictedChatLabel.objects.filter(session=session).exclude(label_id__in=chosen).delete()
            for label_id in chosen - set(existing):
                RestrictedChatLabel.objects.create(session=session, label_id=label_id,
                                                   label_name=names.get(label_id, ''), added_by=request.user)
            for label_id in chosen & set(existing):
                row = existing[label_id]
                if label_id in names and row.label_name != names[label_id]:
                    row.label_name = names[label_id]
                    row.save(update_fields=['label_name'])
        logger.info('wa label access: %s set marketing-only labels on %s to %s',
                    request.user, session, sorted(chosen))
        messages.success(request, 'Saved. Staff outside marketing stop seeing these chats on their next refresh.')
        return redirect(f"{request.path}#number-{session}")

    numbers = []
    restricted_total = 0
    for s in wa_sessions.list_sessions():
        name = s['name']
        rows = {r.label_id: r for r in RestrictedChatLabel.objects.filter(session=name)}
        labels = _number_labels(name)
        items = []
        for l in labels or []:
            items.append({**l, 'restricted': l['id'] in rows, 'gone': False})
        known = {l['id'] for l in labels or []}
        for label_id, r in rows.items():
            if labels is not None and label_id not in known:
                items.append({'id': label_id, 'name': r.label_name or label_id, 'color': '',
                              'restricted': True, 'gone': True})
        restricted_total += len(rows)
        numbers.append({
            'session': name,
            'title': s.get('push_name') or name,
            'phone': s.get('phone') or '',
            'labels': items,
            'unreachable': labels is None,
            'restricted_count': len(rows),
        })
    return render(request, 'workforce/whatsapp_label_access.html', {
        'page_title': 'Marketing-only WhatsApp labels',
        'numbers': numbers,
        'restricted_total': restricted_total,
    })
