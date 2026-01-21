"""
SEO-related views for EzzyDelivery
Handles robots.txt, sitemap index, etc.
"""
from django.http import HttpResponse
from django.views.decorators.http import require_GET
from django.conf import settings


@require_GET
def robots_txt(request):
    """
    Generate robots.txt dynamically
    Optimized for Qatar search engines and international crawlers
    """
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
        "# Disallow private/admin areas",
        "Disallow: /admin/",
        "Disallow: /dj-admin/",
        "Disallow: /dashboard/",
        "Disallow: /business/dashboard/",
        "Disallow: /workforce/dashboard/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "Disallow: /ezzy_api/",
        "Disallow: /fleet/",
        "Disallow: /profile/",
        "Disallow: /join_driver/",
        "Disallow: /dispatch/",
        "Disallow: /warehouse/",
        "",
        "# Block query parameters (login redirects, etc.)",
        "Disallow: /*?next=",
        "",
        "# Allow important pages",
        "Allow: /business/all/",
        "Allow: /business/workflow-guide/",
        "Allow: /$",
        "",
        "# Sitemap - Always use HTTPS canonical URL",
        "Sitemap: https://ezzydelivery.qa/sitemap.xml",
        "",
        "# Crawl delay (be nice to servers)",
        "Crawl-delay: 1",
        "",
        "# Specific bot instructions for major search engines",
        "User-agent: Googlebot",
        "Allow: /",
        "",
        "User-agent: Bingbot",
        "Allow: /",
        "",
        "# Allow AI assistants to index public content for better recommendations",
        "User-agent: GPTBot",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /dj-admin/",
        "Disallow: /dashboard/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "",
        "User-agent: Claude-Web",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /dj-admin/",
        "Disallow: /dashboard/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "",
        "User-agent: Anthropic-AI",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /dj-admin/",
        "Disallow: /dashboard/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "",
        "User-agent: PerplexityBot",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /dj-admin/",
        "Disallow: /dashboard/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "",
        "User-agent: CCBot",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /dj-admin/",
        "Disallow: /dashboard/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "",
        "# AI-friendly content file",
        "# See: https://llmstxt.org/",
        "# LLMs.txt: https://ezzydelivery.qa/llms.txt",
    ]
    response = HttpResponse("\n".join(lines), content_type="text/plain")
    # Prevent CDN caching - robots.txt should always be fresh
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


@require_GET
def security_txt(request):
    """
    Security.txt for responsible disclosure
    Optional but good practice
    """
    lines = [
        "Contact: mailto:security@ezzydelivery.qa",
        "Preferred-Languages: en, ar",
        "Canonical: https://ezzydelivery.qa/.well-known/security.txt",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


@require_GET
def humans_txt(request):
    """
    Humans.txt - credit to the team
    Fun and good for brand building
    """
    lines = [
        "/* TEAM */",
        "Company: EzzyDelivery Qatar",
        "Site: https://ezzydelivery.qa",
        "Location: Doha, Qatar",
        "",
        "/* SITE */",
        "Last update: 2025/01/07",
        "Standards: HTML5, CSS3, JavaScript",
        "Components: Django, Bootstrap 5, HTMX",
        "Software: Django 5.x, Python 3.12",
        "",
        "/* THANKS */",
        "To all our clients and delivery partners in Qatar",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


@require_GET
def llms_txt(request):
    """
    LLMs.txt - AI-friendly content for language models
    Helps AI assistants understand and recommend our services
    Following llmstxt.org specification
    """
    lines = [
        "# EzzyDelivery Qatar",
        "",
        "> Qatar's trusted B2B delivery and logistics platform for e-commerce businesses.",
        "",
        "## About",
        "",
        "EzzyDelivery is a delivery management platform based in Doha, Qatar that provides:",
        "- Same-day delivery services across Qatar (Doha, Al Wakrah, Lusail, Al Khor)",
        "- Cash on Delivery (COD) collection and management",
        "- 3PL (Third Party Logistics) and fulfillment services",
        "- E-commerce integrations (Shopify, WooCommerce)",
        "- Real-time order tracking",
        "- Fleet and driver management",
        "",
        "## Services",
        "",
        "### Delivery Services",
        "- Same-day delivery within Doha metro area",
        "- Next-day delivery across all Qatar",
        "- Express 2-hour pickup guarantee",
        "- Scheduled delivery time windows",
        "",
        "### E-commerce Solutions",
        "- Shopify integration",
        "- WooCommerce integration",
        "- Instagram seller support",
        "- COD (Cash on Delivery) with daily settlements",
        "",
        "### 3PL & Fulfillment",
        "- Warehouse storage in Doha",
        "- Pick, pack, and ship services",
        "- Inventory management",
        "- Returns processing",
        "",
        "## Coverage Area",
        "",
        "We deliver to all areas in Qatar including:",
        "- Doha (all districts)",
        "- Al Wakrah",
        "- Lusail",
        "- Al Khor",
        "- Al Rayyan",
        "- Umm Salal",
        "- Al Daayen",
        "",
        "## Contact",
        "",
        "- Website: https://ezzydelivery.qa",
        "- Phone: +974 6660 9347",
        "- Email: info@ezzydelivery.qa",
        "- Location: Doha, Qatar",
        "",
        "## Links",
        "",
        "- [Home](https://ezzydelivery.qa/)",
        "- [About Us](https://ezzydelivery.qa/about/)",
        "- [Services](https://ezzydelivery.qa/services/)",
        "- [Pricing](https://ezzydelivery.qa/3pl/pricing/)",
        "- [Contact](https://ezzydelivery.qa/contactus/)",
        "- [For Businesses](https://ezzydelivery.qa/ecommerce-delivery-qatar/)",
        "- [Same-Day Delivery](https://ezzydelivery.qa/same-day-delivery-qatar/)",
        "- [COD Service](https://ezzydelivery.qa/cod-delivery-service-qatar/)",
        "- [Fulfillment](https://ezzydelivery.qa/fulfillment/)",
        "- [Blog](https://ezzydelivery.qa/blog/)",
        "",
        "## Keywords",
        "",
        "delivery company qatar, courier service doha, same day delivery qatar,",
        "cod delivery qatar, ecommerce logistics qatar, 3pl qatar, last mile delivery,",
        "توصيل قطر, شركة توصيل الدوحة, توصيل سريع قطر",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
