# Purpose: Registry + resolver for editable outbound WhatsApp message bodies, plus the
#          inventory of staff-driven manual composers that use them.
# Used by: core.whatsapp_utils senders, workforce.views (order/task composers, auto_triggers_list,
#          wf_ai_config Messages tab), workforce.crm_views lead detail.
# Notes: Defaults live here so a fresh install works with no DB rows; staff edits are
#        stored in core.MessageTemplate under the same key and always win. Entries with
#        kind='composer' only pre-fill a textarea — switching one off gives staff a blank
#        composer, it never blocks a send. Entries carrying `toggle_owner` have their
#        on/off owned by an AutoTriggerConfig row, so the Messages tab hides the switch.

import logging

logger = logging.getLogger(__name__)

DRIVER_APPLICATION_THANKS = 'driver_application_thanks'
CRM_LEAD_MANUAL = 'crm_lead_manual'
CRM_DRIVER_LEAD_MANUAL = 'crm_driver_lead_manual'
PRICING_INQUIRY_MANUAL = 'pricing_inquiry_manual'
ORDER_VERIFY_MANUAL = 'order_verify_manual'

KIND_AUTO = 'auto'
KIND_COMPOSER = 'composer'

TEMPLATE_DEFAULTS = {
    DRIVER_APPLICATION_THANKS: {
        'label': 'Driver application — thank you',
        'description': (
            'Sent once from the fleet number when an applicant submits the driver '
            'join form. Re-submissions and later edits never re-send it.'
        ),
        'placeholders': 'first_name',
        'sender': 'fleet',
        'kind': KIND_AUTO,
        'section': 'driver_onboarding',
        'toggle_owner': '',
        'body': """✅ *Application Received — EZZY Delivery*

Hi {first_name},

Thank you for completing your driver application with EZZY Delivery. We have received your details and documents.

Our fleet team is reviewing your application now and will reach back to you on this WhatsApp number shortly.

No action is needed from your side in the meantime — just keep this number handy.

Best regards,
*EZZY Delivery Fleet Team* 🚚""",
    },

    CRM_LEAD_MANUAL: {
        'label': 'CRM business lead — composer starter',
        'description': (
            'Pre-fills the "Send from EZZY" composer on a business lead page. Staff '
            'always read and edit it before sending — switching it off just opens the '
            'composer blank, it never blocks the send.'
        ),
        'placeholders': 'lead_name, company, staff_name',
        'sender': 'default',
        'kind': KIND_COMPOSER,
        'section': 'crm_leads',
        'toggle_owner': '',
        'body': """Hello {lead_name},

This is {staff_name} from *EZZY Delivery* — Qatar's delivery partner for online stores.

Thank you for your interest in our delivery service. I would like to understand your requirement so we can share the right pricing for you:

• How many orders do you ship per week?
• Which areas do you deliver to?
• Do you need Cash on Delivery?

Happy to answer anything on this chat.

*EZZY Delivery* 🚚""",
    },

    CRM_DRIVER_LEAD_MANUAL: {
        'label': 'Driver lead — composer starter',
        'description': (
            'Pre-fills the "Send from EZZY" composer on driver lead and driver profile '
            'pages. Staff edit before sending; switching it off opens a blank composer.'
        ),
        'placeholders': 'lead_name, staff_name',
        'sender': 'fleet',
        'kind': KIND_COMPOSER,
        'section': 'driver_onboarding',
        'toggle_owner': '',
        'body': """Hello {lead_name},

This is {staff_name} from the *EZZY Delivery* fleet team.

Thank you for your interest in driving with us. To move ahead we need your application completed here:
https://ezzydelivery.qa/join_us/driver/

Please keep your QID, driving licence and vehicle papers ready — the form asks for photos of them.

Reply here if anything is unclear.

*EZZY Delivery Fleet Team* 🚚""",
    },

    PRICING_INQUIRY_MANUAL: {
        'label': 'Pricing inquiry — composer starter',
        'description': (
            'Pre-fills the "Send from EZZY" composer on a pricing inquiry page, for the '
            'first reply to a quote request. Staff edit before sending.'
        ),
        'placeholders': 'business_name, contact_name, staff_name',
        'sender': 'default',
        'kind': KIND_COMPOSER,
        'section': 'crm_leads',
        'toggle_owner': '',
        'body': """Hello {contact_name},

This is {staff_name} from *EZZY Delivery*. Thank you for submitting a delivery pricing request for *{business_name}*.

I have reviewed your details and would like to confirm a few points before sending your quotation:

• Pickup location and preferred pickup time
• Average orders per week
• Cash on Delivery — required or not

Once confirmed I will share your pricing on this chat.

*EZZY Delivery* 🚚""",
    },

    ORDER_VERIFY_MANUAL: {
        'label': 'Order location verification — message body',
        'description': (
            'The customer address-verification message. Used by the WhatsApp composer on '
            'order and delivery-task pages, the verification queue "Send now / Resend" '
            'buttons, and the automatic verification pipeline — all four share this text. '
            'On/off is owned by the wa_location_verification trigger.'
        ),
        'placeholders': 'customer_name, order_number, items_line, verify_url',
        'sender': 'default',
        'kind': KIND_COMPOSER,
        'section': 'orders_tasks',
        'toggle_owner': 'wa_location_verification',
        'body': """Hi {customer_name}, this is regarding your order {order_number}. Please confirm your delivery details and availability.

{items_line}📌 Verify your location: {verify_url}""",
    },
}


