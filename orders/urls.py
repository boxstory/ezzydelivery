from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views

# /orders/
app_name = 'orders'
urlpatterns = [
    #path('', orders_views.orders_list, name='orders_list'),
    path('partial/pending/', orders_views.orders_pending_list, name='orders_pending_list'),
    path('partial/successfull/', orders_views.orders_successfull_list, name='orders_successfull_list'),
    path('partial/unsuccess/', orders_views.orders_unsuccessfull_list, name='orders_unsuccessfull_list'),
    path('partial/all/', orders_views.orders_all_list, name='orders_all_list'),
    #path('partial/all', orders_views.orders_list_review, name='orders_list'),


    # ORDERS
    path('add_order/', orders_views.add_order, name='add_order'),
    path('order_update/<int:order_id>/',
         orders_views.order_update, name='order_update'),
    path('delete_order/<int:order_id>/',
         orders_views.delete_order, name='delete_order'),
    path('order_details/<int:order_id>/',
         orders_views.order_details, name='order_details'),
    #uploading order files
    path('upload_file/', orders_views.order_upload_file, name='order_upload_file'),
    path('review_data/', orders_views.order_upload_review_data, name='order_upload_review_data'),

    # Products add to order list
    path('add_order_product/<int:order_id>/', 
         orders_views.add_order_product, name='add_order_product'),
    path('update_order_product/<int:order_id>/', 
         orders_views.update_order_product, name='update_order_product'),
    path('order/<int:order_id>/products/', orders_views.order_product_list, name='order_product_list'), 


    # operation links
    path('update_order_status/', 
         orders_views.update_order_status, name='update_order_status'),

]

