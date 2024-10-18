from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views
from product import views as product_views

app_name = 'product'
urlpatterns = [
    # ITEMS
    path('all/',
         product_views.product_all_list, name='product_all_list'),
    path('all/cards/',
         product_views.product_all_list_card, name='product_all_list_card'),
    path('add/',
         product_views.product_single_add, name='product_single_add'),
    path('<int:product_id>/delete/',
         product_views.product_single_delete, name='product_single_delete'),
    path('<int:product_id>/update/',
         product_views.product_single_update, name='product_single_update'),
  

     # Product categories
     path('product_categories_list/', product_views.product_categories, name='product_categories'),

     # Product Inventory
     path('product_inventory/', product_views.product_inventory, name='product_inventory'),

]
