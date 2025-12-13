"""
Warehouse Forms Module
======================

This module contains forms for warehouse and inventory management.

Forms:
    Warehouse Setup:
        - WarehouseForm: Create/edit warehouse facilities
        - StorageLocationForm: Create/edit storage locations (zones/aisles/racks/bins)

    Inventory:
        - StockLevelForm: Configure stock levels and reorder points
        - ReceiveStockForm: Receive new stock into warehouse
        - AdjustmentForm: Manual inventory adjustments

    Operations:
        - CycleCountForm: Schedule inventory counts
        - CycleCountItemForm: Record count results

Related:
    - warehouse.models: All warehouse models
    - warehouse.views: Views that use these forms
"""

from django import forms
from warehouse import models as warehouse_models

# Local aliases for commonly used models
Warehouse = warehouse_models.Warehouse
StorageLocation = warehouse_models.StorageLocation
StockLevel = warehouse_models.StockLevel
CycleCount = warehouse_models.CycleCount
CycleCountItem = warehouse_models.CycleCountItem


# =============================================================================
# WAREHOUSE FORM
# Create/edit warehouse facilities.
# Code auto-generated if not provided: WH-{business_code}-{uuid}
# Can optionally link to existing PickupLocation.
# =============================================================================


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = warehouse_models.Warehouse
        fields = ['name', 'code', 'address', 'pickup_location', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto-generated if empty'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'pickup_location': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# =============================================================================
# STORAGE LOCATION FORM
# Create/edit storage locations within a warehouse.
# Supports hierarchical structure: zone > aisle > rack > shelf > bin
# Barcode auto-generated if not provided.
# =============================================================================


class StorageLocationForm(forms.ModelForm):
    class Meta:
        model = warehouse_models.StorageLocation
        fields = ['warehouse', 'parent', 'name', 'code', 'location_type', 'is_pickable', 'is_active']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., A-01-03-B'}),
            'location_type': forms.Select(attrs={'class': 'form-select'}),
            'is_pickable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# =============================================================================
# STOCK LEVEL FORM
# Configure stock levels for products at specific warehouse/location.
# Set reorder points and ABC classification for inventory management.
# =============================================================================


class StockLevelForm(forms.ModelForm):
    class Meta:
        model = warehouse_models.StockLevel
        fields = ['product', 'warehouse', 'location', 'quantity_on_hand',
                  'reorder_point', 'reorder_quantity', 'abc_classification']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'quantity_on_hand': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'reorder_point': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'reorder_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'abc_classification': forms.Select(attrs={'class': 'form-select'}),
        }


# =============================================================================
# RECEIVE STOCK FORM
# Form for receiving new stock into warehouse.
# Warehouse queryset filtered by business in __init__.
# Creates InventoryTransaction with type='receive'.
# =============================================================================


class ReceiveStockForm(forms.Form):
    warehouse = forms.ModelChoiceField(
        queryset=warehouse_models.Warehouse.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    location = forms.ModelChoiceField(
        queryset=warehouse_models.StorageLocation.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    product = forms.IntegerField(widget=forms.HiddenInput())
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )

    def __init__(self, business, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['warehouse'].queryset = warehouse_models.Warehouse.objects.filter(
            business=business, is_active=True
        )


# =============================================================================
# CYCLE COUNT FORM
# Schedule inventory counts for accuracy verification.
# Can target specific warehouse/location or entire warehouse.
# =============================================================================


class CycleCountForm(forms.ModelForm):
    class Meta:
        model = warehouse_models.CycleCount
        fields = ['warehouse', 'location', 'scheduled_date', 'assigned_to', 'notes']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'scheduled_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


# =============================================================================
# CYCLE COUNT ITEM FORM
# Record count results for individual items.
# Variance auto-calculated: counted_quantity - system_quantity.
# =============================================================================


class CycleCountItemForm(forms.ModelForm):
    class Meta:
        model = warehouse_models.CycleCountItem
        fields = ['counted_quantity', 'variance_reason']
        widgets = {
            'counted_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'variance_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


# =============================================================================
# ADJUSTMENT FORM
# Manual inventory adjustments (add or remove stock).
# Creates InventoryTransaction with type='adjust_in' or 'adjust_out'.
# Reason required for audit trail.
# =============================================================================


class AdjustmentForm(forms.Form):
    ADJUSTMENT_TYPE_CHOICES = [
        ('adjust_in', 'Adjustment In (Add)'),
        ('adjust_out', 'Adjustment Out (Remove)'),
    ]

    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1})
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )
