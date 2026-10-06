"""
Purpose: Which WhatsApp numbers (WAHA sessions) a staff member may open in the inbox (/waha/wa-chats/).
Used by: whatsapp/wa_chats_view.py (_staff_only gate, tab strip, media), workforce.views (Staff Roles number columns)
Notes: Super admins open every number. Everyone else opens only the numbers ticked on Staff Roles
       (InboxSessionAccess rows) — no row means closed, like a staff member with no desk.
"""
from . import sessions as wa_sessions

REFUSAL = 'This WhatsApp number is not open to you.'


def sees_all(user):
    from core.decorators import is_superadmin

    return bool(getattr(user, 'is_authenticated', False)) and is_superadmin(user)


def allowed(user):
    """Set of session names this user may open, or None for every number."""
    if sees_all(user):
        return None
    if not getattr(user, 'is_authenticated', False):
        return set()
    from .models import InboxSessionAccess

    return set(InboxSessionAccess.objects.filter(user=user).values_list('session', flat=True))


def can_open(user, session):
    names = allowed(user)
    return names is None or session in names


def first_open(user):
    """The number to land on when the requested one is closed: first live one they hold."""
    names = allowed(user)
    live = [s['name'] for s in wa_sessions.list_sessions()]
    for name in live:
        if names is None or name in names:
            return name
    return sorted(names)[0] if names else None


def known_sessions():
    """Numbers the Staff Roles columns offer: live WAHA sessions plus any still granted."""
    from .models import InboxSessionAccess

    rows = [dict(s) for s in wa_sessions.list_sessions()]
    live = {s['name'] for s in rows}
    for name in sorted(set(InboxSessionAccess.objects.values_list('session', flat=True)) - live):
        rows.append({'name': name, 'status': 'GONE', 'phone': '', 'push_name': ''})
    return rows


def set_access(user, session, enabled, actor=None):
    from .models import InboxSessionAccess

    if enabled:
        InboxSessionAccess.objects.get_or_create(user=user, session=session,
                                                 defaults={'granted_by': actor})
    else:
        InboxSessionAccess.objects.filter(user=user, session=session).delete()
