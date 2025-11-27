import debug_toolbar
from django.contrib import admin
from django.urls import path, include , re_path
from django.conf import settings
from django.conf.urls.static import static
from orders import views as orders_views
from django.contrib.sitemaps.views import sitemap
from webpages.sitemaps import StaticViewSitemap, BusinessSitemap, DriverSitemap
from core.sitemaps import StaticViewSitemap as CoreStaticSitemap, BusinessPagesSitemap, WorkforcePagesSitemap, SEOLandingPageSitemap
from core.views_seo import robots_txt, security_txt, humans_txt
from django.views.generic import TemplateView


# Combine all sitemaps for comprehensive SEO
sitemaps = {
    'static': StaticViewSitemap,
    'businesses': BusinessSitemap,
    'drivers': DriverSitemap,
    'core': CoreStaticSitemap,
    'business_pages': BusinessPagesSitemap,
    'workforce_pages': WorkforcePagesSitemap,
    'seo_landing_pages': SEOLandingPageSitemap,  # NEW: Highest priority SEO pages
}

admin.site.site_header = 'Ezzy Delivery Admin'





urlpatterns = [
    path('dj-admin/', admin.site.urls),
    path('__debug__/', include(debug_toolbar.urls)),

    #seo sitemap, robots.txt, security.txt, humans.txt - Qatar delivery SEO optimization
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('.well-known/security.txt', security_txt, name='security_txt'),
    path('humans.txt', humans_txt, name='humans_txt'),
     

    path('accounts/', include('allauth.urls')),

    path('api-auth/', include('rest_framework.urls')),
    path('api/', include('ezzy_api.urls')),

    path('', include('core.urls', namespace='core')),
    path('', include('webpages.urls', namespace='webpages')),
    path('workforce/', include('workforce.urls', namespace='workforce')),

    path('product/', include('product.urls', namespace='product')),

    path('business/', include('client.urls', namespace='business')),
    path('orders/', include('orders.urls', namespace='orders')),

    path('fleet/', include('fleet.urls', namespace='fleet')),
    path('delivery/', include('delivery.urls', namespace='delivery')),

    

]

handler404 = 'webpages.views.handler404'
handler500 = 'webpages.views.handler500'

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
