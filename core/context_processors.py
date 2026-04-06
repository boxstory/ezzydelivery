"""
Context processors for EzzyDelivery
Makes data available to all templates

Also provides utility functions for views to get cached user data:
    - get_cached_profile(request) -> Profile or None
    - get_cached_business(request) -> Business or None
"""
import datetime
from core.seo import SEOMetadata
import json


# =============================================================================
# UTILITY FUNCTIONS FOR VIEWS
# =============================================================================

def get_cached_profile(request):
    """
    Get cached user profile for use in views.
    Uses the same cache as user_profile context processor.

    Usage in views:
        from core.context_processors import get_cached_profile
        profile = get_cached_profile(request)

    Returns:
        Profile object or None
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return None

    # Check if already cached
    if hasattr(request, '_cached_profile'):
        return request._cached_profile

    from core.models import Profile
    try:
        profile = Profile.objects.select_related('user').get(user_id=request.user.id)
        request._cached_profile = profile
        return profile
    except Profile.DoesNotExist:
        request._cached_profile = None
        return None


def get_cached_business(request):
    """
    Get cached user business for use in views.
    Uses the same cache as user_business context processor.

    Usage in views:
        from core.context_processors import get_cached_business
        business = get_cached_business(request)

    Returns:
        Business object or None
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return None

    # Check if already cached
    if hasattr(request, '_cached_user_business'):
        return request._cached_user_business

    # Check if cached via business_permissions_context
    if hasattr(request, '_cached_business_access'):
        business, _, _ = request._cached_business_access
        request._cached_user_business = business
        return business

    # Check if decorator already injected business
    if hasattr(request, 'current_business') and request.current_business:
        request._cached_user_business = request.current_business
        return request.current_business

    from business.models import Business
    try:
        business = Business.objects.filter(user_id=request.user.id).first()
        if business:
            request._cached_user_business = business
            return business

        # Cache None so get_user_business_access skips the duplicate owner query
        request._cached_user_business = None

        # Check if user is a team member (not just owner)
        from business.decorators import get_user_business_access
        team_business, access_type, team_profile = get_user_business_access(request.user, request)
        request._cached_user_business = team_business
        return team_business
    except Exception:
        request._cached_user_business = None
        return None


# =============================================================================
# CONTEXT PROCESSORS
# =============================================================================


def seo_defaults(request):
    """
    Add default SEO metadata to all templates
    Views can override these by passing their own meta dict
    """
    # Skip SEO processing on non-public paths — no SEO meta needed there
    _skip_prefixes = ('/fleet/', '/dashboard/', '/warehouse/', '/workforce/', '/api/', '/admin/', '/__debug__/', '/media/', '/static/')
    if any(request.path.startswith(p) for p in _skip_prefixes):
        return {
            'seo': {},
            'site_name': SEOMetadata.SITE_NAME,
            'business_phone': SEOMetadata.BUSINESS_PHONE,
            'business_email': SEOMetadata.BUSINESS_EMAIL,
        }

    # Get current path for canonical URL
    current_url = request.build_absolute_uri()

    # Default metadata
    default_meta = SEOMetadata.get_page_meta(url=current_url)

    return {
        'seo': default_meta,
        'site_name': SEOMetadata.SITE_NAME,
        'business_phone': SEOMetadata.BUSINESS_PHONE,
        'business_email': SEOMetadata.BUSINESS_EMAIL,
    }


def site_info(request):
    """Add general site information"""
    return {
        'SITE_NAME': 'EzzyDelivery Qatar',
        'SITE_TAGLINE': 'Professional Delivery Services in Qatar',
        'CURRENT_YEAR': datetime.date.today().year,
        'SUPPORT_EMAIL': 'support@ezzydelivery.qa',
        'SUPPORT_PHONE': '+974-XXXX-XXXX',
    }


