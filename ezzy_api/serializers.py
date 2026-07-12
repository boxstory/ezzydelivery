from rest_framework import serializers
from orders import models as orders_models
from fleet import models as fleet_models
from delivery import models as delivery_models
from core import models as core_models
from business import models as business_models
from ezzy_api import models as ezzy_api_models
from django.contrib.auth import get_user_model

User = get_user_model()


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = orders_models.Order
        fields = '__all__'


# Driver App Serializers
class DriverVehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = fleet_models.DriverVehicle
        fields = '__all__'


class DriverDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = fleet_models.DriverDocument
        fields = '__all__'


class DriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = core_models.Profile
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'whatsapp', 'zone_name', 'address']


class DriverSerializer(serializers.ModelSerializer):
    profile = DriverProfileSerializer(read_only=True)
    driver_vehicle = DriverVehicleSerializer(many=True, read_only=True, source='driver_vehicle.all')
    driver_document = DriverDocumentSerializer(many=True, read_only=True, source='driver_document.all')
    
    class Meta:
        model = fleet_models.Driver
        fields = [
            'driver_id', 'driver_code', 'driver_phone', 'driver_whatsapp',
            'driver_bio', 'driver_languages', 'driver_license_number', 'driver_rating',
            'driver_rating_count', 'driver_status', 'driver_availability', 'profile', 'driver_vehicle', 'driver_document',
            'created_at', 'updated_at'
        ]


class DriverLocationSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=19, decimal_places=15)
    longitude = serializers.DecimalField(max_digits=19, decimal_places=15)
    timestamp = serializers.DateTimeField()


# Delivery Task Serializers
class DlAddressUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = delivery_models.DlAddressUpdate
        fields = '__all__'


class DeliveryTaskSerializer(serializers.ModelSerializer):
    order = OrderSerializer(read_only=True)
    dl_address_update = DlAddressUpdateSerializer(read_only=True)
    driver = DriverSerializer(read_only=True)
    
    class Meta:
        model = delivery_models.DeliveryTask
        fields = '__all__'


class DeliveryTaskListSerializer(serializers.ModelSerializer):
    """Simplified serializer for task lists"""
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    customer_name = serializers.CharField(source='order.customer_name', read_only=True)
    customer_phone = serializers.CharField(source='order.customer_phone', read_only=True)
    customer_address = serializers.CharField(source='order.customer_address', read_only=True)
    cod_amount = serializers.IntegerField(source='order.cod_amount', read_only=True)

    class Meta:
        model = delivery_models.DeliveryTask
        fields = [
            'id', 'dl_task_number', 'dl_task_description',
            'dl_task_status', 'dl_task_date', 'order_number',
            'customer_name', 'customer_phone', 'customer_address', 'cod_amount',
            'dl_price', 'dl_category', 'dl_speed', 'created_at', 'updated_at'
        ]


# DMS API Serializers
class OrderListSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business.business_name', read_only=True)
    verification_status_display = serializers.CharField(source='get_verification_status_display', read_only=True)
    
    class Meta:
        model = orders_models.Order
        fields = [
            'id', 'order_number', 'client_order_code', 'business_name',
            'order_status', 'task_status', 'customer_name', 'customer_phone',
            'customer_address', 'cod_amount', 'dl_amount', 'order_date',
            'verification_status', 'verification_status_display', 'address_verified',
            'task_created', 'created_at', 'updated_at'
        ]


class DriverListSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()
    vehicle_type = serializers.SerializerMethodField()

    class Meta:
        model = fleet_models.Driver
        fields = [
            'driver_id', 'driver_code', 'driver_phone',
            'driver_whatsapp', 'driver_status', 'driver_availability', 'driver_rating', 'driver_rating_count',
            'driver_name', 'vehicle_type'
        ]
    
    def get_driver_name(self, obj):
        if obj.profile:
            return f"{obj.profile.first_name or ''} {obj.profile.last_name or ''}".strip()
        return obj.driver_code or f"Driver {obj.driver_id}"
    
    def get_vehicle_type(self, obj):
        vehicle = obj.driver_vehicle.filter(vehicle_status='active').first()
        return vehicle.vehicle_type if vehicle else None


class TaskAssignmentSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    driver_id = serializers.IntegerField()


class TaskStatusUpdateSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=[
        'for_review', 'pending', 'assigned', 'accepted', 'picked_up',
        'start_ride', 'out_for_delivery', 'in_transit', 'contacted',
        'non_reachable', 'address_pending', 'customer_confiration_pending',
        'customer_delaying', 'dl_pending_payment',
        'delivered', 'failed', 'rejected', 'cancelled',
    ])
    notes = serializers.CharField(required=False, allow_blank=True)


# Document Upload Serializers
class TaskDocumentSerializer(serializers.ModelSerializer):
    document_file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ezzy_api_models.TaskDocument
        fields = [
            'id', 'task', 'document_type', 'document_file', 'document_file_url',
            'document_name', 'description', 'uploaded_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['uploaded_by', 'created_at', 'updated_at']
    
    def get_document_file_url(self, obj):
        if obj.document_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.document_file.url)
            return obj.document_file.url
        return None


class OrderDocumentSerializer(serializers.ModelSerializer):
    document_file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ezzy_api_models.OrderDocument
        fields = [
            'id', 'order', 'document_type', 'document_file', 'document_file_url',
            'document_name', 'description', 'uploaded_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['uploaded_by', 'created_at', 'updated_at']
    
    def get_document_file_url(self, obj):
        if obj.document_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.document_file.url)
            return obj.document_file.url
        return None


