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
        max_length=6,
        unique=True,
        editable=False,
        db_index=True,
        null=True,
        blank=True,
        help_text="6-digit unique product identifier (last 2 digits from business code)"
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
        upload_to='product_images/brand_logo', null=True, blank=True)
    product_image = models.ImageField(
        upload_to='product_images/product_images', null=True, blank=True)
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
        Override save to auto-generate unique 6-digit product_id.
        Format: {4-digit-counter}{2-digit-business-code}
        Example: 000101, 000212, 123456

        - First 4 digits: Sequential counter (0001-9999)
        - Last 2 digits: Last 2 digits from business_id
        """
        if not self.product_id:
            from django.db.models import Max

            # Get last 2 digits from business_id
            if self.business and self.business.business_id:
                # Extract only digits from business_id and take last 2
                business_digits = ''.join(filter(str.isdigit, str(self.business.business_id)))
                business_suffix = business_digits[-2:].zfill(2) if business_digits else "00"
            else:
                business_suffix = "00"

            # Find the highest product_id with this business suffix
            suffix_pattern = f"_____{business_suffix}"  # 5 chars + suffix
            last_product = Product.objects.filter(
                product_id__endswith=business_suffix
            ).order_by('-product_id').first()

            if last_product and len(last_product.product_id) == 6:
                # Extract the 4-digit counter from existing product_id
                try:
                    last_counter = int(last_product.product_id[:4])
                    counter = last_counter + 1
                    # If counter exceeds 9999, wrap to 0001
                    if counter > 9999:
                        counter = 1
                except (ValueError, IndexError):
                    counter = 1
            else:
                counter = 1

            # Generate 6-digit product_id: {counter:04d}{business_suffix}
            self.product_id = f"{counter:04d}{business_suffix}"

            # Ensure uniqueness (in case of race condition)
            max_attempts = 9999
            attempts = 0
            while Product.objects.filter(product_id=self.product_id).exists() and attempts < max_attempts:
                counter += 1
                if counter > 9999:
                    counter = 1
                self.product_id = f"{counter:04d}{business_suffix}"
                attempts += 1

            if attempts >= max_attempts:
                raise ValueError(f"Unable to generate unique product_id for business suffix {business_suffix}")

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
        upload_to='services_images', null=True, blank=True, default="services_images/default.jpg")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business = models.ForeignKey(
        business_models.Business, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.service_name

    class Meta:
        verbose_name_plural = "Services"
