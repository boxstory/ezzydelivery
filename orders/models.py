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
        ('publish', 'Published'),
        ('delivered', 'Delivered'),
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
        ('pending', 'COD Pending'),
        ('collected', 'Collected by Driver'),
        ('received_by_company', 'Received by Company'),
        ('invoiced', 'Invoiced'),
        ('settled', 'Settled with Business'),
        ('online_paid', 'Paid Online to Seller'),
        ('disputed', 'Disputed'),
    ]

COD_STATUS_BY_STAFF = [
        ('not_collected', 'Not Collected'),
        ('partially_collected', 'Partially Collected'),
        ('fully_paid', 'Fully Collected'),
        ('cod_with_driver', 'COD Collected & with Driver'),
        ('cod_with_ezzy', 'COD handover to EZZY'),
        ('cod_settled_with_business', 'COD Settled with Business'),
    ]

ORDER_TYPE_CHOICES = [
        ('normal_delivery', 'Normal Delivery'),
        ('pick_and_drop', 'Pick and Drop'),
    ]

class Order(models.Model):

    # Create your models here.
 
    order_number = models.CharField(max_length=64, unique=True, db_index=True)  # INDEX: Unique, frequently searched
    business = models.ForeignKey(
        business_models.Business, on_delete=models.CASCADE, related_name='order', db_index=True)  # INDEX: Filtered in every order query
    client_order_code = models.CharField(max_length=64, unique=True, db_index=True)  # INDEX: Searched by clients
    order_notes = models.CharField(max_length=100, blank=True, null=True)
    package_description = models.CharField(max_length=255, blank=True, default='',
        help_text="Seller's package description e.g. 'Perfumes', 'Food items'")
    package_qty = models.PositiveIntegerField(default=0,
        help_text="Package quantity for the product description")
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
    order_type = models.CharField(
        max_length=20, choices=ORDER_TYPE_CHOICES, default='normal_delivery',
        help_text="Order type: normal delivery or pick and drop")
    scheduled_delivery = models.BooleanField(default=False, help_text="Whether delivery is scheduled for a specific time")
    scheduled_date = models.DateField(blank=True, null=True, help_text="Scheduled delivery date if scheduled_delivery is True")
    scheduled_time = models.TimeField(blank=True, null=True, help_text="Scheduled delivery time if scheduled_delivery is True")

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
    order_source_text = models.TextField(blank=True, null=True, help_text="Raw pasted order text (WhatsApp/chat message) kept for reference")

    # Transferred tag — set by staff when API orders are confirmed and added to the main workflow
    is_transferred = models.BooleanField(default=False, db_index=True, help_text="Order has been transferred/accepted into main workflow by staff")
    transferred_at = models.DateTimeField(null=True, blank=True, help_text="When the order was transferred")
    transferred_by = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='transferred_orders', help_text="Staff who transferred this order"
    )

    # Warehouse stock reservation tracking
    stock_reserved = models.BooleanField(default=False, help_text="Whether stock has been reserved for this order")

    # Delivery customer details
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=100, blank=True)
    customer_whatsapp = models.CharField(max_length=100, blank=True)
    customer_address = models.CharField(max_length=100, blank=True)
    deadline_date = models.CharField(max_length=100, blank=True)
    order_date = models.DateField(auto_now_add=True)
    dl_zone = models.PositiveIntegerField(blank=True, null=True, default=None)
    dl_building = models.PositiveIntegerField(blank=True, null=True, default=None)
    dl_street = models.PositiveIntegerField(blank=True, null=True, default=None)
    latitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    longitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    QNAS_STATUS = [
        ('not_checked', 'Not Checked'),
        ('verified', 'Verified'),
        ('not_found', 'Not Found'),
        ('error', 'Error'),
    ]
    qnas_status = models.CharField(max_length=15, choices=QNAS_STATUS, default='not_checked', blank=True)
    COORDS_ACCURACY = [
        ('exact', 'Exact (Building)'),
        ('street', 'Street Level'),
        ('landmark', 'Landmark/Area'),
        ('zone_center', 'Zone Center'),
        ('ai_estimate', 'AI Estimate'),
    ]
    coords_accuracy = models.CharField(max_length=15, choices=COORDS_ACCURACY, blank=True, null=True)

    # Delivery completion tracking
    delivered_at = models.DateTimeField(blank=True, null=True, help_text="When the order was delivered")
    fulfilled_at = models.DateTimeField(blank=True, null=True, help_text="When the order was marked as fulfilled")

    # Cancellation tracking
    CANCELLATION_REASON_CHOICES = [
        ('client_request', 'Client Request'),
        ('address_issue', 'Address Issue'),
        ('customer_unreachable', 'Customer Unreachable'),
        ('duplicate_order', 'Duplicate Order'),
        ('out_of_stock', 'Out of Stock'),
        ('driver_issue', 'Driver Issue'),
        ('other', 'Other'),
    ]
    cancellation_reason = models.CharField(
        max_length=50, choices=CANCELLATION_REASON_CHOICES, blank=True, null=True,
        help_text="Why the order was cancelled"
    )
    cancellation_notes = models.TextField(
        blank=True, null=True,
        help_text="Additional notes about the cancellation"
    )
    cancelled_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cancelled_orders',
        help_text="Staff member who cancelled the order"
    )

    # Hub delivery tracking
    is_hub_delivery = models.BooleanField(
        default=False,
        help_text="When True, order goes through hub warehouse before last-mile delivery."
    )
    hub_warehouse = models.ForeignKey(
        'warehouse.WarehouseLocation',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='hub_orders',
        help_text="Hub warehouse used as handoff point for hub deliveries."
    )
    hub_pickup_batch = models.ForeignKey(
        'delivery.HubPickupBatch',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='orders',
        help_text="Pickup batch this order belongs to (assigned by staff)."
    )

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

    
    @property
    def whatsapp_product_summary(self):
        """Return a short product summary for WhatsApp messages."""
        items = getattr(self, '_prefetched_objects_cache', {}).get('order_items')
        if items is None:
            items = self.order_items.select_related('product', 'product__product_category').all()[:5]
        parts = []
        for item in items[:5]:
            if item.product:
                cat = ''
                if item.product.product_category:
                    cat = f' ({item.product.product_category})'
                parts.append(f'{item.product.item_name} x{item.quantity}{cat}')
            elif item.notes:
                parts.append(f'{item.notes} x{item.quantity}')
        return ', '.join(parts) if parts else ''

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

    @property
    def display_name(self):
        """Return a human-readable product name for templates."""
        if self.product:
            return self.product.item_name
        if self.notes:
            # notes format: "13__SPECIAL OUD____BUK006" → extract middle part
            parts = self.notes.split('__')
            if len(parts) >= 2:
                return parts[1].strip()
            return self.notes
        return 'Item'

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


