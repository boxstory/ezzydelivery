from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from webpages import models as webpage_models


class StaticViewSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.5

    def items(self):
        return [  'webpages:index', 'webpages:services', 'webpages:delivery_pricing', 'webpages:qcommerce', 'webpages:fulfillment', 'webpages:about', 'webpages:contactus']

    def location(self, item):
        return reverse(item)


