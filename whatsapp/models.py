"""
WhatsApp message store backed by the WAHA bridge.

One row per inbound or outbound message. Webhook upserts on `waha_message_id`.
The legacy `business.WhatsAppNotificationTrigger` model is unrelated — it
configures *what* to send for which order events; this table is the *log*.
"""
from django.db import models


class WhatsAppMessage(models.Model):
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('picked_up', 'Picked Up'),
        ('processed', 'Processed'),
        ('archived', 'Archived'),
        ('failed', 'Failed'),
    ]
    MESSAGE_TYPE_CHOICES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('audio', 'Audio'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('location', 'Location'),
        ('sticker', 'Sticker'),
        ('contact', 'Contact'),
        ('unknown', 'Unknown'),
    ]

    waha_message_id = models.CharField(max_length=255, unique=True, db_index=True)
    session = models.CharField(max_length=64, default='default')
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES)

    from_number = models.CharField(max_length=64, db_index=True, blank=True, default='')
    to_number = models.CharField(max_length=64, db_index=True, blank=True, default='')

    body = models.TextField(blank=True, default='')
    message_type = models.CharField(max_length=16, choices=MESSAGE_TYPE_CHOICES, default='text')

    media_url = models.CharField(max_length=500, blank=True, default='')
    media_mime = models.CharField(max_length=80, blank=True, default='')

    # Populated when message_type='location' — extracted from payload.location.*
    # or payload._data.location.* by the webhook.
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='received')
    error_kind = models.CharField(max_length=64, blank=True, default='')

    business = models.ForeignKey(
        'business.Business',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_messages',
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_messages',
    )

    raw_payload = models.JSONField(default=dict, blank=True)

    received_at = models.DateTimeField(null=True, blank=True, db_index=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'WhatsApp Message'
        verbose_name_plural = 'WhatsApp Messages'
        ordering = ['-received_at', '-created_at']
        indexes = [
            models.Index(fields=['status', 'received_at']),
            models.Index(fields=['from_number', 'received_at']),
            models.Index(fields=['business', 'received_at']),
            models.Index(fields=['direction', 'received_at']),
        ]

    def __str__(self):
        return f'{self.direction} {self.from_number or self.to_number} {self.waha_message_id}'


class WahaConfig(models.Model):
    """Singleton runtime config for the WAHA verify-queue messaging path.

    The env flag WAHA_VERIFY_USE_WAHA decides if WAHA is *wired in*; this row
    is the runtime *kill switch* ops can flip from the banner without a redeploy.
    Both must be truthy for sends to flow.
    """
    verify_messaging_enabled = models.BooleanField(default=True)
    last_toggled_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='waha_config_toggles',
    )
    last_toggled_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'WAHA Config'
        verbose_name_plural = 'WAHA Config'

    def __str__(self):
        return f'WahaConfig(verify_messaging={self.verify_messaging_enabled})'

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AddressVerificationJob(models.Model):
    """Queue row for the WAHA verify-link / recovery flow.

    Two kinds of job, sharing the same queue + drain worker:
      - `auto_import`     : created by the auto-import send_whatsapp stage;
                            asks the customer to pin their delivery location.
      - `delivery_failed` : created when a driver marks a task failed; sent
                            10 min after the failure (via `scheduled_for`)
                            with the driver's reason + a fresh verify link.

    When the customer replies with a WhatsApp location pin, the WAHA webhook
    matches it via `phone` and updates the order's coordinates.
    """

    KIND_CHOICES = [
        ('auto_import',     'Auto-Import Verify'),
        ('delivery_failed', 'Delivery Recovery'),
    ]
    STATUS_CHOICES = [
        ('queued',            'Queued for send'),
        ('sent',              'Sent — awaiting reply'),
        ('verified',          'Verified — coords applied'),
        ('manual_review',     'Manual review needed'),
        ('failed',            'Send failed'),
        ('cancelled',         'Cancelled'),
    ]

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='address_verification_jobs',
    )
    phone = models.CharField(max_length=32, db_index=True,
                             help_text='Digits-only phone (matches WhatsAppMessage.from_number)')

    kind = models.CharField(
        max_length=20, choices=KIND_CHOICES, default='auto_import', db_index=True,
        help_text='Why this job exists (auto-import vs delivery-failed recovery)',
    )
    # When the drain worker is allowed to send. NULL = send immediately.
    # delivery_failed jobs set this to created_at + 10 min so the driver has a
    # grace period to undo before the customer is contacted.
    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True)
    # Captured for delivery_failed jobs only — included in the recovery msg.
    driver_failure_note = models.TextField(blank=True, default='')

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued', db_index=True)
    send_attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True, default='')

    # FKs to the bridge rows so we can audit the full conversation.
    sent_message = models.ForeignKey(
        WhatsAppMessage,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verification_jobs_sent',
    )
    received_message = models.ForeignKey(
        WhatsAppMessage,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verification_jobs_received',
    )

    # Coords that were applied to the Order (kept here for audit even if Order
    # changes later).
    applied_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    applied_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Address Verification Job'
        verbose_name_plural = 'Address Verification Jobs'
        ordering = ['-created_at']
        indexes = [
            # Fast lookup: when a location arrives for `phone`, find the most
            # recent sent-but-unreplied job within the 24h window.
            models.Index(fields=['phone', 'status', 'sent_at']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f'AVJ#{self.pk} order={self.order_id} phone={self.phone} {self.status}'
