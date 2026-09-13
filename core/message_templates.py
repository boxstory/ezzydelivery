# Purpose: Registry + resolver for editable outbound WhatsApp message bodies, plus the
#          inventory of staff-driven manual composers that use them.
# Used by: core.whatsapp_utils senders, workforce.views (order/task composers, auto_triggers_list,
#          wf_message_templates page), workforce.crm_views lead detail.
# Notes: Defaults live here so a fresh install works with no DB rows; staff edits are
#        stored in core.MessageTemplate under the same key and always win. Entries with
#        kind='composer' only pre-fill a textarea — switching one off gives staff a blank
#        composer, it never blocks a send. Entries carrying `toggle_owner` have their
#        on/off owned by an AutoTriggerConfig row, so the Messages page hides the switch.
#        Bodies support `{if name}...{else}...{endif}` blocks - see apply_conditionals.

import logging
import re

logger = logging.getLogger(__name__)

DRIVER_APPLICATION_THANKS = 'driver_application_thanks'
CRM_LEAD_MANUAL = 'crm_lead_manual'
CRM_DRIVER_LEAD_MANUAL = 'crm_driver_lead_manual'
PRICING_INQUIRY_MANUAL = 'pricing_inquiry_manual'
ORDER_VERIFY_MANUAL = 'order_verify_manual'
ORDER_DELIVERY_RECOVERY = 'order_delivery_recovery'
PRICING_INQUIRY_THANKS = 'pricing_inquiry_thanks'
PRICING_INQUIRY_RESUME_NUDGE = 'pricing_inquiry_resume_nudge'
QUOTE_ADMIN_ALERT = 'quote_admin_alert'
QUOTE_AGREED_ALERT = 'quote_agreed_alert'
P2P_BOOKING_CONFIRM = 'p2p_booking_confirm'
P2P_COMMENT_OPS_ALERT = 'p2p_comment_ops_alert'
CLIENT_INVOICE_MANUAL = 'client_invoice_manual'

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
        'placeholders': (
            'customer_name, order_number, client_order_code, items_line, verify_url, '
            'business_name, business_phone, seller_line, customer_phone, '
            'customer_address, delivery_area, cod_amount, cod_line'
        ),
        'required': 'verify_url',
        'sender': 'default',
        'kind': KIND_COMPOSER,
        'section': 'orders_tasks',
        'toggle_owner': 'wa_location_verification',
        'body': """Hi {customer_name}, this is regarding your order {order_number}. Please confirm your delivery details and availability.

{items_line}📌 Verify your location: {verify_url}""",
    },
    ORDER_DELIVERY_RECOVERY: {
        'label': 'Delivery failed — recovery message',
        'description': (
            'Sent to the customer 10 minutes after a driver marks a delivery failed, '
            'carrying the driver\'s reason and a fresh location link so the address can '
            'be fixed and the delivery retried. Switching it off cancels the queued '
            'recovery messages instead of sending a blank one.'
        ),
        'placeholders': ('customer_name, order_number, reason_line, reason, verify_url, '
                         'business_name, customer_phone'),
        'required': 'verify_url',
        'sender': 'default',
        'kind': KIND_AUTO,
        'section': 'orders_tasks',
        'toggle_owner': '',
        'body': """Hi {customer_name}, sorry — we couldn't complete delivery of your order {order_number}.

{reason_line}We'd like to deliver again. Please confirm your location so the driver can find you:
\U0001F4CC {verify_url}

Or reply with your live WhatsApp location pin.""",
    },

    CLIENT_INVOICE_MANUAL: {
        'label': 'Delivery charge invoice — composer starter',
        'description': (
            'Pre-fills the WhatsApp button on a client delivery-charge invoice, so the '
            'seller gets the amount due and a link to their own copy. Staff read and '
            'edit it before sending.'
        ),
        'placeholders': ('invoice_code, business_name, delivery_count, amount_due, '
                         'due_line, due_date, invoice_url'),
        'required': 'invoice_url',
        'sender': 'default',
        'kind': KIND_COMPOSER,
        'section': 'orders_tasks',
        'toggle_owner': '',
        'body': """*EzzyDelivery — Invoice {invoice_code}*

{business_name}
Deliveries: {delivery_count}
Amount due: QAR {amount_due}
{due_line}
Invoice: {invoice_url}""",
    },

    P2P_BOOKING_CONFIRM: {
        'label': 'P2P booking — confirm your delivery',
        'description': (
            'Sent to whoever booked a point-to-point delivery, with what was booked and '
            'the link that releases the job to a driver. On/off is owned by the '
            'p2p_booking_confirm trigger.'
        ),
        'placeholders': ('from_label, to_label, order_number, box_count, price, fee_note, '
                         'cod_amount, return_route, return_order_number, confirm_url'),
        'required': 'confirm_url',
        'sender': 'default',
        'kind': KIND_AUTO,
        'section': 'orders_tasks',
        'toggle_owner': 'p2p_booking_confirm',
        'body': """EzzyDelivery — your P2P delivery

From: {from_label}
To: {to_label}
{if order_number}Order: {order_number}
{endif}{if box_count}Boxes: {box_count}
{endif}{if return_route}Leg back: {return_route}
{endif}{if return_order_number}Return order: {return_order_number}
{endif}{if price}Delivery fee: QAR {price}
{fee_note}
{else}Delivery fee: our team will confirm the price shortly
{endif}{if cod_amount}Cash to collect from the receiver: QAR {cod_amount}
{endif}
Tap to confirm and we will assign a driver:
{confirm_url}""",
    },

    P2P_COMMENT_OPS_ALERT: {
        'label': 'P2P customer comment — desk alert',
        'description': (
            'Internal. Tells the ops desk that a P2P sender replied on their order. '
            'Goes to the number on the p2p_customer_comment trigger row, which also '
            'owns its on/off.'
        ),
        'placeholders': 'order_number, comment',
        'required': '',
        'sender': 'default',
        'kind': KIND_AUTO,
        'section': 'orders_tasks',
        'toggle_owner': 'p2p_customer_comment',
        'body': """P2P customer comment on {order_number}:

{comment}""",
    },

    PRICING_INQUIRY_THANKS: {
        'label': '3PL quote request — thank you',
        'description': (
            'Sent automatically to the lead the moment they finish the delivery pricing '
            'form, from the CRM & Leads number so their reply lands in the sales inbox. '
            'On/off is owned by the wa_quote_thank_you trigger.'
        ),
        'placeholders': 'business_name, contact_name',
        'required': '',
        'sender': 'default',
        'kind': KIND_AUTO,
        'section': 'crm_leads',
        'toggle_owner': 'wa_quote_thank_you',
        'body': """\u2705 *Thank You for Your 3PL Inquiry!*

Hi {business_name},

We've received your inquiry and appreciate your interest in EZZY Delivery.

Our team will review your business requirements and contact you within 24 hours with a customized quote.

In the meantime, feel free to reach out to us if you have any questions.

Best regards,
*EZZY Delivery Team* \U0001F69A""",
    },

    PRICING_INQUIRY_RESUME_NUDGE: {
        'label': '3PL quote request — half-finished nudge',
        'description': (
            'Sent the morning after a lead started the pricing form and never finished '
            'it, once only. The link carries their own quote token, so they resume where '
            'they stopped. On/off is owned by the wa_inquiry_resume_nudge trigger.'
        ),
        'placeholders': 'business_name, resume_url',
        'required': 'resume_url',
        'sender': 'default',
        'kind': KIND_AUTO,
        'section': 'crm_leads',
        'toggle_owner': 'wa_inquiry_resume_nudge',
        'body': """*Your EZZY Delivery quote is half-finished*

{if business_name}Hi {business_name},{else}Hi,{endif}

You started a delivery pricing request with us yesterday but did not get to the end of it.

Your answers are saved. Pick up where you left off here:
{resume_url}

It takes about two minutes, and you will see your rate straight away.

If you would rather just talk it through, reply to this message and someone from the team will help.

*EZZY Delivery* \U0001F69A""",
    },

    QUOTE_ADMIN_ALERT: {
        'label': '3PL quote request — desk alert',
        'description': (
            'Internal. Tells the sales desk a new pricing inquiry arrived, with the '
            'headline answers and a link to the full record. Goes to the number on the '
            'wa_quote_admin_alert trigger row, which also owns its on/off.'
        ),
        'placeholders': ('business_name, contact_name, phone, email, product_category, '
                         'orders_last_month, preferred_start, cod, fulfillment_outside, '
                         'returns, submitted_at, inquiry_id, inquiry_url'),
        'required': 'inquiry_url',
        'sender': 'default',
        'kind': KIND_AUTO,
        'section': 'crm_leads',
        'toggle_owner': 'wa_quote_admin_alert',
        'body': """\U0001F4E9 *NEW 3PL INQUIRY RECEIVED*

*Company:* {business_name}
*Contact:* {contact_name}
*Phone:* {phone}
*Email:* {email}

*Product Category:* {product_category}
*Order Volume (Last Month):* {orders_last_month}
*Preferred Start:* {preferred_start}

*Services Required:*
\u2022 COD: {cod}
\u2022 Fulfillment (Outside QA): {fulfillment_outside}
\u2022 Return Logistics: {returns}

*Submitted:* {submitted_at}
*Inquiry ID:* {inquiry_id}

\U0001F449 View inquiry details:
{inquiry_url}""",
    },

    QUOTE_AGREED_ALERT: {
        'label': '3PL quote — customer picked a plan',
        'description': (
            'Internal. Fires when a prospect accepts a plan on their quote page, or asks '
            'to talk to sales instead — use {if wants_call} to word those two cases '
            'differently. Goes to the number on the wa_quote_agreed_alert trigger row, '
            'which also owns its on/off.'
        ),
        'placeholders': ('wants_call, business_name, contact_name, phone, plan_name, '
                         'agreed_price, confirmed_at, note, inquiry_id, inquiry_url'),
        'required': 'inquiry_url',
        'sender': 'default',
        'kind': KIND_AUTO,
        'section': 'crm_leads',
        'toggle_owner': 'wa_quote_agreed_alert',
        'body': """{if wants_call}\U0001F5E3\uFE0F *QUOTE \u2014 CUSTOMER WANTS TO TALK*{else}\U0001F91D *QUOTE ACCEPTED BY CUSTOMER*{endif}

*Company:* {business_name}
*Contact:* {contact_name}
*Phone:* {phone}

*Plan:* {plan_name}
{if wants_call}*Requested:* Custom plan \u2014 call back to agree a rate{else}*Agreed Price:* {agreed_price}{endif}
*Confirmed:* {confirmed_at}
{if note}
*Customer note:* {note}
{endif}
*Inquiry ID:* {inquiry_id}

\U0001F449 View inquiry details:
{inquiry_url}""",
    },
}