# API Key Serializers
class ClientApiKeySerializer(serializers.ModelSerializer):
    """
    Default (list/manage) serializer. Never returns the full secret; the
    api_key is masked to a short prefix so a leaked list response cannot be
    used to authenticate. The full key + secret are only returned once, at
    creation time, via ClientApiKeyRevealSerializer.
    """
    business_name = serializers.CharField(source='business.business_name', read_only=True)
    api_key = serializers.SerializerMethodField()
    api_secret = serializers.SerializerMethodField()

    class Meta:
        model = ezzy_api_models.ClientApiKey
        fields = [
            'id', 'business', 'business_name', 'api_key', 'api_secret',
            'key_prefix', 'scope', 'key_name', 'is_active', 'last_used', 'expires_at',
            'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['api_key', 'api_secret', 'key_prefix', 'created_at', 'updated_at', 'created_by']

    def get_api_key(self, obj):
        # Only the non-sensitive prefix is ever shown after creation.
        return f"{obj.key_prefix}…" if obj.key_prefix else None

    def get_api_secret(self, obj):
        # Never expose the secret after creation.
        return '••••••••'


class ClientApiKeyRevealSerializer(serializers.ModelSerializer):
    """One-time serializer used only in the create response to reveal the
    full api_key and api_secret to the owner. The full key is available only
    transiently on the freshly-created instance (obj._plaintext_key)."""
    business_name = serializers.CharField(source='business.business_name', read_only=True)
    api_key = serializers.SerializerMethodField()

    class Meta:
        model = ezzy_api_models.ClientApiKey
        fields = [
            'id', 'business', 'business_name', 'api_key', 'api_secret',
            'key_prefix', 'scope', 'key_name', 'is_active', 'last_used', 'expires_at',
            'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['api_secret', 'key_prefix', 'created_at', 'updated_at', 'created_by']

    def get_api_key(self, obj):
        # Full plaintext, exposed exactly once at creation.
        return getattr(obj, '_plaintext_key', None) or (f"{obj.key_prefix}…" if obj.key_prefix else None)


class ClientApiKeyCreateSerializer(serializers.Serializer):
    business_id = serializers.IntegerField()
    key_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    scope = serializers.ChoiceField(
        choices=ezzy_api_models.ClientApiKey.SCOPE_CHOICES,
        required=False,
        default=ezzy_api_models.ClientApiKey.SCOPE_WRITE,
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


# E-commerce Integration Serializers
class EcommerceIntegrationSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business.business_name', read_only=True)
    platform_display = serializers.SerializerMethodField()
    
    class Meta:
        model = ezzy_api_models.EcommerceIntegration
        fields = [
            'id', 'business', 'business_name', 'platform', 'platform_display',
            'api_settings', 'last_sync', 'sync_status', 'sync_error',
            'total_orders_imported', 'created_at', 'updated_at'
        ]
        read_only_fields = ['last_sync', 'sync_status', 'sync_error', 'total_orders_imported', 'created_at', 'updated_at']
    
    def get_platform_display(self, obj):
        """Return formatted platform name"""
        return obj.platform.replace('_', ' ').title() if obj.platform else ''


# Task Completion Serializer
class TaskCompletionSerializer(serializers.Serializer):
    task_id = serializers.IntegerField(required=False)
    status = serializers.ChoiceField(choices=['delivered', 'cancelled', 'rejected', 'failed', 'accepted'])
    delivery_proof = serializers.FileField(required=False, allow_null=True)
    signature = serializers.FileField(required=False, allow_null=True)
    photo = serializers.FileField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    failure_reason = serializers.CharField(required=False, allow_blank=True, max_length=50)
    failure_notes = serializers.CharField(required=False, allow_blank=True)
    cod_collected = serializers.BooleanField(required=False, default=False)
    cod_amount_collected = serializers.IntegerField(required=False, allow_null=True)
    completion_latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    completion_longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)


# Shopify Order Import Serializer
class ShopifyOrderImportSerializer(serializers.Serializer):
    business_id = serializers.IntegerField()
    order_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True
    )
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(required=False, default=50)


# WooCommerce Order Import Serializer
class WooCommerceOrderImportSerializer(serializers.Serializer):
    business_id = serializers.IntegerField()
    order_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    status = serializers.CharField(required=False, allow_blank=True)
    limit = serializers.IntegerField(required=False, default=50)


# Webhook Serializers
class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = ezzy_api_models.WebhookEndpoint
        fields = [
            'id', 'business', 'url', 'events', 'secret', 'is_active',
            'description', 'created_at', 'updated_at', 'last_triggered'
        ]
        read_only_fields = ['business', 'secret', 'created_at', 'updated_at', 'last_triggered']


class WebhookDeliverySerializer(serializers.ModelSerializer):
    webhook_url = serializers.CharField(source='webhook.url', read_only=True)
    
    class Meta:
        model = ezzy_api_models.WebhookDelivery
        fields = [
            'id', 'webhook', 'webhook_url', 'event_type', 'payload',
            'response_status', 'response_body', 'status', 'error_message',
            'attempt_count', 'created_at', 'delivered_at'
        ]
        read_only_fields = ['created_at', 'delivered_at']


# Webhook Payload Serializers (for receiving webhooks from driver apps)
class WebhookTaskStatusUpdateSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=[
        'for_review', 'pending', 'assigned', 'accepted', 'picked_up',
        'start_ride', 'out_for_delivery', 'in_transit', 'contacted',
        'non_reachable', 'delivered', 'failed', 'rejected', 'cancelled',
    ])
    notes = serializers.CharField(required=False, allow_blank=True)
    timestamp = serializers.DateTimeField(required=False)
    driver_id = serializers.IntegerField(required=False)


class WebhookTaskCompletionSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=['delivered', 'cancelled', 'rejected', 'failed'])
    cod_collected = serializers.BooleanField(required=False, default=False)
    cod_amount_collected = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    timestamp = serializers.DateTimeField(required=False)
    driver_id = serializers.IntegerField(required=False)


class WebhookDriverLocationSerializer(serializers.Serializer):
    driver_id = serializers.IntegerField()
    latitude = serializers.DecimalField(max_digits=19, decimal_places=15)
    longitude = serializers.DecimalField(max_digits=19, decimal_places=15)
    timestamp = serializers.DateTimeField()
    accuracy = serializers.FloatField(required=False, allow_null=True)
    speed = serializers.FloatField(required=False, allow_null=True)
