from django.contrib import admin
from product import models as product_models

# Register your models here.





@admin.register(product_models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'brand_name', 'item_name', 'item_sku', 'business',
                    'product_category')
    readonly_fields = ('product_id',)  # Make product_id read-only in admin
    search_fields = ('item_sku', 'barcode', 'item_name', 'client_names', 'brand_name',
                     'variant_label', 'product_id', 'size', 'variant_group', 'item_discription',
                     'color__short_code', 'unit__short_code', 'business__business_name',
                     'product_category__category_name')
    fields = ('product_id', 'brand_name', 'item_name', 'item_sku', 'barcode',
              'client_names', 'color', 'size', 'unit', 'item_price', 'item_discription',
              'brand_logo', 'product_image', 'business', 'product_category')


@admin.register(product_models.ProductInventory)
class Product_inventoryAdmin(admin.ModelAdmin):
    list_display = ('item_sku', 'item_quantity','created_at',  'updated_at')
    search_fields = ('item_sku__item_sku', 'item_sku__item_name', 'item_sku__barcode')
    list_select_related = ('item_sku',)
    raw_id_fields = ('item_sku',)


@admin.register(product_models.ProductCategory)
class Product_categoryAdmin(admin.ModelAdmin):
    list_display = ('category_name', 'sub_category', 'discription')
    search_fields = ('category_name', 'discription', 'sub_category__category_name')
    list_select_related = ('sub_category',)


@admin.register(product_models.ColorVariant)
class Color_variantAdmin(admin.ModelAdmin):
    list_display = ('color_variant', 'short_code', 'discription')
    search_fields = ('color_variant', 'short_code', 'hex_code', 'discription')




@admin.register(product_models.UnitVariant)
class Unit_variantAdmin(admin.ModelAdmin):
    list_display = ('unit_variant', 'short_code', 'discription')
    search_fields = ('unit_variant', 'short_code', 'discription')

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(product_models.ProductCombo)
class ProductComboAdmin(admin.ModelAdmin):
    list_display = ('business', 'combo_name', 'combo_sku', 'combo_price', 'is_active', 'created_at', 'updated_at')
    search_fields = ('combo_sku', 'combo_name', 'description', 'combo_price',
                     'business__business_name')
    list_filter = ('is_active',)
    list_select_related = ('business',)
    raw_id_fields = ('business',)

@admin.register(product_models.ProductComboItem)
class ProductComboItemAdmin(admin.ModelAdmin):
    list_display = ('combo', 'product', 'quantity')
    search_fields = ('combo__combo_sku', 'product__item_sku')
    list_select_related = ('combo', 'product')
    raw_id_fields = ('combo', 'product')

@admin.register(product_models.services)
class ServicesAdmin(admin.ModelAdmin):
    list_display = ('service_name', 'discription', 'created_at', 'updated_at', 'business')
    search_fields = ('service_name', 'discription', 'business__business_name')
    list_select_related = ('business',)
    raw_id_fields = ('business',)
