import os
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from django.core.files import File

from delivery import models as delivery_models
from core import models as core_models
from fleet import models as fleet_models
from client import models as business_models
from orders import models as orders_models
from webpages import models as webpages_models
from product import models as product_models


# Create your models here.

ORDER_STATUS_BY_CLIENT = {
    ('to_review', 'Hold for Review'),
    ('ready_to_pickup', 'Ready to pickup'),
    ('publish', 'Publish for start delivery'),
    ('cancelled', 'Cancelled'),
    
}
ORDER_STATUS_BY_STAFF = {
    ('new_order', 'New Order'),
    ('info_missing', 'Info Missing'),
    ('pending_for_confirm', 'Pending in confirm with Customer'),
    ('dl_task_listed', 'listed in Delivery Tasks'),
    
}

COD_STATUS_BY_CLIENT = {
    ('no_cod', 'No COD'),
    ('include', 'Include'),
}

COD_STATUS_BY_STAFF = {
    ('not_collected', 'Not Collected'),
    ('partially_collected', 'Partially Collected'),
    ('fully_paid', 'Fully Collected'),
    ('cod_with_driver', 'COD Collected & with Driver'),
    ('cod_with_ezzy', 'COD handover to EZZY'),
    ('cod_sattled_with_business', 'COD Sattled with Business'),
}

# orders---------------------------------------------------------------------------------------------------------------------


class Order(models.Model):
    order_number = models.CharField(max_length=64, unique=True)
    business = models.ForeignKey(
        business_models.Business, on_delete=models.CASCADE, related_name='order')
    client_order_code = models.CharField(max_length=64, unique=True)
    order_notes = models.CharField(max_length=100, blank=True, null=True)
    order_status = models.CharField(
        max_length=100, choices=ORDER_STATUS_BY_CLIENT, default='to_review',
    )
    task_status = models.CharField(
        max_length=100, choices=ORDER_STATUS_BY_CLIENT, default='new_order',
    )

    # pickup details
    pickup_location = models.ForeignKey(
        business_models.PickupLocation, on_delete=models.SET_NULL, null=True)

    # cod details
    task_created = models.BooleanField(default=False)
    cod_status_by_client = models.CharField(
        max_length=100, choices=COD_STATUS_BY_CLIENT, blank=True, null=True)
    cod_status_by_staff = models.CharField(
        max_length=100, choices=COD_STATUS_BY_STAFF, blank=True, null=True)
    cod_amount = models.IntegerField(default=0)
    dl_included = models.BooleanField(default="True")
    dl_amount = models.IntegerField(default=0)

    # Delivery customer details
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=100, blank=True)
    customer_whatsapp = models.CharField(max_length=100, blank=True)
    customer_address = models.CharField(max_length=100, blank=True)
    deadline_date = models.CharField(max_length=100, blank=True)
    order_date = models.DateField(auto_now_add=True)
    dl_zone = models.PositiveIntegerField(blank=True)
    dl_building = models.PositiveIntegerField(blank=True)
    dl_street = models.PositiveIntegerField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_dirty_fields(self):
        dirty_fields = {}  # Dictionary to hold modified fields
        for field in self._meta.fields:  # Iterate through fields of the model
            field_name = field.attname  # Get the name of the field
            print(field_name + ' :field')  # Debug print
            oldd_value = getattr(self, f'{field_name}')
            print(oldd_value + ' :field')  # Debug print
            #@todo log entry dict not getting
            if hasattr(self, f'{field_name}'):  # Check if the model instance has an attribute to store the original value
                print('hatt attr')  # Debug print
                old_value = getattr(self, f'_{field_name}')  # Get the original value of the field
                print(old_value + ' old_value :field')  # Debug print
                new_value = getattr(self, field_name)  # Get the current value of the field
                print(new_value + ' new_value :field')  # Debug print
                if old_value != new_value:  # Check if the value has been modified
                    dirty_fields[field_name] = {  # Record the modified field
                        'old_value': old_value,
                        'new_value': new_value
                    }
        print('dirty_fields')  # Debug print
        print(dirty_fields)  # Debug print
        return dirty_fields  # Return the dictionary of modified fields

    
    def __str__(self):
        return f'({self.business}-{self.order_number}-{self.client_order_code})'

    class Meta:
        verbose_name_plural = "Order"

class OrderLog(models.Model):
    # Dictionary field to store the changes
    original_enquiry = models.JSONField()
    change_data_log = models.JSONField()

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.change_data_log

class OrderComments(models.Model):
    order =  models.ForeignKey(
        orders_models.Order, on_delete=models.CASCADE, related_name='order_comments')
    name = models.CharField(max_length=255, blank=True, null=True,)
    body =  models.TextField()


    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return self.order.order_number


def upload_path_handler(instance, filename):
    upload_dir = os.path.join(
        str(instance.path), 'barcode')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    return os.path.join(upload_dir, filename)

class OrderBarcode(models.Model):
    order =  models.ForeignKey(
        orders_models.Order, on_delete=models.CASCADE, related_name='order_barcode')
    order_number = models.CharField(max_length=255, blank=True, null=True,)
    barcode =  models.ImageField(
        upload_to="business/orders/", default="business/orders/barcode.png", blank=True, null=True)
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return self.order_number
    
    def save(self, *args, **kwargs):
        EAN = barcode.get_barcode_class('code128')
        ean = EAN(self.order_number, writer=ImageWriter())
        buffer = BytesIO()
        ean.write(buffer)
        self.barcode.save(f"{self.order_number}.png", File(buffer), save=False)
        return super().save(*args, **kwargs)





class OrderProductList(models.Model):
    order =  models.ForeignKey(
        orders_models.Order, on_delete=models.CASCADE, related_name='order_product_list')
    product01_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product01_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product02_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product02_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product03_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product03_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product04_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product04_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product05_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product05_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product06_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product06_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product07_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product07_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product08_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product08_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product09_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product09_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product10_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product10_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product11_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product11_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product12_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product12_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product13_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product13_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product14_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product14_qty = models.PositiveIntegerField(blank=True, null=True, default=0)
    product15_name = models.ForeignKey(product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True, related_name='+')
    product15_qty = models.PositiveIntegerField(blank=True, null=True, default=0)

    
    def __str__(self):
        return str(self.order)

    class Meta:
        verbose_name_plural = "Order product lists"