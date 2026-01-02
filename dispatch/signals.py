"""
Dispatch Signals - Event handlers for dispatch system.

Handles:
- Batch status changes
- Shift status changes
- Order completion tracking
"""
import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger('dispatch')

# We don't register order signals here - they are handled in orders/signals.py
# to maintain the existing signal flow and add the batching branch.

# Batch signals could be added here for future extensions
# e.g., triggering notifications when batch status changes
