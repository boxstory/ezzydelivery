from django.urls import path, include
from ezzy_api import views as ezzy_api_views

#path('api/', include('ezzy_api.urls'))

app_name = 'ezzy_api'
urlpatterns = [
    path('orderlist/', ezzy_api_views.OrderList.as_view(), name='order_list_api'),
    #path('orderlist/shipday/', ezzy_api_views.ShipdayOrderList.as_view(), name='shipday_order_list_api'),
    path('carrierslist/shipday/', ezzy_api_views.shipday_feet_list, name='shipday_feet_list'),
    path('orderlist/shipday/', ezzy_api_views.shipday_order_list, name='shipday_order_list'),


]