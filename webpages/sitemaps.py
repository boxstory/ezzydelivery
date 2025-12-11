from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from webpages import models as webpage_models
from business import models as business_models
from fleet import models as fleet_models
from django.utils import timezone

class StaticViewSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.5

    def items(self):
        return [  'webpages:index', 'webpages:services', 'webpages:delivery_pricing', 'webpages:qcommerce', 'webpages:fulfillment', 'webpages:about', 'webpages:contactus', 'webpages:privacy', 'webpages:terms']

    def location(self, item):
        return reverse(item)


class BusinessSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        # Return only active businesses to be included in the sitemap
        return business_models.Business.objects.filter(business_status='active')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('business:business_profile_display', args=[obj.business_id])


class DriverSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        # Return only approved drivers
        return fleet_models.Driver.objects.filter(driver_status='Approved')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('fleet:driver_profile', args=[obj.driver_id])
