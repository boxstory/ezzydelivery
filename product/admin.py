from django.contrib import admin
from product import models as product_models

# Register your models here.





@admin.register(product_models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'brand_name', 'item_name', 'item_sku', 'business',
                    'product_category')
    readonly_fields = ('product_id',)  # Make product_id read-only in admin
    search_fields = ('item_name', 'item_sku', 'barcode', 'client_names')
    fields = ('product_id', 'brand_name', 'item_name', 'item_sku', 'barcode',
              'client_names', 'color', 'size', 'unit', 'item_price', 'item_discription',
              'brand_logo', 'product_image', 'business', 'product_category')


@admin.register(product_models.ProductInventory)
class Product_inventoryAdmin(admin.ModelAdmin):
    list_display = ('item_sku', 'item_quantity','created_at',  'updated_at')


@admin.register(product_models.ProductCategory)
class Product_categoryAdmin(admin.ModelAdmin):
    list_display = ('category_name', 'sub_category', 'discription')


@admin.register(product_models.ColorVariant)
class Color_variantAdmin(admin.ModelAdmin):
    list_display = ('color_variant', 'short_code', 'discription')




@admin.register(product_models.UnitVariant)
class Unit_variantAdmin(admin.ModelAdmin):
    list_display = ('unit_variant', 'short_code', 'discription')
