"""
Purpose: CRM lead ownership — who may see, take, release and reassign a lead, and which owned leads have gone idle.
Used by: workforce/crm_views.py, workforce/dashboard_marketing.py, workforce/context_processors.py, whatsapp/chat_panel.py, whatsapp/wa_chats_view.py, workforce/views.py (staff roles)
Notes: Lead managers (Profile.lead_manager, or any super admin) see every lead; everyone else sees their own plus the unassigned pool. Takes and releases are conditional UPDATEs, so two people pressing Take on one card cannot both win.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from core.departments import MKT, OPS, user_departments

#: An owned, open lead whose owner has logged nothing on it for this many days is flagged.
IDLE_DAYS = 7

#: Desks that work the pool: their staff may take a lead and be handed one.
CLAIM_DEPARTMENTS = {OPS, MKT}


def user_label(user):
    if user is None:
        return ''
    return user.get_full_name() or user.username


def is_lead_manager(user):
    """Sees every lead and may hand any lead to anyone. Super admins always are."""
    from core.decorators import is_superadmin

    if not getattr(user, 'is_authenticated', False):
        return False
    if is_superadmin(user):
        return True
    return bool(getattr(getattr(user, 'profile', None), 'lead_manager', False))


def can_claim(user):
    return bool(user_departments(user) & CLAIM_DEPARTMENTS)


def visible_leads(queryset, user):
    """The rows this user may list: everything for a manager, else own + pool."""
    if is_lead_manager(user):
        return queryset
    return queryset.filter(Q(assigned_to=user) | Q(assigned_to__isnull=True))


def card_of(lead):
    """An absorbed duplicate is owned through the card it sits inside."""
    return lead.merged_into if lead.merged_into_id else lead


def can_see_lead(user, lead):
    if is_lead_manager(user):
        return True
    return card_of(lead).assigned_to_id in (None, user.pk)


def assignable_users():
    """Who a lead can be handed to: active staff on the Operations or Marketing desk,
    and super admins (who hold every desk)."""
    return (User.objects.filter(is_active=True, is_staff=True)
            .filter(Q(profile__dept_operations=True) | Q(profile__dept_marketing=True)
                    | Q(profile__is_superadmin=True) | Q(is_superuser=True))
            .distinct().order_by('first_name', 'username'))


def owner_choices(user, lead=None):
    """The assignee picker's options. A manager gets the desk; anyone else only
    themselves, because the only moves open to them are take and release. The
    current owner is always kept, so saving the form never silently clears it."""
    users = list(assignable_users()) if is_lead_manager(user) else [user]
    current = getattr(lead, 'assigned_to', None) if lead is not None else None
    if current is not None and all(u.pk != current.pk for u in users):
        users.append(current)
    return users


def _log(lead, body, user):
    from crm.models import LeadActivity

    LeadActivity.objects.create(
        lead=lead, activity_type=LeadActivity.TYPE_ASSIGNMENT, body=body, created_by=user)


def _mirror(lead, owner, when):
    """Keep the in-memory row in step with an UPDATE, so a later full save() on the
    same object writes the new owner back rather than the stale one."""
    lead.assigned_to = owner
    lead.assigned_at = when
    lead._loaded_assigned_to_id = owner.pk if owner else None


def claim_lead(lead, user):
    """Take an unassigned lead. Returns (ok, message)."""
    from crm.models import Lead

    lead = card_of(lead)
    if not can_claim(user):
        return False, 'Only Operations and Marketing staff can take leads.'
    now = timezone.now()
    taken = Lead.objects.filter(pk=lead.pk, assigned_to__isnull=True).update(
        assigned_to=user, assigned_at=now, updated_at=now)
    if not taken:
        lead.refresh_from_db(fields=['assigned_to', 'assigned_at'])
        if lead.assigned_to_id == user.pk:
            return True, 'This lead is already yours.'
        return False, f'Already taken by {user_label(lead.assigned_to)}.'
    _mirror(lead, user, now)
    _log(lead, f'Taken from the pool by {user_label(user)}', user)
    return True, f'Lead #{lead.pk} is now yours.'


def release_lead(lead, user):
    """Hand your own lead back to the pool. Returns (ok, message)."""
    from crm.models import Lead

    lead = card_of(lead)
    now = timezone.now()
    released = Lead.objects.filter(pk=lead.pk, assigned_to=user).update(
        assigned_to=None, assigned_at=None, updated_at=now)
    if not released:
        return False, 'Only the owner or a lead manager can release this lead.'
    _mirror(lead, None, None)
    _log(lead, f'Released back to the pool by {user_label(user)}', user)
    return True, f'Lead #{lead.pk} is back in the pool.'


def set_owner(lead, target, user):
    """Every assignee change a page posts goes through here. `target` is a User or
    None (unassigned). Returns (ok, message, changed).

    A manager may hand the lead to anyone on the desk or clear it. Anyone else
    can only take an unassigned lead or release their own — the same two moves
    as the Take / Release buttons, through the same race-safe updates.
    """
    from crm.models import Lead

    lead = card_of(lead)
    target_id = target.pk if target else None
    if target_id == lead.assigned_to_id:
        return True, '', False

    if not is_lead_manager(user):
        if target_id == user.pk and lead.assigned_to_id is None:
            ok, message = claim_lead(lead, user)
            return ok, message, ok
        if target_id is None and lead.assigned_to_id == user.pk:
            ok, message = release_lead(lead, user)
            return ok, message, ok
        if lead.assigned_to_id and lead.assigned_to_id != user.pk:
            return False, (f'This lead belongs to {user_label(lead.assigned_to)} — '
                           'only a lead manager can reassign it.'), False
        return False, 'Only a lead manager can give a lead to someone else.', False

    if target is not None and not assignable_users().filter(pk=target_id).exists():
        return False, (f'{user_label(target)} is not on the Operations or Marketing desk, '
                       'so they cannot own a lead.'), False
    now = timezone.now()
    Lead.objects.filter(pk=lead.pk).update(
        assigned_to=target, assigned_at=now if target else None, updated_at=now)
    _mirror(lead, target, now if target else None)
    if target is None:
        _log(lead, f'Assignment cleared by {user_label(user)}', user)
        return True, 'Assignment cleared.', True
    _log(lead, f'Assigned to {user_label(target)} by {user_label(user)}', user)
    return True, f'Assigned to {user_label(target)}.', True


def may_create_with_owner(user, target):
    """Owner picked on the New Lead form. Returns an error string, '' when allowed."""
    if target is None:
        return ''
    if is_lead_manager(user):
        if assignable_users().filter(pk=target.pk).exists():
            return ''
        return f'{user_label(target)} is not on the Operations or Marketing desk.'
    if target.pk == user.pk and can_claim(user):
        return ''
    return 'Only a lead manager can give a lead to someone else.'


def filter_idle(leads, now=None):
    """Owned, open leads whose owner has logged nothing on them for IDLE_DAYS.

    Counted from when they got the card, so a fresh take is never idle. Notes,
    stage moves and follow-up changes are activity; a WhatsApp sent from the lead
    page is not, because the composer writes no timeline entry.
    """
    from crm.models import LeadActivity
    from crm.services import closed_stage_keys

    cutoff = (now or timezone.now()) - timedelta(days=IDLE_DAYS)
    touched = LeadActivity.objects.filter(
        lead=OuterRef('pk'), created_by=OuterRef('assigned_to'), created_at__gte=cutoff)
    return (leads.filter(assigned_to__isnull=False, assigned_at__lte=cutoff)
            .exclude(stage__in=closed_stage_keys())
            .exclude(Exists(touched)))


def mark_idle(leads):
    """Set `lead.is_idle` on a list of leads with one query."""
    from crm.models import Lead

    owned = [lead.pk for lead in leads if lead.assigned_to_id]
    idle = set()
    if owned:
        idle = set(filter_idle(Lead.objects.filter(pk__in=owned)).values_list('pk', flat=True))
    for lead in leads:
        lead.is_idle = lead.pk in idle
    return leads
