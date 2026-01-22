"""
AI Agent Views

API endpoints for the AI Operations Agent.
"""

import logging
import json

from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes

from ai_agent.serializers import (
    ChatRequestSerializer,
    ParseAddressRequestSerializer,
    VerifyOrderRequestSerializer,
    CODRiskRequestSerializer,
    EstimateDeliveryRequestSerializer,
    SuggestDriverRequestSerializer,
    ConversationSerializer,
    WhatsAppWebhookSerializer,
)
from ai_agent.services.agent_service import get_agent_service

logger = logging.getLogger(__name__)


class ChatAPIView(APIView):
    """
    Main chat endpoint for AI agent interactions.

    POST /api/ai-agent/chat/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if AI agent is enabled
        if not getattr(settings, 'AI_AGENT_ENABLED', False):
            return Response(
                {'success': False, 'error': 'AI Agent is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        agent_service = get_agent_service()

        # Get or create conversation
        conversation = agent_service.get_or_create_conversation(
            conversation_id=str(serializer.validated_data.get('conversation_id', '')),
            channel=serializer.validated_data.get('channel', 'api'),
            user=request.user,
            business=getattr(request.user, 'business', None),
        )

        # Process message
        result = agent_service.process_message(
            message=serializer.validated_data['message'],
            conversation=conversation,
            user=request.user,
            tools_enabled=True
        )

        if result.get('success'):
            return Response(result)
        else:
            return Response(
                result,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ChatStreamAPIView(APIView):
    """
    Streaming chat endpoint for real-time responses.

    POST /api/ai-agent/chat/stream/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not getattr(settings, 'AI_AGENT_ENABLED', False):
            return Response(
                {'success': False, 'error': 'AI Agent is disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        agent_service = get_agent_service()

        conversation = agent_service.get_or_create_conversation(
            conversation_id=str(serializer.validated_data.get('conversation_id', '')),
            channel=serializer.validated_data.get('channel', 'api'),
            user=request.user,
            business=getattr(request.user, 'business', None),
        )

        def generate():
            for chunk in agent_service.process_message_stream(
                message=serializer.validated_data['message'],
                conversation=conversation,
                user=request.user,
                tools_enabled=True
            ):
                yield f"data: {json.dumps(chunk)}\n\n"

        response = StreamingHttpResponse(
            generate(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        return response


class ConversationAPIView(APIView):
    """
    Get conversation history.

    GET /api/ai-agent/conversations/<id>/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        agent_service = get_agent_service()
        result = agent_service.get_conversation_history(conversation_id)

        if result.get('success'):
            return Response(result)
        else:
            return Response(
                result,
                status=status.HTTP_404_NOT_FOUND
            )

    def delete(self, request, conversation_id):
        """Close/archive a conversation."""
        agent_service = get_agent_service()
        success = agent_service.close_conversation(conversation_id)

        if success:
            return Response({'success': True, 'message': 'Conversation closed'})
        else:
            return Response(
                {'success': False, 'error': 'Conversation not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class ParseAddressAPIView(APIView):
    """
    Direct address parsing endpoint.

    POST /api/ai-agent/tools/parse-address/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ParseAddressRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        agent_service = get_agent_service()
        result = agent_service.execute_single_tool(
            tool_name='parse_address',
            params={'address': serializer.validated_data['address']},
            user=request.user
        )

        return Response(result)


class VerifyOrderAPIView(APIView):
    """
    Direct order verification endpoint.

    POST /api/ai-agent/tools/verify-order/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyOrderRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        agent_service = get_agent_service()
        result = agent_service.execute_single_tool(
            tool_name='verify_order',
            params={'order_number': serializer.validated_data['order_number']},
            user=request.user
        )

        return Response(result)


class CODRiskAPIView(APIView):
    """
    COD risk assessment endpoint.

    POST /api/ai-agent/tools/cod-risk/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CODRiskRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        agent_service = get_agent_service()
        params = {
            'phone_number': serializer.validated_data['phone_number']
        }
        if serializer.validated_data.get('order_amount'):
            params['order_amount'] = float(serializer.validated_data['order_amount'])
        if serializer.validated_data.get('zone_number'):
            params['zone_number'] = serializer.validated_data['zone_number']

        result = agent_service.execute_single_tool(
            tool_name='assess_cod_risk',
            params=params,
            user=request.user
        )

        return Response(result)


class EstimateDeliveryAPIView(APIView):
    """
    Delivery time estimation endpoint.

    POST /api/ai-agent/tools/estimate-delivery/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EstimateDeliveryRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        agent_service = get_agent_service()
        params = {}
        if serializer.validated_data.get('order_number'):
            params['order_number'] = serializer.validated_data['order_number']
        if serializer.validated_data.get('pickup_zone'):
            params['pickup_zone'] = serializer.validated_data['pickup_zone']
        if serializer.validated_data.get('delivery_zone'):
            params['delivery_zone'] = serializer.validated_data['delivery_zone']

        result = agent_service.execute_single_tool(
            tool_name='estimate_delivery',
            params=params,
            user=request.user
        )

        return Response(result)


class SuggestDriverAPIView(APIView):
    """
    Driver suggestion endpoint.

    POST /api/ai-agent/tools/suggest-driver/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SuggestDriverRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        agent_service = get_agent_service()
        params = {
            'limit': serializer.validated_data.get('limit', 5)
        }
        if serializer.validated_data.get('delivery_zone'):
            params['delivery_zone'] = serializer.validated_data['delivery_zone']
        if serializer.validated_data.get('order_number'):
            params['order_number'] = serializer.validated_data['order_number']
        if serializer.validated_data.get('vehicle_required'):
            params['vehicle_required'] = serializer.validated_data['vehicle_required']

        result = agent_service.execute_single_tool(
            tool_name='suggest_driver',
            params=params,
            user=request.user
        )

        return Response(result)


class WhatsAppWebhookAPIView(APIView):
    """
    WhatsApp webhook for messages from n8n.

    POST /api/ai-agent/webhooks/whatsapp/
    """
    permission_classes = [AllowAny]  # Authenticated via webhook secret

    def post(self, request):
        # Verify webhook secret (should be configured in n8n)
        webhook_secret = request.headers.get('X-Webhook-Secret', '')
        expected_secret = getattr(settings, 'AI_AGENT_WEBHOOK_SECRET', '')

        if expected_secret and webhook_secret != expected_secret:
            logger.warning("Invalid webhook secret")
            return Response(
                {'error': 'Unauthorized'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not getattr(settings, 'AI_AGENT_WHATSAPP_ENABLED', False):
            return Response(
                {'error': 'WhatsApp integration disabled'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        serializer = WhatsAppWebhookSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        agent_service = get_agent_service()

        # Get or create conversation by phone number
        conversation = agent_service.get_or_create_conversation(
            channel='whatsapp',
            phone_number=serializer.validated_data['phone'],
        )

        # Process message
        result = agent_service.process_message(
            message=serializer.validated_data['message'],
            conversation=conversation,
            tools_enabled=True
        )

        # Return response for n8n to send back via WhatsApp
        return Response({
            'success': result.get('success', False),
            'reply': result.get('response', ''),
            'phone': serializer.validated_data['phone'],
            'conversation_id': str(conversation.conversation_id),
        })


class AgentStatusAPIView(APIView):
    """
    Get AI agent status and usage statistics.

    GET /api/ai-agent/status/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from ai_agent.services.claude_service import get_claude_service
        from ai_agent.models import UsageLog, Conversation
        from django.db.models import Sum, Count
        from django.utils import timezone
        from datetime import timedelta

        claude_service = get_claude_service()

        # Check availability
        available, msg = claude_service.is_available()

        # Get budget usage
        budget_usage = claude_service.budget_tracker.get_usage()

        # Get usage stats for today
        today = timezone.now().date()
        today_stats = UsageLog.objects.filter(
            created_at__date=today
        ).aggregate(
            total_calls=Count('id'),
            total_tokens_input=Sum('tokens_input'),
            total_tokens_output=Sum('tokens_output'),
            total_cost=Sum('estimated_cost'),
        )

        # Get conversation count
        active_conversations = Conversation.objects.filter(
            status='active',
            last_activity__gte=timezone.now() - timedelta(hours=24)
        ).count()

        return Response({
            'available': available,
            'status_message': msg,
            'model': claude_service.model,
            'budget': budget_usage,
            'today_usage': {
                'api_calls': today_stats['total_calls'] or 0,
                'tokens_input': today_stats['total_tokens_input'] or 0,
                'tokens_output': today_stats['total_tokens_output'] or 0,
                'estimated_cost': float(today_stats['total_cost'] or 0),
            },
            'active_conversations': active_conversations,
        })
