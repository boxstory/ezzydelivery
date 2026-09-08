"""
Product Models Module
=====================

This module contains models for product and inventory management.

Models:
    Product Catalog:
        - ProductCategory: Hierarchical product categories
        - ColorVariant: Color options for products
        - UnitVariant: Unit types (kg, piece, box, etc.)
        - Product: Main product entity with SKU, barcode, pricing

    Inventory:
        - ProductInventory: Stock quantity tracking per product

    Services:
        - services: Business service offerings

Product Structure:
    Category → Product → Inventory
              ↳ ColorVariant
              ↳ UnitVariant

Indexes:
    - Product.item_sku: SKU lookups
    - Product.barcode: Barcode scanning
    - Product.business + created_at: Business product listings

Related:
    - orders.models.OrderItem: Products in orders
    - business.models.Business: Product owner
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from business import models as business_models
from product import models as product_models
from core.validators import image_validators


# =============================================================================
# PRODUCT CATEGORY & VARIANTS
# =============================================================================


class ProductCategory(models.Model):
    """
    Hierarchical product category model.

    Supports nested categories through self-referencing FK.

    Fields:
        - category_name: Display name
        - sub_category: Parent category (null for top-level)
        - discription: Category description

    Usage:
        >>> electronics = ProductCategory.objects.create(category_name='Electronics')
        >>> phones = ProductCategory.objects.create(category_name='Phones', sub_category=electronics)
    """
    category_name = models.CharField(max_length=100)
    sub_category = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True)
    discription = models.CharField(max_length=100)
    product_category_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.category_name

    class Meta:
        verbose_name_plural = "Product Category"


class ColorVariant(models.Model):
    color_variant = models.CharField(max_length=100)
    short_code = models.CharField(max_length=5, null=True, blank=True)
    hex_code = models.CharField(max_length=7, null=True, blank=True, help_text="Hex color code e.g. #FF0000")
    discription = models.CharField(max_length=100)
    color_variants_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.color_variant

    class Meta:
        verbose_name_plural = "Color Variants"



class UnitVariant(models.Model):
    unit_variant = models.CharField(max_length=100)
    short_code = models.CharField(max_length=5, null=True, blank=True)
    discription = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.unit_variant

    class Meta:
        verbose_name_plural = "Unit Variants"





class Product(models.Model):
    product_id = models.CharField(
        max_length=15,
        unique=True,
        editable=False,
        db_index=True,
        null=True,
        blank=True,
        help_text="Unique product identifier: {business_pk}-{5-digit-counter} (e.g. 3-00001)"
    )  # Unique, non-editable product ID for inventory tracking
    brand_name = models.CharField(max_length=100)
    item_name = models.CharField(max_length=100)
    item_sku = models.CharField(max_length=100, db_index=True)  # INDEX: Frequently searched/filtered
    barcode = models.CharField(max_length=100, blank=True, null=True, db_index=True)  # Product barcode (UPC/EAN/etc.)
    color = models.ForeignKey(
        ColorVariant, on_delete=models.SET_NULL, null=True, blank=True)
    size = models.CharField(max_length=100, null=True, blank=True)
    unit = models.ForeignKey(
        UnitVariant, on_delete=models.SET_NULL, null=True, blank=True)
    item_price = models.PositiveIntegerField(_("Price"), default=0)
    item_discription = models.CharField(max_length=100, null=True, blank=True)
    client_names = models.TextField(
        blank=True, null=True,
        help_text="Comma-separated alternate names clients use for this product (e.g. 'Oud 50ml, special oud')"
    )

    brand_logo = models.ImageField(
        upload_to='product_images/brand_logo', null=True, blank=True,
        validators=image_validators(max_mb=5))
    product_image = models.ImageField(
        upload_to='product_images/product_images', null=True, blank=True,
        validators=image_validators(max_mb=8))
    business = models.ForeignKey(
        business_models.Business, on_delete=models.SET_NULL, null=True, related_name='product', db_index=True)  # INDEX: Filtered in every product query
    product_category = models.ForeignKey(
        product_models.ProductCategory, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)  # INDEX: Used for ordering (.order_by('-created_at'))
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.brand_name + " " + self.item_name

    def get_client_names_list(self):
        """Return list of stripped client alias names."""
        if not self.client_names:
            return []
        return [n.strip() for n in self.client_names.split(',') if n.strip()]

    def add_client_name(self, name):
        """Append a new alias if not already present (case-insensitive)."""
        existing = self.get_client_names_list()
        if name.strip().lower() not in [e.lower() for e in existing]:
            existing.append(name.strip())
            self.client_names = ', '.join(existing)
            self.save(update_fields=['client_names'])

    def save(self, *args, **kwargs):
        """
        Override save to auto-generate unique product_id.
        Format: {business_pk}-{5-digit-counter}
        Example: 3-00001, 12-00045

        - Prefix: business primary key (scoped per business, no collisions)
        - Counter: 5-digit sequential (00001-99999) per business
        - Products without a business use prefix "0"
        """
        if not self.product_id:
            biz_pk = self.business.pk if self.business else 0
            prefix = str(biz_pk)

            # Find highest counter for this business
            existing = Product.objects.filter(
                product_id__startswith=f"{prefix}-"
            ).order_by('-product_id')

            counter = 1
            if existing.exists():
                last_id = existing.first().product_id
                try:
                    last_counter = int(last_id.split('-', 1)[1])
                    counter = last_counter + 1
                except (ValueError, IndexError):
                    counter = 1

            self.product_id = f"{prefix}-{counter:05d}"

            # Ensure uniqueness (race condition guard)
            max_attempts = 99999
            attempts = 0
            while Product.objects.filter(product_id=self.product_id).exists() and attempts < max_attempts:
                counter += 1
                self.product_id = f"{prefix}-{counter:05d}"
                attempts += 1

            if attempts >= max_attempts:
                raise ValueError(f"Unable to generate unique product_id for business {biz_pk}")

        # Require item_sku for businesses with fulfillment enabled
        if self.business and getattr(self.business, 'fulfillment_service_enabled', False):
            if not self.item_sku or not self.item_sku.strip():
                raise ValueError(
                    "SKU is required for products in fulfillment-enabled businesses. "
                    "Please provide a valid item_sku."
                )

        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Products items"
        # COMPOUND INDEX: business + created_at for faster filtering and ordering
        indexes = [
            models.Index(fields=['business', '-created_at'], name='product_business_created_idx'),
            models.Index(fields=['item_sku'], name='product_sku_idx'),
            models.Index(fields=['barcode'], name='product_barcode_idx'),
        ]




class ProductInventory(models.Model):
    item_sku = models.ForeignKey(
        product_models.Product, on_delete=models.SET_NULL, null=True, related_name='product_inventory')
    item_quantity = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.item_sku} - Qty: {self.item_quantity}"

    class Meta:
        verbose_name_plural = "Product Inventory"


class services(models.Model):
    service_name = models.CharField(max_length=100)
    discription = models.CharField(max_length=100)
    image = models.ImageField(
        upload_to='services_images', null=True, blank=True, default="services_images/default.jpg",
        validators=image_validators(max_mb=5))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business = models.ForeignKey(
        business_models.Business, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.service_name

    class Meta:
        verbose_name_plural = "Services"


# =============================================================================
# PRODUCT COMBOS / BUNDLES
# =============================================================================


class ProductCombo(models.Model):
    """
    A bundle/combo of multiple products that can be quickly added to orders.

    Fields:
        - combo_name: Display name for the combo
        - combo_sku: Optional SKU for the bundle
        - combo_price: Override price (if different from sum of items)
        - is_active: Whether the combo is available

    Related:
        - ProductComboItem: Individual products in the combo
        - business.models.Business: Owner business
    """
    business = models.ForeignKey(
        'business.Business', on_delete=models.CASCADE, related_name='product_combos')
    combo_name = models.CharField(max_length=200)
    combo_sku = models.CharField(max_length=100, blank=True, default='', db_index=True)
    description = models.TextField(blank=True, default='')
    combo_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Bundle price (if different from sum of items)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_combo'
        ordering = ['-created_at']

    def __str__(self):
        return self.combo_name

    @property
    def total_items_price(self):
        return sum(
            item.product.item_price * item.quantity
            for item in self.items.select_related('product').all()
            if item.product.item_price
        )


class ProductComboItem(models.Model):
    """
    A single product entry within a ProductCombo.

    Fields:
        - combo: Parent combo
        - product: The product included
        - quantity: How many of this product in the combo
    """
    combo = models.ForeignKey(ProductCombo, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='combo_memberships')
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'product_comboitem'
        unique_together = ('combo', 'product')

    def __str__(self):
        return f"{self.quantity}x {self.product.item_name}"
