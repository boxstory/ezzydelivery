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
            'webpages:home',
            'webpages:about',
            'webpages:contact',
            'webpages:pricing',
            'webpages:services',
            'webpages:careers',
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


# You can add dynamic sitemaps for businesses, products, etc.
# Example:
# class BusinessProfileSitemap(Sitemap):
#     changefreq = 'weekly'
#     priority = 0.6
#
#     def items(self):
#         from client.models import Business
#         return Business.objects.filter(business_status='active')
#
#     def lastmod(self, obj):
#         return obj.updated_at
#
#     def location(self, obj):
#         return reverse('business:business_profile_display', args=[obj.business_id])
