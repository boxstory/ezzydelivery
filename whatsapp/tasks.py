"""
Celery wrappers for WhatsApp/WAHA periodic work.
Scheduled in ezzydelivery/celery.py beat_schedule.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone


logger = logging.getLogger(__name__)


@shared_task(name='whatsapp.tasks.run_backfill', ignore_result=True)
def run_backfill(skip_today=True, days=120, limit_per_chat=100, max_chats=200,
                 min_sleep=3, max_sleep=8, force=False, session=None):
    args = []
    if skip_today:
        args.append('--skip-today')
    if force:
        args.append('--force')
    args += [
        f'--days={days}',
        f'--limit-per-chat={limit_per_chat}',
        f'--max-chats={max_chats}',
        f'--min-sleep={min_sleep}',
        f'--max-sleep={max_sleep}',
    ]
    if session:
        args.append(f'--session={session}')
    call_command('backfill_waha', *args)


@shared_task(name='whatsapp.tasks.sync_wa_contacts', ignore_result=True)
def sync_wa_contacts(session=None):
    """Refresh the WhatsAppContact directory from WAHA (lids + contacts)."""
    from whatsapp.contacts import sync_contacts
    try:
        result = sync_contacts(session=session)
        logger.info('wa contact sync: %s', result)
    except Exception:
        logger.exception('wa contact sync failed')


# =============================================================================
# Address Verification Queue Drain
# =============================================================================

@shared_task(name='whatsapp.tasks.drain_verification_queue', ignore_result=True)
def drain_verification_queue():
    """Drain the AddressVerificationJob queue, rate-limited.

    Called every minute by Celery beat. Picks up to WAHA_VERIFY_SEND_RATE
    jobs in status='queued', sends the verify-link WhatsApp message, and
    flips the job to 'sent'. Errors are recorded as last_error + attempt
    increment; jobs that fail 3+ times are flipped to 'failed'.

    Send path priority:
      1. WAHA (if WAHA_ENABLED) — so the inbound reply lands on WAHA webhook.
      2. Evolution API fallback (existing path).
    """
    from datetime import timedelta
    from django.db import transaction

    from whatsapp.models import AddressVerificationJob
    from whatsapp.waha_views import send_waha_text
    # Late import — workforce/views.py imports whatsapp, avoid a cycle.
    from workforce.views import (
        _build_order_whatsapp_message,
        _build_delivery_recovery_whatsapp_message,
        _send_order_whatsapp_internal,
    )

    rate = max(1, int(getattr(settings, 'WAHA_VERIFY_SEND_RATE', 20)))
    per_biz_hour = max(1, int(getattr(settings, 'WAHA_VERIFY_PER_BUSINESS_MAX_PER_HOUR', 50)))
    max_attempts = max(1, int(getattr(settings, 'WAHA_VERIFY_MAX_ATTEMPTS', 3)))
    # Per-feature flag — independent of WAHA_ENABLED (which controls platform-
    # wide order notification routing). Falling back to WAHA_ENABLED keeps the
    # original "use WAHA when platform-wide enabled" behavior if the verify
    # flag isn't set.
    use_waha = bool(
        getattr(settings, 'WAHA_VERIFY_USE_WAHA', False)
        or getattr(settings, 'WAHA_ENABLED', False)
    )

    # Runtime kill switch — ops can pause all verify-queue sends from the
    # banner without a redeploy. Defaults to ON when the table is empty.
    try:
        from whatsapp.models import WahaConfig
        if not WahaConfig.get_solo().verify_messaging_enabled:
            logger.info('drain_verification_queue: messaging is paused (runtime toggle)')
            return {'sent': 0, 'skipped': 0, 'failed': 0, 'paused': True}
    except Exception:
        # Defensive — if the migration isn't ready, fall through to normal send.
        pass

    # Per-business throttle: count sends in the last hour, skip when over.
    cutoff = timezone.now() - timedelta(hours=1)
    now = timezone.now()
    # Filter on scheduled_for: jobs with scheduled_for in the future are not
    # yet eligible (delivery_failed grace window). NULL means "send now".
    from django.db.models import Q
    candidate_qs = (
        AddressVerificationJob.objects
        .select_related('order', 'order__business')
        .filter(status='queued')
        .filter(Q(scheduled_for__isnull=True) | Q(scheduled_for__lte=now))
        .order_by('created_at')[:rate * 3]   # over-fetch; we filter per-biz
    )

    sent_count = 0
    skipped = 0
    failed = 0
    biz_hour_counts = {}  # business_id -> sends in last hour

    for job in candidate_qs:
        if sent_count >= rate:
            break

        biz_id = job.order.business_id
        # Lazy-compute the per-business hour count once per business.
        if biz_id not in biz_hour_counts:
            biz_hour_counts[biz_id] = AddressVerificationJob.objects.filter(
                order__business_id=biz_id,
                status__in=('sent', 'verified', 'manual_review'),
                sent_at__gte=cutoff,
            ).count()
        if biz_hour_counts[biz_id] >= per_biz_hour:
            skipped += 1
            continue

        if job.kind == 'delivery_failed':
            text = _build_delivery_recovery_whatsapp_message(job.order, job.driver_failure_note)
        else:
            text = _build_order_whatsapp_message(job.order)
        ok, info = (False, {'error': 'no sender'})
        sent_msg = None

        if use_waha:
            ok, info = send_waha_text(job.phone, text)
            sent_msg = info.get('message_obj') if ok else None

        if not ok:
            # Evolution fallback (legacy path). Logs no WhatsAppMessage.
            ok, info = _send_order_whatsapp_internal(job.order, message=text)

        with transaction.atomic():
            job.send_attempts = (job.send_attempts or 0) + 1
            if ok:
                job.status = 'sent'
                job.sent_at = timezone.now()
                if sent_msg is not None:
                    job.sent_message = sent_msg
                job.last_error = ''
                biz_hour_counts[biz_id] += 1
                sent_count += 1
            else:
                job.last_error = str(info.get('error', ''))[:250]
                if job.send_attempts >= max_attempts:
                    job.status = 'failed'
                    failed += 1
                # else: stays 'queued', will retry next tick
            job.save(update_fields=[
                'send_attempts', 'status', 'sent_at',
                'sent_message', 'last_error',
            ])

    logger.info(
        'drain_verification_queue: sent=%s skipped_per_biz=%s failed=%s',
        sent_count, skipped, failed,
    )
    return {'sent': sent_count, 'skipped': skipped, 'failed': failed}
