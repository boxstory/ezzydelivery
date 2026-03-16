"""
Webpages Views Module
=====================

This module handles public-facing website pages and marketing content.

View Categories:
    Landing Pages:
        - index: Homepage with hero section
        - about: About us page
        - contact: Contact information
        - services: Services listing

    Pricing & Inquiries:
        - delivery_pricing: 3PL pricing information
        - delivery_inquiry: Multi-step pricing inquiry form
        - delivery_request: Delivery request form

    For Businesses:
        - for_fleets: Fleet partnership information
        - join_us: Partnership onboarding

    For Drivers:
        - careers: Driver job listings
        - join_us_driver: Driver application

    Help & Support:
        - help_center: Main help center
        - help_guides: How-to guides
        - faq: Frequently asked questions

    SEO & Content:
        - seo_landing: Dynamic SEO landing pages
        - testimonials: Customer testimonials

    Error Pages:
        - error_403, error_404, error_500: Custom error handlers

SEO:
    All views include SEO metadata from core.seo.SEOMetadata
    for optimal search engine indexing.

Public Access:
    Most views are accessible without authentication.
    Some forms save to WhatsAppInquiry/PricingEnquiry models.

Related:
    - webpages.models: WhatsAppInquiry, PricingEnquiry
    - webpages.forms: Contact and inquiry forms
    - core.seo: SEOMetadata for page meta tags
"""

import logging
import random
from urllib.parse import quote
from django.forms.fields import DateTimeField
from django.shortcuts import redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from webpages import forms as webpages_forms
from webpages import models as webpages_models
from django.core.mail import mail_admins, send_mail
from business import models as business_models
from fleet import models as fleet_models
from core.seo import SEOMetadata

# Local aliases for commonly used models/forms
WhatsAppInquiry = webpages_models.WhatsAppInquiry
PricingEnquiry = webpages_models.PricingEnquiry
ContactForm = webpages_forms.ContactForm
CareersForm = webpages_forms.CareersForm
PricingEnquiryForm = webpages_forms.PricingEnquiryForm
DeliveryRequestForm = webpages_forms.DeliveryRequestForm
Business = business_models.Business
Driver = fleet_models.Driver

logger = logging.getLogger('webpages')


# =============================================================================
# LANDING PAGES
# =============================================================================


def index(request):
    meta = SEOMetadata.get_home_meta()
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/index.html', data)


def delivery_pricing(request):
    meta = SEOMetadata.get_pricing_meta()
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/3pl_pricing.html', data)

def _save_step1_to_db(inquiry, data):
    """Save step 1 fields to a PricingEnquiry instance."""
    inquiry.full_name = data.get('full_name', '')
    inquiry.business_name = data.get('business_name', '')
    inquiry.business_contact_number = data.get('business_contact_number', '')
    inquiry.operation_team_contact_number = data.get('operation_team_contact_number', '')
    inquiry.website_url = data.get('website_url', '')
    inquiry.social_profile = data.get('social_profile', '')
    inquiry.product_category = data.get('product_category', '')
    inquiry.is_personalized_product = data.get('is_personalized_product', 'False') == 'True'
    inquiry.is_located_in_qatar = data.get('is_located_in_qatar', 'False') == 'True'
    inquiry.is_registered_company_in_qatar = data.get('is_registered_company_in_qatar', 'False') == 'True'
    inquiry.business_location_country = data.get('business_location_country', '')
    inquiry.is_team_available_in_qatar = data.get('is_team_available_in_qatar', 'False') == 'True'
    inquiry.average_order_value_qar = data.get('average_order_value_qar', '')
    inquiry.business_operating_age = data.get('business_operating_age', '')
    inquiry.save()


