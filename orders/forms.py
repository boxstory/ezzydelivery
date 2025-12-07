from django import forms
from django.utils.translation import gettext_lazy as _
from datetime import timezone

from requests import request

from orders.models import *
from client import models as business_models
from product import models as product_models

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


# ORDERS FORM ---------------------------------------------------------------------------------------------------------------------


class AddOrderForm(forms.ModelForm):
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
    """Form for adding products to an order using OrderItem model"""

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
    file = forms.FileField()
    



class UpdateOrderForm(forms.ModelForm):
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




 
