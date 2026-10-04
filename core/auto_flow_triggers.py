# Purpose: What each Auto Flow trigger hands the flow engine, and therefore which
#          "Send To" recipients can actually resolve a phone number for it.
# Used by: workforce.views (auto_flow_add / auto_flow_edit — options + save validation),
#          workforce/templates/workforce/auto_flow_add.html, core.auto_flow_executor.
# Notes: A recipient the trigger cannot feed does not fail at save time — it fails weeks
#        later as "No phone numbers resolved" in the flow log, with nothing on screen to
#        say why. This map is what keeps the form from offering one. Register a trigger
#        here in the same commit as its execute_flows_for_trigger() call: an unregistered
#        key falls back to SUBJECT_INERT, which offers only broadcast recipients and warns
#        that the trigger runs no flows. core/tests_auto_flow_triggers.py fails the build
#        if a fired trigger is missing.

# What the event carries, which is the only thing that decides who can be messaged.
SUBJECT_TASK = 'task'      # a DeliveryTask — its order, customer, driver, seller, zone
SUBJECT_ORDER = 'order'    # an Order — customer, seller, zone, but no assigned driver
SUBJECT_PERSON = 'person'  # one person's phone in the context (lead, driver, seller)
SUBJECT_NONE = 'none'      # runs flows, but carries no order, task or phone
SUBJECT_INERT = 'inert'    # nothing calls execute_flows_for_trigger() with this key
SUBJECT_UNSET = 'unset'    # no trigger chosen yet — nothing is known, so nothing is ruled out

# Who the person is, when the subject is a person. Names the two "person" options
# after whoever is actually on the other end, so nobody has to guess what "the
# context" means while building a flow.
PERSON_LABELS = {
    'driver': 'The driver this event is about',
    'lead': 'The lead this event is about',
    'seller': 'The seller this event is about',
}
PERSON_LABEL_DEFAULT = 'The person this event is about'

TRIGGER_FEEDS = {
    # --- Delivery task events: task=instance ------------------------------
    # delivery/signals.py and ezzy_api/views.py. The richest kind — the order
    # is derived from the task, so every recipient resolves.
    'staff_task_assign_driver': {'subject': SUBJECT_TASK},
    'staff_task_status_change': {'subject': SUBJECT_TASK},
    'staff_task_cancel': {'subject': SUBJECT_TASK},
    'staff_task_publish': {'subject': SUBJECT_TASK},
    'staff_task_reschedule': {'subject': SUBJECT_TASK},
    'staff_cod_collected': {'subject': SUBJECT_TASK},
    'wa_driver_assigned': {'subject': SUBJECT_TASK},
    'wa_out_for_delivery': {'subject': SUBJECT_TASK},
    'wa_delivered': {'subject': SUBJECT_TASK},
    'wa_delivery_failed': {'subject': SUBJECT_TASK},
    'wa_location_verification': {'subject': SUBJECT_TASK},
    'wh_task_accepted': {'subject': SUBJECT_TASK},
    'wh_task_rejected': {'subject': SUBJECT_TASK},
    'wh_task_completed': {'subject': SUBJECT_TASK},
    'wh_task_status_update': {'subject': SUBJECT_TASK},
    'wh_cod_collected': {'subject': SUBJECT_TASK},

    # --- Order events: order=instance -------------------------------------
    # No delivery task exists yet (or is not the subject), so nothing can reach
    # "the driver" — an order has no driver until a task is assigned one.
    'staff_order_create': {'subject': SUBJECT_ORDER},
    'staff_order_verify': {'subject': SUBJECT_ORDER},
    'staff_order_edit': {'subject': SUBJECT_ORDER},
    'staff_order_publish': {'subject': SUBJECT_ORDER},
    'staff_order_cancel': {'subject': SUBJECT_ORDER},
    'wa_order_cancelled': {'subject': SUBJECT_ORDER},
    'business_unapproved_order': {'subject': SUBJECT_ORDER},

    # --- Events about a person: a phone in the context ---------------------
    'driver_application_submitted': {'subject': SUBJECT_PERSON, 'person': 'driver'},
    'staff_driver_approved': {'subject': SUBJECT_PERSON, 'person': 'driver'},
    'staff_driver_rejected': {'subject': SUBJECT_PERSON, 'person': 'driver'},
    'staff_driver_suspended': {'subject': SUBJECT_PERSON, 'person': 'driver'},
    'staff_cod_settled': {'subject': SUBJECT_PERSON, 'person': 'driver'},
    'business_cod_settled': {'subject': SUBJECT_PERSON, 'person': 'seller'},
    'lead_created': {'subject': SUBJECT_PERSON, 'person': 'lead'},
    'lead_stage_changed': {'subject': SUBJECT_PERSON, 'person': 'lead'},
    'lead_won': {'subject': SUBJECT_PERSON, 'person': 'lead'},
    'lead_lost': {'subject': SUBJECT_PERSON, 'person': 'lead'},

    # --- Fires flows, but is about a batch / a run / a count ---------------
    # Nobody in particular is on the other end, so only a broadcast recipient
    # (all drivers, a desk, a fixed number) can receive one of these.
    'staff_earnings_approved': {'subject': SUBJECT_NONE},
    'staff_orders_imported': {'subject': SUBJECT_NONE},
    'staff_temp_orders_transferred': {'subject': SUBJECT_NONE},
    'staff_batch_created': {'subject': SUBJECT_NONE},
    'staff_batch_dispatched': {'subject': SUBJECT_NONE},
}


