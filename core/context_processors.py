"""
Context processors for EzzyDelivery
Makes data available to all templates

Also provides utility functions for views to get cached user data:
    - get_cached_profile(request) -> Profile or None
    - get_cached_business(request) -> Business or None
"""
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

    from business.models import Business
    try:
        business = Business.objects.filter(user_id=request.user.id).first()
        request._cached_user_business = business
        return business
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
        'CURRENT_YEAR': 2025,
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