# ---------------------------------------------------------------------------
# What each {placeholder} actually puts in the message.
#
# Shown as the tooltip on the insert chips (Messages page and the Auto Triggers
# popup) so a staff member choosing between `business_name` and `seller_line`
# can tell them apart without sending a test message to a real customer.
#
# A name ending in `_line` is a whole ready-made line, emoji and trailing
# newline included, and renders as nothing when the value is missing — drop one
# on its own line and the message closes up when there is no value to show.
# ---------------------------------------------------------------------------
PLACEHOLDER_HINTS = {
    'first_name': "Applicant's first name",
    'lead_name': "Lead's name",
    'contact_name': 'Contact person on the inquiry',
    'company': "Lead's company",
    'business_name': 'Seller / store the order belongs to',
    'business_phone': "Seller's contact number",
    'staff_name': 'The staff member sending the message',
    'customer_name': 'Customer name on the order',
    'customer_phone': 'Customer phone number on the order',
    'customer_address': 'Address text saved on the order',
    'delivery_area': 'Neighbourhood resolved from the delivery pin',
    'order_number': 'EZZY order number',
    'client_order_code': "Seller's own order reference",
    'cod_amount': 'Amount to collect, e.g. 250.00 — blank when prepaid',
    'verify_url': 'One-time link the customer taps to pin their location',
    'seller_line': 'Whole line: 🏬 Order from: <store> — blank if unknown',
    'items_line': 'Whole line: 🛒 Items: … — blank when nothing is itemised',
    'cod_line': 'Whole line: 💵 Cash on delivery: QAR … — blank when prepaid',
    # Delivery recovery
    'reason': 'What the driver said went wrong',
    'reason_line': 'Whole line: Reason: … — blank when the driver left no note',
    # Client charge invoice
    'invoice_code': 'Invoice number',
    'delivery_count': 'How many deliveries the invoice covers',
    'amount_due': 'Amount due, e.g. 1,250.00',
    'due_date': 'Payment due date, e.g. 14 Sep 2026',
    'due_line': 'Whole line: Due by: … — blank when the invoice has no due date',
    'invoice_url': "Link to the seller's own copy of the invoice",
    # P2P booking
    'from_label': 'Pickup point the customer typed',
    'to_label': 'Drop point the customer typed',
    'box_count': 'Number of boxes booked',
    'price': 'Agreed delivery fee — blank until staff price it',
    'fee_note': 'The one-line explanation of how that fee was reached',
    'confirm_url': 'Link the booker taps to release the job to a driver',
    'comment': 'What the customer wrote',
    # 3PL quote / lead
    'resume_url': 'Link back into their half-finished pricing form',
    'inquiry_id': 'Pricing inquiry ID',
    'inquiry_url': 'Staff link to the full inquiry record',
    'phone': 'Contact number on the inquiry',
    'email': 'Email on the inquiry',
    'product_category': 'What the lead sells',
    'orders_last_month': 'Orders they did last month',
    'preferred_start': 'When they want to start',
    'cod': 'Yes / No — COD required',
    'fulfillment_outside': 'Yes / No — fulfilment for a seller outside Qatar',
    'returns': 'Yes / No — return logistics required',
    'submitted_at': 'When the form was submitted (Qatar time)',
    'wants_call': 'Set only when they asked to talk instead of accepting a plan',
    'plan_name': 'Plan they picked',
    'agreed_price': 'Price of the plan they accepted',
    'confirmed_at': 'When they confirmed (Qatar time)',
    'note': 'Note the customer left with their choice — blank if none',
}


