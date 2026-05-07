from django.urls import path

from . import waha_views

app_name = 'whatsapp'

urlpatterns = [
    path('webhook/',                          waha_views.waha_webhook,            name='webhook'),
    path('messages/',                         waha_views.waha_messages_list,      name='messages_list'),
    path('messages/<int:message_id>/processed/', waha_views.waha_message_processed, name='message_processed'),
    path('send/',                             waha_views.waha_send,               name='send'),
]