class OrderStatusHistory(models.Model):
    """Track all status changes across order lifecycle"""
    STATUS_FIELD_CHOICES = [
        ('order_status', 'Order Status'),
        ('task_status', 'Task Status'),
        ('verification_status', 'Verification Status'),
        ('cod_status_by_staff', 'COD Status'),
        ('dl_task_status', 'Delivery Task Status'),
        ('dl_task_publish', 'Published to Fleet'),
        ('order_edited', 'Order Edited'),
        ('task_edited', 'Task Edited'),
        ('item_deleted', 'Item Deleted'),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='status_history')
    field_name = models.CharField(max_length=50, choices=STATUS_FIELD_CHOICES)
    old_value = models.CharField(max_length=100, blank=True, null=True)
    new_value = models.CharField(max_length=100)
    old_display = models.CharField(max_length=100, blank=True, null=True)
    new_display = models.CharField(max_length=100)
    changed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Order Status History"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order', '-created_at'], name='ord_status_hist_idx'),
        ]

    def __str__(self):
        return f"{self.order.order_number} - {self.field_name}: {self.old_display} → {self.new_display}"


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


class OneDriveSource(models.Model):
    """OneDrive Excel file source for bulk order import."""
    business = models.ForeignKey(
        business_models.Business, on_delete=models.CASCADE,
        related_name='onedrive_sources'
    )
    label = models.CharField(max_length=200, help_text="Friendly name for this source")
    share_link = models.URLField(max_length=1000, help_text="OneDrive shared link to Excel file")
    is_active = models.BooleanField(default=True)
    last_import_at = models.DateTimeField(blank=True, null=True)
    last_import_count = models.PositiveIntegerField(default=0)
    last_import_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    last_sheet_name = models.CharField(max_length=200, blank=True, default='')
    last_start_row = models.PositiveIntegerField(default=2)
    last_import_max_row = models.PositiveIntegerField(default=0)
    last_imported_rows = models.JSONField(default=list, blank=True, help_text="List of row numbers imported in last batch")
    last_column_mapping = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "OneDrive Sources"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business.business_name} - {self.label}"

    def get_download_url(self):
        """Convert OneDrive share link to direct download URL.

        Supported formats:
        1. Short share link: https://1drv.ms/x/s!AbcDef...
        2. OneDrive embed/view with resid+authkey
        3. OneDrive edit.aspx with resid (needs encoding trick)
        4. SharePoint guestaccess links
        """
        import base64
        from urllib.parse import urlparse, parse_qs, quote

        link = self.share_link.strip()

        # Method 1: 1drv.ms short links — use sharing API
        if '1drv.ms' in link:
            encoded = base64.urlsafe_b64encode(link.encode()).decode().rstrip('=')
            return f"https://api.onedrive.com/v1.0/shares/u!{encoded}/root/content"

        # Method 2: onedrive.live.com with resid
        elif 'onedrive.live.com' in link:
            parsed = urlparse(link)
            params = parse_qs(parsed.query)
            resid = params.get('resid', [None])[0]
            authkey = params.get('authkey', [None])[0]

            if resid and authkey:
                return f"https://onedrive.live.com/download?resid={resid}&authkey={authkey}"
            elif resid:
                # No authkey — use download endpoint with resid directly
                # Also try the sharing API as fallback
                return f"https://onedrive.live.com/download?resid={quote(resid)}"

        # Method 3: SharePoint links
        elif 'sharepoint.com' in link:
            if 'guestaccess.aspx' in link:
                return link.replace('guestaccess.aspx', 'download.aspx')
            if '/:x:/' in link or '/:w:/' in link:
                return link + ('&' if '?' in link else '?') + 'download=1'
            encoded = base64.urlsafe_b64encode(link.encode()).decode().rstrip('=')
            return f"https://api.onedrive.com/v1.0/shares/u!{encoded}/root/content"

        return link


