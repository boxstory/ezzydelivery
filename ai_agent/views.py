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

from ai_agent.tools.base import get_user_role


def _resolve_user_business(user):
    """Resolve the Business instance for a user (owner or team member)."""
    if not user or not user.is_authenticated:
        return None
    try:
        role = get_user_role(user)
        if role == 'business':
            # Direct business owner
            biz = user.user_business.first()
            if biz:
                return biz
            # Team member
            from business.models import BusinessTeamProfile
            team = BusinessTeamProfile.objects.filter(
                user=user, team_status='active'
            ).select_related('business').first()
            if team:
                return team.business
    except Exception:
        pass
    return None


from ai_agent.serializers import (
    ChatRequestSerializer,
    ParseAddressRequestSerializer,
    ConversationSerializer,
    WhatsAppWebhookSerializer,
    ExtractOrderRequestSerializer,
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
            business=_resolve_user_business(request.user),
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
            business=_resolve_user_business(request.user),
        )

        def generate():
            for chunk in agent_service.process_message_stream(
                message=serializer.validated_data['message'],
                conversation=conversation,
                user=request.user,
                tools_enabled=True
            ):
                yield f"data: {json.dumps(chunk, default=str)}\n\n"

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
        result = agent_service.get_conversation_history(conversation_id, user=request.user)

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



class WhatsAppWebhookAPIView(APIView):
    """
    WhatsApp webhook for messages from n8n.

    POST /api/ai-agent/webhooks/whatsapp/
    """
    permission_classes = [AllowAny]  # Authenticated via webhook secret

    def post(self, request):
        # Verify webhook secret (configured in n8n). Fail CLOSED: if no secret is
        # configured server-side, reject — an unset secret must never mean "open",
        # since this endpoint drives the LLM agent and its tools.
        import hmac
        webhook_secret = request.headers.get('X-Webhook-Secret', '')
        expected_secret = getattr(settings, 'AI_AGENT_WEBHOOK_SECRET', '')

        if not expected_secret or not hmac.compare_digest(webhook_secret, expected_secret):
            logger.warning("Invalid or missing AI agent webhook secret")
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


