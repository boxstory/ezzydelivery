from django.contrib import admin
from fleet import models as fleet_models
# Register your models here.


@admin.register(fleet_models.Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('user', 'driver_code',  'driver_phone',
                    'driver_whatsapp',  'driver_status', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    list_per_page = 10


@admin.register(fleet_models.DriverVehicle)
class DriverVehicleAdmin(admin.ModelAdmin):
    list_display = ('driver','vehicle_type', 'vehicle_no',
                    'vehicle_color', 'vehicle_model', 'vehicle_status', 'vehicle_date')
    list_filter = ('vehicle_status', 'vehicle_date')
    list_per_page = 10


admin.register(fleet_models.DriverDocument)