class PublicLinkSource(models.Model):
    """Public URL source for importing orders from HTML tables."""
    business = models.ForeignKey(
        business_models.Business, on_delete=models.CASCADE,
        related_name='public_link_sources'
    )
    label = models.CharField(max_length=200, help_text="Friendly name for this source")
    url = models.URLField(max_length=1000, help_text="Public URL to HTML page with order table")
    is_active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(blank=True, null=True)
    last_sync_count = models.PositiveIntegerField(default=0)
    last_column_mapping = models.JSONField(default=dict, blank=True,
        help_text="Auto-detected column mapping: {col_idx: db_field}")
    last_headers = models.JSONField(default=list, blank=True,
        help_text="Column headers from last sync")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Public Link Sources"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business.business_name} - {self.label}"


class TempOrder(models.Model):
    """Cached row from external sources (OneDrive, Google Sheet, API, Public Link), synced periodically or manually.

    These rows are displayed on the Temp Orders page. When staff imports
    a row into a real Order, the status flips to 'imported'.
    """
    STATUS_CHOICES = [
        ('new', 'New'),
        ('imported', 'Imported'),
        ('skipped', 'Skipped'),
    ]
    SOURCE_TYPE_CHOICES = [
        ('onedrive', 'OneDrive'),
        ('google_sheet', 'Google Sheet'),
        ('shopify', 'Shopify'),
        ('woocommerce', 'WooCommerce'),
        ('public_link', 'Public Link'),
    ]

    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, default='onedrive', db_index=True)
    onedrive_source = models.ForeignKey(
        'orders.OneDriveSource', on_delete=models.CASCADE,
        related_name='temp_orders', null=True, blank=True,
    )
    api_settings = models.ForeignKey(
        'business.BusinessApiSettings', on_delete=models.CASCADE,
        related_name='temp_orders', null=True, blank=True,
    )
    public_link_source = models.ForeignKey(
        'orders.PublicLinkSource', on_delete=models.CASCADE,
        related_name='temp_orders', null=True, blank=True,
    )
    business = models.ForeignKey(
        business_models.Business, on_delete=models.CASCADE,
        related_name='temp_orders', db_index=True,
    )
    sheet_name = models.CharField(max_length=200, blank=True, default='')
    row_num = models.PositiveIntegerField(default=0, help_text="Row number (1-indexed) or 0 for API orders")
    platform_id = models.CharField(max_length=100, blank=True, default='', help_text="Platform order ID for API sources")

    # Mapped fields
    client_order_code = models.CharField(max_length=100, blank=True, default='')
    customer_name = models.CharField(max_length=200, blank=True, default='')
    customer_phone = models.CharField(max_length=100, blank=True, default='')
    customer_address = models.CharField(max_length=500, blank=True, default='')
    dl_zone = models.CharField(max_length=20, blank=True, default='')
    dl_street = models.CharField(max_length=20, blank=True, default='')
    dl_building = models.CharField(max_length=20, blank=True, default='')
    cod_amount = models.CharField(max_length=30, blank=True, default='')
    order_date = models.CharField(max_length=50, blank=True, default='')
    package_desc = models.CharField(max_length=500, blank=True, default='')

    # Raw row data for reference
    raw_row = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new', db_index=True)
    imported_order = models.ForeignKey(
        'orders.Order', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='source_temp_order',
    )

    synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-row_num']
        verbose_name = "Temp Order"
        verbose_name_plural = "Temp Orders"

    def __str__(self):
        return f"{self.business} - {self.source_type} Row {self.row_num} ({self.status})"

    @property
    def source_label(self):
        if self.onedrive_source:
            return self.onedrive_source.label
        if self.api_settings:
            return f"{self.api_settings.get_api_type_display()}"
        if self.public_link_source:
            return self.public_link_source.label
        return self.get_source_type_display()


