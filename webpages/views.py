import random
from urllib.parse import quote
from django.forms.fields import DateTimeField
from django.shortcuts import redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from webpages.forms import *
from webpages.models import WhatsAppInquiry, PricingEnquiry
from django.core.mail import mail_admins, send_mail
from client import models as business_models
from fleet import models as fleet_models
from core.seo import SEOMetadata
# Create your views here.


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

def delivery_inquiry(request):
    """Multi-step pricing inquiry form"""
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

        # Handle navigation
        if 'next_step' in request.POST:
            next_step = current_step + 1
            return redirect(f'/3pl/inquiry/?step={next_step}')

        elif 'prev_step' in request.POST:
            prev_step = max(1, current_step - 1)
            return redirect(f'/3pl/inquiry/?step={prev_step}')

        elif 'submit_final' in request.POST:
            # Save complete inquiry
            inquiry_data = request.session.get('inquiry_data', {})

            # Create pricing enquiry instance
            pricing_enquiry = PricingEnquiry.objects.create(
                full_name=inquiry_data.get('full_name', ''),
                business_name=inquiry_data.get('business_name', ''),
                business_contact_number=inquiry_data.get('business_contact_number', ''),
                operation_team_contact_number=inquiry_data.get('operation_team_contact_number', ''),
                website_url=inquiry_data.get('website_url', ''),
                social_profile=inquiry_data.get('social_profile', ''),
                product_category=inquiry_data.get('product_category', ''),
                is_personalized_product=inquiry_data.get('is_personalized_product', 'False') == 'True',
                is_registered_company_in_qatar=inquiry_data.get('is_registered_company_in_qatar', 'False') == 'True',
                is_located_in_qatar=inquiry_data.get('is_located_in_qatar', 'False') == 'True',
                is_team_available_in_qatar=inquiry_data.get('is_team_available_in_qatar', 'False') == 'True',
                is_required_COD_service=inquiry_data.get('is_required_COD_service', 'False') == 'True',
                is_required_fulfillment_service_for_operate_from_outside_qatar=inquiry_data.get('is_required_fulfillment_service_for_operate_from_outside_qatar', 'False') == 'True',
                is_required_fulfillment_service_for_make_hub_in_doha=inquiry_data.get('is_required_fulfillment_service_for_make_hub_in_doha', 'False') == 'True',
                avarage_number_of_order_last_week=inquiry_data.get('avarage_number_of_order_last_week', ''),
                avarage_number_of_order_done_last_month=inquiry_data.get('avarage_number_of_order_done_last_month', ''),
                avarage_number_of_order_expect_next_month=inquiry_data.get('avarage_number_of_order_expect_next_month', ''),
                orders_expected_in_next_3_months_milestone=inquiry_data.get('orders_expected_in_next_3_months_milestone', ''),
                speed_delivery_offer_to_customers=inquiry_data.get('speed_delivery_offer_to_customers', ''),
                is_frequent_same_day_pick_and_delivery_required=inquiry_data.get('is_frequent_same_day_pick_and_delivery_required', 'False') == 'True',
                preferred_delivery_time_window=inquiry_data.get('preferred_delivery_time_window', ''),
                typical_package_size=inquiry_data.get('typical_package_size', ''),
                is_special_handling_required=inquiry_data.get('is_special_handling_required', 'False') == 'True',
                type_of_pickup_location=inquiry_data.get('type_of_pickup_location', ''),
                pickup_Location_area_name=inquiry_data.get('pickup_Location_area_name', ''),
                pickup_location_time_slab=inquiry_data.get('pickup_location_time_slab', ''),
                number_of_pickup_times_in_day=inquiry_data.get('number_of_pickup_times_in_day', '1'),
            )

            # Clear session
            request.session.pop('inquiry_data', None)
            request.session.pop('inquiry_step', None)

            messages.success(request, "Thank you! Your inquiry has been submitted successfully. Our team will contact you soon.")
            return redirect('/')

    # Get saved data from session
    saved_data = request.session.get('inquiry_data', {})

    data = {
        'current_step': current_step,
        'saved_data': saved_data,
        'total_steps': 3,
    }
    return render(request, 'webpages/delivery_pricing_inquiry.html', data)


def about(request):
    meta = SEOMetadata.get_about_meta()
    brands = list(business_models.Business.objects.all())
    # brands = list(fleet_models.Driver.objects.all())

    print(len(brands))
    if len(brands) > 5:
        brands = random.sample(brands, 6)
    else:
        brands = random.sample(brands, len(brands))

    print('brands', brands)

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


def test(request):
    data = {

    }
    return render(request, 'webpages/test.html', data)


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
    data = {

    }
    return render(request, 'webpages/affiliate.html', data)


def fleets(request):
    data = {

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
    meta = SEOMetadata.get_default_meta(
        title="Customer Testimonials - Ezzy Delivery",
        description="Read what our customers say about Ezzy Delivery's reliable and fast delivery services in Qatar.",
        keywords="testimonials, reviews, customer feedback, delivery service Qatar"
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
    meta = SEOMetadata.get_default_meta(
        title="Request Delivery - Ezzy Delivery",
        description="Request a delivery service in Qatar. Choose from Pick and Delivery or Store Pickup and Delivery options.",
        keywords="delivery request, Qatar delivery, pick and delivery, store pickup"
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
        title="Help Center - Ezzy Delivery Qatar",
        description="Get help with Ezzy Delivery services. Find FAQs, guides, and support for clients and drivers.",
        keywords="help center, support, FAQs, guides, delivery help Qatar"
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/help_center.html', data)


def client_faq(request):
    """Client FAQ page"""
    meta = SEOMetadata.get_page_meta(
        title="Client FAQ - Ezzy Delivery Qatar",
        description="Frequently asked questions for e-commerce sellers and online stores using Ezzy Delivery services in Qatar.",
        keywords="client FAQ, seller questions, ecommerce delivery Qatar"
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/client_faq.html', data)


def driver_faq(request):
    """Driver FAQ page"""
    meta = SEOMetadata.get_page_meta(
        title="Driver FAQ - Ezzy Delivery Qatar",
        description="Frequently asked questions for delivery drivers and couriers working with Ezzy Delivery in Qatar.",
        keywords="driver FAQ, courier questions, delivery driver Qatar"
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/driver_faq.html', data)


def help_guides(request):
    """Help guides and onboarding kits overview"""
    meta = SEOMetadata.get_page_meta(
        title="Guides & Resources - Ezzy Delivery Qatar",
        description="Onboarding guides and resources for clients and drivers. Learn how to get started with Ezzy Delivery.",
        keywords="onboarding guides, client kit, driver kit, delivery resources Qatar"
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/help_guides.html', data)


def client_guide(request):
    """Client onboarding guide"""
    meta = SEOMetadata.get_page_meta(
        title="Client Onboarding Guide - Ezzy Delivery Qatar",
        description="Complete onboarding guide for eCommerce sellers and online stores. Learn how to get started with Ezzy Delivery services.",
        keywords="client onboarding, seller guide, ecommerce setup Qatar"
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/client_guide.html', data)


def driver_guide(request):
    """Driver onboarding guide"""
    meta = SEOMetadata.get_page_meta(
        title="Driver Onboarding Guide - Ezzy Delivery Qatar",
        description="Complete onboarding guide for delivery drivers and couriers. Learn about requirements, workflow, and getting started.",
        keywords="driver onboarding, courier guide, delivery driver Qatar"
    )

    data = {
        'seo': meta,
    }
    return render(request, 'webpages/driver_guide.html', data)