# ---------------------------------------------------------------------------
# Manual composers — every surface where a staff member types a WhatsApp
# message and sends it from a platform number (or, for the last two rows,
# demonstrably does NOT). Rendered as its own group on the Auto Triggers page
# so no send path is invisible there.
#
# `url` is a reverse() name unless `url_is_path`, in which case it is a literal
# path (the WAHA ops pages sit outside the Django URL namespaces staff browse).
# `template_key` empty = free text with nothing to configure.
# ---------------------------------------------------------------------------
MANUAL_COMPOSERS = [
    {
        'code': 'composer_crm_lead',
        'label': 'CRM business lead — "Send from EZZY"',
        'description': 'Staff composer on a business lead page. Sends from the platform '
                       'number so replies come back to the CRM inbox.',
        'action': 'workforce.views.whatsapp_send_routed',
        'department': 'mkt',
        'section': 'crm_leads',
        'template_key': CRM_LEAD_MANUAL,
        'links': [('Leads Board', 'workforce:crm_leads_board')],
    },
    {
        'code': 'composer_crm_driver_lead',
        'label': 'Driver lead — "Send from EZZY"',
        'description': 'Same composer on a lead whose category is Driver. Routed to the '
                       'driver number, not the business one.',
        'action': 'workforce.views.whatsapp_send_routed',
        'department': 'mkt',
        'section': 'driver_onboarding',
        'template_key': CRM_DRIVER_LEAD_MANUAL,
        'links': [('Driver Leads Board', 'workforce:crm_driver_leads_board')],
    },
    {
        'code': 'composer_driver_profile',
        'label': 'Driver profile — "Send from EZZY"',
        'description': 'Staff composer on a driver profile page (applications and active '
                       'drivers alike).',
        'action': 'workforce.views.whatsapp_send_routed',
        'department': 'mkt',
        'section': 'driver_onboarding',
        'template_key': CRM_DRIVER_LEAD_MANUAL,
        'links': [('Driver Applications', 'workforce:driver_verification_list')],
    },
    {
        'code': 'composer_pricing_inquiry',
        'label': 'Pricing inquiry — "Send from EZZY"',
        'description': 'Staff composer on a 3PL quote request, for the first reply before '
                       'the lead is worked in the CRM.',
        'action': 'workforce.views.whatsapp_send_routed',
        'department': 'mkt',
        'section': 'crm_leads',
        'template_key': PRICING_INQUIRY_MANUAL,
        'links': [('Pricing Inquiries', 'workforce:pricing_inquiries_list')],
    },
    {
        'code': 'composer_order_detail',
        'label': 'Order page — WhatsApp customer',
        'description': 'The send modal on an order page and the orders list, pre-filled '
                       'with the location-verification message.',
        'action': 'workforce.views.send_order_whatsapp',
        'department': 'ops',
        'section': 'orders_tasks',
        'template_key': ORDER_VERIFY_MANUAL,
        'links': [('Orders', 'workforce:wf_orders_all')],
    },
    {
        'code': 'composer_task_detail',
        'label': 'Delivery task — WhatsApp customer',
        'description': 'The same send modal on a delivery task page, pre-filled with the '
                       'location-verification message.',
        'action': 'workforce.views.send_order_whatsapp',
        'department': 'ops',
        'section': 'orders_tasks',
        'template_key': ORDER_VERIFY_MANUAL,
        'links': [('Delivery Tasks', 'workforce:dl_list_all')],
    },
    {
        'code': 'composer_task_reply',
        'label': 'Delivery task — reply thread',
        'description': 'The chat box on a delivery task page that shows the customer\'s '
                       'last message and sends a free-text reply. Separate widget from '
                       'the send modal above it. Uses the routed number but always goes '
                       'out over Evolution, so a WAHA channel here is not honoured yet.',
        'action': 'workforce.views.whatsapp_send_message',
        'department': 'ops',
        'section': 'orders_tasks',
        'template_key': '',
        'links': [('Delivery Tasks', 'workforce:dl_list_all')],
    },
    {
        'code': 'composer_verify_queue',
        'label': 'Verification queue — Send now / Resend',
        'description': 'Force-sends a queued address-verification message immediately, '
                       'bypassing the rate-limit window. Same body as the order composer.',
        'action': 'workforce.views._verify_action_send_now',
        'department': 'ops',
        'section': 'orders_tasks',
        'template_key': ORDER_VERIFY_MANUAL,
        'links': [('Pending Verification', 'workforce:orders_pending_verification')],
    },
    {
        'code': 'composer_wa_chats',
        'label': 'WhatsApp Chats — agent reply box',
        'description': 'Free-text reply from the WAHA agent inbox. Goes out on whichever '
                       'session the chat is open on, so the sender routes below do not '
                       'apply and there is no template to edit.',
        'action': 'whatsapp.wa_chats_view.wa_chats_send',
        'department': 'ops',
        'section': '',
        'template_key': '',
        'links': [('WhatsApp Chats', '/waha/wa-chats/')],
        'url_is_path': True,
    },
    {
        'code': 'composer_wa_me_links',
        'label': 'wa.me buttons (staff\'s own WhatsApp)',
        'description': 'The green WhatsApp icons on order, task, driver, lead and store '
                       'pages open the staff member\'s OWN WhatsApp with text pre-filled. '
                       'They never touch a platform number, so nothing on this page '
                       'affects them and the customer replies to that person privately.',
        'action': 'template wa.me links (not a platform send)',
        'department': 'admin',
        'section': '',
        'template_key': '',
        'links': [],
    },
]


