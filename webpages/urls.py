from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views
from core import views as core_views
from django.views.generic import TemplateView



app_name = 'webpages'
urlpatterns = [
    path('', webpages_views.index, name='index'),
    path('about/', webpages_views.about, name='about'),
    path('contactus/', webpages_views.contactus, name='contactus'),
    path('llm/', webpages_views.llm_knowledge_panel, name='llm_knowledge_panel'),
    path('services/', webpages_views.services, name='services'),
    path('join_driver/', core_views.join_driver, name='join_driver'),
    path('privacy/', webpages_views.privacy, name='privacy'),
    path('careers/', webpages_views.careers, name='careers'),

    path('fulfillment/', webpages_views.fulfillment, name='fulfillment'),
    path('qcommerce/', webpages_views.qcommerce, name='qcommerce'),
    path('3pl/pricing/', webpages_views.delivery_pricing, name='delivery_pricing'),
    path('3pl/inquiry/', webpages_views.delivery_inquiry, name='delivery_inquiry'),
    path('3pl/inquiry/success/', webpages_views.inquiry_success, name='inquiry_success'),
    path('affiliate/', webpages_views.affiliate, name='affiliate_marketing'),



    path('terms/', webpages_views.terms, name='terms'),
    path('testimonials/', webpages_views.testimonials, name='testimonials'),
    path('delivery-request/', webpages_views.delivery_request, name='delivery_request'),

    # Help Center
    path('help/', webpages_views.help_center, name='help_center'),
    path('help/client-faq/', webpages_views.client_faq, name='client_faq'),
    path('help/100-faqs/', webpages_views.client_faq_100, name='client_faq_100'),
    path('help/driver-faq/', webpages_views.driver_faq, name='driver_faq'),
    path('help/guides/', webpages_views.help_guides, name='help_guides'),
    path('help/guides/client/', webpages_views.client_guide, name='client_guide'),
    path('help/guides/driver/', webpages_views.driver_guide, name='driver_guide')
,

    # SEO Landing Pages (Based on Search Console Analysis)
    path('delivery-companies-in-qatar/', webpages_views.delivery_companies_qatar, name='delivery_companies_qatar'),
    path('delivery-service-in-qatar/', webpages_views.delivery_service_qatar, name='delivery_service_qatar'),
    path('same-day-delivery-qatar/', webpages_views.same_day_delivery_qatar, name='same_day_delivery_qatar'),
    path('cod-delivery-service-qatar/', webpages_views.cod_delivery_qatar, name='cod_delivery_qatar'),
    path('ecommerce-delivery-qatar/', webpages_views.ecommerce_delivery_qatar, name='ecommerce_delivery_qatar'),
    path('instagram-sellers-delivery-qatar/', webpages_views.instagram_sellers_delivery, name='instagram_sellers_delivery'),

    # Additional SEO Landing Pages (Expanded Keywords)
    path('express-delivery-qatar/', webpages_views.express_delivery_qatar, name='express_delivery_qatar'),
    path('courier-service-qatar/', webpages_views.courier_service_qatar, name='courier_service_qatar'),
    path('3pl-qatar/', webpages_views.three_pl_qatar, name='three_pl_qatar'),
    path('last-mile-delivery-qatar/', webpages_views.last_mile_delivery_qatar, name='last_mile_delivery_qatar'),
    path('logistics-services-qatar/', webpages_views.logistics_services_qatar, name='logistics_services_qatar'),
    path('online-store-delivery-qatar/', webpages_views.online_store_delivery_qatar, name='online_store_delivery_qatar'),

    # New SEO Landing Pages - Location Specific
    path('delivery-doha/', webpages_views.delivery_doha, name='delivery_doha'),
    path('al-wakrah-delivery/', webpages_views.al_wakrah_delivery, name='al_wakrah_delivery'),
    path('lusail-delivery/', webpages_views.lusail_delivery, name='lusail_delivery'),

    # New SEO Landing Pages - Service Specific
    path('business-delivery-qatar/', webpages_views.business_delivery_qatar, name='business_delivery_qatar'),
    path('package-delivery-qatar/', webpages_views.package_delivery_qatar, name='package_delivery_qatar'),
    path('shopify-delivery-qatar/', webpages_views.shopify_delivery_qatar, name='shopify_delivery_qatar'),
    path('food-delivery-partner-qatar/', webpages_views.food_delivery_partner_qatar, name='food_delivery_partner_qatar'),

    # New SEO Landing Pages - Arabic Keywords
    path('توصيل-قطر/', webpages_views.delivery_qatar_arabic, name='delivery_qatar_arabic'),
    path('شركة-توصيل-الدوحة/', webpages_views.courier_doha_arabic, name='courier_doha_arabic'),

    path('500/', TemplateView.as_view(template_name='page_not_found.html')),

]
