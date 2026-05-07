from django.urls import path
from . import wa_chats_view

app_name = 'whatsapp_chats'

urlpatterns = [
    path('',         wa_chats_view.wa_chats,         name='wa_chats'),
    path('send/',    wa_chats_view.wa_chats_send,    name='wa_chats_send'),
    path('resync/',  wa_chats_view.wa_chats_resync,  name='wa_chats_resync'),
]
