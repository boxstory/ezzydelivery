"""
Dispatch Serializers - DRF serializers for dispatch API endpoints.
"""
from rest_framework import serializers
from .models import OrderBatch, BatchOrder, RiderShift, RiderKPI


class BatchOrderSerializer(serializers.ModelSerializer):
    """Serializer for orders within a batch."""
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    customer_name = serializers.CharField(source='order.customer_name', read_only=True)
    customer_phone = serializers.CharField(source='order.customer_phone', read_only=True)
    customer_address = serializers.CharField(source='order.customer_address', read_only=True)
    cod_amount = serializers.DecimalField(
        source='order.cod_amount',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    dl_zone = serializers.IntegerField(source='order.dl_zone', read_only=True)
    dl_street = serializers.IntegerField(source='order.dl_street', read_only=True)
    dl_building = serializers.IntegerField(source='order.dl_building', read_only=True)
    sla_remaining_minutes = serializers.ReadOnlyField()

    class Meta:
        model = BatchOrder
        fields = [
            'id', 'sequence', 'order_number',
            'customer_name', 'customer_phone', 'customer_address',
            'cod_amount', 'dl_zone', 'dl_street', 'dl_building',
            'sla_deadline', 'sla_remaining_minutes', 'is_sla_at_risk',
            'added_at'
        ]


class OrderBatchSerializer(serializers.ModelSerializer):
    """Serializer for order batches."""
    orders = BatchOrderSerializer(source='batch_orders', many=True, read_only=True)
    pickup_location_name = serializers.CharField(
        source='pickup_location.pickup_location_title',
        read_only=True
    )
    pickup_address = serializers.SerializerMethodField()
    assigned_rider_code = serializers.CharField(
        source='assigned_rider.driver_code',
        read_only=True,
        allow_null=True
    )
    hold_remaining_seconds = serializers.ReadOnlyField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = OrderBatch
        fields = [
            'id', 'batch_code', 'status', 'status_display',
            'pickup_location_name', 'pickup_address',
            'destination_zone', 'order_count', 'total_cod',
            'hold_started_at', 'hold_expires_at', 'hold_remaining_seconds',
            'release_reason', 'released_at',
            'assigned_rider_code', 'assigned_at',
            'created_at', 'completed_at',
            'orders'
        ]

    def get_pickup_address(self, obj):
        loc = obj.pickup_location
        return f"Zone {loc.pickup_zone_no}, Street {loc.pickup_street_no}"


class OrderBatchListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for batch lists (without nested orders)."""
    pickup_location_name = serializers.CharField(
        source='pickup_location.pickup_location_title',
        read_only=True
    )
    assigned_rider_code = serializers.CharField(
        source='assigned_rider.driver_code',
        read_only=True,
        allow_null=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = OrderBatch
        fields = [
            'id', 'batch_code', 'status', 'status_display',
            'pickup_location_name', 'destination_zone',
            'order_count', 'total_cod',
            'assigned_rider_code', 'created_at'
        ]


class RiderShiftSerializer(serializers.ModelSerializer):
    """Serializer for rider shifts."""
    rider_code = serializers.CharField(source='rider.driver_code', read_only=True)
    rider_name = serializers.SerializerMethodField()
    pickup_location_name = serializers.CharField(
        source='pickup_location.pickup_location_title',
        read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    shift_type_display = serializers.CharField(source='get_shift_type_display', read_only=True)
    duration_hours = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()

    class Meta:
        model = RiderShift
        fields = [
            'id', 'shift_code', 'status', 'status_display',
            'rider_code', 'rider_name',
            'pickup_location_name',
            'shift_type', 'shift_type_display',
            'scheduled_start', 'scheduled_end',
            'actual_start', 'actual_end',
            'duration_hours', 'is_active',
            'batches_completed', 'orders_delivered'
        ]

    def get_rider_name(self, obj):
        user = obj.rider.user
        return f"{user.first_name} {user.last_name}".strip() or user.username


class RiderShiftListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for shift lists."""
    pickup_location_name = serializers.CharField(
        source='pickup_location.pickup_location_title',
        read_only=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RiderShift
        fields = [
            'id', 'shift_code', 'status', 'status_display',
            'pickup_location_name',
            'scheduled_start', 'scheduled_end',
            'batches_completed', 'orders_delivered'
        ]


class RiderKPISerializer(serializers.ModelSerializer):
    """Serializer for rider KPIs."""
    rider_code = serializers.CharField(source='rider.driver_code', read_only=True)
    pickup_location_name = serializers.CharField(
        source='pickup_location.pickup_location_title',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = RiderKPI
        fields = [
            'id', 'rider_code', 'date', 'pickup_location_name',
            'total_orders', 'batched_orders', 'single_orders',
            'total_batches', 'batches_with_2_orders',
            'total_active_minutes', 'avg_delivery_time',
            'sla_compliant_orders', 'sla_breached_orders',
            'orders_per_hour', 'batching_percentage', 'sla_compliance_rate'
        ]