# ---------------------------------------------------------------------------
# The Send To list. One definition, read by the form, the JS and the save —
# three copies of it is how the form came to offer options that never resolve.
#
# `needs` is the subject a recipient must have to resolve a number, and mirrors
# core.auto_flow_executor._resolve_recipient_phones exactly:
#   None     — always resolvable, it reads the database, not the event
#   'order'  — reads the order (a task carries one, so a task satisfies this)
#   'task'   — reads task.driver, which only a task has
#   'person' — reads the phone the event put in the context
# ---------------------------------------------------------------------------
RECIPIENTS = [
    {'value': 'customer', 'group': 'Customer',
     'label': 'Customer — Order Phone', 'needs': 'order'},
    {'value': 'customer_whatsapp', 'group': 'Customer',
     'label': 'Customer — WhatsApp Number', 'needs': 'order'},

    {'value': 'driver', 'group': 'Driver',
     'label': 'Assigned Driver — Phone', 'needs': 'task'},
    {'value': 'driver_whatsapp', 'group': 'Driver',
     'label': 'Assigned Driver — WhatsApp', 'needs': 'task'},
    {'value': 'all_active_drivers', 'group': 'Driver',
     'label': 'All Active Drivers', 'needs': None},
    {'value': 'zone_drivers', 'group': 'Driver',
     'label': 'Drivers in Same Zone', 'needs': 'order'},
    {'value': 'available_drivers', 'group': 'Driver',
     'label': 'All Available Drivers', 'needs': None},

    {'value': 'seller', 'group': 'Seller / Business',
     'label': 'Seller — Business Phone', 'needs': 'order'},
    {'value': 'seller_owner', 'group': 'Seller / Business',
     'label': 'Seller — Owner Phone', 'needs': 'order'},

    # Two numbers, not one: a driver's WhatsApp is its own field and is often not
    # the line they answer calls on. The WhatsApp option falls back to the phone
    # when the subject has no separate number (a CRM lead has only the one).
    {'value': 'context_whatsapp', 'group': 'The person this is about',
     'label': 'Person this event is about — WhatsApp', 'needs': 'person',
     'person_suffix': 'WhatsApp'},
    {'value': 'context_phone', 'group': 'The person this is about',
     'label': 'Person this event is about — Phone', 'needs': 'person',
     'person_suffix': 'Phone'},

    {'value': 'staff_ops', 'group': 'Staff', 'label': 'Operations Staff', 'needs': None},
    {'value': 'staff_fin', 'group': 'Staff', 'label': 'Finance Staff', 'needs': None},
    {'value': 'staff_mkt', 'group': 'Staff', 'label': 'Marketing / Sales Staff', 'needs': None},
    {'value': 'staff_all', 'group': 'Staff', 'label': 'All Staff Members', 'needs': None},

    {'value': 'custom', 'group': 'Custom', 'label': 'Custom Phone Number', 'needs': None},
    {'value': 'custom_group', 'group': 'Custom', 'label': 'WhatsApp Group ID', 'needs': None},
]

# Why an option is greyed out, said in terms of the trigger rather than the code.
_REASONS = {
    ('order', SUBJECT_PERSON): 'this event has no order',
    ('order', SUBJECT_NONE): 'this event has no order',
    ('order', SUBJECT_INERT): 'this event has no order',
    ('task', SUBJECT_ORDER): 'no driver is assigned yet at this point',
    ('task', SUBJECT_PERSON): 'this event has no delivery task',
    ('task', SUBJECT_NONE): 'this event has no delivery task',
    ('task', SUBJECT_INERT): 'this event has no delivery task',
    ('person', SUBJECT_TASK): 'use the customer, driver or seller options instead',
    ('person', SUBJECT_ORDER): 'use the customer or seller options instead',
    ('person', SUBJECT_NONE): 'this event is not about one person',
    ('person', SUBJECT_INERT): 'this event is not about one person',
}

