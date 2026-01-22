"""
AI Agent Models

Models for conversation tracking, usage logging, zone training data,
and COD risk assessment.
"""

import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Conversation(models.Model):
    """
    Tracks chat conversations across all channels (web, WhatsApp, API).

    Stores conversation context and metadata for continuity
    across multiple messages.
    """
    CHANNEL_CHOICES = [
        ('web', 'Web Chat'),
        ('whatsapp', 'WhatsApp'),
        ('api', 'REST API'),
    ]

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('archived', 'Archived'),
    ]

    conversation_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    channel = models.CharField(
        max_length=20,
        choices=CHANNEL_CHOICES,
        default='web'
    )

    # User context (optional - WhatsApp may not have user)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_conversations'
    )
    business = models.ForeignKey(
        'business.Business',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_conversations'
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        db_index=True,
        help_text='Phone number for WhatsApp conversations'
    )

    # Conversation state
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text='Active context: current order, zone, etc.'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )

    # Metrics
    total_messages = models.PositiveIntegerField(default=0)
    total_tokens_input = models.PositiveIntegerField(default=0)
    total_tokens_output = models.PositiveIntegerField(default=0)

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['channel', 'status']),
            models.Index(fields=['user', '-last_activity']),
            models.Index(fields=['business', '-last_activity']),
            models.Index(fields=['phone_number']),
        ]

    def __str__(self):
        return f"Conversation {self.conversation_id} ({self.channel})"

    @property
    def total_tokens(self):
        return self.total_tokens_input + self.total_tokens_output


class ConversationMessage(models.Model):
    """
    Individual messages within a conversation.

    Stores both user messages and AI responses, along with
    any tool calls and their results.
    """
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
        ('tool', 'Tool Result'),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()

    # Tool call tracking
    tool_name = models.CharField(max_length=100, blank=True)
    tool_input = models.JSONField(null=True, blank=True)
    tool_output = models.JSONField(null=True, blank=True)

    # Metrics
    tokens_input = models.PositiveIntegerField(default=0)
    tokens_output = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['conversation', 'created_at']),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."


