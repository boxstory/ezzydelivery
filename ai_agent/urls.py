"""
AI Agent URL Configuration
"""

from django.urls import path
from ai_agent import views

app_name = 'ai_agent'

urlpatterns = [
    # Main chat endpoints
    path('chat/', views.ChatAPIView.as_view(), name='chat'),
    path('chat/stream/', views.ChatStreamAPIView.as_view(), name='chat_stream'),

    # Conversation management
    path('conversations/<uuid:conversation_id>/',
         views.ConversationAPIView.as_view(), name='conversation'),

    # Direct tool endpoints
    path('tools/parse-address/', views.ParseAddressAPIView.as_view(), name='parse_address'),
    path('tools/verify-order/', views.VerifyOrderAPIView.as_view(), name='verify_order'),
    path('tools/cod-risk/', views.CODRiskAPIView.as_view(), name='cod_risk'),
    path('tools/estimate-delivery/', views.EstimateDeliveryAPIView.as_view(), name='estimate_delivery'),
    path('tools/suggest-driver/', views.SuggestDriverAPIView.as_view(), name='suggest_driver'),

    # Webhooks
    path('webhooks/whatsapp/', views.WhatsAppWebhookAPIView.as_view(), name='whatsapp_webhook'),

    # Status
    path('status/', views.AgentStatusAPIView.as_view(), name='status'),
]
