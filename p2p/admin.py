# Purpose: Ops screens for the P2P rate card and booking records.
# Used by: /admin/p2p/ — the rate card is editable here so a price change needs no deploy.
# Notes: Bookings are read-mostly; the money and quote fields are frozen because they are the
#        audit record of what the customer was shown and agreed to.

from django.contrib import admin

from p2p.models import P2PBooking, P2PBoxTier, P2PRateBand
from p2p import models as p2p_models


@admin.register(P2PRateBand)
class P2PRateBandAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'min_boxes', 'max_boxes', 'size', 'up_to_kg',
        'vehicle', 'speed', 'up_to_km', 'price', 'needs_quote',
        'priority', 'is_active',
    )
    list_editable = ('price', 'needs_quote', 'priority', 'is_active')
    list_filter = ('is_active', 'needs_quote', 'size', 'vehicle', 'speed')
    search_fields = ('size', 'vehicle', 'speed', 'up_to_km', 'price')
    ordering = ('-priority', 'up_to_km', 'id')
    fieldsets = (
        ('When this row applies', {
            'fields': ('min_boxes', 'max_boxes', 'size', 'up_to_kg',
                       'vehicle', 'speed', 'up_to_km'),
            'description': (
                'Leave a field blank to mean "any". Priority decides first — a row '
                'with a higher Priority beats every other match, which is how you '
                'override the card without restructuring rows. When Priority is equal '
                '(it is 0 everywhere by default), the row with the most fields filled '
                'in wins, then the tightest distance limit.'
            ),
        }),
        ('Price', {'fields': ('price', 'needs_quote', 'priority', 'is_active')}),
    )


@admin.register(P2PBoxTier)
class P2PBoxTierAdmin(admin.ModelAdmin):
    """The box-count uplift. Also editable on the staff rate card page, which is where
    ops actually work — this exists so the table is reachable like every other one."""

    list_display = ('id', 'min_boxes', 'max_boxes', 'uplift', 'needs_quote', 'is_active')
    list_editable = ('uplift', 'needs_quote', 'is_active')
    list_filter = ('is_active', 'needs_quote')
    search_fields = ('min_boxes', 'max_boxes', 'uplift')
    ordering = ('min_boxes', 'id')


@admin.register(P2PBooking)
class P2PBookingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'status', 'customer', 'from_label', 'to_label',
        'box_count', 'size', 'weight_kg', 'vehicle', 'speed', 'return_trip',
        'distance_km', 'quoted_price', 'staff_price', 'fee_status', 'created_at',
    )
    list_filter = ('status', 'needs_quote', 'return_trip', 'fee_status', 'speed',
                   'size', 'vehicle')
    search_fields = ('from_label', 'to_label', 'sender_name', 'receiver_name', 'sender_phone',
                     'booker_phone', 'receiver_phone', 'pickup_locality', 'pickup_zone',
                     'pickup_street', 'pickup_building', 'status', 'fee_status', 'token',
                     'category', 'size', 'vehicle', 'order__order_number',
                     'fee_txn__transaction_code', 'return_order__order_number',
                     'customer__username', 'priced_by__username')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('customer', 'order', 'return_order', 'priced_by')
    # The quote is what the customer was shown and agreed to. Editing it after the
    # fact would destroy the only record of that, so it is frozen here — a wrong
    # price is corrected through the staff pricing action, which leaves a trail.
    readonly_fields = (
        'token', 'from_label', 'to_label', 'from_lat', 'from_lng', 'to_lat', 'to_lng',
        'distance_km', 'quoted_price', 'needs_quote', 'rate_band', 'ladder_version',
        'customer_agreed_at', 'fee_txn', 'source_ip', 'user_agent',
        'created_at', 'updated_at',
    )

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(p2p_models.P2PBookingLine)
class P2PBookingLineAdmin(admin.ModelAdmin):
    list_display = ('booking', 'size', 'count', 'created_at')
    search_fields = ('size', 'booking__from_label')
    list_filter = ('size',)
    list_select_related = ('booking',)
    raw_id_fields = ('booking',)

@admin.register(p2p_models.P2PVehicleBoxLimit)
class P2PVehicleBoxLimitAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'size', 'max_boxes', 'is_active', 'created_at', 'updated_at')
    search_fields = ('vehicle', 'size')
    list_filter = ('vehicle', 'size', 'is_active')

@admin.register(p2p_models.P2PVehicleCapacity)
class P2PVehicleCapacityAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'capacity_cbm', 'min_cbm', 'is_active', 'created_at', 'updated_at')
    search_fields = ('vehicle',)
    list_filter = ('vehicle', 'is_active')
