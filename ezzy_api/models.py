"""
Ezzy API Models Module
======================

This module contains models for API management, webhooks, and document storage.

Models:
    API Authentication:
        - ClientApiKey: API keys for business authentication

    Documents:
        - TaskDocument: Documents attached to delivery tasks
        - OrderDocument: Documents attached to orders

    Integrations:
        - EcommerceIntegration: Track e-commerce platform connections

    Webhooks:
        - WebhookEndpoint: Webhook configuration for external notifications
        - WebhookDelivery: Track webhook delivery attempts

API Key System:
    - Auto-generates unique 32-char API keys
    - Supports expiration dates
    - Tracks last usage for monitoring

Webhook Events:
    - task_status_update: Delivery task status changes
    - task_completed: Task completion notification
    - task_accepted/rejected: Driver acceptance
    - driver_location_update: Real-time driver location
    - cod_collected: COD collection confirmation
    - document_uploaded: New document notification

Document Types:
    Task: delivery_proof, signature, photo, invoice, receipt
    Order: invoice, receipt, label, manifest

Related:
    - business.models.Business: API key owner
    - delivery.models.DeliveryTask: Task documents
    - orders.models.Order: Order documents
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from business import models as business_models
from delivery import models as delivery_models
from orders import models as orders_models
import os

User = get_user_model()


# =============================================================================
# UPLOAD PATH HANDLERS
# =============================================================================


def api_key_upload_path(instance, filename):
    """Generate upload path for API key documents"""
    return f'api_keys/{instance.business.business_id}/{filename}'


def task_document_upload_path(instance, filename):
    """Generate upload path for task documents"""
    return f'tasks/{instance.task.id}/documents/{filename}'


def order_document_upload_path(instance, filename):
    """Generate upload path for order documents"""
    return f'orders/{instance.order.id}/documents/{filename}'


class ClientApiKey(models.Model):
    """API Key model for business authentication"""
    business = models.ForeignKey(
        business_models.Business,
        on_delete=models.CASCADE,
        related_name='api_keys'
    )
    api_key = models.CharField(max_length=64, unique=True, db_index=True)
    api_secret = models.CharField(max_length=64, blank=True, null=True)
    key_name = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    last_used = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_api_keys'
    )

    class Meta:
        verbose_name_plural = "Client API Keys"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business.business_name} - {self.api_key[:8]}..."

    def save(self, *args, **kwargs):
        if not self.api_key:
            # Generate a unique API key
            while True:
                key = get_random_string(32)
                if not ClientApiKey.objects.filter(api_key=key).exists():
                    self.api_key = key
                    break
        if not self.api_secret:
            # Generate a secret key
            self.api_secret = get_random_string(32)
        super().save(*args, **kwargs)

    def is_valid(self):
        """Check if API key is valid and not expired"""
        from django.utils import timezone
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class WebhookImportKey(models.Model):
    """Unique inbound webhook key per business for receiving orders via POST."""
    business = models.OneToOneField(
        business_models.Business,
        on_delete=models.CASCADE,
        related_name='webhook_import_key',
    )
    key = models.CharField(max_length=48, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(blank=True, null=True)
    total_received = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Webhook Import Keys"

    def __str__(self):
        return f"{self.business.business_name} - {self.key[:12]}..."

    def save(self, *args, **kwargs):
        if not self.key:
            while True:
                k = get_random_string(40)
                if not WebhookImportKey.objects.filter(key=k).exists():
                    self.key = k
                    break
        super().save(*args, **kwargs)


class WebhookImportLog(models.Model):
    """Log each inbound webhook call with raw JSON payload."""
    webhook_key = models.ForeignKey(
        WebhookImportKey, on_delete=models.CASCADE, related_name='logs',
    )
    business = models.ForeignKey(
        business_models.Business, on_delete=models.CASCADE, related_name='webhook_import_logs',
    )
    payload = models.JSONField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    headers = models.JSONField(blank=True, null=True)
    status = models.CharField(max_length=20, default='received', choices=[
        ('received', 'Received'),
        ('processed', 'Processed'),
        ('error', 'Error'),
    ])
    error_message = models.TextField(blank=True, default='')
    orders_created = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Webhook Import Logs"

    def __str__(self):
        return f"Webhook {self.business.business_name} @ {self.created_at}"


class TaskDocument(models.Model):
    """Document model for delivery tasks (DMS uploads)"""
    DOCUMENT_TYPES = (
        ('delivery_proof', 'Delivery Proof'),
        ('signature', 'Customer Signature'),
        ('photo', 'Photo'),
        ('invoice', 'Invoice'),
        ('receipt', 'Receipt'),
        ('other', 'Other'),
    )
    
    task = models.ForeignKey(
        delivery_models.DeliveryTask,
        on_delete=models.CASCADE,
        related_name='task_documents'
    )
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES, default='other')
    document_file = models.FileField(upload_to=task_document_upload_path)
    document_name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Task Documents"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task.dl_task_number} - {self.document_type}"


class OrderDocument(models.Model):
    """Document model for orders (DMS uploads)"""
    DOCUMENT_TYPES = (
        ('invoice', 'Invoice'),
        ('receipt', 'Receipt'),
        ('label', 'Shipping Label'),
        ('manifest', 'Manifest'),
        ('other', 'Other'),
    )
    
    order = models.ForeignKey(
        orders_models.Order,
        on_delete=models.CASCADE,
        related_name='order_documents'
    )
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES, default='other')
    document_file = models.FileField(upload_to=order_document_upload_path)
    document_name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Order Documents"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order.order_number} - {self.document_type}"


class EcommerceIntegration(models.Model):
    """Model to track e-commerce platform integrations"""
    INTEGRATION_STATUS = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('error', 'Error'),
        ('pending', 'Pending'),
    )
    
    business = models.ForeignKey(
        business_models.Business,
        on_delete=models.CASCADE,
        related_name='ecommerce_integrations'
    )
    platform = models.CharField(max_length=50)  # shopify, woocommerce, etc.
    api_settings = models.ForeignKey(
        business_models.BusinessApiSettings,
        on_delete=models.CASCADE,
        related_name='integrations'
    )
    last_sync = models.DateTimeField(blank=True, null=True)
    sync_status = models.CharField(max_length=20, choices=INTEGRATION_STATUS, default='pending')
    sync_error = models.TextField(blank=True, null=True)
    total_orders_imported = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "E-commerce Integrations"
        unique_together = ('business', 'platform')

    def __str__(self):
        return f"{self.business.business_name} - {self.platform}"


class WebhookEndpoint(models.Model):
    """Webhook endpoint configuration for receiving driver app status updates"""
    WEBHOOK_EVENTS = (
        ('task_status_update', 'Task Status Update'),
        ('task_completed', 'Task Completed'),
        ('task_accepted', 'Task Accepted'),
        ('task_rejected', 'Task Rejected'),
        ('driver_location_update', 'Driver Location Update'),
        ('driver_status_change', 'Driver Status Change'),
        ('cod_collected', 'COD Collected'),
        ('document_uploaded', 'Document Uploaded'),
    )
    
    business = models.ForeignKey(
        business_models.Business,
        on_delete=models.CASCADE,
        related_name='webhook_endpoints',
        null=True,
        blank=True
    )
    url = models.URLField(max_length=500)
    events = models.JSONField(default=list, help_text="List of event types to subscribe to")
    secret = models.CharField(max_length=64, help_text="Secret key for webhook signature verification")
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_triggered = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Webhook Endpoints"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.url} - {len(self.events)} events"
    
    def save(self, *args, **kwargs):
        if not self.secret:
            self.secret = get_random_string(32)
        super().save(*args, **kwargs)


class WebhookDelivery(models.Model):
    """Track webhook delivery attempts and responses"""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    )
    
    webhook = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name='deliveries'
    )
    event_type = models.CharField(max_length=50)
    payload = models.JSONField()
    response_status = models.IntegerField(blank=True, null=True)
    response_body = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True)
    attempt_count = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = "Webhook Deliveries"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.webhook.url} - {self.event_type} - {self.status}"
