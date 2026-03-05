"""
Sitemaps for EzzyDelivery Qatar
Helps search engines discover and index pages
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from blog.models import BlogPost, BlogCategory


class StaticViewSitemap(Sitemap):
    """Sitemap for static pages"""
    changefreq = 'weekly'

    # Per-page priority overrides (default is 0.8)
    _priority_map = {
        'webpages:affiliate_marketing': 0.7,
        'webpages:delivery_request': 0.7,
        'webpages:client_faq': 0.6,
        'webpages:driver_faq': 0.6,
        'webpages:help_guides': 0.6,
        'webpages:client_guide': 0.6,
        'webpages:driver_guide': 0.6,
    }

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
            'webpages:affiliate_marketing',
            'webpages:delivery_request',
            'webpages:client_faq',
            'webpages:driver_faq',
            'webpages:help_guides',
            'webpages:client_guide',
            'webpages:driver_guide',
        ]

    def priority(self, item):
        return self._priority_map.get(item, 0.8)

    def location(self, item):
        return reverse(item)


class SEOLandingPageSitemap(Sitemap):
    """Sitemap for SEO landing pages - HIGHEST PRIORITY"""
    priority = 1.0
    changefreq = 'daily'

    def items(self):
        return [
            # Original SEO pages
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
            # New location-specific pages
            'webpages:delivery_doha',
            'webpages:al_wakrah_delivery',
            'webpages:lusail_delivery',
            # New service-specific pages
            'webpages:business_delivery_qatar',
            'webpages:package_delivery_qatar',
            'webpages:shopify_delivery_qatar',
            'webpages:food_delivery_partner_qatar',
            # Arabic keyword pages
            'webpages:delivery_qatar_arabic',
            'webpages:courier_doha_arabic',
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


class BlogPostSitemap(Sitemap):
    """Sitemap for blog posts - Critical for content authority"""
    priority = 0.9
    changefreq = 'weekly'

    def items(self):
        return BlogPost.objects.filter(status='published').order_by('-published_at')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return obj.get_absolute_url()


class BlogCategorySitemap(Sitemap):
    """Sitemap for blog categories"""
    priority = 0.7
    changefreq = 'weekly'

    def items(self):
        return BlogCategory.objects.all()

    def location(self, obj):
        return obj.get_absolute_url()