def _save_step2_to_db(inquiry, data):
    """Save step 2 fields to a PricingEnquiry instance."""
    inquiry.avarage_number_of_order_last_week = data.get('avarage_number_of_order_last_week', '')
    inquiry.avarage_number_of_order_done_last_month = data.get('avarage_number_of_order_done_last_month', '')
    inquiry.avarage_number_of_order_expect_next_month = data.get('avarage_number_of_order_expect_next_month', '')
    inquiry.orders_expected_in_next_3_months_milestone = data.get('orders_expected_in_next_3_months_milestone', '')
    inquiry.is_required_COD_service = data.get('is_required_COD_service', 'False') == 'True'
    inquiry.is_required_fulfillment_service_for_operate_from_outside_qatar = data.get('is_required_fulfillment_service_for_operate_from_outside_qatar', 'False') == 'True'
    inquiry.is_required_fulfillment_service_for_make_hub_in_doha = data.get('is_required_fulfillment_service_for_make_hub_in_doha', 'False') == 'True'
    inquiry.current_courier_provider = data.get('current_courier_provider', '')
    inquiry.delivery_coverage = data.get('delivery_coverage', '')
    inquiry.is_return_logistics_required = data.get('is_return_logistics_required', 'False') == 'True'
    inquiry.preferred_start_date = data.get('preferred_start_date', '')
    inquiry.save()


def _save_step3_to_db(inquiry, data):
    """Save step 3 fields to a PricingEnquiry instance."""
    inquiry.speed_delivery_offer_to_customers = data.get('speed_delivery_offer_to_customers', '')
    inquiry.is_frequent_same_day_pick_and_delivery_required = data.get('is_frequent_same_day_pick_and_delivery_required', 'False') == 'True'
    inquiry.preferred_delivery_time_window = data.get('preferred_delivery_time_window', '')
    inquiry.typical_package_size = data.get('typical_package_size', '')
    inquiry.is_special_handling_required = data.get('is_special_handling_required', 'False') == 'True'
    inquiry.type_of_pickup_location = data.get('type_of_pickup_location', '')
    inquiry.pickup_Location_area_name = data.get('pickup_Location_area_name', '')
    inquiry.pickup_location_time_slab = data.get('pickup_location_time_slab', '')
    inquiry.number_of_pickup_times_in_day = data.get('number_of_pickup_times_in_day', '1')
    inquiry.order_management_system = data.get('order_management_system', '')
    inquiry.preferred_communication_channel = data.get('preferred_communication_channel', '')
    inquiry.is_delivery_free_to_customers = data.get('is_delivery_free_to_customers', '')
    inquiry.preferred_pickup_time = data.get('preferred_pickup_time', '')
    inquiry.preferred_payment_method = data.get('preferred_payment_method', '')
    inquiry.save()


