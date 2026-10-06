"""
WhatsApp message store backed by the WAHA bridge.

One row per inbound or outbound message. Webhook upserts on `waha_message_id`.
The legacy `business.WhatsAppNotificationTrigger` model is unrelated — it
configures *what* to send for which order events; this table is the *log*.
"""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from core.validators import media_validators


def _private_media_storage():
    """Storage outside MEDIA_ROOT — customer WhatsApp media must not be
    reachable through the public /media/ nginx alias. Served only via the
    staff-gated CRM proxy view."""
    return FileSystemStorage(location=os.path.join(settings.BASE_DIR, 'private_media'))


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
        # Protocol chatter (encryption notices, hosted-account banners, group
        # membership changes). Nobody sent these; ingest drops them now, and
        # the label exists so the ones already stored can be told apart from a
        # real message we merely failed to classify ('unknown').
        ('system', 'System notification'),
        ('unknown', 'Unknown'),
    ]

    # NOT globally unique: WAHA message ids are unique per chat, not per
    # session, so the same id can legitimately arrive on two sessions. The
    # uniqueness that matters is (session, waha_message_id) — see Meta below.
    waha_message_id = models.CharField(max_length=255, db_index=True)
    session = models.CharField(max_length=64, default='default', db_index=True)
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES)

    from_number = models.CharField(max_length=64, db_index=True, blank=True, default='')
    to_number = models.CharField(max_length=64, db_index=True, blank=True, default='')

    body = models.TextField(blank=True, default='')
    message_type = models.CharField(max_length=16, choices=MESSAGE_TYPE_CHOICES, default='text')

    media_url = models.CharField(max_length=500, blank=True, default='')
    media_mime = models.CharField(max_length=80, blank=True, default='')
    # Local archive of the WAHA media file — WAHA purges its own copy within
    # minutes, so the archive_wa_media cron downloads it into private storage.
    media_file = models.FileField(
        upload_to='whatsapp/media/', storage=_private_media_storage,
        blank=True, default='', validators=media_validators(max_mb=25),
    )

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
            models.Index(fields=['session', 'received_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'waha_message_id'],
                name='waha_msg_unique_per_session',
            ),
        ]

    def __str__(self):
        return f'{self.direction} {self.from_number or self.to_number} {self.waha_message_id}'


class WhatsAppContact(models.Model):
    """Directory of WhatsApp contacts synced from WAHA — one row per phone.

    Persists the lid→phone mapping and names so the CRM inbox (and anything
    else) resolves senders from the DB instead of hitting WAHA per page load.
    Upserted by whatsapp.contacts.sync_contacts(); phone/lid are bare digits.

    Scoped per WAHA session: a lid identifies a contact *relative to the linked
    device*, so the same customer has a different lid on each of our numbers.
    One row per (session, phone) keeps the two syncs from overwriting each
    other's lid on every cron pass.
    """
    session = models.CharField(max_length=64, default='default', db_index=True)
    phone = models.CharField(max_length=32, db_index=True)
    lid = models.CharField(max_length=32, blank=True, default='', db_index=True)
    saved_name = models.CharField(max_length=255, blank=True, default='')
    push_name = models.CharField(max_length=255, blank=True, default='')
    is_business = models.BooleanField(default=False)
    is_my_contact = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
    # The WhatsApp Business labels on this contact's chat for this number, as
    # [{'id', 'name', 'colorHex'}]. WhatsApp stays the source of truth; this
    # mirror is what answers "who carries label X" without walking every chat
    # through WAHA. Written on every save and read in the inbox, refreshed
    # nightly by sync_wa_chat_labels. See whatsapp/chat_labels.py.
    labels = models.JSONField(default=list, blank=True)
    labels_synced_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'WhatsApp Contact'
        verbose_name_plural = 'WhatsApp Contacts'
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'phone'],
                name='waha_contact_unique_per_session',
            ),
        ]

    def __str__(self):
        return f'{self.phone} ({self.saved_name or self.push_name or "unnamed"})'

    @property
    def display_name(self):
        return self.saved_name or self.push_name or ''


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


class WhatsAppProfilePhoto(models.Model):
    """Saved copy of a chat's WhatsApp profile photo, per session.

    WhatsApp hands out profile-photo URLs on its CDN that expire within days, so
    the inbox keeps its own copy in private storage and refreshes it weekly.
    A row with has_photo=False records "this chat has no photo" so we do not
    ask WAHA again on every page load.
    """
    session = models.CharField(max_length=64)
    chat_id = models.CharField(max_length=100)
    photo = models.ImageField(
        upload_to='whatsapp/avatars/', storage=_private_media_storage,
        blank=True, validators=media_validators(2),
    )
    has_photo = models.BooleanField(default=False)
    fetched_at = models.DateTimeField()

    class Meta:
        unique_together = [('session', 'chat_id')]

    def __str__(self):
        return f'{self.session}:{self.chat_id}'


class RestrictedChatLabel(models.Model):
    """A WhatsApp label whose chats only marketing staff may open.

    Label ids are per number (session), so the same name on two numbers is two
    rows. `label_name` is a snapshot for the settings page, which can then still
    show a restricted label after it is renamed or deleted on the phone. Which
    chats carry the label is read live from WAHA (whatsapp/label_access.py).
    """
    session = models.CharField(max_length=64)
    label_id = models.CharField(max_length=64)
    label_name = models.CharField(max_length=120, blank=True, default='')
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+',
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('session', 'label_id')]
        ordering = ['session', 'label_name']

    def __str__(self):
        return f'{self.session}:{self.label_name or self.label_id}'


class InboxSessionAccess(models.Model):
    """One WhatsApp number (WAHA session) a staff member may open in the inbox.

    No row = that number is closed to them; super admins open every number and
    need no rows. Ticked on Staff Roles, enforced on every /waha/wa-chats/
    endpoint by whatsapp/session_access.py.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wa_inbox_sessions',
    )
    session = models.CharField(max_length=64)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+',
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'session')]
        ordering = ['user_id', 'session']

    def __str__(self):
        return f'{self.user_id}:{self.session}'


class WhatsAppReaction(models.Model):
    """One emoji reaction on a WhatsApp message, by one sender.

    WAHA's message list only says a message `hasReaction`, never which emoji,
    so reactions are kept here: ours when staff react from the inbox, and other
    people's from the `message.reaction` webhook event (once WAHA sends it).
    `message_id` is the reacted message's full serialized id, as the inbox keys
    its rows; `sender` is 'me' for our own number, else the bare phone/lid.
    An empty `emoji` is a removed reaction.
    """
    session = models.CharField(max_length=64, default='default', db_index=True)
    message_id = models.CharField(max_length=255, db_index=True)
    sender = models.CharField(max_length=64)
    emoji = models.CharField(max_length=32, blank=True, default='')
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'message_id', 'sender'],
                name='wa_reaction_one_per_sender',
            ),
        ]

    def __str__(self):
        return f'{self.sender} {self.emoji or "(removed)"} {self.message_id}'
