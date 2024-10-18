from django.contrib import admin
from delivery import models as delivery_models

# Register your models here.


@admin.register(delivery_models.DeliveryTask)
class DeliveryTaskAdmin(admin.ModelAdmin):
    list_display = ('dl_task_number',  'dl_price')


@admin.register(delivery_models.DlAddressUpdate)
class DlAddressUpdateAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'dl_zone', 'dl_street', 'dl_building')