def delivery_inquiry(request):
    """Multi-step pricing inquiry form — saves to DB on each step."""
    # Initialize session data if not exists
    if 'inquiry_data' not in request.session:
        request.session['inquiry_data'] = {}

    # Get current step (default to 1)
    current_step = int(request.GET.get('step', request.session.get('inquiry_step', 1)))

    if request.method == 'POST':
        # Handle WhatsApp quick inquiry
        if 'whatsapp_submit' in request.POST:
            company_name = request.POST.get('wa_company_name')
            contact_person = request.POST.get('wa_contact_person')
            contact_number = request.POST.get('wa_contact_number')
            product_category = request.POST.get('wa_product_category')
            product_name = request.POST.get('wa_product_name', '')
            additional_info = request.POST.get('wa_additional_info', '')

            # Save to database
            WhatsAppInquiry.objects.create(
                company_name=company_name,
                contact_person=contact_person,
                contact_number=contact_number,
                product_category=product_category,
                product_name=product_name,
                additional_info=additional_info
            )

            # Generate WhatsApp message
            wa_message = f"Hi, I'm {contact_person} from {company_name}. "
            wa_message += f"I'm interested in delivery services for {product_category}"
            if product_name:
                wa_message += f" ({product_name})"
            wa_message += f". Contact: {contact_number}"
            if additional_info:
                wa_message += f". Additional info: {additional_info}"

            # WhatsApp business number (replace with actual number)
            wa_number = "97466609347"  # Example Qatar number
            wa_link = f"https://wa.me/{wa_number}?text={quote(wa_message)}"

            return JsonResponse({'success': True, 'redirect_url': wa_link})

        # Store current step data in session
        step_data = {}
        for key, value in request.POST.items():
            if key != 'csrfmiddlewaretoken':
                step_data[key] = value

        request.session['inquiry_data'].update(step_data)
        request.session['inquiry_step'] = current_step
        request.session.modified = True

        # Get or create the DB inquiry record
        inquiry_id = request.session.get('inquiry_id')
        inquiry = None
        if inquiry_id:
            try:
                inquiry = PricingEnquiry.objects.get(id=inquiry_id)
            except PricingEnquiry.DoesNotExist:
                inquiry = None

        # Merge session data for DB save (covers fields from prior steps)
        all_data = request.session.get('inquiry_data', {})

        # Handle navigation
        if 'next_step' in request.POST:
            if current_step == 1:
                if inquiry is None:
                    # Create new partial record
                    inquiry = PricingEnquiry(is_complete=False)
                _save_step1_to_db(inquiry, all_data)
                request.session['inquiry_id'] = inquiry.id
                request.session.modified = True
            elif current_step == 2:
                if inquiry:
                    _save_step2_to_db(inquiry, all_data)

            next_step = current_step + 1
            return redirect(f'/3pl/inquiry/?step={next_step}')

        elif 'prev_step' in request.POST:
            # Save current step data to DB before going back
            if inquiry:
                if current_step == 2:
                    _save_step2_to_db(inquiry, all_data)
                elif current_step == 3:
                    _save_step3_to_db(inquiry, all_data)

            prev_step = max(1, current_step - 1)
            return redirect(f'/3pl/inquiry/?step={prev_step}')

        elif 'submit_final' in request.POST:
            if inquiry is None:
                # Fallback: create from all session data (shouldn't normally happen)
                inquiry = PricingEnquiry(is_complete=False)
                _save_step1_to_db(inquiry, all_data)
                _save_step2_to_db(inquiry, all_data)

            _save_step3_to_db(inquiry, all_data)
            inquiry.is_complete = True
            inquiry.save()

            # Clear session
            request.session.pop('inquiry_data', None)
            request.session.pop('inquiry_step', None)
            request.session.pop('inquiry_id', None)

            return redirect('webpages:inquiry_success')

    # Get saved data from session
    saved_data = request.session.get('inquiry_data', {})

    # SEO metadata for inquiry form
    meta = SEOMetadata.get_page_meta(
        title="Get Delivery Quote Qatar | 3PL Pricing Inquiry",  # 50 chars
        description=(
            "Request a customized delivery quote for your Qatar business. Fill out our 3PL pricing "
            "inquiry form. Fast response, competitive rates, no obligation."
        ),  # 152 chars
    )

    data = {
        'seo': meta,
        'current_step': current_step,
        'saved_data': saved_data,
        'total_steps': 3,
    }
    return render(request, 'webpages/delivery_pricing_inquiry.html', data)


def inquiry_success(request):
    """Success page shown after completing the 3PL pricing inquiry."""
    meta = SEOMetadata.get_page_meta(
        title="Inquiry Submitted | EzzyDelivery Qatar",
        description="Your 3PL pricing inquiry has been submitted successfully. Our team will reach out within 24 hours.",
    )
    return render(request, 'webpages/inquiry_success.html', {'seo': meta})


def about(request):
    meta = SEOMetadata.get_about_meta()
    brands = list(business_models.Business.objects.all())

    logger.debug(f'about page - found {len(brands)} brands')
    if len(brands) > 5:
        brands = random.sample(brands, 6)
    else:
        brands = random.sample(brands, len(brands))

    logger.debug(f'about page - sampled {len(brands)} brands')

    data = {
        'seo': meta,
        'brands': brands,
    }
    return render(request, 'webpages/about.html', data)


def services(request):
    meta = SEOMetadata.get_services_meta()
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/services.html', data)


def terms(request):
    meta = SEOMetadata.get_terms_meta()
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/terms.html', data)


def fulfillment(request):
    meta = SEOMetadata.get_fulfillment_meta()
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/fulfillment.html', data)


