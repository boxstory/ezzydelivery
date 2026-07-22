# Purpose: {% service_schema %} template tag — emits Service JSON-LD on SEO landing pages.
# Used by: templates/includes/head.html (renders on every page; outputs only for mapped URL names)
# Notes: Keyed by URL name from request.resolver_match; provider references the sitewide
#        Organization node (#organization). Add a new landing page by adding one dict entry.
import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ORG_ID = "https://ezzydelivery.qa/#organization"
QATAR = {"@type": "Country", "name": "Qatar"}


def _city(name):
    return {"@type": "City", "name": name, "containedInPlace": QATAR}


# Maps each SEO landing page (URL name) to its Service schema content.
# Keep `description` aligned with the visible page copy to avoid schema/content mismatch.
SERVICE_SCHEMA = {
    "delivery_companies_qatar": {
        "name": "Delivery & Courier Services Qatar",
        "serviceType": "Courier Service",
        "description": "Professional delivery and courier services across Qatar, including same-day delivery, COD collection and real-time tracking for businesses in Doha, Al Wakrah and Lusail.",
    },
    "delivery_service_qatar": {
        "name": "Delivery Service Qatar",
        "serviceType": "Courier Service",
        "description": "Fast, reliable delivery service across all of Qatar for businesses and individuals, with quick pickup, live tracking and Cash on Delivery available.",
    },
    "same_day_delivery_qatar": {
        "name": "Same-Day Delivery Qatar",
        "serviceType": "Same-Day Delivery",
        "description": "Guaranteed same-day delivery in Qatar with pickup within 2 hours and delivery by end of day across Doha, Al Wakrah, Lusail and Al Rayyan.",
    },
    "cod_delivery_qatar": {
        "name": "Cash on Delivery (COD) Service Qatar",
        "serviceType": "Cash on Delivery",
        "description": "Secure Cash on Delivery service for Qatar e-commerce and Instagram sellers, with cash collection across all of Qatar, daily settlement and full reconciliation reporting.",
    },
    "ecommerce_delivery_qatar": {
        "name": "E-commerce Delivery Qatar",
        "serviceType": "E-commerce Fulfillment",
        "description": "Complete e-commerce shipping solutions in Qatar with Shopify and WooCommerce integration, automated order import, COD and same-day delivery for online stores.",
    },
    "instagram_sellers_delivery": {
        "name": "Delivery Service for Instagram Sellers Qatar",
        "serviceType": "Courier Service",
        "description": "Delivery service built for Instagram and social-commerce sellers in Qatar — no minimum orders, Cash on Delivery, branded tracking and WhatsApp order booking.",
    },
    "express_delivery_qatar": {
        "name": "Express Delivery Qatar",
        "serviceType": "Express Delivery",
        "description": "Express delivery service in Qatar with a 2-hour pickup guarantee and priority handling for urgent documents and parcels across Doha and beyond.",
    },
    "courier_service_qatar": {
        "name": "Courier Service Qatar",
        "serviceType": "Courier Service",
        "description": "Reliable courier service in Qatar for documents, parcels and B2B deliveries, with GPS tracking and proof of delivery on every shipment.",
    },
    "three_pl_qatar": {
        "name": "3PL Services Qatar",
        "serviceType": "Third-Party Logistics",
        "description": "Full third-party logistics (3PL) in Qatar covering warehousing, inventory management and pick-pack-ship fulfillment for e-commerce businesses.",
    },
    "last_mile_delivery_qatar": {
        "name": "Last-Mile Delivery Qatar",
        "serviceType": "Last-Mile Delivery",
        "description": "Last-mile delivery service in Qatar with a high first-attempt success rate, real-time GPS tracking and trained drivers for e-commerce fulfillment.",
    },
    "logistics_services_qatar": {
        "name": "Logistics Services Qatar",
        "serviceType": "Logistics Service",
        "description": "End-to-end logistics services in Qatar — delivery, warehousing, fulfillment and distribution — for businesses shipping across the country.",
    },
    "online_store_delivery_qatar": {
        "name": "Online Store Delivery Qatar",
        "serviceType": "E-commerce Fulfillment",
        "description": "Delivery and fulfillment service for online stores in Qatar, with automated order sync, COD collection and same-day delivery across all zones.",
    },
    "delivery_doha": {
        "name": "Delivery Service in Doha",
        "serviceType": "Courier Service",
        "description": "Fast delivery and courier service across all districts of Doha, with same-day delivery, COD and real-time tracking.",
        "areaServed": _city("Doha"),
    },
    "al_wakrah_delivery": {
        "name": "Delivery Service in Al Wakrah",
        "serviceType": "Courier Service",
        "description": "Reliable delivery and courier service in Al Wakrah, Qatar, with same-day delivery, Cash on Delivery and live tracking.",
        "areaServed": _city("Al Wakrah"),
    },
    "lusail_delivery": {
        "name": "Delivery Service in Lusail",
        "serviceType": "Courier Service",
        "description": "Delivery and courier service across Lusail, Qatar, including Fox Hills, Marina District and Entertainment City, with same-day delivery and COD.",
        "areaServed": _city("Lusail"),
    },
    "business_delivery_qatar": {
        "name": "Business Delivery Qatar (B2B)",
        "serviceType": "B2B Delivery",
        "description": "B2B delivery service in Qatar for office-to-office documents and parcels, with corporate accounts, monthly invoicing and bulk shipping rates.",
    },
    "package_delivery_qatar": {
        "name": "Package Delivery Qatar",
        "serviceType": "Parcel Delivery",
        "description": "Package and parcel delivery service across Qatar with quick pickup, real-time tracking, proof of delivery and Cash on Delivery options.",
    },
    "shopify_delivery_qatar": {
        "name": "Shopify Delivery Integration Qatar",
        "serviceType": "E-commerce Fulfillment",
        "description": "Native Shopify delivery integration for Qatar stores — orders sync automatically, labels are generated and tracking updates push back to Shopify in real time.",
    },
    "food_delivery_partner_qatar": {
        "name": "Food Delivery Partner Qatar",
        "serviceType": "Last-Mile Delivery",
        "description": "Last-mile delivery partner for food and restaurant businesses in Qatar, with fast pickup, temperature-aware handling and live order tracking.",
    },
    "delivery_qatar_arabic": {
        "name": "خدمة التوصيل في قطر",
        "serviceType": "Courier Service",
        "description": "خدمة توصيل سريعة وموثوقة في جميع أنحاء قطر مع الدفع عند الاستلام والتتبع المباشر.",
    },
    "courier_doha_arabic": {
        "name": "شركة توصيل في الدوحة",
        "serviceType": "Courier Service",
        "description": "شركة توصيل وشحن في الدوحة، قطر، مع توصيل في نفس اليوم والدفع عند الاستلام.",
        "areaServed": _city("Doha"),
    },
}


@register.simple_tag(takes_context=True)
def service_schema(context):
    """Render Service JSON-LD for the current SEO landing page, or '' elsewhere."""
    request = context.get("request")
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is None:
        return ""

    entry = SERVICE_SCHEMA.get(resolver_match.url_name)
    if entry is None:
        return ""

    page_url = request.build_absolute_uri(request.path)
    data = {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": entry["name"],
        "serviceType": entry["serviceType"],
        "description": entry["description"],
        "url": page_url,
        "provider": {"@id": ORG_ID, "name": "EzzyDelivery"},
        "areaServed": entry.get("areaServed", QATAR),
        "availableChannel": {
            "@type": "ServiceChannel",
            "serviceUrl": page_url,
            "servicePhone": "+974-6645-1589",
            "availableLanguage": ["English", "Arabic"],
        },
    }
    json_ld = json.dumps(data, ensure_ascii=False, indent=2)
    return mark_safe(
        '<!-- Service Schema for AI & Search Engines -->\n'
        '<script type="application/ld+json">\n' + json_ld + '\n</script>'
    )