class ExtractOrderAPIView(APIView):
    """
    Extract order fields from unstructured text using AI.

    POST /api/ai-agent/tools/extract-order/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ExtractOrderRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        raw_text = serializer.validated_data['text']

        from ai_agent.services.unified_service import get_chat_service
        ai = get_chat_service(purpose='chat')

        available, _ = ai.is_available()

        if available:
            system_prompt = (
                "You are an order data extraction assistant for a delivery service in Qatar. "
                "Extract structured fields from the raw text. Return ONLY valid JSON with these keys: "
                "customer_name, customer_phone, dl_zone, dl_street, dl_building, "
                "customer_address, cod_amount, order_notes, zone_name. "
                "Rules: phone should be digits only (8 digits, no country code). "
                "dl_zone/dl_street/dl_building should be numbers or empty string. "
                "cod_amount should be a number or empty string. "
                "zone_name should be the area/neighborhood name if mentioned (e.g. West Bay, Al Sadd, Pearl Qatar). "
                "order_notes should capture any delivery instructions. "
                "If a field is not found, use empty string. Return ONLY the JSON object, nothing else."
            )

            result = ai.chat(
                messages=[{'role': 'user', 'content': f"Extract order fields from this text:\n\n{raw_text}"}],
                system=system_prompt,
                user_id=request.user.id,
            )

            if result.get('error'):
                return Response(
                    {'success': False, 'error': result.get('message', 'AI extraction failed')},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            try:
                content = result.get('content', '').strip()
                if content.startswith('```'):
                    content = content.split('\n', 1)[1] if '\n' in content else content[3:]
                    if content.endswith('```'):
                        content = content[:-3].strip()
                data = json.loads(content)
            except (json.JSONDecodeError, AttributeError):
                return Response(
                    {'success': False, 'error': 'Could not parse AI response'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        else:
            # Regex fallback — works without any API key
            import re
            text = raw_text

            # Phone: 8 digits, optionally preceded by +974 / 00974 / 974
            phone_match = re.search(r'(?:(?:\+|00)?974\s*)?(\b[3-7]\d{7}\b)', text)
            phone = phone_match.group(1) if phone_match else ''

            # Zone / Street / Building — look for keywords
            zone_match = re.search(r'\bzone\s*[:#]?\s*(\d+)', text, re.IGNORECASE)
            street_match = re.search(r'\bst(?:reet)?\s*[:#]?\s*(\d+)', text, re.IGNORECASE)
            building_match = re.search(r'\bb(?:uilding|ldg|ld)?\s*[:#]?\s*(\d+)', text, re.IGNORECASE)

            # COD amount — number followed by QR/QAR/ر.ق or preceded by COD/amount
            cod_match = re.search(
                r'(?:cod|amount|total|price)\s*[:#]?\s*(\d+(?:\.\d+)?)'
                r'|(\d+(?:\.\d+)?)\s*(?:qr|qar|ر\.ق)',
                text, re.IGNORECASE
            )
            cod_amount = ''
            if cod_match:
                cod_amount = cod_match.group(1) or cod_match.group(2) or ''

            # Customer name — first word(s) before phone/zone if no keyword, else look for "name:" prefix
            name = ''
            name_kw = re.search(r'(?:name|customer)\s*[:#]?\s*([A-Za-z][A-Za-z\s]{1,30}?)(?:\s+\d|\s*,|$)', text, re.IGNORECASE)
            if name_kw:
                name = name_kw.group(1).strip()
            elif phone:
                before_phone = text[:text.find(phone_match.group(0))].strip()
                words = re.findall(r'[A-Za-z]+', before_phone)
                if words:
                    name = ' '.join(words[:3])

            # Notes — anything after "note/instructions/remarks"
            notes_match = re.search(r'(?:note|instruction|remark|comment)\s*[:#]?\s*(.+)', text, re.IGNORECASE)
            notes = notes_match.group(1).strip() if notes_match else ''

            # Full address — after "address:" keyword or fallback to full text stripped of name/phone
            addr_match = re.search(r'(?:address|addr|location)\s*[:#]?\s*(.+?)(?:\n|cod|zone|$)', text, re.IGNORECASE)
            address = addr_match.group(1).strip() if addr_match else ''

            # zone_name — area/neighbourhood names
            area_match = re.search(
                r'\b(west\s*bay|pearl\s*qatar|the\s*pearl|al[\s-]sadd|al[\s-]wakra|al[\s-]rayyan|'
                r'lusail|msheireb|madinat\s*khalifa|al[\s-]khor|duhail|ain\s*khaled|'
                r'old\s*airport|new\s*airport|al[\s-]gharafa|al[\s-]waab|al[\s-]aziziyah|'
                r'industrial\s*area|al[\s-]muntazah|fereej\s*bin\s*mahmoud)\b',
                text, re.IGNORECASE
            )
            zone_name = area_match.group(1).strip() if area_match else ''
            if zone_name and not address:
                address = zone_name

            data = {
                'customer_name': name,
                'customer_phone': phone,
                'dl_zone': zone_match.group(1) if zone_match else '',
                'dl_street': street_match.group(1) if street_match else '',
                'dl_building': building_match.group(1) if building_match else '',
                'customer_address': address,
                'cod_amount': cod_amount,
                'order_notes': notes,
                'zone_name': zone_name,
            }

        # Server-side zone resolution: if zone empty but zone_name given, look up via ZoneArea/ZoneName
        zone_val = str(data.get('dl_zone', '')).strip()
        zone_name_val = str(data.get('zone_name', '')).strip()
        address_val = str(data.get('customer_address', '')).strip()

        from delivery.models import ZoneArea, ZoneName

        if not zone_val and zone_name_val:
            # Try to find zone by area name
            area = ZoneArea.objects.filter(
                area_name__icontains=zone_name_val, is_active=True
            ).select_related('zone').first()
            if area:
                data['dl_zone'] = str(area.zone.zone_number)
                if not address_val:
                    data['customer_address'] = zone_name_val
            else:
                # Try ZoneName directly
                zone_obj = ZoneName.objects.filter(
                    zone_name__icontains=zone_name_val, is_active=True
                ).first()
                if zone_obj:
                    data['dl_zone'] = str(zone_obj.zone_number)
                    if not address_val:
                        data['customer_address'] = zone_name_val

        # Reverse: if zone number given but no address, try to get zone name
        if zone_val and not address_val:
            try:
                zone_num = int(zone_val)
                zone_obj = ZoneName.objects.filter(zone_number=zone_num, is_active=True).first()
                if zone_obj:
                    data['customer_address'] = zone_obj.zone_name
            except (ValueError, TypeError):
                pass

        # Also check address text for area names if zone still empty
        zone_val = str(data.get('dl_zone', '')).strip()
        if not zone_val and address_val:
            area = ZoneArea.objects.filter(
                area_name__icontains=address_val, is_active=True
            ).select_related('zone').first()
            if area:
                data['dl_zone'] = str(area.zone.zone_number)

        # Clean up: remove zone_name from response (not a form field)
        data.pop('zone_name', None)

        return Response({'success': True, 'data': data})


class AgentStatusAPIView(APIView):
    """
    Get AI agent status and usage statistics.

    GET /api/ai-agent/status/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from ai_agent.services.unified_service import get_chat_service
        from ai_agent.models import UsageLog, Conversation
        from django.db.models import Sum, Count
        from django.utils import timezone
        from datetime import timedelta

        chat_service = get_chat_service(purpose='chat')

        # Check availability
        available, msg = chat_service.is_available()

        # Budget tracking only available on Claude service
        budget_usage = {}
        _bt = getattr(chat_service, 'budget_tracker', None)
        if _bt is not None:
            budget_usage = _bt.get_usage()

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
            'model': chat_service.model,
            'budget': budget_usage,
            'today_usage': {
                'api_calls': today_stats['total_calls'] or 0,
                'tokens_input': today_stats['total_tokens_input'] or 0,
                'tokens_output': today_stats['total_tokens_output'] or 0,
                'estimated_cost': float(today_stats['total_cost'] or 0),
            },
            'active_conversations': active_conversations,
        })
