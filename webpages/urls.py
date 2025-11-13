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
    path('services/', webpages_views.services, name='services'),
    path('join_driver/', core_views.join_driver, name='join_driver'),
    path('privacy/', webpages_views.privacy, name='privacy'),
    path('careers/', webpages_views.careers, name='careers'),

    path('fulfillment/', webpages_views.fulfillment, name='fulfillment'),
    path('qcommerce/', webpages_views.qcommerce, name='qcommerce'),
    path('3pl/pricing/', webpages_views.delivery_pricing, name='delivery_pricing'),
    path('3pl/inquiry/', webpages_views.delivery_inquiry, name='delivery_inquiry'),
    path('affiliate/', webpages_views.affiliate, name='affiliate_marketing'),



    path('terms/', webpages_views.terms, name='terms'),
    path('testimonials/', webpages_views.testimonials, name='testimonials'),
    path('test/', webpages_views.test, name='test'),
    path('500/', TemplateView.as_view(template_name='page_not_found.html')),

]
