import debug_toolbar
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from orders import views as orders_views


admin.site.site_header = 'Ezzy Delivery Admin'

urlpatterns = [
    path('dj-admin/', admin.site.urls),
    path('__debug__/', include(debug_toolbar.urls)),

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