def qcommerce(request):
    meta = SEOMetadata.get_qcommerce_meta()
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/qcommerce.html', data)


def affiliate(request):
    meta = SEOMetadata.get_page_meta(
        title="Affiliate Program Qatar | Earn with EzzyDelivery",  # 50 chars
        description=(
            "Join EzzyDelivery's affiliate program in Qatar. Earn commissions by referring "
            "businesses to our delivery services. Simple signup, competitive payouts."
        ),  # 152 chars
    )
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/affiliate.html', data)


def fleets(request):
    meta = SEOMetadata.get_page_meta(
        title="Fleet Partnership Qatar | Join Our Delivery Network",  # 53 chars
        description=(
            "Partner with EzzyDelivery as a fleet operator in Qatar. Grow your business with "
            "consistent delivery jobs, flexible schedules & reliable payments."
        ),  # 150 chars
    )
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/fleets.html', data)


def contactus(request):
    meta = SEOMetadata.get_contact_meta()
    if request.method == 'POST':
        f = ContactForm(request.POST)
        if f.is_valid():
            full_name = f.cleaned_data['full_name']
            email = f.cleaned_data['email']
            mobile = f.cleaned_data['mobile']
            purpose = f.cleaned_data['purpose']
            message = f.cleaned_data['message']
            f.save()

            return redirect('/')
    else:
        f = ContactForm()

    return render(request, 'webpages/contactus.html', {'seo': meta, 'form': f})

def careers(request):
    meta = SEOMetadata.get_careers_meta()
    f = CareersForm(request.POST or None)
    if request.method == 'POST':
        f = CareersForm(request.POST)
        if f.is_valid():
            f.save()
            messages.success(request, "Successful Submission")
            return redirect('/')

    return render(request, 'webpages/careers.html', {'seo': meta, 'form': f})


def privacy(request):
    meta = SEOMetadata.get_privacy_meta()
    data = {
        'seo': meta,
    }
    return render(request, 'webpages/privacy.html', data)


def handler404(request, exception):
    return render(request, 'webpages/page_not_found.html', status=404)


def handler500(request):
    return render(request, 'webpages/server_error.html', status=500)


def testimonials(request):
    """
    Testimonials page with sample customer reviews
    """
    meta = SEOMetadata.get_page_meta(
        title="Customer Reviews Qatar | EzzyDelivery Testimonials",  # 51 chars
        description=(
            "Read reviews from 500+ satisfied businesses using EzzyDelivery in Qatar. "
            "Real testimonials about our same-day delivery, COD & fulfillment services."
        ),  # 153 chars
    )

    # Sample testimonials data
    testimonials_data = [
        {
            'name': 'Ahmed Al-Mansoori',
            'role': 'E-commerce Business Owner',
            'company': 'Qatar Fashion Store',
            'rating': 5,
            'text': 'Ezzy Delivery has transformed our logistics operations. Their 3PL service is reliable, fast, and professional. Our customers are happier than ever with the timely deliveries!',
            'date': '2 weeks ago'
        },
        {
            'name': 'Sarah Johnson',
            'role': 'Marketing Manager',
            'company': 'Tech Solutions Qatar',
            'rating': 5,
            'text': 'Outstanding service! The delivery tracking system is excellent and our clients always receive their orders on time. Highly recommended for any business in Qatar.',
            'date': '1 month ago'
        },
        {
            'name': 'Mohammed Hassan',
            'role': 'Restaurant Owner',
            'company': 'Doha Food Hub',
            'rating': 5,
            'text': 'Quick commerce delivery has been a game-changer for our restaurant. Orders reach customers within hours, keeping our food fresh and customers satisfied.',
            'date': '3 weeks ago'
        },
        {
            'name': 'Fatima Al-Kuwari',
            'role': 'Online Store Owner',
            'company': 'Beauty & Wellness Qatar',
            'rating': 5,
            'text': 'The fulfillment service is exceptional! They handle our inventory perfectly and the delivery process is seamless. Customer support is always responsive and helpful.',
            'date': '2 months ago'
        },
        {
            'name': 'John Smith',
            'role': 'Operations Director',
            'company': 'Electronics Plus',
            'rating': 5,
            'text': 'Professional, reliable, and cost-effective. Ezzy Delivery has helped us scale our business without worrying about logistics. Their team is wonderful to work with.',
            'date': '1 month ago'
        },
        {
            'name': 'Layla Abdullah',
            'role': 'Boutique Owner',
            'company': 'Luxury Fashion Qatar',
            'rating': 5,
            'text': 'I love how easy it is to integrate with their system. The drivers are courteous and always handle our products with care. Best delivery partner in Qatar!',
            'date': '3 weeks ago'
        }
    ]

    data = {
        'seo': meta,
        'testimonials': testimonials_data,
    }
    return render(request, 'webpages/testimonials.html', data)


