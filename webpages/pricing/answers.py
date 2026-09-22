# Purpose: Store a pricing-inquiry answer that is too long for its column instead of losing it.
# Used by: webpages.views (the public 3PL form) and workforce.views.pricing_inquiry_detail.
# Notes: The form never rejects an over-long answer — column widths are our storage problem,
#        not the seller's. The value is saved cut to fit, the full text is kept on the record
#        in PricingEnquiry.trimmed_answers, and the seller is asked to shorten it themselves.

from core.validators import sanitize_text

# TextField has no width of its own, so give it one rather than accept a
# megabyte of pasted text into a field sales has to read.
LONG_TEXT_LIMIT = 5000

# Field -> what the form calls it, for the "please shorten these" notice and the
# staff panel. Only answers a human types freely can overflow; picker answers are
# our own strings and always fit.
ANSWER_LABELS = {
    'full_name': 'Contact Person Name',
    'business_name': 'Business Name',
    'business_contact_number': 'Business Contact Number',
    'operation_team_contact_number': 'Operations Team Contact',
    'email': 'Email',
    'website_url': 'Website URL',
    'instagram_profile': 'Instagram',
    'facebook_profile': 'Facebook',
    'social_profile': 'Social Profile',
    'product_category': 'Product Category',
    'business_location_country': 'Business Location Country',
    'current_courier_provider': 'Current Courier / 3PL Provider',
    'special_handling_detail': 'Special Handling Detail',
    'type_of_pickup_location': 'Type of Pickup Location',
    'pickup_Location_area_name': 'Pickup Location Area',
    'order_management_system': 'Order Management System',
    'additional_notes': 'Additional Notes',
}


def apply_answers(inquiry, answers, flags=None):
    """Write one step's answers onto the record, clamped to the column widths.

    Returns {field: full text} for every answer that had to be cut, and keeps the
    same on ``inquiry.trimmed_answers`` so sales still has what was actually
    submitted. An answer the seller has since shortened drops back out of it, and
    only the fields this step owns are touched.
    """
    trimmed = {}
    for field_name, raw in answers.items():
        field = inquiry._meta.get_field(field_name)
        # Notes are a paragraph: collapsing their whitespace would run the
        # seller's line breaks together. Every other answer is a single line.
        text = sanitize_text(raw or '', collapse_whitespace=field_name != 'additional_notes')
        limit = field.max_length or LONG_TEXT_LIMIT
        if len(text) > limit:
            trimmed[field_name] = text
            text = text[:limit].rstrip()
        setattr(inquiry, field_name, text)

    for field_name, value in (flags or {}).items():
        setattr(inquiry, field_name, value)

    kept = {name: value for name, value in (inquiry.trimmed_answers or {}).items()
            if name not in answers}
    kept.update(trimmed)
    inquiry.trimmed_answers = kept
    inquiry.save()
    return trimmed


def trimmed_labels(inquiry):
    """Form labels for every answer still sitting on the record cut short."""
    return [ANSWER_LABELS.get(name, name)
            for name in sorted(inquiry.trimmed_answers or {})]


def trimmed_detail(inquiry):
    """[(label, full text)] for the staff panel, longest answers read as typed."""
    return [(ANSWER_LABELS.get(name, name), value)
            for name, value in sorted((inquiry.trimmed_answers or {}).items())]
