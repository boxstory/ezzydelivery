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
from product import forms as product_forms
from core.forms_base import SanitizedForm, SanitizedFormMixin, SanitizedModelForm

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


class WarehouseForm(SanitizedModelForm):
    """
    Form for creating/editing fulfillment centers.
    Staff-only form - warehouses are NOT owned by sellers.
    """
    class Meta:
        model = warehouse_models.Warehouse
        fields = [
            'name', 'code', 'description', 'address', 'city', 'state',
            'postal_code', 'country', 'latitude', 'longitude',
            'phone', 'email', 'is_active', 'is_default', 'manager'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter fulfillment center name'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Auto-generated if empty (WH-FC-XXXXXXXX)'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Warehouse description and operational details'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Full warehouse address'
            }),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State/Region'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Postal Code'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'latitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001',
                'placeholder': 'Latitude (for auto-selection)'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001',
                'placeholder': 'Longitude (for auto-selection)'
            }),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact phone'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Contact email'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'manager': forms.Select(attrs={'class': 'form-select'}),
        }
        help_texts = {
            'code': 'Leave empty to auto-generate unique code',
            'is_default': 'Set as default fulfillment center for auto-selection',
            'latitude': 'GPS coordinates used for distance-based warehouse selection',
            'longitude': 'GPS coordinates used for distance-based warehouse selection',
        }


class WarehouseLocationForm(SanitizedModelForm):
    """
    Form for creating/editing warehouse pickup/dispatch locations.
    Each warehouse can have multiple physical locations.
    """
    class Meta:
        model = warehouse_models.WarehouseLocation
        fields = [
            'warehouse', 'name', 'code', 'address', 'zone_number',
            'latitude', 'longitude', 'is_active', 'is_default',
            'operating_hours', 'notes'
        ]
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., North Gate, Main Entrance, Loading Dock A'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., NG, ME, LDA'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Specific location address or directions'
            }),
            'zone_number': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Primary delivery zone served by this location'
            }),
            'latitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001',
                'placeholder': 'GPS latitude'
            }),
            'longitude': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.000001',
                'placeholder': 'GPS longitude'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'operating_hours': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'e.g., Mon-Fri 8AM-5PM, Sat 9AM-2PM'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Special instructions for drivers'
            }),
        }
        help_texts = {
            'is_default': 'Set as default location for this warehouse',
            'zone_number': 'Links this location to a delivery zone for automatic selection',
        }


class SellerWarehouseLinkForm(SanitizedModelForm):
    """
    Form for linking sellers to fulfillment centers.
    Staff-only form - controls which warehouses serve which sellers.
    """
    class Meta:
        model = warehouse_models.SellerWarehouseLink
        fields = [
            'business', 'warehouse', 'default_location',
            'is_default', 'is_active', 'priority', 'notes'
        ]
        widgets = {
            'business': forms.Select(attrs={'class': 'form-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'default_location': forms.Select(attrs={'class': 'form-select'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'priority': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': 'Higher priority = preferred for auto-selection'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Special notes about this warehouse-seller relationship'
            }),
        }
        help_texts = {
            'is_default': 'Set as default warehouse for this seller',
            'priority': 'Higher values are preferred during automatic warehouse selection',
            'default_location': 'Default pickup location at this warehouse for this seller',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter locations based on selected warehouse
        if 'instance' in kwargs and kwargs['instance'].pk:
            warehouse = kwargs['instance'].warehouse
            self.fields['default_location'].queryset = warehouse_models.WarehouseLocation.objects.filter(
                warehouse=warehouse,
                is_active=True
            )


# =============================================================================
# STORAGE LOCATION FORM
# Create/edit storage locations within a warehouse.
# Supports hierarchical structure: zone > aisle > rack > shelf > bin
# Barcode auto-generated if not provided.
# =============================================================================


class StorageLocationForm(SanitizedModelForm):
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


class StockLevelForm(SanitizedModelForm):
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


class ReceiveStockForm(SanitizedForm):
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
        self.business = business

        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business,
            is_active=True
        ).values_list('warehouse_id', flat=True)

        self.fields['warehouse'].queryset = warehouse_models.Warehouse.objects.filter(
            id__in=linked_warehouse_ids,
            is_active=True
        )

    def clean_product(self):
        """Fix: Validate product belongs to the user's business to prevent IDOR."""
        from product.models import Product
        product_id = self.cleaned_data.get('product')

        if product_id and self.business:
            try:
                product = Product.objects.get(id=product_id)
                if product.business_id != self.business.business_id:
                    raise forms.ValidationError(
                        'You do not have permission to receive stock for this product.'
                    )
            except Product.DoesNotExist:
                raise forms.ValidationError('Product not found.')

        return product_id


# =============================================================================
# CYCLE COUNT FORM
# Schedule inventory counts for accuracy verification.
# Can target specific warehouse/location or entire warehouse.
# =============================================================================


class CycleCountForm(SanitizedModelForm):
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


class CycleCountItemForm(SanitizedModelForm):
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


class AdjustmentForm(SanitizedForm):
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


# =============================================================================
# STAFF PRODUCT ADD FORM
# Warehouse-side quick add for a seller's catalogue.
# =============================================================================


class StaffProductAddForm(product_forms.AddItemsForm):
    """
    The seller's product form, relaxed for the receiving desk.

    The seller-facing form demands a brand, a SKU, a price and a category
    because a seller is describing a product they are about to sell. Warehouse
    staff are usually adding an item that just turned up in a box, and holding
    the record hostage to a category they have no opinion about means the
    product never gets created at all. Only the name is required here; the
    seller fills the rest in later on their own screen.
    """

    OPTIONAL_FOR_STAFF = ('brand_name', 'item_sku', 'item_price', 'product_category')

    def __init__(self, *args, business=None, **kwargs):
        # The chosen seller, needed for the SKU rule below. Not a form field:
        # the view owns it, the same way it owns which business is saved.
        self.business = business
        super().__init__(*args, **kwargs)
        for name in self.OPTIONAL_FOR_STAFF:
            if name in self.fields:
                self.fields[name].required = False
        # Deliberately left not-required even for a fulfilment seller: the
        # standard "This field is required." says nothing about why, so the
        # check lives in clean_item_sku where it can explain itself.

    def _business_needs_sku(self):
        return bool(self.business and getattr(self.business, 'fulfillment_service_enabled', False))

    def clean_item_price(self):
        # PositiveIntegerField is NOT NULL with a default of 0 — a blank box
        # means "not priced yet", not "no value allowed".
        return self.cleaned_data.get('item_price') or 0

    def clean_brand_name(self):
        return (self.cleaned_data.get('brand_name') or '').strip()

    def clean_item_sku(self):
        sku = (self.cleaned_data.get('item_sku') or '').strip()
        # Product.save() refuses a blank SKU for a fulfilment-enabled seller.
        # Catch it here so it reads as a field error instead of a 500.
        if not sku and self._business_needs_sku():
            raise forms.ValidationError(
                "This seller is fulfilment-enabled, so every product needs a SKU."
            )
        return sku
