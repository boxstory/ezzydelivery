from django import forms
from django.utils.translation import gettext_lazy as _
from datetime import timezone

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
    
    
    class Meta:
        model = Order
        fields = ['pickup_location', 'client_order_code', 'customer_name', 'customer_phone', 'customer_whatsapp',   'cod_status_by_client', 'cod_amount',
                  'dl_building', 'dl_street', 'dl_zone', 'customer_address', 'order_notes', ]
        exclude = ['order_number', 'business', 'delivery_task', 'deadline_date', 'cod_status_by_staff',
                   'updated_at', 'created_at']
        widgets = {
            'order_notes': forms.TextInput(attrs={'class': 'form-control'}),
            'order_status': forms.Select(attrs={'class': 'form-control'}, choices=ORDER_STATUS),

        }
        labels = {
            'order_notes': _('Order Short description'),
            'client_order_code': _('Order Number'),
            'cod_amount': 'Enter COD with Delivery charge',
            'dl_building': 'Customer building No',
            'dl_street': 'Customer Street No',
            'dl_zone': 'Customer Zone No',
        }

    def __init__(self,  *args, **kwargs):
        business_id = kwargs.pop('business_id', None)
        

        super().__init__(*args, **kwargs)
        for field in iter(self.fields):
            self.fields[field].widget.attrs.update(
                {'class': 'form-control'})
            
            self.fields['dl_building'].initial = '0'
            self.fields['dl_street'].initial = '0'
            self.fields['dl_zone'].initial = '0'
            #@todo: check business code display in form and disabled fields
            #self.fields['business_code'].disabled = business_code

            self.fields['cod_status_by_client'].widget = forms.RadioSelect(
                choices=COD_STATUS_BY_CLIENT, attrs={'checked': 'checked'})

            # @todo: need to specify business only products

            #self.fields['product_list'].widget = forms.CheckboxSelectMultiple()

        # Access the form data to filter pickup_location choices
        if business_id is not None:
            self.fields['pickup_location'].queryset = business_models.PickupLocation.objects.filter(
                business_id=business_id)
            
        

    def save(self, commit=True):
        order = super().save(commit=False)

        if commit:
            order.save()
        return order


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


class AddOrderProductsForm(forms.ModelForm):
    
    class Meta:
        model = OrderProductList
        fields = '__all__' 

        labels = {
                
            }
       

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['order'].widget = forms.TextInput(attrs={'readonly': 'readonly', 'hidden': 'hidden'})


class OrderFileUploadForm(forms.Form):
    file = forms.FileField()


 