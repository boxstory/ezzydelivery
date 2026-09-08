"""
Purpose: Record every delivery-location change (pin, accuracy, QNAS check) as an OrderStatusHistory row so the timeline shows who moved the address and how.
Used by: workforce/views.py (staff QNAS verify, pin paste, AI parse), orders/views.py (customer verification link), fleet/views.py (driver app), whatsapp/waha_views.py (shared WhatsApp pin).
Notes: Writes field_name='location_update'; returns None when nothing actually changed so repeated clicks do not spam the timeline.
"""

from decimal import Decimal, InvalidOperation

from .models import Order, OrderStatusHistory


def _coord_text(lat, lng):
    """Render a lat/lng pair as '25.231351, 51.538119' — '' when either is missing."""
    if lat in (None, '') or lng in (None, ''):
        return ''
    try:
        return f"{Decimal(str(lat)):.6f}, {Decimal(str(lng)):.6f}"
    except (InvalidOperation, ValueError, TypeError):
        return ''


def _accuracy_label(accuracy):
    return dict(Order.COORDS_ACCURACY).get(accuracy or '', '')


def _side_label(coords, accuracy):
    """Human label for one side of the change: 'By Staff · 25.231351, 51.538119'."""
    parts = [p for p in [_accuracy_label(accuracy), coords] if p]
    return ' · '.join(parts) if parts else 'No pin'


def log_location_update(order, *, source, actor=None,
                        old_lat=None, old_lng=None, old_accuracy='',
                        new_lat=None, new_lng=None, new_accuracy='',
                        note=None, force=False):
    """
    Write one "Location Updated" timeline row for an address/pin change.

    source  — short phrase naming what moved it ("QNAS verify", "Customer
              verification link", "Driver app", "Shared WhatsApp pin").
    actor   — User who did it, or None for customer/driver-app/automated flows.
    force   — write the row even when the pin and accuracy are unchanged (used
              for QNAS-status-only checks, which the caller already guards).

    Returns the created row, or None when nothing changed.
    """
    old_coords = _coord_text(old_lat, old_lng)
    new_coords = _coord_text(new_lat, new_lng)
    accuracy_changed = (new_accuracy or '') != (old_accuracy or '')

    if not force and not accuracy_changed and old_coords == new_coords:
        return None

    notes = source if not note else f"{source} — {note}"

    return OrderStatusHistory.objects.create(
        order=order,
        field_name='location_update',
        old_value=old_coords[:100],
        new_value=(new_coords or (new_accuracy or ''))[:100],
        old_display=_side_label(old_coords, old_accuracy)[:100],
        new_display=_side_label(new_coords, new_accuracy)[:100],
        changed_by=actor if (actor is not None and getattr(actor, 'is_authenticated', False)) else None,
        notes=notes[:255] if notes else None,
    )


def log_qnas_check(order, *, status, actor=None, zone=None, street=None, building=None):
    """
    Record a QNAS lookup result ("verified" / "not_found" / "error") on the timeline.

    Called only when Order.qnas_status actually changes, so re-clicking Verify on an
    already-verified address does not add a row.
    """
    label = dict(Order.QNAS_STATUS).get(status, status)
    address = ' / '.join(str(p) for p in [zone, street, building] if p)
    return OrderStatusHistory.objects.create(
        order=order,
        field_name='location_update',
        old_value='',
        new_value=f'qnas:{status}'[:100],
        old_display='QNAS not checked',
        new_display=f'QNAS: {label}'[:100],
        changed_by=actor if (actor is not None and getattr(actor, 'is_authenticated', False)) else None,
        notes=(f'QNAS verify — Zone/Street/Building {address}' if address else 'QNAS verify')[:255],
    )