def delivery_request(request):
    """
    Delivery request page for users/non-sellers
    """
    meta = SEOMetadata.get_page_meta(
        title="Request a Delivery Qatar | Book Pickup & Drop-off",  # 51 chars
        description=(
            "Request delivery service in Qatar. Easy online booking for pickup & delivery. "
            "Same-day available across Doha. Track your shipment in real-time."
        ),  # 148 chars
    )

    form = DeliveryRequestForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Your delivery request has been submitted successfully. We will contact you soon!")
            return redirect('webpages:index')

    data = {
        'seo': meta,
        'form': form,
    }
    return render(request, 'webpages/delivery_request.html', data)


def help_center(request):
    """Main help center page with overview of all help resources"""
    meta = SEOMetadata.get_page_meta(
        title="Help Center | EzzyDelivery Qatar Support & FAQs",  # 50 chars
        description=(
            "Get help with EzzyDelivery services. FAQs, guides & support for businesses and "
            "drivers. Find answers to delivery questions or contact our Qatar team."
        ),  # 152 chars
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/help_center.html', data)


def client_faq(request):
    """Client FAQ page"""
    meta = SEOMetadata.get_page_meta(
        title="Client FAQ | E-commerce Seller Questions Qatar",  # 49 chars
        description=(
            "FAQs for e-commerce sellers using EzzyDelivery in Qatar. Answers about pricing, "
            "COD, order management, integrations & delivery tracking for businesses."
        ),  # 154 chars
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/client_faq.html', data)


def client_faq_100(request):
    """100 Marketing FAQs - Comprehensive FAQ page"""
    meta = SEOMetadata.get_page_meta(
        title="100 Marketing FAQs | Complete Ezzy Delivery Guide",  # 50 chars
        description=(
            "All 100 verified FAQs for Ezzy Delivery Qatar across 13 sections: services, "
            "pricing, delivery speed, coverage, COD, packaging, returns & more."
        ),  # 150 chars
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/client_faq_100.html', data)


def driver_faq(request):
    """Driver FAQ page"""
    meta = SEOMetadata.get_page_meta(
        title="Driver FAQ | Courier Questions EzzyDelivery Qatar",  # 51 chars
        description=(
            "FAQs for delivery drivers working with EzzyDelivery Qatar. Answers about pay, "
            "schedules, requirements, app usage & COD handling for couriers."
        ),  # 147 chars
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/driver_faq.html', data)


def help_guides(request):
    """Help guides and onboarding kits overview"""
    meta = SEOMetadata.get_page_meta(
        title="Onboarding Guides | Get Started with EzzyDelivery",  # 51 chars
        description=(
            "Step-by-step guides to get started with EzzyDelivery Qatar. Onboarding resources "
            "for e-commerce businesses and delivery drivers. Start shipping today."
        ),  # 153 chars
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/help_guides.html', data)


def client_guide(request):
    """Client onboarding guide"""
    meta = SEOMetadata.get_page_meta(
        title="Business Onboarding Guide | Start with EzzyDelivery",  # 53 chars
        description=(
            "Complete setup guide for e-commerce sellers joining EzzyDelivery Qatar. Learn to "
            "connect your store, manage orders & configure delivery preferences."
        ),  # 154 chars
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/client_guide.html', data)


def driver_guide(request):
    """Driver onboarding guide"""
    meta = SEOMetadata.get_page_meta(
        title="Driver Onboarding Guide | Join EzzyDelivery Qatar",  # 51 chars
        description=(
            "Complete guide for new EzzyDelivery drivers in Qatar. Requirements, app setup, "
            "delivery workflow & earning tips. Start your courier career today."
        ),  # 150 chars
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/driver_guide.html', data)


# SEO Landing Pages Views (Based on Search Console Data)

def delivery_companies_qatar(request):
    """Landing page for 'delivery companies in qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_delivery_companies_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Best Delivery Companies in Qatar',
        'hero_subtitle': 'Compare Top Courier Services in Doha, Al Wakrah & Lusail',
    }
    return render(request, 'webpages/seo/delivery_companies_qatar.html', data)


def delivery_service_qatar(request):
    """Landing page for 'delivery service in qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_delivery_service_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Professional Delivery Service in Qatar',
        'hero_subtitle': 'Fast, Reliable & Affordable Courier Service Across All Qatar',
    }
    return render(request, 'webpages/seo/delivery_service_qatar.html', data)


def same_day_delivery_qatar(request):
    """Landing page for 'same day delivery qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_same_day_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Same Day Delivery Qatar',
        'hero_subtitle': 'Express Courier Service - Pickup & Delivery Within Hours',
    }
    return render(request, 'webpages/seo/same_day_delivery_qatar.html', data)


def cod_delivery_qatar(request):
    """Landing page for 'COD service qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_cod_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'COD Delivery Service Qatar',
        'hero_subtitle': 'Secure Cash on Delivery for Online Stores & E-commerce',
    }
    return render(request, 'webpages/seo/cod_delivery_qatar.html', data)


def ecommerce_delivery_qatar(request):
    """Landing page for 'ecommerce delivery qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_ecommerce_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'E-commerce Delivery Solutions Qatar',
        'hero_subtitle': 'Complete Shipping Solutions for Online Stores in Doha',
    }
    return render(request, 'webpages/seo/ecommerce_delivery_qatar.html', data)


def instagram_sellers_delivery(request):
    """Landing page for Instagram sellers in Qatar"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_instagram_sellers_delivery_meta()

    data = {
        'seo': meta,
        'page_title': 'Delivery Service for Instagram Sellers Qatar',
        'hero_subtitle': 'Perfect Shipping Solution for Social Commerce & Small Businesses',
    }
    return render(request, 'webpages/seo/instagram_sellers_delivery.html', data)


def express_delivery_qatar(request):
    """Landing page for 'express delivery qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_express_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Express Delivery Qatar',
        'hero_subtitle': 'Urgent Courier Service - 2 Hour Pickup Guarantee',
    }
    return render(request, 'webpages/seo/express_delivery_qatar.html', data)


def courier_service_qatar(request):
    """Landing page for 'courier service qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_courier_service_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Courier Service Qatar',
        'hero_subtitle': 'Professional Courier & Logistics Solutions Across Qatar',
    }
    return render(request, 'webpages/seo/courier_service_qatar.html', data)


def three_pl_qatar(request):
    """Landing page for '3pl qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_3pl_qatar_meta()

    data = {
        'seo': meta,
        'page_title': '3PL Services Qatar',
        'hero_subtitle': 'Third Party Logistics & Fulfillment Solutions for E-commerce',
    }
    return render(request, 'webpages/seo/3pl_qatar.html', data)


def last_mile_delivery_qatar(request):
    """Landing page for 'last mile delivery qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_last_mile_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Last Mile Delivery Qatar',
        'hero_subtitle': 'Efficient Final-Mile Logistics for E-commerce & Businesses',
    }
    return render(request, 'webpages/seo/last_mile_delivery_qatar.html', data)


def logistics_services_qatar(request):
    """Landing page for 'logistics services qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_logistics_services_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Logistics Services Qatar',
        'hero_subtitle': 'Complete Supply Chain & Delivery Solutions in Doha',
    }
    return render(request, 'webpages/seo/logistics_services_qatar.html', data)


def online_store_delivery_qatar(request):
    """Landing page for 'online store delivery qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_online_store_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Online Store Delivery Qatar',
        'hero_subtitle': 'Reliable Shipping Partner for Your Online Business',
    }
    return render(request, 'webpages/seo/online_store_delivery_qatar.html', data)


# =============================================================================
# NEW SEO LANDING PAGES - Arabic Keywords & Location-Specific
# =============================================================================

def delivery_doha(request):
    """Landing page for 'delivery doha' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_delivery_doha_meta()

    data = {
        'seo': meta,
        'page_title': 'Delivery Service Doha',
        'hero_subtitle': 'Fast Courier Across All Doha Districts - West Bay to Al Wakra Road',
    }
    return render(request, 'webpages/seo/delivery_doha.html', data)


def business_delivery_qatar(request):
    """Landing page for 'business delivery qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_business_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Business Delivery Qatar',
        'hero_subtitle': 'Professional B2B Courier & Corporate Logistics Solutions',
    }
    return render(request, 'webpages/seo/business_delivery_qatar.html', data)


def package_delivery_qatar(request):
    """Landing page for 'package delivery qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_package_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Package Delivery Qatar',
        'hero_subtitle': 'Secure Parcel Delivery Across All Qatar - Any Size, Any Weight',
    }
    return render(request, 'webpages/seo/package_delivery_qatar.html', data)


def shopify_delivery_qatar(request):
    """Landing page for 'shopify delivery qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_shopify_delivery_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Shopify Delivery Qatar',
        'hero_subtitle': 'Seamless Shopify Integration - Auto-Sync Orders in Minutes',
    }
    return render(request, 'webpages/seo/shopify_delivery_qatar.html', data)


