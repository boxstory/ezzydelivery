from django.contrib import admin
from django.urls import path, include , re_path
from django.conf import settings
from django.conf.urls.static import static
from orders import views as orders_views
from django.contrib.sitemaps.views import sitemap
from webpages.sitemaps import BusinessSitemap
from core.sitemaps import StaticViewSitemap, BusinessPagesSitemap, WorkforcePagesSitemap, SEOLandingPageSitemap, BlogPostSitemap, BlogCategorySitemap
from core.views_seo import robots_txt, security_txt, humans_txt, llms_txt
from django.views.generic import TemplateView
from django.views.static import serve as static_serve
from django.http import FileResponse, HttpResponseNotFound
from django.contrib.staticfiles import finders
import os


def service_worker_view(request):
    """Serve sw.js from root scope with Service-Worker-Allowed header."""
    # Try STATIC_ROOT first (production), then use staticfiles finders (development)
    sw_path = None
    if settings.STATIC_ROOT:
        production_path = os.path.join(settings.STATIC_ROOT, 'sw.js')
        if os.path.exists(production_path):
            sw_path = production_path

    # Fallback to staticfiles finder for development
    if not sw_path:
        sw_path = finders.find('sw.js')

    if not sw_path or not os.path.exists(sw_path):
        return HttpResponseNotFound('Service worker not found')

    response = FileResponse(open(sw_path, 'rb'), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


# Combine all sitemaps for comprehensive SEO
# Note: Removed duplicate StaticViewSitemap from webpages and DriverSitemap (fleet blocked in robots.txt)
sitemaps = {
    'static': StaticViewSitemap,
    'businesses': BusinessSitemap,
    'business_pages': BusinessPagesSitemap,
    'workforce_pages': WorkforcePagesSitemap,
    'seo_landing_pages': SEOLandingPageSitemap,
    'blog_posts': BlogPostSitemap,
    'blog_categories': BlogCategorySitemap,
}

admin.site.site_header = 'Ezzy Delivery Admin'





urlpatterns = [
    path('dj-admin/', admin.site.urls),

    #seo sitemap, robots.txt, security.txt, humans.txt - Qatar delivery SEO optimization
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', robots_txt, name='robots_txt'),
    path('.well-known/security.txt', security_txt, name='security_txt'),
    path('humans.txt', humans_txt, name='humans_txt'),
    path('llms.txt', llms_txt, name='llms_txt'),
    path('sw.js', service_worker_view, name='service_worker'),
     

    path('accounts/', include('allauth.urls')),

    path('api-auth/', include('rest_framework.urls')),
    # API versioning: v1 is current version, unversioned path kept for backwards compatibility
    path('api/v1/', include('ezzy_api.urls', namespace='ezzy_api_v1')),
    path('api/', include('ezzy_api.urls')),  # Legacy support (defaults to v1)

    path('', include('core.urls', namespace='core')),
    path('', include('webpages.urls', namespace='webpages')),
    path('workforce/', include('workforce.urls', namespace='workforce')),

    path('product/', include('product.urls', namespace='product')),

    path('business/', include('business.urls', namespace='business')),
    path('orders/', include('orders.urls', namespace='orders')),
    path('v/<str:phone>/<str:token>/', orders_views.verify_location_short, name='verify_location_short'),

    path('fleet/', include('fleet.urls', namespace='fleet')),
    path('delivery/', include('delivery.urls', namespace='delivery')),

    path('blog/', include('blog.urls', namespace='blog')),

    path('workforce/warehouse/', include('warehouse.urls', namespace='warehouse')),

    # Dispatch & Batching (Store Portal + Rider API)
    path('dispatch/', include('dispatch.urls', namespace='dispatch')),

    # AI Operations Agent
    path('api/ai-agent/', include('ai_agent.urls', namespace='ai_agent')),

]

handler404 = 'webpages.views.handler404'
handler500 = 'webpages.views.handler500'

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Add debug toolbar URLs only in DEBUG mode
if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
