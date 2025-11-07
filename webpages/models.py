from django.conf import settings
from django.db import models

# Create your models here.


class ContactUs(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    mobile = models.BigIntegerField()
    purpose = models.CharField(max_length=100)
    message = models.TextField()
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    class Meta:
        verbose_name_plural = "Contact Us"


class Careers(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    mobile = models.BigIntegerField()
    qid = models.BigIntegerField()
    job = models.CharField(max_length=100)
    self_intro = models.TextField()
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    class Meta:
        verbose_name_plural = "Careers"


class PricingEnquiry(models.Model):
    # Personal Information
    full_name = models.CharField(max_length=100)
    business_name = models.CharField(max_length=100)
    business_contact_number = models.CharField(max_length=100)
    operation_team_contact_number = models.CharField(max_length=100, blank=True, null=True)

    # Contact Information
    website_url = models.CharField(max_length=200, blank=True, null=True)
    social_profile = models.CharField(max_length=200, blank=True, null=True)

    # Product Information
    product_category = models.CharField(max_length=200)
    is_personalized_product = models.BooleanField(default=False)

    # company Information
    is_registered_company_in_qatar = models.BooleanField(default=False)
    is_located_in_qatar = models.BooleanField(default=False)
    is_team_available_in_qatar = models.BooleanField(default=False)

    # Service Information
    is_required_COD_service = models.BooleanField(default=False)
    is_required_fulfillment_service_for_operate_from_outside_qatar = models.BooleanField(default=False) 
    is_required_fulfillment_service_for_make_hub_in_doha = models.BooleanField(default=False)

    # Order Information
    avarage_number_of_order_last_week = models.CharField(blank=True, null=True, max_length=20)
    avarage_number_of_order_done_last_month = models.CharField(blank=True, null=True, max_length=20)
    avarage_number_of_order_expect_next_month = models.CharField(blank=True, null=True, max_length=20)
    orders_expected_in_next_3_months_milestone = models.CharField(blank=True, null=True, max_length=20)
    

    # Delivery Information
    speed_delivery_offer_to_customers = models.CharField(max_length=200, blank=True, null=True)
    is_frequent_same_day_pick_and_delivery_required = models.BooleanField(default=False)

    # Additional Relevant Questions for Last Mile Delivery
    preferred_delivery_time_window = models.CharField(max_length=200, blank=True, null=True)
    typical_package_size = models.CharField(max_length=100, blank=True, null=True)
    is_special_handling_required = models.BooleanField(default=False)

    # pickup Information
    type_of_pickup_location = models.CharField(max_length=200, blank=True, null=True)
    pickup_Location_area_name = models.CharField(max_length=200, blank=True, null=True)
    pickup_location_time_slab = models.CharField(max_length=200, blank=True, null=True)
    number_of_pickup_times_in_day = models.CharField(max_length=200, default='1', blank=True, null=True)
    
    # date created
    date_created = models.DateField(auto_now_add=True, null=True)
    date_modified = models.DateField(auto_now=True, null=True) 

    def __str__(self):
        return self.business_name

    class Meta:
        verbose_name_plural = "Pricing Inquiries"


