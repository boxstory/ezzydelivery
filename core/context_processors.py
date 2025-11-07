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
