"""
Sitemaps for EzzyDelivery Qatar
Helps search engines discover and index pages
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    """Sitemap for static pages"""
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        # List of URL names for static pages
        return [
            'webpages:index',
            'webpages:about',
            'webpages:contactus',
            'webpages:delivery_pricing',
            'webpages:services',
            'webpages:careers',
            'webpages:fulfillment',
            'webpages:qcommerce',
            'webpages:testimonials',
            'webpages:privacy',
            'webpages:terms',
            'webpages:help_center',
            'webpages:client_faq',
        ]

    def location(self, item):
        return reverse(item)


class SEOLandingPageSitemap(Sitemap):
    """Sitemap for SEO landing pages - HIGHEST PRIORITY"""
    priority = 1.0
    changefreq = 'daily'

    def items(self):
        return [
            'webpages:delivery_companies_qatar',
            'webpages:delivery_service_qatar',
            'webpages:same_day_delivery_qatar',
            'webpages:cod_delivery_qatar',
            'webpages:ecommerce_delivery_qatar',
            'webpages:instagram_sellers_delivery',
            'webpages:express_delivery_qatar',
            'webpages:courier_service_qatar',
            'webpages:three_pl_qatar',
            'webpages:last_mile_delivery_qatar',
            'webpages:logistics_services_qatar',
            'webpages:online_store_delivery_qatar',
        ]

    def location(self, item):
        return reverse(item)


class BusinessPagesSitemap(Sitemap):
    """Sitemap for business-related pages"""
    priority = 0.7
    changefreq = 'daily'

    def items(self):
        return [
            'business:all_business',
            'business:workflow_guide',
        ]

    def location(self, item):
        return reverse(item)


class WorkforcePagesSitemap(Sitemap):
    """Sitemap for workforce pages"""
    priority = 0.6
    changefreq = 'daily'

    def items(self):
        return [
            'workforce:workflow_guide',
        ]

    def location(self, item):
        return reverse(item)
