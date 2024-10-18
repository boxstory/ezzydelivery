from django import forms
from product import models as product_models
# ITEMS FORM ----------------------------------------------------------------------------------------------------------------------


class AddItemsForm(forms.ModelForm):
    class Meta:
        model = product_models.Product
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        fields = '__all__'
        exclude = ('inventory', 'business', 'items_sku')
        widgets = {
            'item_name': forms.TextInput(attrs={'class': 'form-control'}),
            'item_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'item_quantity': forms.NumberInput(attrs={'class': 'form-control'}),

        }
