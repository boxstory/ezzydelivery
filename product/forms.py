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


class AddItemsForm(forms.ModelForm):
    class Meta:
        model = product_models.Product
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        fields = '__all__'
        exclude = ('inventory', 'business', 'items_sku', 'product_id')  # product_id is auto-generated
        widgets = {
            'item_name': forms.TextInput(attrs={'class': 'form-control'}),
            'item_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'item_quantity': forms.NumberInput(attrs={'class': 'form-control'}),

        }
