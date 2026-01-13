"""
Orders Models - Core order management for EzzyDelivery

This module contains models for:
- Order: Main order entity with status tracking and verification
- OrderLog: Audit trail for order changes
- OrderComments: Comments/notes on orders
- OrderBarcode: Auto-generated barcodes for orders
- OrderItem: Individual items within an order
- OrderVerificationLog: Verification history tracking
- AddressVerification: Customer address verification workflow
"""
import os
import logging
from django.conf import settings
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
import barcode
from barcode.writer import ImageWriter
import qrcode
from io import BytesIO
from django.core.files import File

from delivery import models as delivery_models
from core import models as core_models
from fleet import models as fleet_models
from business import models as business_models
from orders import models as orders_models
from webpages import models as webpages_models
from product import models as product_models

logger = logging.getLogger(__name__)



# orders---------------------------------------------------------------------------------------------------------------------

ORDER_STATUS_BY_CLIENT = [
        ('to_review', 'Hold for Review'),
        ('ready_to_pickup', 'Ready to pickup'),
        ('publish', 'Publish for start delivery'),
        ('delivered', 'Delivered'),
        ('fulfilled', 'Fulfilled'),
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
        ('cod_settled_with_business', 'COD Settled with Business'),
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

    # Warehouse stock reservation tracking
    stock_reserved = models.BooleanField(default=False, help_text="Whether stock has been reserved for this order")

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

    # Delivery completion tracking
    delivered_at = models.DateTimeField(blank=True, null=True, help_text="When the order was delivered")
    fulfilled_at = models.DateTimeField(blank=True, null=True, help_text="When the order was marked as fulfilled")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_dirty_fields(self):
        """
        Get dictionary of fields that have been modified since last save.

        Returns:
            dict: Dictionary with field names as keys and {'old_value': x, 'new_value': y} as values
        """
        dirty_fields = {}
        for field in self._meta.fields:
            field_name = field.attname
            logger.debug(f"Checking field: {field_name}")

            current_value = getattr(self, field_name, None)

            # Check if we have stored the original value
            original_attr = f'_{field_name}'
            if hasattr(self, original_attr):
                old_value = getattr(self, original_attr)
                logger.debug(f"Field {field_name}: old={old_value}, new={current_value}")

                if old_value != current_value:
                    dirty_fields[field_name] = {
                        'old_value': old_value,
                        'new_value': current_value
                    }

        logger.debug(f"Dirty fields found: {dirty_fields}")
        return dirty_fields

    
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
        # Generate QR code instead of barcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(self.order_number)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        qr_image.save(buffer, format='PNG')
        buffer.seek(0)
        self.barcode.save(f"{self.order_number}_qr.png", File(buffer), save=False)
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


# OrderProductList model removed - use OrderItem instead


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