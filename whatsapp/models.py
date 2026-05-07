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

    waha_message_id = models.CharField(max_length=128, unique=True, db_index=True)
    session = models.CharField(max_length=64, default='default')
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES)

    from_number = models.CharField(max_length=64, db_index=True, blank=True, default='')
    to_number = models.CharField(max_length=64, db_index=True, blank=True, default='')

    body = models.TextField(blank=True, default='')
    message_type = models.CharField(max_length=16, choices=MESSAGE_TYPE_CHOICES, default='text')

    media_url = models.CharField(max_length=500, blank=True, default='')
    media_mime = models.CharField(max_length=80, blank=True, default='')

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
