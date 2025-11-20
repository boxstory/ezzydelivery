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



# orders---------------------------------------------------------------------------------------------------------------------

ORDER_STATUS_BY_CLIENT = [
        ('to_review', 'Hold for Review'),
        ('ready_to_pickup', 'Ready to pickup'),
        ('publish', 'Publish for start delivery'),
        ('cancelled', 'Cancelled'),
    ]

TASK_STATUS_BY_STAFF = [
        ('new_order', 'New Order'),
        ('info_missing', 'Info Missing'),
        ('pending_for_confirm', 'Pending in confirm with Customer'),
        ('dl_task_listed', 'listed in Delivery Tasks'),
    ]

COD_STATUS_BY_CLIENT = [
        ('no_cod', 'No COD'),
        ('include', 'Include'),
    ]

COD_STATUS_BY_STAFF = [
        ('not_collected', 'Not Collected'),
        ('partially_collected', 'Partially Collected'),
        ('fully_paid', 'Fully Collected'),
        ('cod_with_driver', 'COD Collected & with Driver'),
        ('cod_with_ezzy', 'COD handover to EZZY'),
        ('cod_sattled_with_business', 'COD Sattled with Business'),
    ]

class Order(models.Model):

    # Create your models here.
 
    order_number = models.CharField(max_length=64, unique=True, db_index=True)  # INDEX: Unique, frequently searched
    business = models.ForeignKey(
        business_models.Business, on_delete=models.CASCADE, related_name='order', db_index=True)  # INDEX: Filtered in every order query
    client_order_code = models.CharField(max_length=64, unique=True, db_index=True)  # INDEX: Searched by clients
    order_notes = models.CharField(max_length=100, blank=True, null=True)
    order_status = models.CharField(
        max_length=100, choices=ORDER_STATUS_BY_CLIENT, default='to_review', db_index=True  # INDEX: Filtered for pending/published orders
    )
    task_status = models.CharField(
        max_length=100, choices=TASK_STATUS_BY_STAFF, default='new_order', db_index=True  # INDEX: Filtered for new/pending tasks
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
    dl_included = models.BooleanField(default=True)
    dl_amount = models.IntegerField(default=0)
    
    # Verification tracking
    VERIFICATION_STATUS = (
        ('pending', 'Pending Verification'),
        ('address_verified', 'Address Verified'),
        ('address_needs_update', 'Address Needs Update'),
        ('customer_contacted', 'Customer Contacted'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    )
    verification_status = models.CharField(
        max_length=50, choices=VERIFICATION_STATUS, default='pending')
    address_verified = models.BooleanField(default=False)
    address_verified_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_addresses')
    address_verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_orders')
    verified_at = models.DateTimeField(blank=True, null=True)
    verification_notes = models.TextField(blank=True, null=True)
    
    # Original order data (proof/backup)
    original_order_data = models.JSONField(blank=True, null=True, help_text="Original order data as proof")

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
        # COMPOUND INDEXES: business + status + created_at for fast filtering and ordering
        indexes = [
            models.Index(fields=['business', 'order_status', '-created_at'], name='ord_biz_status_created_idx'),
            models.Index(fields=['business', 'task_status'], name='ord_biz_task_idx'),
            models.Index(fields=['order_number'], name='ord_number_idx'),
            models.Index(fields=['client_order_code'], name='ord_client_code_idx'),
            models.Index(fields=['-created_at'], name='ord_created_idx'),
            models.Index(fields=['verification_status'], name='ord_verification_idx'),
        ]

class OrderLog(models.Model):
    # Dictionary field to store the changes
    original_enquiry = models.JSONField()
    change_data_log = models.JSONField()

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.change_data_log)

class OrderComments(models.Model):
    order =  models.ForeignKey(
        orders_models.Order, on_delete=models.CASCADE, related_name='order_comments')
    name = models.CharField(max_length=255, blank=True, null=True,)
    body =  models.TextField()


    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return str(self.order.order_number)


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
        return str(self.order_number)
    
    def save(self, *args, **kwargs):
        EAN = barcode.get_barcode_class('code128')
        ean = EAN(self.order_number, writer=ImageWriter())
        buffer = BytesIO()
        ean.write(buffer)
        self.barcode.save(f"{self.order_number}.png", File(buffer), save=False)
        return super().save(*args, **kwargs)





class OrderItem(models.Model):
    """Individual items in an order (replaces OrderProductList with proper many-to-many)"""
    order = models.ForeignKey(
        orders_models.Order, on_delete=models.CASCADE, related_name='order_items')
    product = models.ForeignKey(
        product_models.Product, on_delete=models.DO_NOTHING, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-calculate total_price if unit_price and quantity are provided
        if self.unit_price and self.quantity:
            self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_number} - {self.product} x {self.quantity}" if self.product else f"{self.order.order_number} - Item"

    class Meta:
        verbose_name_plural = "Order Items"
        ordering = ['id']


class OrderProductList(models.Model):
    """DEPRECATED: Legacy model for backward compatibility. Use OrderItem instead."""
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
        verbose_name_plural = "Order product lists (DEPRECATED)"


class OrderVerificationLog(models.Model):
    """Track order verification history"""
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='verification_logs')
    verified_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=100)  # 'address_verified', 'order_verified', 'rejected', etc.
    notes = models.TextField(blank=True, null=True)
    old_status = models.CharField(max_length=50, blank=True, null=True)
    new_status = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Order Verification Logs"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.order.order_number} - {self.action}"


class AddressVerification(models.Model):
    """Track address verification details"""
    VERIFICATION_RESULT = (
        ('valid', 'Valid'),
        ('invalid', 'Invalid'),
        ('needs_update', 'Needs Update'),
        ('pending', 'Pending'),
        ('address_verified', 'Address Verified by Customer'),
        ('verified', 'Verified by Staff'),
    )

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='address_verifications')
    verification_token = models.CharField(max_length=64, unique=True, blank=True, null=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)
    original_address = models.CharField(max_length=500)
    verified_address = models.CharField(max_length=500, blank=True, null=True)
    verification_result = models.CharField(
        max_length=50, choices=VERIFICATION_RESULT, default='pending')
    verified_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    customer_verified_at = models.DateTimeField(blank=True, null=True)
    latitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    longitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    zone_number = models.PositiveIntegerField(blank=True, null=True)
    street_number = models.PositiveIntegerField(blank=True, null=True)
    building_number = models.PositiveIntegerField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Address Verifications"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order.order_number} - {self.verification_result}"

    def is_token_expired(self):
        """Check if verification token has expired"""
        if not self.token_expires_at:
            return True
        from django.utils import timezone
        return timezone.now() > self.token_expires_at

    def generate_token(self):
        """Generate a unique verification token"""
        import secrets
        self.verification_token = secrets.token_urlsafe(32)
        from django.utils import timezone
        from datetime import timedelta
        self.token_expires_at = timezone.now() + timedelta(days=7)  # Token valid for 7 days
        return self.verification_token