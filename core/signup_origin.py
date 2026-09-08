# Purpose: Track how a visitor arrived (driver join / client join / pricing inquiry / plain website) and keep it on the session until they sign up.
# Used by: core/middleware.py (SignupOriginMiddleware), core/signals.py (stamps the new Profile), webpages/views.py (pricing inquiry form).
# Notes: Intent is "last one wins" — someone who reads the blog then opens the driver link is a driver signup, not a website visit.

from urllib.parse import urlparse

SESSION_KEY = 'signup_origin'

SOURCE_DRIVER = 'driver_join'
SOURCE_BUSINESS = 'business_join'
SOURCE_TEAM = 'team_join'
SOURCE_PRICING = 'pricing_inquiry'
SOURCE_WEBSITE = 'website'
SOURCE_DIRECT = 'direct_login'
SOURCE_UNKNOWN = 'unknown'

SOURCE_CHOICES = [
    (SOURCE_DRIVER, 'Driver Join Link'),
    (SOURCE_BUSINESS, 'Client Join'),
    (SOURCE_TEAM, 'Team Join'),
    (SOURCE_PRICING, 'Pricing Inquiry'),
    (SOURCE_WEBSITE, 'Website Visit'),
    (SOURCE_DIRECT, 'Direct Login'),
    (SOURCE_UNKNOWN, 'Unknown'),
]

# Path prefixes that carry a clear intent. Longest/most specific first.
INTENT_PATHS = [
    ('/join_us/driver', SOURCE_DRIVER),
    ('/ar/join_us/driver', SOURCE_DRIVER),
    ('/join_driver', SOURCE_DRIVER),
    ('/driver/start', SOURCE_DRIVER),
    ('/join_us/business', SOURCE_BUSINESS),
    ('/join_us/team', SOURCE_TEAM),
    ('/3pl/inquiry', SOURCE_PRICING),
    ('/3pl/pricing', SOURCE_PRICING),
    ('/p2p/pricing', SOURCE_PRICING),
]

# The auth pages themselves are not an intent — landing straight on one is.
AUTH_PREFIXES = ('/accounts/',)

# Never attribute from these — assets, machine traffic and internal consoles.
SKIP_PREFIXES = (
    '/static/', '/staticroot/', '/media/', '/private_media/',
    '/api/', '/webhook', '/waha/', '/admin/', '/__debug__/',
    '/favicon', '/robots.txt', '/sitemap',
)

UTM_KEYS = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gclid', 'fbclid')

# Crawlers never sign up, and every session we open for one is a django_session row.
BOT_UA_TOKENS = (
    'bot', 'crawl', 'spider', 'slurp', 'archiver', 'headlesschrome',
    'python-requests', 'curl/', 'wget', 'facebookexternalhit', 'whatsapp',
    'preview', 'monitor', 'pingdom', 'lighthouse',
)

MAX_LEN = 255


def classify_path(path):
    """Return the intent source for a path, or None when the path carries no intent."""
    for prefix, source in INTENT_PATHS:
        if path.startswith(prefix):
            return source
    return None


def is_bot(request):
    """True for obvious crawler / monitor traffic, which must not open a session."""
    ua = (request.META.get('HTTP_USER_AGENT') or '').lower()
    if not ua:
        return True
    return any(token in ua for token in BOT_UA_TOKENS)


def _blank_origin(path, request):
    """First-touch record: where the visitor landed, what sent them, and any campaign tags."""
    referrer = (request.META.get('HTTP_REFERER') or '')[:MAX_LEN]
    # An off-site referrer is real attribution; our own pages are just internal navigation.
    if referrer:
        host = urlparse(referrer).netloc.lower()
        if host and host.split(':')[0] in _own_hosts(request):
            referrer = ''

    utm = {k: request.GET.get(k)[:MAX_LEN] for k in UTM_KEYS if request.GET.get(k)}

    landed_on_auth = path.startswith(AUTH_PREFIXES)
    return {
        'source': SOURCE_DIRECT if landed_on_auth else SOURCE_WEBSITE,
        'landing_path': path[:MAX_LEN],
        'referrer': referrer,
        'utm': utm,
    }


def _own_hosts(request):
    host = request.get_host().split(':')[0].lower()
    return {host, 'www.' + host, host[4:] if host.startswith('www.') else host}


def capture(request, first_touch=True):
    """Record first-touch on the first anonymous page view, then upgrade the source on any intent page.

    first_touch=False (already-authenticated visitors) only upgrades an existing
    record on intent pages — someone mid-signup who clicks the driver link after
    logging in still counts as a driver signup, but a normal browsing session
    never starts an attribution.
    """
    path = request.path
    if path.startswith(SKIP_PREFIXES) or is_bot(request):
        return

    session = request.session
    origin = session.get(SESSION_KEY)
    intent = classify_path(path)
    if not isinstance(origin, dict):
        if not first_touch and intent is None:
            return
        origin = _blank_origin(path, request)
        session[SESSION_KEY] = origin

    if intent and origin.get('source') != intent:
        origin['source'] = intent
        session[SESSION_KEY] = origin
        session.modified = True


def mark_intent(request, source):
    """Force the intent from a view — used where the URL alone does not prove it (e.g. a submitted pricing form)."""
    session = getattr(request, 'session', None)
    if session is None:
        return
    origin = session.get(SESSION_KEY)
    if not isinstance(origin, dict):
        origin = _blank_origin(request.path, request)
    origin['source'] = source
    session[SESSION_KEY] = origin
    session.modified = True


def apply_to(profile, request):
    """Copy the session origin onto an unsaved Profile. The caller still saves it."""
    origin = read(request)
    profile.signup_source = origin['source']
    profile.signup_landing_path = origin['landing_path']
    profile.signup_referrer = origin['referrer']
    profile.signup_utm = origin['utm']
    return profile


def read(request):
    """Return the session origin for stamping onto a Profile, with safe fallbacks."""
    session = getattr(request, 'session', None) if request is not None else None
    origin = session.get(SESSION_KEY) if session is not None else None
    if not isinstance(origin, dict):
        return {'source': SOURCE_UNKNOWN, 'landing_path': '', 'referrer': '', 'utm': {}}
    return {
        'source': origin.get('source') or SOURCE_UNKNOWN,
        'landing_path': (origin.get('landing_path') or '')[:MAX_LEN],
        'referrer': (origin.get('referrer') or '')[:MAX_LEN],
        'utm': origin.get('utm') if isinstance(origin.get('utm'), dict) else {},
    }
