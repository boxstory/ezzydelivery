from django.urls import path
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
    path('add_order_bulk/', orders_views.add_order_bulk, name='add_order_bulk'),
    path('add_order_with_product/', orders_views.add_order_with_product, name='add_order_with_product'),
    path('add_order/<int:pickup_id>/', orders_views.deliver_to_here, name='deliver_to_here'),
    path('pick_from_here/<int:pickup_id>/', orders_views.pick_from_here, name='pick_from_here'),
    path('order_update/<int:order_id>/',
         orders_views.order_update, name='order_update'),
    path('delete_order/<int:order_id>/',
         orders_views.delete_order, name='delete_order'),
    path('order_details/<int:order_id>/',
         orders_views.order_details, name='order_details'),
    path('order/<int:order_id>/update-zone/',
         orders_views.update_order_zone, name='update_order_zone'),
    #uploading order files
    path('upload_file/', orders_views.order_upload_file, name='order_upload_file'),
    path('review_data/', orders_views.order_upload_review_data, name='order_upload_review_data'),
    path('bulk_entry/', orders_views.bulk_order_entry, name='bulk_order_entry'),

    # Products add to order list
    path('add_order_product/<int:order_id>/',
         orders_views.add_order_product, name='add_order_product'),
    path('update_order_product/<int:order_id>/',
         orders_views.update_order_product, name='update_order_product'),
    path('order/<int:order_id>/products/', orders_views.order_product_list, name='order_product_list'),
    path('api/product-search/', orders_views.product_search_api, name='product_search_api'), 


    # operation links
    path('update_order_status/',
         orders_views.update_order_status, name='update_order_status'),
    path('bulk-update-status/',
         orders_views.bulk_update_order_status, name='bulk_update_order_status'),
    path('<int:order_id>/update-status/',
         orders_views.update_order_status, name='update_order_status_by_id'),

    # Order comments
    path('order/<int:order_id>/comments/',
         orders_views.get_order_comments, name='get_order_comments'),
    path('order/<int:order_id>/comments/add/',
         orders_views.add_order_comment, name='add_order_comment'),


     # orders by API
     path('api/all/', orders_views.get_order_by_api, name='get_order_by_api'),
     path('api/import/', orders_views.import_shopify_orders, name='import_shopify_orders'),
     path('api/shopify_orders/', orders_views.get_orders_by_base_api, name='get_orders_by_base_api'),

     # Location Verification (Public URL)
     path('verify-location/<str:token>/', orders_views.verify_location, name='verify_location'),

     # Customer Self-Service Location Update (Public URL)
     path('verify/', orders_views.update_location, name='update_location'),

     # Bulk Import (Client Dashboard)
     path('bulk-import/', orders_views.bulk_import_orders, name='bulk_import_orders'),
     path('bulk-import/preview/', orders_views.bulk_import_preview, name='bulk_import_preview'),
     path('bulk-import/save/', orders_views.bulk_import_save, name='bulk_import_save'),
     path('bulk-import/save-mapping/', orders_views.bulk_import_save_mapping, name='bulk_import_save_mapping'),
     path('bulk-import/finalize/', orders_views.bulk_import_finalize, name='bulk_import_finalize'),

]

