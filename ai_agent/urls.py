"""
AI Agent URL Configuration
"""

from django.urls import path
from ai_agent import views
from ai_agent import aiagent_api

app_name = 'ai_agent'

urlpatterns = [
    # Main chat endpoints
    path('chat/', views.ChatAPIView.as_view(), name='chat'),
    path('chat/stream/', views.ChatStreamAPIView.as_view(), name='chat_stream'),

    # ── External conversation API (service-token auth, session-keyed; n8n etc.) ──
    path('aiagent/chat/', aiagent_api.AiAgentChatView.as_view(), name='aiagent_chat'),
    path('aiagent/conversations/<str:session_id>/',
         aiagent_api.AiAgentConversationView.as_view(), name='aiagent_conversation'),
    path('aiagent/conversations/<str:session_id>/close/',
         aiagent_api.AiAgentCloseConversationView.as_view(), name='aiagent_conversation_close'),
    path('aiagent/health/', aiagent_api.AiAgentHealthView.as_view(), name='aiagent_health'),

    # Conversation management
    path('conversations/<uuid:conversation_id>/',
         views.ConversationAPIView.as_view(), name='conversation'),

    # Direct tool endpoints
    path('tools/parse-address/', views.ParseAddressAPIView.as_view(), name='parse_address'),
    path('tools/extract-order/', views.ExtractOrderAPIView.as_view(), name='extract_order'),

    # Webhooks
    path('webhooks/whatsapp/', views.WhatsAppWebhookAPIView.as_view(), name='whatsapp_webhook'),

    # Status
    path('status/', views.AgentStatusAPIView.as_view(), name='status'),
]