def social_media_links(request):
    """
    Add social media links to all templates
    Update these URLs with your actual social media profiles
    """
    return {
        'SOCIAL_MEDIA': {
            'facebook': 'https://www.facebook.com/ezzydeliveryqatar',
            'instagram': 'https://www.instagram.com/ezzydeliveryqatar',
            'whatsapp': 'https://wa.me/97412345678',  # Replace with actual WhatsApp business number
            'twitter': 'https://twitter.com/ezzydeliveryqa',
            'linkedin': 'https://www.linkedin.com/company/ezzydelivery-qatar',
            'youtube': 'https://www.youtube.com/@ezzydeliveryqatar',
        },
        'CONTACT_LINKS': {
            'support': '/contact/',
            'help_center': '/help-center/',
            'faq': '/faq/',
            'terms': '/terms/',
            'privacy': '/privacy/',
        },
    }


def htmx_request(request):
    """
    Detect HTMX requests and add flag to context
    HTMX sends 'HX-Request' header with value 'true' for all requests
    """
    is_htmx = request.headers.get('HX-Request') == 'true'
    return {
        'is_htmx': is_htmx,
        'htmx_target': request.headers.get('HX-Target', ''),
        'htmx_trigger': request.headers.get('HX-Trigger', ''),
    }


def user_profile(request):
    """
    Add user profile to template context to avoid duplicate queries.
    Templates should use {{ user_profile }} instead of {{ user.profile }}.
    Caches the profile on the request object for reuse by views.

    Views can also use: from core.context_processors import get_cached_profile
    """
    return {'user_profile': get_cached_profile(request)}


def user_business(request):
    """
    Add user's business to template context to avoid duplicate queries.
    Templates should use {{ user_business }} instead of {{ request.user.user_business.first }}.
    Caches the business on the request object for reuse.

    Views can also use: from core.context_processors import get_cached_business
    """
    return {'user_business': get_cached_business(request)}


def user_driver(request):
    """
    Add user's Driver record to template context.
    Templates use {{ user_driver.driver_id }} for fleet profile links.
    Only queries for authenticated users with is_driver flag.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'user_driver': None}

    if hasattr(request, '_cached_user_driver'):
        return {'user_driver': request._cached_user_driver}

    profile = get_cached_profile(request)
    if not profile or not profile.is_driver:
        request._cached_user_driver = None
        return {'user_driver': None}

    try:
        from fleet.models import Driver
        driver = Driver.objects.only('driver_id', 'user_id').get(user_id=request.user.id)
        request._cached_user_driver = driver
        return {'user_driver': driver}
    except Exception:
        request._cached_user_driver = None
        return {'user_driver': None}


def dl_task_status_choices(request):
    """
    Expose DeliveryTask status choices as JSON for the status modal dropdown.
    Only runs on workforce paths to avoid overhead elsewhere.
    """
    if not request.path.startswith('/workforce/'):
        return {}
    from delivery.models import DeliveryTask
    choices = [{'value': v, 'label': l} for v, l in DeliveryTask._meta.get_field('dl_task_status').choices]
    return {
        'dl_task_status_choices_json': json.dumps(choices),
        'dl_task_status_choices': choices,
    }


def driver_pending_tasks(request):
    """
    Inject pending_tasks_count for fleet PWA bottom nav badge.
    Only queries for authenticated users on /fleet/ paths.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'pending_tasks_count': 0}

    # Only run on fleet URLs to avoid overhead on every page
    path = request.path
    if not path.startswith('/fleet/'):
        return {'pending_tasks_count': 0}

    # Check request cache to avoid duplicate queries per request
    if hasattr(request, '_driver_pending_tasks_count'):
        return {'pending_tasks_count': request._driver_pending_tasks_count}

    try:
        from fleet.models import Driver
        from delivery.models import DeliveryTask
        driver = Driver.objects.only('driver_id').get(user_id=request.user.id)
        count = DeliveryTask.objects.filter(
            driver=driver,
            dl_task_status__in=['assigned', 'accepted', 'picked_up', 'start_ride', 'out_for_delivery', 'in_transit', 'contacted', 'non_reachable']
        ).count()
        request._driver_pending_tasks_count = count
        return {'pending_tasks_count': count}
    except Exception:
        return {'pending_tasks_count': 0}
