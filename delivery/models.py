from django.db import models

from core import models as core_models
from orders import models as orders_models
from delivery import models as delivery_models
from client import models as business_models
from fleet import models as fleet_models


# Create your models here.

# drivers---------------------------------------------------------------------------------------------------------------------


# Task---------------------------------------------------------------------------------------------------------------------

class DlAddressUpdate(models.Model):
    full_name = models.CharField(max_length=100)
    mobile_no = models.CharField(max_length=11)
    area_name = models.CharField(max_length=100)
    dl_zone = models.PositiveIntegerField(blank=True)
    dl_building = models.PositiveIntegerField(blank=True)
    dl_street = models.PositiveIntegerField(blank=True)
    dl_latitude = models.DecimalField(max_digits=19, decimal_places=15,blank=True)
    dl_longitude = models.DecimalField(max_digits=19, decimal_places=15,blank=True)
    dl_pluscode = models.PositiveIntegerField(blank=True, null=True)
    dl_unit = models.CharField(max_length=2)
    is_villa_compound = models.BooleanField(default=False)
    is_flat = models.BooleanField(default=False)
    is_office = models.BooleanField(default=False)
    dl_task_number = models.CharField(max_length=100)
    dms_id = models.CharField(max_length=100,blank=True, null=True)
    time_slot = models.CharField(max_length=100,blank=True, null=True)
    order = models.ForeignKey(orders_models.Order, on_delete=models.DO_NOTHING, related_name='delivery_addresses')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

    class Meta:
        verbose_name_plural = "Delivery Address"
        app_label = 'delivery'


class DeliveryTask(models.Model):
    dl_task_status_client = (
        ('for_review', 'For Review'),
        ('customer_confiration_pending', 'Customer Confirmation Pending'),
        ('0', 'Assigned to Driver'),
        ('2', 'Delivered'),
        ('rejected', 'Rejected'),
        ('9', 'Cancelled'),
    )
    dl_task_status = (
        ('for_review', 'For Review'),
        ('pending', 'Pending'),
        ('address_pending', 'Address Pending'),
        ('customer_confiration_pending', 'Customer Confirmation Pending'),
        ('customer_delaying', 'Customer make delaying'),
        ('dl_pending_payment', 'Pending Delivery charge Payment'),
        ('publish_to_dms', 'Publish to DMS'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    )
    dl_task_status_dms = (
        ('0', 'Assigned'),
        ('1', 'Started'),
        ('2', 'Successful'),
        ('3', 'Failed'),
        ('4', 'InProgress/Arrived'),
        ('6', 'Unassigned'),
        ('7', 'Accepted/Acknowledged'),
        ('8', 'Decline'),
        ('9', 'Cancel'),
        ('10', 'Deleted'),
    )

    dl_task_publish = models.BooleanField(default=False)
    dl_task_number = models.CharField(max_length=100)
    dl_task_number_dms = models.CharField(max_length=100)
    dl_task_description = models.CharField(max_length=100)
    dl_task_status_client = models.CharField(
        max_length=100, choices=dl_task_status_client)
    dl_task_status = models.CharField(max_length=100, choices=dl_task_status)
    dl_task_status_dms = models.CharField(
        max_length=100, default=6, choices=dl_task_status_dms)
    dl_task_date = models.DateField(auto_now_add=True)
    order = models.ForeignKey(orders_models.Order, on_delete=models.DO_NOTHING, related_name='delivery_task')
    dl_address_update = models.ForeignKey(
        DlAddressUpdate, on_delete=models.DO_NOTHING, blank=True, null=True, related_name='dl_task')
    driver = models.ForeignKey(
        fleet_models.Driver, on_delete=models.DO_NOTHING, blank=True, null=True)
    business = models.ForeignKey(
        business_models.Business, on_delete=models.DO_NOTHING, blank=True, null=True)

    pickup_location = models.ForeignKey(
        business_models.PickupLocation, on_delete=models.DO_NOTHING, blank=True, null=True)

    dl_waight = models.IntegerField(default=1)
    dl_category_choices = (
        ('Food', 'Food'),
        ('Regular', 'Regular'),
        ('Electronics', 'Electronics'),
        ('Others', 'Others'),
    )
    dl_category = models.CharField(
        max_length=100, choices=dl_category_choices, blank=True)
    dl_speed_choices = (
        ('Normal', 'Normal'),
        ('Same Day', 'Same Day'),
        ('On Demand',   'On Demand'),
        ('White Glove',   'White Glove'),

    )
    dl_speed = models.CharField(
        max_length=100, choices=dl_speed_choices, blank=True)
    dl_price = models.IntegerField(null=True, blank=True)
    dl_to_address = models.ForeignKey(
        delivery_models.DlAddressUpdate, on_delete=models.DO_NOTHING, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order}-{self.dl_task_number}"

    class Meta:
        verbose_name_plural = "Delivery Task"


class ZoneName(models.Model):
    zone_name = models.CharField(max_length=100)
    zone_number = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.zone_name

    class Meta:
        verbose_name_plural = "Zone Name"
        app_label = 'delivery'

class LatLonList(models.Model):
    zone_number = models.PositiveIntegerField()
    street_number = models.PositiveIntegerField()
    building_number = models.PositiveIntegerField( blank=True, null=True)
    latitude = models.PositiveIntegerField( blank=True, null=True)
    longitude = models.PositiveIntegerField( blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.zone_name) + " " + str(self.street_number)

    class Meta:
        verbose_name_plural = " LatLons"
        app_label = 'delivery'



class AssignedDriver(models.Model):
    driver = models.ForeignKey(fleet_models.Driver, on_delete=models.CASCADE)
    dl_task = models.ForeignKey(DeliveryTask, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.driver.driver_name

    class Meta:
        verbose_name_plural = "Assigned Driver"
        app_label = 'delivery'
