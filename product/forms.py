"""
Product Forms Module
====================

This module contains forms for product catalog management.

Forms:
    - AddItemsForm: Create/update products in business catalog

Related:
    - product.models: Product, ProductCategory, ColorVariant, UnitVariant
    - product.views: product_single_add, product_single_update
"""

from django import forms
from product import models as product_models
from core.forms_base import SanitizedForm, SanitizedFormMixin, SanitizedModelForm

# Local aliases for commonly used models
Product = product_models.Product
ProductCategory = product_models.ProductCategory


# =============================================================================
# ADD ITEMS FORM
# Form for adding/editing products in the business catalog.
# Excludes business field (set in view), inventory (managed separately),
# and items_sku (auto-generated or manually set).
# Used in: product_single_add, product_single_update views
# Template: product/product_single_add.html, product/product_single_update.html
# =============================================================================


class AddItemsForm(SanitizedModelForm):
    class Meta:
        model = product_models.Product
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        fields = [
            'brand_name',
            'item_name',
            'item_sku',
            'barcode',
            'color',
            'size',
            'unit',
            'item_price',
            'item_discription',
            'brand_logo',
            'product_image',
            'product_category',
        ]
        # Exclude protected fields - business set in view, product_id auto-generated
        exclude = ['business', 'product_id', 'created_at', 'updated_at']
        widgets = {
            'item_name': forms.TextInput(attrs={'class': 'form-control'}),
            'item_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'item_discription': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
