"""
Orders Forms Module
===================

This module contains forms for order creation, editing, and management.

Forms:
    Order Management:
        - AddOrderForm: Create new orders with customer and delivery details
        - UpdateOrderForm: Edit existing orders
        - AddOrderProductsForm: Add products/items to orders
        - OrderFileUploadForm: CSV file upload for bulk order import

Order Flow:
    1. Business creates order with AddOrderForm
    2. Products added with AddOrderProductsForm
    3. Order goes through verification (workforce)
    4. Delivery task created automatically
    5. Updates via UpdateOrderForm as needed

Validation:
    - Auto-generates unique order numbers
    - Validates COD amounts
    - Filters pickup locations by business
    - Filters products by business

Related:
    - orders.models: Order, OrderItem
    - orders.views: Order creation and management views
    - delivery.models: DeliveryTask (created from verified orders)
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from datetime import timezone

from requests import request

from orders import models as orders_models
from business import models as business_models
from product import models as product_models

# Local aliases for commonly used models
Order = orders_models.Order
OrderItem = orders_models.OrderItem


# =============================================================================
# CONSTANTS
# =============================================================================

ORDER_STATUS = {
    ('ready_to_pickup', 'Ready to pickup'),
    ('out_for_delivery', 'Out for delivery'),
    ('customer _cofirm', 'Customer Confirmation Pending'),
    ('delivered', 'Delivered'),
    ('customer _delaying', 'Customer make delaying'),
    ('cancelled', 'Cancelled'),
}

COD_STATUS_BY_CLIENT = {
    ('no_cod', 'No COD'),
    ('include', 'Include'),
}


# =============================================================================
# ORDER FORMS
# =============================================================================


class AddOrderForm(forms.ModelForm):
    """
    Order creation form.

    Used by businesses to create new delivery orders with customer
    and delivery information.

    Fields:
        Order Info:
            - client_order_code: Business's internal order number
            - order_notes: Short description/notes
            - order_status: to_review, ready_to_pickup, publish, cancelled

        Customer Details:
            - customer_name: Recipient name
            - customer_phone: Contact phone
            - customer_whatsapp: WhatsApp number

        Delivery Address:
            - dl_zone: Zone number
            - dl_street: Street number
            - dl_building: Building number
            - customer_address: Full address text

        COD (Cash on Delivery):
            - cod_status_by_client: no_cod or include
            - cod_amount: Amount to collect

        Pickup:
            - pickup_location: Business pickup location (filtered by business)

    Auto-generated:
        - order_number: Unique order ID (BusinessCode-ClientCode-SystemID)

    Template:
        orders/order_add.html

    View:
        orders.views.order_add
    """
    # Add a field to display the unique order number preview
    order_number_preview = forms.CharField(
        label='Unique Order Number (Auto-generated)',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': 'readonly',
            'id': 'order_number_preview',
            'placeholder': 'Will be generated: [Business Code]-[Your Order Number]-[System ID]'
        })
    )

    class Meta:
        model = Order
        fields = ['pickup_location', 'client_order_code', 'customer_name', 'customer_phone', 'customer_whatsapp',   'cod_status_by_client', 'cod_amount',
                  'dl_building', 'dl_street', 'dl_zone', 'customer_address', 'order_notes', 'order_status']
        exclude = ['order_number', 'business', 'delivery_task', 'deadline_date', 'cod_status_by_staff',
                   'updated_at', 'created_at']
        widgets = {
            'order_notes': forms.TextInput(attrs={'class': 'form-control'}),
            'order_status': forms.Select(attrs={'class': 'form-control'}, choices=ORDER_STATUS),
            'client_order_code': forms.TextInput(attrs={'class': 'form-control', 'id': 'client_order_code_input'}),
        }
        labels = {
            'order_notes': _('Order Short description'),
            'client_order_code': _('Your Order Number'),
            'cod_amount': 'Enter COD with Delivery charge',
            'dl_building': 'Customer building No',
            'dl_street': 'Customer Street No',
            'dl_zone': 'Customer Zone No',
        }

    def __init__(self,  *args, **kwargs):
        business_id = kwargs.pop('business_id', None)
        business_code = kwargs.pop('business_code', None)

        super().__init__(*args, **kwargs)

        # Store business_code for use in JavaScript
        if business_code:
            self.fields['order_number_preview'].widget.attrs['data-business-code'] = business_code

        for field in iter(self.fields):
            self.fields[field].widget.attrs.update(
                {'class': 'form-control'})

            self.fields['dl_building'].initial = '0'
            self.fields['dl_street'].initial = '0'
            self.fields['dl_zone'].initial = '0'

            self.fields['cod_status_by_client'].widget = forms.RadioSelect(
                choices=COD_STATUS_BY_CLIENT, attrs={'checked': 'checked'})

        # Access the form data to filter pickup_location choices
        if business_id is not None:
            self.fields['pickup_location'].queryset = business_models.PickupLocation.objects.filter(
                business_id= business_id)
            
        

    def save(self, commit=True):
        order = super().save(commit=False)

        if commit:
            order.save()
        return order


class AddOrderProductsForm(forms.ModelForm):
    """
    Order product/item form.

    Used to add individual products to an order. Each order can have
    multiple OrderItems linked to it.

    Fields:
        - order: Parent order (hidden field)
        - product: Product from business inventory
        - quantity: Number of units
        - unit_price: Price per unit
        - notes: Item-specific notes

    Auto-calculated:
        - total_price: unit_price * quantity (in model save)

    Template:
        orders/order_product_add.html

    View:
        orders.views.order_product_add

    Note:
        Products are filtered to show only those belonging
        to the order's business.
    """

    class Meta:
        model = OrderItem
        fields = ['order', 'product', 'quantity', 'unit_price', 'notes']

        labels = {
            'product': 'Product',
            'quantity': 'Quantity',
            'unit_price': 'Unit Price',
            'notes': 'Notes',
        }

        widgets = {
            'order': forms.HiddenInput(),
            'quantity': forms.NumberInput(attrs={'min': 1, 'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].widget.attrs.update({'class': 'form-control'})
        self.fields['notes'].required = False

        # Filter products by business if order instance exists
        if self.instance and self.instance.order_id:
            try:
                order = Order.objects.get(id=self.instance.order_id)
                business_products = product_models.Product.objects.filter(business=order.business)

                # Apply filter to all product fields
                for i in range(1, 8):  # products 1-7
                    field_name = f'product{i:02d}_name'
                    if field_name in self.fields:
                        self.fields[field_name].queryset = business_products
                        self.fields[field_name].required = False
                        # Add styling
                        self.fields[field_name].widget.attrs.update({'class': 'form-control'})

                    qty_field = f'product{i:02d}_qty'
                    if qty_field in self.fields:
                        self.fields[qty_field].required = False
                        self.fields[qty_field].widget.attrs.update({
                            'class': 'form-control',
                            'min': '0',
                            'type': 'number'
                        })
            except Order.DoesNotExist:
                pass


  
    




class OrderFileUploadForm(forms.Form):
    """
    CSV file upload form for bulk order import.

    Allows businesses to upload multiple orders at once via CSV file.

    Fields:
        - file: CSV file with order data

    Expected CSV Columns:
        - client_order_code, customer_name, customer_phone
        - customer_whatsapp, customer_address
        - dl_zone, dl_street, dl_building
        - cod_amount, order_notes

    Template:
        orders/order_file_upload.html

    View:
        orders.views.order_file_upload
    """
    file = forms.FileField()


class UpdateOrderForm(forms.ModelForm):
    """
    Order update form.

    Used to edit existing orders. Some fields are read-only to preserve
    order integrity after creation.

    Fields:
        Editable:
            - customer_name, customer_phone, customer_whatsapp
            - cod_status_by_client, cod_amount
            - dl_zone, customer_address
            - pickup_location, order_notes
            - task_created: Mark if delivery task was created

        Read-only (via widget attrs):
            - customer_name (disabled)
            - customer_whatsapp (readonly)

    Template:
        orders/order_update.html (if exists)

    View:
        orders.views.order_update
    """
    class Meta:
        model = Order
        fields = [ 'customer_name', 'customer_phone', 'customer_whatsapp',  'task_created', 'cod_status_by_client', 'cod_amount',
                  'dl_zone', 'customer_address', 'pickup_location', 'order_notes', ]

        exclude = ['order_number','client_order_code', 'business', 'delivery_task', 'order_date',
                   'pickup_location_id', 'updated_at', 'created_at']
        labels = {
            'order_notes': 'Order Name / Notes',
            'cod_amount': 'Balance COD with Delivery charge'
        }
        widgets = {
            'customer_name': forms.TextInput(attrs={'class': 'form-control', 'disabled': True}),
            'customer_whatsapp': forms.TextInput(attrs={'class': 'form-control', 'readonly': True}),
            'order_notes': forms.TextInput(attrs={'class': 'form-control'}),
            'cod_amount': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        business_id = kwargs.pop('business_id', None)
        super().__init__(*args, **kwargs)
        for field in iter(self.fields):
            self.fields[field].widget.attrs.update(
                {'class': 'form-control'})
            self.fields['task_created'].widget = forms.CheckboxInput(
                attrs={'class': 'form-check-input '})
            
            self.fields['cod_status_by_client'].widget = forms.RadioSelect(
                choices=COD_STATUS_BY_CLIENT)
            # @todo: need to specify business only products
            
            
        if business_id is not None:
            self.fields['pickup_location'].queryset = business_models.PickupLocation.objects.filter(
                business_id=business_id)




 
