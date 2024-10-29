from django import forms
from webpages.models import *
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit

from fleet import models as fleet_models


class ContactForm(forms.Form):
    DELIVERY_REQUEST = 'dr'
    fulfillment = 'fl'
    AFFLILIATE = 'af'
    DRIVER_JOB = 'd'
    FEEDBACK = 'fb'
    OTHER = 'o'
    purpose_choices = (
        (DELIVERY_REQUEST, 'Delivery Request'),
        (fulfillment, 'fulfillment Request'),
        (AFFLILIATE, 'Affiliate Marketing Program'),
        (DRIVER_JOB, 'Driver Jobs'),
        (FEEDBACK, 'Feedback'),
        (OTHER, 'Other'),
    )

    full_name = forms.CharField()
    email = forms.EmailField()
    mobile = forms.CharField()
    purpose = forms.MultipleChoiceField(choices=purpose_choices,
                                        widget=forms.CheckboxSelectMultiple())
    message = forms.CharField(
        widget=forms.Textarea(attrs={'cols': 20, 'rows': 3}))

    def save(self):
        data = self.cleaned_data
        contactus = ContactUs(full_name=data['full_name'], email=data['email'],
                              mobile=data['mobile'], purpose=data['purpose'],
                              message=data['message'])
        contactus.save()
        return contactus


class CareersForm(forms.ModelForm):
    class Meta:
        model = Careers
        fields = '__all__'

    def clean_qid(self):
        qid = self.cleaned_data.get('qid')
        print(type(qid))
        qid = str(qid)
        # Check if qid is 10 digits and starts with 2 or 3
        if not (len(qid) == 11 and qid.isdigit() and (qid.startswith('2') or qid.startswith('3'))):
            raise forms.ValidationError("The qid should be real")

        return qid

    

  

class PricingEnquiryForm(forms.ModelForm):
    # Override boolean fields with ChoiceField
    is_personalized_product = forms.ChoiceField(choices=[ (False, 'No'),(True, 'Yes')])
    is_registered_company_in_qatar = forms.ChoiceField(choices=[(True, 'Yes'), (False, 'No')])
    is_located_in_qatar = forms.ChoiceField(choices=[(True, 'Yes'), (False, 'No')])
    is_team_available_in_qatar = forms.ChoiceField(choices=[(True, 'Yes'), (False, 'No')])
    is_required_COD_service = forms.ChoiceField(choices=[(True, 'Yes'), (False, 'No')])
    speed_delivery_offer_to_customers = forms.MultipleChoiceField(choices=[('5Days', '6: 5 Days Delivery'), ('NextDay48', '5: Next 48 Hrs Delivery'),('NextDay24', '4: Next 24 Hrs Delivery'),('SameDay', '3: Same Day Delivery'),('WithIn6Hr', '2: With In 6Hrs'),('WithIn2Hr', '1: With In 2Hrs'), ('None', 'None') ]) 
    is_required_fulfillment_service_for_operate_from_outside_qatar = forms.ChoiceField(choices=[(True, 'Yes'), (False, 'No')]) 
    is_required_fulfillment_service_for_make_hub_in_doha = forms.ChoiceField(choices=[(True, 'Yes'), (False, 'No')])
    is_frequent_same_day_pick_and_delivery_required = forms.ChoiceField(choices=[(False, 'No'), (True, 'Yes, Pick And Delivery Same time') ])
    is_special_handling_required = forms.ChoiceField(choices=[(False, 'No'), (True, 'Yes')])
    type_of_pickup_location = forms.ChoiceField(choices=[('Home', 'Home'), ("Office", 'Office'), ("Store", 'Store'), ("Multiple Store", 'Multiple Store'), ("Fulfillment", 'Fulfillment')])
    typical_package_size = forms.MultipleChoiceField(choices=[('Packets samll (Below 20cm)', 'Packets samll (Below 20cm)'), ('Packets Big (above 20cm)', 'Packets Big (above 20cm)'), ('Boxs samll', 'Boxs samll (Below 20cm)'),('Boxs Big', 'Boxs Big (Above 20cm)'),('Boxs Bigger', 'Boxs Bigger (Above  50cm)')])
    pickup_location_time_slab = forms.MultipleChoiceField(choices=[('AllDay', 'All day'), ('Office Timing 8Am-3Pm', 'Office Timing( 8Am - 3Pm)'),('Before11Am', 'Before 11Am'), ('11AM-4Pm', '11AM-4Pm'), ('After4PM', 'After 4PM')])
    avarage_number_of_order_last_week = forms.ChoiceField(choices=[('1-4', '1 to 4'),('5-25', '5 to 25'), ('26-60', '26 to 60'), ('61-100', '61 to 100'),('100-200', '100 to 200'),('200-300', '200 to 300'),('300-500', '300 to 500'),('500-1000', '500 to 1000'),('1000-1500', '1000 to 1500'),('1500+', '1500+')])
    avarage_number_of_order_done_last_month = forms.ChoiceField(choices=[('1-4', '1 to 4'),('5-25', '5 to 25'), ('26-60', '26 to 60'), ('61-100', '61 to 100'),('100-200', '100 to 200'),('200-300', '200 to 300'),('300-500', '300 to 500'),('500-1000', '500 to 1000'),('1000-1500', '1000 to 1500'),('1500+', '1500+')])
    avarage_number_of_order_expect_next_month = forms.ChoiceField(choices=[('1-4', '1 to 4'),('5-25', '5 to 25'), ('26-60', '26 to 60'), ('61-100', '61 to 100'),('100-200', '100 to 200'),('200-300', '200 to 300'),('300-500', '300 to 500'),('500-1000', '500 to 1000'),('1000-1500', '1000 to 1500'),('1500+', '1500+')])
    orders_expected_in_next_3_months_milestone = forms.ChoiceField(choices=[('1-4', '1 to 4'),('5-25', '5 to 25'), ('26-60', '26 to 60'), ('61-100', '61 to 100'),('100-200', '100 to 200'),('200-300', '200 to 300'),('300-500', '300 to 500'),('500-1000', '500 to 1000'),('1000-1500', '1000 to 1500'),('1500+', '1500+')])

    class Meta:
        model = PricingEnquiry
        fields = '__all__'  # Include all fields from the model

    def __init__(self, *args, **kwargs):
        super(PricingEnquiryForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('full_name'),
            Field('business_name'),
            Field('is_personalized_product'),
            Field('is_registered_company_in_qatar'),
            Field('is_located_in_qatar'),
            Field('is_team_available_in_qatar'),
            Field('is_required_COD_service'),
            Field('is_required_COD_service'),
            Field('is_required_fulfillment_service_for_operate_from_outside_qatar'),
            Field('is_required_fulfillment_service_for_make_hub_in_doha'),
            Field('avarage_number_of_order_last_week'),
            Field('avarage_number_of_order_done_last_month'),
            Field('avarage_number_of_order_expect_next_month'),
            Field('orders_expected_in_next_3_months_milestone'),
            Field('speed_delivery_offer_to_customers'),
            Field('is_frequent_same_day_pick_and_delivery_required'),
            Field('website_url'),
            Field('social_profile'),
            Field('preferred_delivery_time_window'),
            Field('typical_package_size'),
            Field('is_special_handling_required'),
            Field('type_of_pickup_location'),
            Field('pickup_location_area_name'),
            Field('pickup_location_time_slab'),
            Field('number_of_pickup_times_in_day'),
            Submit('submit', 'Submit', css_class='btn-success')
        )