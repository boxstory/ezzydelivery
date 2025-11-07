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
        "Disallow: /business/dashboard/",
        "Disallow: /workforce/dashboard/",
        "Disallow: /accounts/",
        "Disallow: /api/",
        "",
        "# Allow important pages",
        "Allow: /business/all/",
        "Allow: /business/workflow-guide/",
        "Allow: /$",
        "",
        "# Sitemap",
        f"Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml",
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
        "# Block AI scrapers (optional - remove if you want AI indexing)",
        "User-agent: GPTBot",
        "Disallow: /",
        "",
        "User-agent: CCBot",
        "Disallow: /",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


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
