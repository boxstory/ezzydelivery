from django.urls import path

from . import wa_dashboard_view

app_name = 'whatsapp_dashboard'

urlpatterns = [
    path('', wa_dashboard_view.wa_dashboard, name='wa_dashboard'),
]
