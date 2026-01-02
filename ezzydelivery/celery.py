"""
Celery configuration for EzzyDelivery project.
Handles async tasks for batch timer engine, auto-assignment, and KPI calculation.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')

# Create Celery app
app = Celery('ezzydelivery')

# Load config from Django settings, namespace='CELERY'
# This means all celery-related config keys should have a `CELERY_` prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all registered Django apps
app.autodiscover_tasks()

# Beat schedule for periodic tasks
app.conf.beat_schedule = {
    # Check for expired batch hold windows - every 30 seconds
    'check-batch-timeouts': {
        'task': 'dispatch.tasks.check_batch_timeouts',
        'schedule': 30.0,
        'options': {'queue': 'dispatch'},
    },

    # Auto-assign ready batches to available riders - every 15 seconds
    'auto-assign-batches': {
        'task': 'dispatch.tasks.auto_assign_ready_batches',
        'schedule': 15.0,
        'options': {'queue': 'dispatch'},
    },

    # Check for SLA risk and force-release - every minute
    'check-sla-risk': {
        'task': 'dispatch.tasks.check_sla_risk',
        'schedule': 60.0,
        'options': {'queue': 'dispatch'},
    },

    # Auto-end expired shifts - every 5 minutes
    'check-shift-expirations': {
        'task': 'dispatch.tasks.check_shift_expirations',
        'schedule': 300.0,
        'options': {'queue': 'dispatch'},
    },

    # Calculate daily KPIs - daily at 00:05
    'calculate-daily-kpis': {
        'task': 'dispatch.tasks.calculate_daily_kpis',
        'schedule': crontab(hour=0, minute=5),
        'options': {'queue': 'dispatch'},
    },
}

# Task routing
app.conf.task_routes = {
    'dispatch.tasks.*': {'queue': 'dispatch'},
}

# Task default settings
app.conf.task_default_queue = 'default'
app.conf.task_acks_late = True  # Acknowledge after task completes
app.conf.task_reject_on_worker_lost = True


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery setup."""
    print(f'Request: {self.request!r}')
