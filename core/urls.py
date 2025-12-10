from django.urls import path
from core import views as core_views
from core import password_reset_views
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views
from client import views as business_views


app_name = 'core'
urlpatterns = [
    path('profile/', core_views.profile_view, name='profile_view'),
    path('profile/<int:pk>/', core_views.profile, name='profile'),
    path('profile/<int:pk>/review/', core_views.profile_completion_test,
         name='profile_completion_test'),
    path('profile/<int:pk>/update/',
         core_views.profile_update_redirect, name='profile_update'),
    path('profile/add/',
         core_views.profile_add, name='profile_add'),
     path('profile/photo/update/',
         core_views.profile_picture_update, name='profile_picture_update'),

    path('dashboard/', core_views.main_dashboard, name='main_dashboard'),

    path('join_us/',
         core_views.join_us, name='join_us'),
    path('join_us/business/',
         core_views.join_business, name='join_business'),
    path('join_us/driver/',
         core_views.join_driver, name='join_driver'),
    path('join_us/business/update/',
         core_views.business_profile_update, name='business_profile_update'),
    path('join_us/driver/update/',
         core_views.update_driver, name='update_driver'),

    path('driverjobform/', core_views.driverjobform, name='driverjobform'),

    # NEW VERIFICATION WORKFLOW URLs
    path('profile/complete/', core_views.profile_complete_update, name='profile_complete_update'),
    path('business/register/', core_views.business_register, name='business_register'),
    path('driver/register/', core_views.driver_register, name='driver_register'),

    # WhatsApp Password Reset URLs
    path('password/reset/request/', password_reset_views.password_reset_request, name='password_reset_request'),
    path('password/reset/verify/', password_reset_views.password_reset_verify, name='password_reset_verify'),
    path('password/reset/confirm/', password_reset_views.password_reset_confirm, name='password_reset_confirm'),

    # Temporary staff setup (remove after use)
    path('make-staff/', core_views.make_staff, name='make_staff'),
]
