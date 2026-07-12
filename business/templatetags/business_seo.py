# Purpose: {% business_profile_schema %} template tag — emits JSON-LD for a business profile page.
# Used by: business/templates/business/frontend/business_profile.html (inside block content)
# Notes: Builds a schema.org @graph — Store (the client's business, with products/address/social),
#        a Service node provided by EzzyDelivery (#organization), and a BreadcrumbList. Reads
#        business/business_profile/products/request from the render context, so both the owner
#        (/profile/) and public (/<id>/display/) views get the same structured data.
import json

from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

register = template.Library()

ORG_ID = "https://ezzydelivery.qa/#organization"
QATAR = {"@type": "Country", "name": "Qatar"}


def _social_links(business, bp):
    """Assemble absolute social profile URLs (sameAs) from business + profile fields."""
    def pick(*vals):
        for v in vals:
            v = (v or "").strip()
            if v:
                return v
        return ""

    handles = [
        ("https://www.instagram.com/{}", pick(getattr(bp, "business_instagram", ""), getattr(business, "business_instagram", ""))),
        ("https://www.facebook.com/{}", pick(getattr(bp, "business_facebook_page", ""), getattr(business, "business_facebook_page", ""))),
        ("https://www.tiktok.com/@{}", pick(getattr(bp, "business_tiktok", ""))),
        ("https://www.youtube.com/{}", pick(getattr(bp, "business_youtube", ""))),
        ("https://www.twitter.com/{}", pick(getattr(bp, "business_twitter", ""))),
        ("https://www.linkedin.com/company/{}", pick(getattr(bp, "business_linkedin", ""))),
        ("https://www.snapchat.com/add/{}", pick(getattr(bp, "business_snapchat", ""))),
    ]
    links = [tmpl.format(val) for tmpl, val in handles if val]

    website = (getattr(bp, "business_website", "") or "").strip()
    if website:
        links.append(website if website.startswith("http") else f"http://{website}")
    return links


def _postal_address(bp):
    """Build a PostalAddress node from the business profile, or None if empty."""
    if not bp:
        return None
    street = (getattr(bp, "business_address", "") or "").strip()
    city = (getattr(bp, "business_city", "") or "").strip()
    region = (getattr(bp, "business_state", "") or "").strip()
    postal = (getattr(bp, "business_zip_code", "") or "").strip()
    if not (street or city or region):
        return None
    addr = {"@type": "PostalAddress", "addressCountry": "QA"}
    if street:
        addr["streetAddress"] = street
    if city:
        addr["addressLocality"] = city
    if region:
        addr["addressRegion"] = region
    if postal:
        addr["postalCode"] = postal
    return addr


def _offers(products, request, buy_url=""):
    """Map featured products to schema.org Offer/Product nodes.

    buy_url (the business website) becomes each offer's `url` so search engines
    know where the product can be purchased.
    """
    offers = []
    for p in products or []:
        name = (getattr(p, "item_name", "") or "").strip()
        if not name:
            continue
        product_node = {"@type": "Product", "name": name}
        brand = (getattr(p, "brand_name", "") or "").strip()
        if brand:
            product_node["brand"] = {"@type": "Brand", "name": brand}
        desc = (getattr(p, "item_discription", "") or "").strip()
        if desc:
            product_node["description"] = desc
        img = getattr(p, "product_image", None)
        if img:
            try:
                product_node["image"] = request.build_absolute_uri(img.url)
            except Exception:
                pass

        offer = {
            "@type": "Offer",
            "itemOffered": product_node,
            "priceCurrency": "QAR",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/NewCondition",
        }
        price = getattr(p, "item_price", None)
        if price not in (None, ""):
            offer["price"] = str(price)
        if buy_url:
            offer["url"] = buy_url
        offers.append(offer)
    return offers


@register.simple_tag(takes_context=True)
def business_profile_schema(context):
    """Render the business-profile JSON-LD @graph, or '' when there's no business."""
    request = context.get("request")
    business = context.get("business")
    if not (request and business):
        return ""

    bp = context.get("business_profile")
    products = context.get("products")
    logo = context.get("business_logo_img")

    name = (getattr(business, "business_name", "") or "Business").strip()
    profile_url = request.build_absolute_uri(
        reverse("business:business_profile_display", args=[business.business_id])
    )
    logo_abs = request.build_absolute_uri(logo) if logo else None

    # --- Store node: the client's business -------------------------------
    store = {
        "@type": "Store",
        "@id": f"{profile_url}#business",
        "name": name,
        "url": profile_url,
        "areaServed": QATAR,
    }
    description = (getattr(bp, "business_description", "") or "").strip() or (
        getattr(business, "business_bio", "") or ""
    ).strip()
    if description:
        store["description"] = description
    if logo_abs:
        store["logo"] = logo_abs
        store["image"] = logo_abs
    category = (
        (getattr(bp, "business_catagory_main", "") or "")
        or (getattr(business, "business_product_category", "") or "")
    ).strip()
    if category:
        store["category"] = category
    # Note: telephone/email intentionally omitted — the visible page shows only
    # website + social, and schema must match on-page content.
    address = _postal_address(bp)
    if address:
        store["address"] = address
    sameas = _social_links(business, bp)
    if sameas:
        store["sameAs"] = sameas
    website = (getattr(bp, "business_website", "") or "").strip()
    buy_url = (website if website.startswith("http") else f"http://{website}") if website else ""
    offers = _offers(products, request, buy_url)
    if offers:
        store["makesOffer"] = offers

    # --- Service node: fulfilled by EzzyDelivery (our service showcase) ---
    service = {
        "@type": "Service",
        "name": f"Same-Day Delivery for {name}",
        "serviceType": "Delivery Service",
        "description": (
            f"Orders from {name} are delivered across Qatar by EzzyDelivery — "
            f"same-day delivery, Cash on Delivery and live tracking in Doha, "
            f"Al Wakrah and Lusail."
        ),
        "provider": {"@id": ORG_ID, "name": "EzzyDelivery"},
        "areaServed": QATAR,
        "url": profile_url,
    }

    # --- Breadcrumb ------------------------------------------------------
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "EzzyDelivery", "item": "https://ezzydelivery.qa/"},
            {"@type": "ListItem", "position": 2, "name": "Businesses",
             "item": request.build_absolute_uri(reverse("business:all_business"))},
            {"@type": "ListItem", "position": 3, "name": name, "item": profile_url},
        ],
    }

    data = {"@context": "https://schema.org", "@graph": [store, service, breadcrumb]}
    # ensure_ascii keeps non-Latin names safe; escape '<' so a business name can't break out of <script>
    json_ld = json.dumps(data, ensure_ascii=True, indent=2).replace("<", "\\u003c")
    return mark_safe(
        "<!-- Business Profile Schema (Store + EzzyDelivery Service) for AI & Search Engines -->\n"
        '<script type="application/ld+json">\n' + json_ld + "\n</script>"
    )
