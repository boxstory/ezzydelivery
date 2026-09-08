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
    path('all/table/',
         product_views.product_all_list_table, name='product_all_list_table'),
    path('add/',
         product_views.product_single_add, name='product_single_add'),
    path('<int:product_id>/delete/',
         product_views.product_single_delete, name='product_single_delete'),
    path('<int:product_id>/update/',
         product_views.product_single_update, name='product_single_update'),
    path('<int:product_id>/inline-update/',
         product_views.product_inline_update, name='product_inline_update'),

    # API Product Import Wizard
    path('api/wizard/', product_views.product_api_wizard, name='product_api_wizard'),
    path('api/fetch/', product_views.product_api_fetch, name='product_api_fetch'),
    path('api/import/', product_views.product_api_import, name='product_api_import'),

    # CSV Product Import
    path('csv/import/', product_views.product_csv_import, name='product_csv_import'),
    path('csv/sample/', product_views.product_csv_sample, name='product_csv_sample'),

    # Staff actions (from seller detail page)
    path('<int:product_id>/staff-delete/', product_views.product_staff_delete, name='product_staff_delete'),
    path('staff/bulk-update/', product_views.product_staff_bulk_update, name='product_staff_bulk_update'),

    # Product categories
    path('product_categories_list/', product_views.product_categories, name='product_categories'),

    # Product Inventory
    path('product_inventory/', product_views.product_inventory, name='product_inventory'),
    path('<int:product_id>/inventory/update/', product_views.inventory_qty_update, name='inventory_qty_update'),

    # Inventory Management (moved from warehouse app)
    path('inventory/', product_views.inventory_list, name='inventory_list'),
    path('inventory/<int:product_id>/', product_views.stock_card, name='stock_card'),
    path('transactions/', product_views.transaction_list, name='transaction_list'),

    # Test images
    path('test-images/', product_views.test_images, name='test_images'),

    # Product Combos / Bundles
    path('combos/', product_views.combo_list, name='combo_list'),
    path('combos/create/', product_views.combo_create, name='combo_create'),
    path('combos/<int:combo_id>/update/', product_views.combo_update, name='combo_update'),
    path('combos/<int:combo_id>/delete/', product_views.combo_delete, name='combo_delete'),

]
