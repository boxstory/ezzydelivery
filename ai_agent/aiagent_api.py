# Purpose: Machine-authenticated REST API for external clients (n8n, etc.) to drive AI-agent conversations (chat, history, close, health).
# Used by: ai_agent/urls.py (/api/ai-agent/aiagent/...); callers authenticate with the AIAGENT_API_TOKEN service token.
# Notes: Conversations are keyed by the caller-supplied session_id (external_id) so the client stays stateless; runs the full AgentService (tools on) as an anonymous/customer role.

import logging

from django.conf import settings
from django.utils.crypto import constant_time_compare

from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from rest_framework import serializers

from ai_agent.models import Conversation
from ai_agent.serializers import ConversationMessageSerializer
from ai_agent.services.agent_service import get_agent_service

logger = logging.getLogger(__name__)


# ── Auth ─────────────────────────────────────────────────────────────────────
class _ServiceToken:
    """Marker placed on request.auth so throttling/permission can identify the
    caller without a Django user."""
    is_service_token = True


class AiAgentServiceTokenAuthentication(BaseAuthentication):
    """Authenticate an external client via the shared AIAGENT_API_TOKEN.

    Accepts either header:
        X-AIAgent-Token: <token>
        Authorization: Bearer <token>

    Leaves request.user anonymous (the agent runs as the 'anonymous'
    customer-facing role); sets request.auth to a _ServiceToken marker.
    """

    def authenticate(self, request):
        token = self._extract(request)
        if not token:
            return None  # let other authenticators / permission decide

        expected = getattr(settings, 'AIAGENT_API_TOKEN', '') or ''
        if not expected:
            raise AuthenticationFailed('AI agent API is not configured on the server')
        if not constant_time_compare(token, expected):
            raise AuthenticationFailed('Invalid AI agent API token')

        from django.contrib.auth.models import AnonymousUser
        return (AnonymousUser(), _ServiceToken())

    def authenticate_header(self, request):
        return 'Bearer'

    @staticmethod
    def _extract(request):
        tok = request.META.get('HTTP_X_AIAGENT_TOKEN', '').strip()
        if tok:
            return tok
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        parts = auth.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            return parts[1].strip() or None
        return None


class HasAiAgentServiceToken(BasePermission):
    message = 'A valid AI agent service token is required.'

    def has_permission(self, request, view):
        return isinstance(getattr(request, 'auth', None), _ServiceToken)


class AiAgentTokenRateThrottle(SimpleRateThrottle):
    """Per-token request throttle, rate from settings.AIAGENT_API_RATE_LIMIT."""
    scope = 'aiagent'

    def get_rate(self):
        return getattr(settings, 'AIAGENT_API_RATE_LIMIT', '120/min')

    def get_cache_key(self, request, view):
        if not isinstance(getattr(request, 'auth', None), _ServiceToken):
            return None  # only throttle authenticated service calls
        return 'throttle_aiagent_api'


# ── Serializers ──────────────────────────────────────────────────────────────
class AiAgentChatRequestSerializer(serializers.Serializer):
    session_id = serializers.CharField(
        max_length=128,
        help_text='Stable key for this conversation (e.g. the customer WhatsApp number).')
    message = serializers.CharField(max_length=4000, help_text='The end-user message text.')
    channel = serializers.ChoiceField(
        choices=[c[0] for c in Conversation.CHANNEL_CHOICES],
        default='api', required=False)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True,
                                  help_text='Optional customer phone for the conversation record.')
    reset = serializers.BooleanField(
        default=False, required=False,
        help_text='Start a fresh conversation for this session_id instead of continuing.')


# ── Base view (shared auth/permission/throttle + enabled check) ───────────────
class _AiAgentBaseView(APIView):
    authentication_classes = [AiAgentServiceTokenAuthentication]
    permission_classes = [HasAiAgentServiceToken]
    throttle_classes = [AiAgentTokenRateThrottle]


def _get_active_conversation(session_id):
    return (
        Conversation.objects
        .filter(external_id=session_id, status='active')
        .order_by('-last_activity')
        .first()
    )


# ── Endpoints ────────────────────────────────────────────────────────────────
class AiAgentChatView(_AiAgentBaseView):
    """POST /api/ai-agent/aiagent/chat/ — send a message, get the agent's reply.

    Body: {session_id, message, channel?, phone?, reset?}
    """

    def post(self, request):
        if not getattr(settings, 'AI_AGENT_ENABLED', False):
            return Response({'success': False, 'error': 'AI Agent is disabled'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        ser = AiAgentChatRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response({'success': False, 'errors': ser.errors},
                            status=status.HTTP_400_BAD_REQUEST)
        data = ser.validated_data
        session_id = data['session_id'].strip()

        agent = get_agent_service()

        conversation = None if data.get('reset') else _get_active_conversation(session_id)
        if conversation is None:
            conversation = Conversation.objects.create(
                channel=data.get('channel', 'api'),
                external_id=session_id,
                phone_number=(data.get('phone') or '')[:20],
                status='active',
                context={},
            )

        result = agent.process_message(
            message=data['message'],
            conversation=conversation,
            user=None,            # anonymous / customer-facing role
            tools_enabled=True,
        )

        if not result.get('success'):
            return Response({
                'success': False,
                'error': result.get('error', 'Agent error'),
                'session_id': session_id,
                'conversation_id': str(conversation.conversation_id),
            }, status=status.HTTP_502_BAD_GATEWAY)

        return Response({
            'success': True,
            'reply': result.get('response') or '',
            'session_id': session_id,
            'conversation_id': str(conversation.conversation_id),
            'tool_calls': result.get('tool_calls', []),
            'tokens_used': result.get('tokens_used', {}),
        })


class AiAgentConversationView(_AiAgentBaseView):
    """GET /api/ai-agent/aiagent/conversations/<session_id>/ — the active
    conversation's message history for a session."""

    def get(self, request, session_id):
        conversation = _get_active_conversation(session_id.strip())
        if conversation is None:
            return Response({'success': False, 'error': 'No active conversation for this session'},
                            status=status.HTTP_404_NOT_FOUND)
        messages = list(conversation.messages.order_by('created_at'))
        return Response({
            'success': True,
            'session_id': session_id,
            'conversation_id': str(conversation.conversation_id),
            'status': conversation.status,
            'total_messages': len(messages),
            'messages': ConversationMessageSerializer(messages, many=True).data,
        })


class AiAgentCloseConversationView(_AiAgentBaseView):
    """POST /api/ai-agent/aiagent/conversations/<session_id>/close/ — end the
    active conversation so the next message starts fresh."""

    def post(self, request, session_id):
        conversation = _get_active_conversation(session_id.strip())
        if conversation is None:
            return Response({'success': False, 'error': 'No active conversation for this session'},
                            status=status.HTTP_404_NOT_FOUND)
        conversation.status = 'closed'
        conversation.save(update_fields=['status', 'last_activity'])
        return Response({'success': True, 'session_id': session_id,
                         'conversation_id': str(conversation.conversation_id),
                         'status': conversation.status})


class AiAgentHealthView(_AiAgentBaseView):
    """GET /api/ai-agent/aiagent/health/ — verify the token works and the agent is up."""

    def get(self, request):
        return Response({
            'success': True,
            'agent_enabled': bool(getattr(settings, 'AI_AGENT_ENABLED', False)),
            'model': getattr(settings, 'AI_AGENT_MODEL', ''),
        })
