from django.urls import path
from . import wa_chats_actions, wa_chats_view

app_name = 'whatsapp_chats'

urlpatterns = [
    path('',         wa_chats_view.wa_chats,         name='wa_chats'),
    path('send/',    wa_chats_view.wa_chats_send,    name='wa_chats_send'),
    path('read/',    wa_chats_view.wa_chats_mark_read, name='wa_chats_mark_read'),
    path('resync/',  wa_chats_view.wa_chats_resync,  name='wa_chats_resync'),
    path('avatar/', wa_chats_view.wa_chats_avatar, name='wa_chats_avatar'),
    path('link-lead/', wa_chats_view.wa_chats_link_lead, name='wa_chats_link_lead'),
    path('set-labels/', wa_chats_view.wa_chats_set_labels, name='wa_chats_set_labels'),
    path('create-label/', wa_chats_view.wa_chats_create_label, name='wa_chats_create_label'),
    path('save-doc/', wa_chats_view.wa_chats_save_doc, name='wa_chats_save_doc'),
    path('media/<int:msg_id>/', wa_chats_view.wa_chats_media, name='wa_chats_media'),
    path('media-live/', wa_chats_view.wa_chats_media_live, name='wa_chats_media_live'),
    path('send-media/', wa_chats_actions.wa_chats_send_media, name='wa_chats_send_media'),
    path('react/', wa_chats_actions.wa_chats_react, name='wa_chats_react'),
    path('forward/', wa_chats_actions.wa_chats_forward, name='wa_chats_forward'),
    path('edit/', wa_chats_actions.wa_chats_edit, name='wa_chats_edit'),
    path('delete/', wa_chats_actions.wa_chats_delete, name='wa_chats_delete'),
    path('check-number/', wa_chats_actions.wa_chats_check_number, name='wa_chats_check_number'),
    path('chat-action/', wa_chats_actions.wa_chats_chat_action, name='wa_chats_chat_action'),
]