def placeholder_hint(name):
    """Tooltip for one placeholder chip; a generic nudge for unlisted names."""
    return PLACEHOLDER_HINTS.get(name, 'Insert at the cursor')


def placeholder_list(placeholders):
    """``'a, b'`` -> ``[{'name': 'a', 'hint': …}, …]`` for the chip rows."""
    return [
        {'name': p.strip(), 'hint': placeholder_hint(p.strip())}
        for p in (placeholders or '').split(',') if p.strip()
    ]


# ---------------------------------------------------------------------------
# Which AutoTriggerConfig row SENDS each stored body.
#
# Not the same question as ``toggle_owner``, which says which trigger owns a
# body's on/off switch. The driver thank-you keeps its own switch on the
# Messages page yet is fired by ``wa_driver_application_thanks``, so it appears
# here and not there; the verification body is the reverse case and appears in
# both. Used by the Auto Triggers page to hang the body editor on the trigger
# row that produces it.
# ---------------------------------------------------------------------------
TRIGGER_TEMPLATES = {
    'wa_driver_application_thanks': DRIVER_APPLICATION_THANKS,
    'wa_location_verification': ORDER_VERIFY_MANUAL,
    'wa_quote_thank_you': PRICING_INQUIRY_THANKS,
    'wa_inquiry_resume_nudge': PRICING_INQUIRY_RESUME_NUDGE,
    'wa_quote_admin_alert': QUOTE_ADMIN_ALERT,
    'wa_quote_agreed_alert': QUOTE_AGREED_ALERT,
    'p2p_booking_confirm': P2P_BOOKING_CONFIRM,
    'p2p_customer_comment': P2P_COMMENT_OPS_ALERT,
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
        'code': 'composer_client_invoice',
        'label': 'Delivery charge invoice — WhatsApp the client',
        'description': 'The WhatsApp button on a client delivery-charge invoice. Sends '
                       'the amount due and a link to the seller\'s own copy of it.',
        'action': 'workforce.views.client_charge_invoice_whatsapp',
        # Finance staff press this button, but it leaves on the orders/tasks route —
        # and a composer must sit on the desk that owns the route row it uses, or it
        # cross-links to a row that is not on screen.
        'department': 'ops',
        'section': 'orders_tasks',
        'template_key': CLIENT_INVOICE_MANUAL,
        'links': [('Client Invoices', 'workforce:client_charge_invoices')],
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


# ---------------------------------------------------------------------------
# Conditional blocks — ``{if cod_amount}…{else}…{endif}``
#
# Staff asked to word the optional lines themselves rather than take whatever
# wording a ready-made ``*_line`` placeholder ships with: show a COD line only
# when there is COD to collect, name the store only when it is known. Kept to
# one placeholder name per condition, no operators — a zero amount and a blank
# field are the same "nothing to say here" case, and an editor that can express
# more than that is an editor that can break a customer send.
#
# A tag alone on its own line takes that line with it, so a false block leaves
# no blank gap. Nesting is not supported: the first {endif} closes the block.
# ---------------------------------------------------------------------------
_TAG_OWN_LINE_RE = re.compile(
    r'^[ \t]*(\{(?:if\s+\w+|else|endif)\})[ \t]*\r?\n', re.MULTILINE)
_COND_RE = re.compile(
    r'\{if\s+(\w+)\}(.*?)(?:\{else\}(.*?))?\{endif\}', re.DOTALL)

_FALSEY_WORDS = {'0', 'false', 'none', 'no'}


def _has_value(value):
    """True when a placeholder has something worth printing.

    A zero amount is nothing to say, so ``{if cod_amount}`` is also the
    "COD is greater than zero" test staff read it as.
    """
    if value is None:
        return False
    text = str(value).strip()
    if not text or text.lower() in _FALSEY_WORDS:
        return False
    try:
        return float(text.replace(',', '')) != 0
    except ValueError:
        return True


def apply_conditionals(body, context):
    """Resolve every ``{if …}`` block against ``context``."""
    body = _TAG_OWN_LINE_RE.sub(r'\1', body)

    def resolve(match):
        name, yes, no = match.group(1), match.group(2), match.group(3) or ''
        return yes if _has_value(context.get(name)) else no

    # One pass per nesting level would invite runaway bodies; a single pass
    # matches the documented "no nesting" rule.
    return _COND_RE.sub(resolve, body)


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
        'required': default.get('required', ''),
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


def required_placeholders(key):
    """Placeholder names a body for ``key`` cannot be saved without."""
    raw = TEMPLATE_DEFAULTS.get(key, {}).get('required', '')
    return [p.strip() for p in raw.split(',') if p.strip()]


def validate_body(key, body):
    """Error string when this body must not be saved, else ''.

    A reworded message that drops its link or its code still sends — it just
    sends something useless to a customer, from a page whose whole point is
    that staff can reword safely. So the tokens a message cannot work without
    are refused at the save rather than discovered in a support call.
    """
    missing = [name for name in required_placeholders(key)
               if '{' + name + '}' not in (body or '')]
    if not missing:
        return ''
    tokens = ', '.join('{' + name + '}' for name in missing)
    return (f'This message cannot be sent without {tokens} — put it back in the '
            f'text before saving.')


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
        body = apply_conditionals(body, context)
        return body.format_map(_SafeDict(**context)).strip()
    except Exception:
        logger.exception('Message template %s failed to render — sending raw body', key)
        return body.strip()
