"""
AI Agent Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from ai_agent.models import (
    Conversation,
    ConversationMessage,
    AgentTool,
    UsageLog,
    ZoneTrainingData,
    CODRiskScore,
)


class ConversationMessageInline(admin.TabularInline):
    model = ConversationMessage
    extra = 0
    readonly_fields = ['role', 'content', 'tool_name', 'tokens_input', 'tokens_output', 'created_at']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        'conversation_id',
        'channel',
        'user',
        'business',
        'status',
        'total_messages',
        'total_tokens',
        'started_at',
        'last_activity',
    ]
    list_filter = ['channel', 'status', 'started_at']
    search_fields = ['conversation_id', 'user__username', 'phone_number']
    readonly_fields = [
        'conversation_id',
        'total_messages',
        'total_tokens_input',
        'total_tokens_output',
        'started_at',
        'last_activity',
    ]
    inlines = [ConversationMessageInline]
    date_hierarchy = 'started_at'


@admin.register(AgentTool)
class AgentToolAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'is_enabled',
        'requires_auth',
        'total_calls',
        'total_errors',
        'error_rate',
        'avg_latency_ms',
    ]
    list_filter = ['is_enabled', 'requires_auth']
    search_fields = ['name', 'description']
    readonly_fields = ['total_calls', 'total_errors', 'avg_latency_ms', 'created_at', 'updated_at']

    def error_rate(self, obj):
        if obj.total_calls == 0:
            return '0%'
        rate = (obj.total_errors / obj.total_calls) * 100
        color = 'green' if rate < 5 else 'orange' if rate < 20 else 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, rate
        )
    error_rate.short_description = 'Error Rate'


@admin.register(UsageLog)
class UsageLogAdmin(admin.ModelAdmin):
    list_display = [
        'created_at',
        'api_call_type',
        'model',
        'tokens_total',
        'estimated_cost',
        'latency_ms',
        'success',
        'user',
    ]
    list_filter = ['api_call_type', 'model', 'success', 'created_at']
    search_fields = ['user__username', 'conversation__conversation_id']
    readonly_fields = [
        'conversation',
        'user',
        'business',
        'api_call_type',
        'model',
        'tokens_input',
        'tokens_output',
        'estimated_cost',
        'latency_ms',
        'success',
        'error_message',
        'created_at',
    ]
    date_hierarchy = 'created_at'

    def tokens_total(self, obj):
        return obj.tokens_input + obj.tokens_output
    tokens_total.short_description = 'Total Tokens'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ZoneTrainingData)
class ZoneTrainingDataAdmin(admin.ModelAdmin):
    list_display = [
        'zone',
        'text_input',
        'input_type',
        'language',
        'confidence',
        'is_verified',
    ]
    list_filter = ['input_type', 'language', 'is_verified', 'zone']
    search_fields = ['text_input', 'zone__zone_name']
    autocomplete_fields = ['zone']


@admin.register(CODRiskScore)
class CODRiskScoreAdmin(admin.ModelAdmin):
    list_display = [
        'phone_number',
        'risk_score_display',
        'total_orders',
        'delivered_orders',
        'cod_refused_orders',
        'delivery_rate_display',
        'last_order_at',
    ]
    list_filter = ['last_calculated', 'primary_zone']
    search_fields = ['phone_number']
    readonly_fields = [
        'risk_factors',
        'delivery_rate',
        'cod_collection_rate',
        'last_calculated',
        'created_at',
    ]

    def risk_score_display(self, obj):
        score = obj.risk_score
        if score < 0.3:
            color = 'green'
            label = 'Low'
        elif score < 0.5:
            color = 'blue'
            label = 'Normal'
        elif score < 0.7:
            color = 'orange'
            label = 'Elevated'
        else:
            color = 'red'
            label = 'High'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.2f} ({})</span>',
            color, score, label
        )
    risk_score_display.short_description = 'Risk Score'

    def delivery_rate_display(self, obj):
        rate = obj.delivery_rate
        color = 'green' if rate >= 0.9 else 'orange' if rate >= 0.7 else 'red'
        return format_html(
            '<span style="color: {};">{:.0%}</span>',
            color, rate
        )
    delivery_rate_display.short_description = 'Delivery Rate'
