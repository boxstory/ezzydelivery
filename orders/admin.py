from atexit import register
from django.contrib import admin
from orders import models as order_models
from import_export.admin import ImportExportModelAdmin

# Register your models here.


@admin.register(order_models.Order)
class OrderAdmin(ImportExportModelAdmin):
    list_display = ('order_number', 'business', 'order_notes', 'order_status')

@admin.register(order_models.OrderProductList)
class OrderProductListAdmin(ImportExportModelAdmin):
    list_display = ('order', 'product01_name', 'product01_qty', 'product02_name', 'product02_qty')



admin.site.register(order_models.OrderLog)


admin.site.register(order_models.OrderBarcode)


@admin.register(order_models.OrderComments)
class OrderCommentsAdmin(ImportExportModelAdmin):
    list_display = ('order', 'name', 'body')