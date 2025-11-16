from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from client import models as business_models
from product import models as product_models
# Create your models here.


class ProductCategory(models.Model):
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
    brand_name = models.CharField(max_length=100)
    item_name = models.CharField(max_length=100)
    item_sku = models.CharField(max_length=100, db_index=True)  # INDEX: Frequently searched/filtered
    color = models.ForeignKey(
        ColorVariant, on_delete=models.SET_NULL, null=True, blank=True)
    size = models.CharField(max_length=100, null=True, blank=True)
    unit = models.ForeignKey(
        UnitVariant, on_delete=models.SET_NULL, null=True, blank=True)
    item_price = models.PositiveIntegerField(_("Price"), default=0)
    item_discription = models.CharField(max_length=100, null=True, blank=True)

    brand_logo = models.ImageField(
        upload_to='product_images/brand_logo', null=True, blank=True, default="business/product_images/brand_logo_default.jpg")
    product_image = models.ImageField(
        upload_to='product_images/product_images', null=True, blank=True, default="business/product_images/product_image_default.jpg")
    business = models.ForeignKey(
        business_models.Business, on_delete=models.SET_NULL, null=True, related_name='product', db_index=True)  # INDEX: Filtered in every product query
    product_category = models.ForeignKey(
        product_models.ProductCategory, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)  # INDEX: Used for ordering (.order_by('-created_at'))
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.brand_name + " " + self.item_name

    class Meta:
        verbose_name_plural = "Products items"
        # COMPOUND INDEX: business + created_at for faster filtering and ordering
        indexes = [
            models.Index(fields=['business', '-created_at'], name='product_business_created_idx'),
            models.Index(fields=['item_sku'], name='product_sku_idx'),
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
