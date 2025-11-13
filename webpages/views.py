import random
from django.forms.fields import DateTimeField
from django.shortcuts import redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from webpages.forms import *
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
    form = PricingEnquiryForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Successful Submission")
            
            # Send email to admins
            subject = "New Delivery Inquiry"
            message = f"New delivery inquiry submitted by {form.cleaned_data['name']}."
            mail_admins(subject, message)
            
            # Send email to Gmail
            send_mail(
                subject,
                message,
                'zellaqatar@gmail.com',  # Replace with your Gmail address
                ['ezzydelivery@gmail.com'],  # Replace with recipient's email address
                fail_silently=False,
            )
            
            return redirect('/')

    data = {
        'form': form
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