class _SafeDict(dict):
    """Leaves unknown ``{placeholders}`` untouched instead of raising KeyError."""

    def __missing__(self, key):
        return '{' + key + '}'


def get_template(key):
    """Return the effective template for ``key`` as a dict.

    Keys: label, description, placeholders, body, is_enabled, is_customised,
    kind, section, toggle_owner.
    Falls back to the code default when no staff-edited row exists.
    """
    from core.models import MessageTemplate

    default = TEMPLATE_DEFAULTS.get(key, {})
    data = {
        'key': key,
        'label': default.get('label', key),
        'description': default.get('description', ''),
        'placeholders': default.get('placeholders', ''),
        'sender': default.get('sender', 'default'),
        'kind': default.get('kind', KIND_AUTO),
        'section': default.get('section', ''),
        'toggle_owner': default.get('toggle_owner', ''),
        'body': default.get('body', ''),
        'default_body': default.get('body', ''),
        'is_enabled': True,
        'is_customised': False,
    }
    row = MessageTemplate.objects.filter(key=key).first()
    if row:
        data['is_enabled'] = row.is_enabled
        data['is_customised'] = bool((row.body or '').strip()) and row.body.strip() != data['default_body'].strip()
        if (row.body or '').strip():
            data['body'] = row.body
    return data


def list_templates():
    """All registered templates with their current staff overrides applied."""
    return [get_template(key) for key in TEMPLATE_DEFAULTS]


def get_body(key, **context):
    """Formatted body ignoring the on/off switch — for templates whose enable
    state is owned elsewhere (``toggle_owner``), where returning None would
    silently break an automatic pipeline."""
    tpl = get_template(key)
    return _format(key, tpl['body'], context)


def render_template(key, **context):
    """Return the formatted body, or None when the template is switched off.

    Unknown placeholders are left as-is rather than blowing up a send.
    """
    tpl = get_template(key)
    if not tpl['is_enabled']:
        return None
    return _format(key, tpl['body'], context)


def _format(key, body, context):
    try:
        return body.format_map(_SafeDict(**context)).strip()
    except Exception:
        logger.exception('Message template %s failed to render — sending raw body', key)
        return body.strip()