# The line under the picker: what this trigger can reach, before anything is chosen.
_NOTES = {
    SUBJECT_UNSET: ('none', 'Pick a trigger first — it decides who this message can be '
                            'sent to.'),
    SUBJECT_TASK: ('ok', 'This event carries a delivery task — its customer, driver, '
                         'seller and zone can all be messaged.'),
    SUBJECT_ORDER: ('ok', 'This event carries an order — the customer, the seller and the '
                          'zone can be messaged. No driver is assigned yet, so the '
                          '"Assigned Driver" options cannot be used.'),
    SUBJECT_PERSON: ('ok', 'This event is about one person, so it can be sent to their own '
                           'WhatsApp or phone number. There is no order behind it, so the '
                           'customer, driver-on-a-task and seller options cannot be used.'),
    SUBJECT_NONE: ('warn', 'This event is not about one order, task or person, so it can '
                           'only be sent to a fixed recipient: a desk, all drivers, or a '
                           'number you type in.'),
    SUBJECT_INERT: ('danger', 'Nothing runs automation flows on this trigger yet — a flow '
                              'built on it will never fire. Pick another trigger, or ask '
                              'for this one to be wired up.'),
}


def trigger_feed(trigger_key):
    """What ``trigger_key`` hands the flow engine.

    No key at all means the form has not been given a trigger yet, which is not
    the same as a trigger that feeds nothing — so it rules nothing out. A key
    that is not registered reads as inert.
    """
    if not trigger_key:
        return {'subject': SUBJECT_UNSET}
    return TRIGGER_FEEDS.get(trigger_key, {'subject': SUBJECT_INERT})


def _satisfied(needs, subject):
    if needs is None or subject == SUBJECT_UNSET:
        return True
    if needs == 'order':
        # A task carries its order, so a task satisfies an order need.
        return subject in (SUBJECT_TASK, SUBJECT_ORDER)
    if needs == 'task':
        return subject == SUBJECT_TASK
    if needs == 'person':
        return subject == SUBJECT_PERSON
    return False


def recipients_for(trigger_key):
    """Every Send To option for ``trigger_key``, in form order.

    Each row is the RECIPIENTS entry plus ``available`` and, when it is not,
    ``reason``. Nothing is dropped: an option that cannot work is shown greyed
    out with why, because a staff member who came looking for "the driver"
    needs to be told there is no driver here, not left hunting a missing line.
    """
    feed = trigger_feed(trigger_key)
    subject, person = feed['subject'], feed.get('person')
    rows = []
    for rec in RECIPIENTS:
        available = _satisfied(rec['needs'], subject)
        row = dict(rec, available=available)
        if rec.get('person_suffix'):
            base = PERSON_LABELS.get(person, PERSON_LABEL_DEFAULT)
            row['label'] = base + ' — ' + rec['person_suffix']
        if not available:
            row['reason'] = _REASONS.get((rec['needs'], subject), 'not available for this trigger')
        rows.append(row)
    return rows


def recipient_groups(trigger_key):
    """recipients_for() bucketed into the picker's optgroups, order preserved."""
    groups, order = {}, []
    for row in recipients_for(trigger_key):
        if row['group'] not in groups:
            groups[row['group']] = []
            order.append(row['group'])
        groups[row['group']].append(row)
    return [{'label': name, 'rows': groups[name]} for name in order]


def allowed_recipients(trigger_key):
    """The Send To values that can resolve a number for ``trigger_key``."""
    return {r['value'] for r in recipients_for(trigger_key) if r['available']}


# What the picker should land on per subject: the most specific recipient that
# trigger can feed. Falling through the list in form order instead would open a
# driver-approval flow on "All Active Drivers" — one keystroke from messaging
# the whole fleet about one person's application.
_DEFAULT_BY_SUBJECT = {
    SUBJECT_TASK: 'customer',
    SUBJECT_ORDER: 'customer',
    SUBJECT_PERSON: 'context_whatsapp',
    SUBJECT_NONE: 'staff_ops',
    SUBJECT_INERT: 'staff_ops',
    SUBJECT_UNSET: 'customer',
}


def default_recipient(trigger_key):
    """What the picker should land on for this trigger."""
    allowed = allowed_recipients(trigger_key)
    preferred = _DEFAULT_BY_SUBJECT.get(trigger_feed(trigger_key)['subject'])
    if preferred in allowed:
        return preferred
    for row in recipients_for(trigger_key):
        if row['available']:
            return row['value']
    return 'custom'


def trigger_note(trigger_key):
    """``{'level', 'text'}`` for the line under the picker."""
    level, text = _NOTES[trigger_feed(trigger_key)['subject']]
    return {'level': level, 'text': text}


def scope_map(trigger_keys):
    """``{trigger_key: {allowed, labels, reasons, note, default}}`` for the page JS.

    Built for every trigger in the picker so switching trigger re-scopes the
    Send To list with no round trip.
    """
    out = {}
    for key in trigger_keys:
        rows = recipients_for(key)
        out[key] = {
            'allowed': [r['value'] for r in rows if r['available']],
            'reasons': {r['value']: r['reason'] for r in rows if not r['available']},
            'labels': {r['value']: r['label'] for r in rows},
            'default': default_recipient(key),
            'note': trigger_note(key),
        }
    return out
