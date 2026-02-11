"""
AI Agent Serializers

DRF serializers for AI agent API endpoints.
"""

from rest_framework import serializers
from ai_agent.models import Conversation, ConversationMessage, UsageLog


class ChatRequestSerializer(serializers.Serializer):
    """Serializer for chat request."""
    message = serializers.CharField(
        max_length=4000,
        help_text='User message'
    )
    conversation_id = serializers.UUIDField(
        required=False,
        help_text='Existing conversation ID to continue'
    )
    channel = serializers.ChoiceField(
        choices=['web', 'whatsapp', 'api'],
        default='api',
        help_text='Communication channel'
    )


class ChatResponseSerializer(serializers.Serializer):
    """Serializer for chat response."""
    success = serializers.BooleanField()
    response = serializers.CharField(allow_null=True)
    conversation_id = serializers.UUIDField()
    tool_calls = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )
    tokens_used = serializers.DictField(required=False)
    error = serializers.CharField(required=False)


class ParseAddressRequestSerializer(serializers.Serializer):
    """Serializer for address parsing request."""
    address = serializers.CharField(
        max_length=500,
        help_text='Free-text address to parse'
    )


class VerifyOrderRequestSerializer(serializers.Serializer):
    """Serializer for order verification request."""
    order_number = serializers.CharField(
        max_length=100,
        help_text='Order number to verify'
    )


class CODRiskRequestSerializer(serializers.Serializer):
    """Serializer for COD risk assessment request."""
    phone_number = serializers.CharField(
        max_length=20,
        help_text='Customer phone number'
    )
    order_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        help_text='COD amount for the order'
    )
    zone_number = serializers.IntegerField(
        required=False,
        help_text='Delivery zone number'
    )


class EstimateDeliveryRequestSerializer(serializers.Serializer):
    """Serializer for delivery estimation request."""
    pickup_zone = serializers.IntegerField(
        required=False,
        help_text='Pickup zone number'
    )
    delivery_zone = serializers.IntegerField(
        required=False,
        help_text='Delivery zone number'
    )
    order_number = serializers.CharField(
        required=False,
        max_length=100,
        help_text='Order number (alternative to zones)'
    )

    def validate(self, data):
        if not data.get('order_number') and not (data.get('pickup_zone') and data.get('delivery_zone')):
            raise serializers.ValidationError(
                'Provide either order_number or both pickup_zone and delivery_zone'
            )
        return data


class SuggestDriverRequestSerializer(serializers.Serializer):
    """Serializer for driver suggestion request."""
    delivery_zone = serializers.IntegerField(
        required=False,
        help_text='Delivery zone number'
    )
    order_number = serializers.CharField(
        required=False,
        max_length=100,
        help_text='Order number (alternative to zone)'
    )
    vehicle_required = serializers.CharField(
        required=False,
        max_length=20,
        help_text='Required vehicle type (bike, car, van)'
    )
    limit = serializers.IntegerField(
        default=5,
        min_value=1,
        max_value=20,
        help_text='Max drivers to return'
    )


class ConversationMessageSerializer(serializers.ModelSerializer):
    """Serializer for conversation messages."""

    class Meta:
        model = ConversationMessage
        fields = [
            'role',
            'content',
            'tool_name',
            'created_at'
        ]


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for conversation details."""
    messages = ConversationMessageSerializer(many=True, read_only=True)
    total_tokens = serializers.IntegerField(read_only=True)

    class Meta:
        model = Conversation
        fields = [
            'conversation_id',
            'channel',
            'status',
            'total_messages',
            'total_tokens',
            'started_at',
            'last_activity',
            'messages'
        ]


class UsageLogSerializer(serializers.ModelSerializer):
    """Serializer for usage logs."""

    class Meta:
        model = UsageLog
        fields = [
            'api_call_type',
            'model',
            'tokens_input',
            'tokens_output',
            'estimated_cost',
            'latency_ms',
            'success',
            'created_at'
        ]


class ExtractOrderRequestSerializer(serializers.Serializer):
    """Serializer for AI order text extraction request."""
    text = serializers.CharField(
        max_length=2000,
        help_text='Raw order text (WhatsApp message, SMS, notes)'
    )


class WhatsAppWebhookSerializer(serializers.Serializer):
    """Serializer for WhatsApp webhook (from n8n)."""
    phone = serializers.CharField(
        max_length=20,
        help_text='Sender phone number'
    )
    message = serializers.CharField(
        max_length=4000,
        help_text='Message content'
    )
    message_id = serializers.CharField(
        required=False,
        help_text='WhatsApp message ID'
    )
    timestamp = serializers.DateTimeField(
        required=False,
        help_text='Message timestamp'
    )
