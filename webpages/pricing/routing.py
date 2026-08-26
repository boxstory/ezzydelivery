# Purpose: Spot a pricing inquiry that is really a one-off personal sender, not a 3PL client.
# Used by: workforce.views.pricing_inquiry_detail (staff banner) and webpages.views.inquiry_quote
#          (a P2P link offered to the sender).
# Notes: Scored rather than a single rule, because every individual signal has honest false
#        positives — plenty of real businesses start at home with no orders yet. Only the
#        combination is telling. Never blocks anything: it points at the P2P page, that is all.

from webpages.pricing import bands

# Phrases people actually write when the form is the wrong one for them. Kept as
# whole phrases: a bare "gift" would flag every florist, and "Gifts & Flowers" is
# one of the product categories on the form.
PERSONAL_PHRASES = (
    'not a business', 'not business', 'no business', 'personal use', 'personal gift',
    'personal delivery', 'personal only', 'one time', 'one-time', 'one off', 'one-off',
    'for myself', 'my own use', 'individual use', 'private use', 'single delivery',
)

# What someone types when they have no company name.
PERSONAL_NAMES = {
    'personal', 'individual', 'private', 'self', 'myself', 'me', 'none', 'n/a', 'na',
    'personal use', 'no business', 'not a business', 'private individual',
}

# Enough signal to be worth a sales person's attention. Tuned so a genuine
# home-run startup (new + low volume + home pickup = 3) stays below it and only
# trips when the name or the notes also say "personal".
THRESHOLD = 4

VERY_LOW_MONTHLY_ORDERS = 25


def p2p_signals(inquiry):
    """{'is_likely_p2p': bool, 'score': int, 'reasons': [str]} for one inquiry."""
    reasons = []
    score = 0

    name = (inquiry.business_name or '').strip().lower()
    if name in PERSONAL_NAMES:
        score += 3
        reasons.append(f'Business name is "{inquiry.business_name}"')

    notes = (inquiry.additional_notes or '').lower()
    matched = next((phrase for phrase in PERSONAL_PHRASES if phrase in notes), '')
    if matched:
        score += 3
        reasons.append(f'Their note says "{matched}"')

    if (inquiry.business_operating_age or '').strip() == 'New (not started yet)':
        score += 1
        reasons.append('Business has not started trading')

    monthly = bands.normalise_enquiry(inquiry).get('monthly_orders')
    if monthly is not None and monthly < VERY_LOW_MONTHLY_ORDERS:
        score += 1
        reasons.append(f'Very low volume (about {int(monthly)} orders a month)')

    if (inquiry.type_of_pickup_location or '').strip() == 'Home':
        score += 1
        reasons.append('Pickup from home')

    return {
        'is_likely_p2p': score >= THRESHOLD,
        'score': score,
        'reasons': reasons,
    }