class AgentTool(models.Model):
    """
    Registry of available AI agent tools.

    Stores tool configurations, schemas, and usage limits.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    schema = models.JSONField(
        help_text='JSON Schema for tool input parameters'
    )

    is_enabled = models.BooleanField(default=True)
    requires_auth = models.BooleanField(
        default=False,
        help_text='Requires authenticated user to execute'
    )
    rate_limit_per_minute = models.PositiveIntegerField(default=60)

    # Metrics
    total_calls = models.PositiveIntegerField(default=0)
    total_errors = models.PositiveIntegerField(default=0)
    avg_latency_ms = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.name} ({status})"


class UsageLog(models.Model):
    """
    API usage tracking for cost management and analytics.

    Records every API call with token counts and estimated costs.
    """
    API_CALL_TYPES = [
        ('chat', 'Chat Completion'),
        ('tool_use', 'Tool Use'),
        ('embedding', 'Embedding'),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='usage_logs'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    business = models.ForeignKey(
        'business.Business',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    api_call_type = models.CharField(max_length=50, choices=API_CALL_TYPES)
    model = models.CharField(max_length=50)

    tokens_input = models.PositiveIntegerField(default=0)
    tokens_output = models.PositiveIntegerField(default=0)
    estimated_cost = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal('0.000000')
    )

    # Request metadata
    latency_ms = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['api_call_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.api_call_type} - {self.tokens_input + self.tokens_output} tokens"


class ZoneTrainingData(models.Model):
    """
    Training data for zone recognition from free-text addresses.

    Maps various text inputs (area names, landmarks, typos) to zones.
    Used by the AI agent to parse Qatar addresses.
    """
    INPUT_TYPES = [
        ('area_name', 'Area Name'),
        ('street_ref', 'Street Reference'),
        ('landmark', 'Landmark'),
        ('typo', 'Common Typo'),
        ('alias', 'Alias'),
    ]

    LANGUAGES = [
        ('en', 'English'),
        ('ar', 'Arabic'),
    ]

    zone = models.ForeignKey(
        'delivery.ZoneName',
        on_delete=models.CASCADE,
        related_name='training_data'
    )

    text_input = models.CharField(
        max_length=200,
        help_text='Text that maps to this zone (e.g., "الدفنة", "Defna", "Al Dafna")'
    )
    input_type = models.CharField(
        max_length=20,
        choices=INPUT_TYPES,
        default='area_name'
    )
    language = models.CharField(
        max_length=10,
        choices=LANGUAGES,
        default='en'
    )
    confidence = models.FloatField(
        default=1.0,
        help_text='Confidence score 0-1 for this mapping'
    )

    is_verified = models.BooleanField(
        default=False,
        help_text='Manually verified by admin'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['zone', 'text_input']
        ordering = ['zone', 'text_input']
        indexes = [
            models.Index(fields=['text_input']),
            models.Index(fields=['language', 'input_type']),
        ]

    def __str__(self):
        return f"Zone {self.zone.zone_number}: {self.text_input}"


class CODRiskScore(models.Model):
    """
    Customer COD (Cash on Delivery) risk assessment.

    Tracks order history and calculates risk scores for
    customers based on their behavior patterns.
    """
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True
    )

    # Order history counts
    total_orders = models.PositiveIntegerField(default=0)
    delivered_orders = models.PositiveIntegerField(default=0)
    cancelled_orders = models.PositiveIntegerField(default=0)
    cod_refused_orders = models.PositiveIntegerField(default=0)
    returned_orders = models.PositiveIntegerField(default=0)

    # Financial history
    total_cod_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    collected_cod_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    # Risk metrics (0-1 scale, higher = riskier)
    risk_score = models.FloatField(
        default=0.5,
        help_text='Composite risk score 0-1'
    )
    risk_factors = models.JSONField(
        default=list,
        help_text='List of contributing risk factors'
    )

    # Zone-based risk modifier
    primary_zone = models.ForeignKey(
        'delivery.ZoneName',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Most common delivery zone'
    )
    zone_risk_modifier = models.FloatField(
        default=0.0,
        help_text='Risk adjustment based on zone patterns'
    )

    # Timestamps
    last_order_at = models.DateTimeField(null=True, blank=True)
    last_calculated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-risk_score']
        indexes = [
            models.Index(fields=['risk_score']),
            models.Index(fields=['phone_number']),
        ]

    def __str__(self):
        return f"{self.phone_number} - Risk: {self.risk_score:.2f}"

    @property
    def delivery_rate(self):
        """Calculate successful delivery rate."""
        if self.total_orders == 0:
            return 0.0
        return self.delivered_orders / self.total_orders

    @property
    def cod_collection_rate(self):
        """Calculate COD collection rate."""
        if self.total_cod_amount == 0:
            return 1.0
        return float(self.collected_cod_amount / self.total_cod_amount)

    def calculate_risk_score(self):
        """
        Calculate composite risk score based on multiple factors.

        Factors:
        - Delivery rate (lower = higher risk)
        - COD refusal rate (higher = higher risk)
        - Zone modifier
        - Order frequency
        """
        factors = []
        score = 0.5  # Base score

        # Delivery rate factor
        if self.total_orders >= 3:
            delivery_rate = self.delivery_rate
            if delivery_rate < 0.5:
                score += 0.3
                factors.append('Low delivery rate')
            elif delivery_rate < 0.8:
                score += 0.1
                factors.append('Below average delivery rate')
            elif delivery_rate > 0.95:
                score -= 0.2
                factors.append('Excellent delivery history')

        # COD refusal factor
        if self.total_orders >= 3:
            refusal_rate = self.cod_refused_orders / self.total_orders
            if refusal_rate > 0.2:
                score += 0.3
                factors.append('High COD refusal rate')
            elif refusal_rate > 0.1:
                score += 0.1
                factors.append('Some COD refusals')

        # New customer factor
        if self.total_orders < 3:
            score += 0.1
            factors.append('New customer')

        # Zone modifier
        score += self.zone_risk_modifier
        if self.zone_risk_modifier > 0.1:
            factors.append('High-risk zone')
        elif self.zone_risk_modifier < -0.1:
            factors.append('Low-risk zone')

        # Clamp score to 0-1 range
        self.risk_score = max(0.0, min(1.0, score))
        self.risk_factors = factors
        return self.risk_score