def delivery_qatar_arabic(request):
    """Landing page for Arabic keywords 'توصيل قطر'"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_delivery_qatar_arabic_meta()

    data = {
        'seo': meta,
        'page_title': 'توصيل قطر | خدمة توصيل سريعة',
        'hero_subtitle': 'أفضل شركة توصيل في قطر - توصيل سريع في نفس اليوم',
        'is_rtl': True,
    }
    return render(request, 'webpages/seo/delivery_qatar_arabic.html', data)


def courier_doha_arabic(request):
    """Landing page for Arabic keywords 'شركة توصيل الدوحة'"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_courier_doha_arabic_meta()

    data = {
        'seo': meta,
        'page_title': 'شركة توصيل الدوحة',
        'hero_subtitle': 'كوريير قطر الموثوق لخدمات التوصيل السريع',
        'is_rtl': True,
    }
    return render(request, 'webpages/seo/courier_doha_arabic.html', data)


def food_delivery_partner_qatar(request):
    """Landing page for 'food delivery partner qatar' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_food_delivery_partner_qatar_meta()

    data = {
        'seo': meta,
        'page_title': 'Food Delivery Partner Qatar',
        'hero_subtitle': 'Reliable Restaurant Delivery Service - Temperature-Controlled Logistics',
    }
    return render(request, 'webpages/seo/food_delivery_partner_qatar.html', data)


def al_wakrah_delivery(request):
    """Landing page for 'delivery al wakrah' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_al_wakrah_delivery_meta()

    data = {
        'seo': meta,
        'page_title': 'Delivery Service Al Wakrah',
        'hero_subtitle': 'Fast Courier in Al Wakrah - Same Day Pickup & Delivery',
    }
    return render(request, 'webpages/seo/al_wakrah_delivery.html', data)


def lusail_delivery(request):
    """Landing page for 'delivery lusail' keyword"""
    from core.seo import SEOLandingPages
    meta = SEOLandingPages.get_lusail_delivery_meta()

    data = {
        'seo': meta,
        'page_title': 'Delivery Service Lusail City',
        'hero_subtitle': 'Premium Courier Service for Lusail - Fox Hills, Marina & More',
    }
    return render(request, 'webpages/seo/lusail_delivery.html', data)