class ImportLog(models.Model):
    """Unified log for every batch import, regardless of source channel."""

    SOURCE_CHOICES = [
        ('csv_upload', 'CSV / Excel Upload'),
        ('onedrive', 'OneDrive'),
        ('shopify', 'Shopify'),
        ('woocommerce', 'WooCommerce'),
        ('google_sheet', 'Google Sheet'),
    ]

    STATUS_CHOICES = [
        ('started', 'Started'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('completed_with_errors', 'Completed with Errors'),
        ('failed', 'Failed'),
    ]

    business = models.ForeignKey(
        'business.Business', on_delete=models.CASCADE,
        related_name='import_logs', db_index=True,
    )
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, db_index=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='started')
    initiated_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
    )

    # Counts
    total_rows = models.PositiveIntegerField(default=0)
    orders_created = models.PositiveIntegerField(default=0)
    orders_skipped = models.PositiveIntegerField(default=0)
    orders_failed = models.PositiveIntegerField(default=0)

    # Raw data BEFORE mapping — the audit trail
    raw_data = models.JSONField(default=list, blank=True)

    # Column mapping used (for CSV/Excel/OneDrive/Google Sheets)
    column_mapping = models.JSONField(default=dict, blank=True)

    # Source-specific metadata (file_name, sheet_name, share_link, shop_name, etc.)
    source_meta = models.JSONField(default=dict, blank=True)

    # Error details: [{row: N, error: "msg"}, ...]
    errors = models.JSONField(default=list, blank=True)

    # Link to created orders
    orders = models.ManyToManyField('orders.Order', blank=True, related_name='import_logs')

    # Optional FK to OneDriveSource
    onedrive_source = models.ForeignKey(
        'orders.OneDriveSource', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='import_logs',
    )

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['business', 'source', '-started_at'], name='implog_biz_src_dt_idx'),
        ]

    def __str__(self):
        return f"{self.business} | {self.get_source_display()} | {self.started_at:%Y-%m-%d %H:%M} | {self.orders_created} orders"

    def mark_completed(self):
        from django.utils import timezone
        self.status = 'completed_with_errors' if self.errors else 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])

    def mark_failed(self, error_msg=''):
        from django.utils import timezone
        if error_msg:
            current_errors = self.errors or []
            current_errors.append(error_msg)
            self.errors = current_errors
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'errors', 'completed_at'])

    @property
    def source_meta_display(self):
        """Format source_meta for template display — clean labels, skip internal IDs."""
        meta = self.source_meta or {}
        label_map = {
            'source_label': 'Source',
            'sheet_name': 'Sheet',
            'share_link': 'Link',
            'file_name': 'File',
            'file_size': 'Size',
            'site_url': 'Site URL',
            'api_type': 'Type',
            'shop_name': 'Shop',
            'spreadsheet_name': 'Spreadsheet',
            'sheet_url': 'Sheet URL',
        }
        skip_keys = {'api_settings_id', 'row_numbers', 'platform_ids'}
        result = []
        for key, val in meta.items():
            if key in skip_keys or not val:
                continue
            label = label_map.get(key, key.replace('_', ' ').title())
            if key == 'file_size' and isinstance(val, (int, float)):
                val = f"{val / 1024:.1f} KB" if val < 1048576 else f"{val / 1048576:.1f} MB"
            result.append({'label': label, 'value': val})
        # Add row count from row_numbers
        row_nums = meta.get('row_numbers') or meta.get('platform_ids')
        if row_nums and isinstance(row_nums, list):
            result.append({'label': 'Selected items', 'value': f"{len(row_nums)} rows"})
        return result

    @property
    def mapping_display(self):
        """Format column_mapping for compact badge display."""
        mapping = self.column_mapping or {}
        seen_fields = set()
        result = []
        for col, field in mapping.items():
            if field and field not in seen_fields:
                seen_fields.add(field)
                col_label = col if not col.isdigit() else f"Col {col}"
                field_label = field.replace('_', ' ').title()
                result.append({'col': col_label, 'field': field_label})
        return result

    @property
    def mapping_count(self):
        mapping = self.column_mapping or {}
        return len(set(v for v in mapping.values() if v))

    @property
    def raw_data_count(self):
        return len(self.raw_data) if self.raw_data else 0

    @property
    def raw_data_headers(self):
        """Get column headers from first raw data row."""
        if not self.raw_data:
            return []
        first = self.raw_data[0]
        if isinstance(first, dict):
            return list(first.keys())
        if isinstance(first, list):
            return [f"Col {i+1}" for i in range(len(first))]
        return []

    @property
    def raw_data_preview(self):
        """Get first 5 rows of raw data as list of cell values."""
        if not self.raw_data:
            return []
        rows = self.raw_data[:5]
        result = []
        for row in rows:
            if isinstance(row, dict):
                cells = list(row.values())
            elif isinstance(row, list):
                cells = row
            else:
                cells = [str(row)]
            result.append([str(c) if c else '' for c in cells])
        return result