"""
Celery wrappers for WhatsApp/WAHA periodic work.
Scheduled in ezzydelivery/celery.py beat_schedule.
"""
from celery import shared_task
from django.core.management import call_command


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
