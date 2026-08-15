from django.urls import path
from django.views.generic.base import RedirectView
from core import views as core_views
from core import password_reset_views
from core import views_password_warning
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views
from business import views as business_views


app_name = 'core'
urlpatterns = [
    # Static profile paths MUST come before the <str:user_number> wildcard
    path('profile/', core_views.profile_view, name='profile_view'),
    path('profile/add/', core_views.profile_add, name='profile_add'),
    path('profile/photo/update/', core_views.profile_picture_update, name='profile_picture_update'),
    path('profile/complete/', core_views.profile_complete_update, name='profile_complete_update'),
    path('api/check-whatsapp/', core_views.check_whatsapp_availability, name='check_whatsapp_availability'),
    path('api/check-phone/', core_views.check_phone_availability, name='check_phone_availability'),
    # Wildcard profile paths
    path('profile/<str:user_number>/', core_views.profile, name='profile'),
    path('profile/<str:user_number>/review/', core_views.profile_completion_test,
         name='profile_completion_test'),
    path('profile/<str:user_number>/update/',
         core_views.profile_update_redirect, name='profile_update'),

    path('dashboard/', core_views.main_dashboard, name='main_dashboard'),

    path('join_us/',
         core_views.join_us, name='join_us'),
    path('join_us/team/',
         core_views.join_us_team, name='join_us_team'),
    path('join_us/business/',
         core_views.join_business, name='join_business'),
    path('join_us/driver/',
         core_views.join_driver, name='join_driver'),
    path('join_us/driver/start/',
         core_views.join_driver_start, name='join_driver_start'),
    # Arabic hreflang pair of the driver landing page
    path('ar/join_us/driver/start/',
         core_views.join_driver_start_ar, name='join_driver_start_ar'),
    # Short URL: /driver/start/ -> /join_us/driver/start/
    path('driver/start/',
         RedirectView.as_view(pattern_name='core:join_driver_start', permanent=True),
         name='join_driver_start_short'),
    path('join_us/business/update/',
         core_views.business_profile_update, name='business_profile_update'),
    path('join_us/driver/update/',
         core_views.update_driver, name='update_driver'),

    path('driverjobform/', core_views.driverjobform, name='driverjobform'),

    # NEW VERIFICATION WORKFLOW URLs
    path('business/register/', core_views.business_register, name='business_register'),
    path('driver/register/', core_views.driver_register, name='driver_register'),

    # WhatsApp Password Reset URLs
    path('password/reset/request/', password_reset_views.password_reset_request, name='password_reset_request'),
    path('password/reset/verify/', password_reset_views.password_reset_verify, name='password_reset_verify'),
    path('password/reset/confirm/', password_reset_views.password_reset_confirm, name='password_reset_confirm'),

    # Weak-password nudge for existing accounts
    path('password/weak/', views_password_warning.weak_password_warning, name='weak_password_warning'),

    # Temporary staff setup (remove after use)
    path('make-staff/', core_views.make_staff, name='make_staff'),

    # Google One Tap sign-in callback
    path('accounts/google/one-tap/', core_views.google_one_tap_callback, name='google_one_tap'),
]
