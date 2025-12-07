"""
Context processors for EzzyDelivery
Makes data available to all templates
"""
from core.seo import SEOMetadata, QATAR_KEYWORDS
import json


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
        'qatar_keywords': QATAR_KEYWORDS,
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
