# Purpose: Morning cron — WhatsApp one reminder to each prospect who started the 3PL pricing
#          form yesterday and left without finishing, with a link that resumes their answers.
# Used by: cron (see --help); sends via core.whatsapp_utils.send_inquiry_resume_nudge.
# Notes: Never messages anyone twice (PricingEnquiry.resume_nudge_sent_at) and never messages
#        someone who started today — the day boundary is Asia/Qatar, not the server's UTC.

import logging
import re
from datetime import time as dt_time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

QATAR_TZ = 'Asia/Qatar'

# A Qatar mobile is 8 digits opening 3/5/6/7, optionally behind the 974 country
# code. The form takes free text, so the abandoned rows include scraper traffic
# from every country — messaging those costs money and teaches us nothing.
QATAR_LOCAL = re.compile(r'^[3567]\d{7}$')
QATAR_INTL = re.compile(r'^974[3567]\d{7}$')


def is_plausible_qatar_number(raw):
    from crm.services import normalize_phone
    digits = normalize_phone(raw)
    return bool(QATAR_LOCAL.match(digits) or QATAR_INTL.match(digits))


class Command(BaseCommand):
    help = ('WhatsApp a resume link to prospects who abandoned the 3PL pricing form. '
            'Intended to run once each morning:  30 6 * * *  (server UTC = 09:30 Qatar). '
            'Always try --dry-run first; it reports exactly who would be messaged and sends '
            'nothing.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List who would be messaged and exit without sending or stamping anything.')
        parser.add_argument(
            '--max-age-days', type=int, default=3,
            help='Ignore inquiries abandoned longer ago than this (default 3). Stops a first '
                 'run from messaging the whole historical backlog.')
        parser.add_argument(
            '--limit', type=int, default=50,
            help='Most messages to send in one run (default 50).')
        parser.add_argument(
            '--allow-any-country', action='store_true',
            help='Also message numbers that are not Qatar mobiles. Off by default — the '
                 'abandoned rows carry a lot of overseas scraper traffic.')

    def handle(self, *args, **options):
        from django.conf import settings
        from core.whatsapp_utils import send_inquiry_resume_nudge, trigger_enabled
        from webpages.models import PricingEnquiry

        dry_run = options['dry_run']

        # Checked up front, not per-send: if the switch is off, send_inquiry_resume_nudge
        # returns disabled for every row and we would stamp them all as nudged.
        if not trigger_enabled('wa_inquiry_resume_nudge'):
            self.stdout.write(self.style.WARNING(
                'Trigger "wa_inquiry_resume_nudge" is switched off on the Auto Triggers page. '
                'Nothing sent.'))
            return

        try:
            import zoneinfo
            qatar = zoneinfo.ZoneInfo(QATAR_TZ)
        except Exception:
            qatar = timezone.get_current_timezone()

        now_qatar = timezone.now().astimezone(qatar)
        # Anyone who started today may still be filling the form in — the cutoff is
        # midnight Qatar, so the morning run only ever picks up yesterday and older.
        today_start = timezone.make_aware(
            timezone.datetime.combine(now_qatar.date(), dt_time.min), qatar)
        window_start = today_start - timedelta(days=options['max_age_days'])

        candidates = (PricingEnquiry.objects
                      .filter(is_complete=False,
                              resume_nudge_sent_at__isnull=True,
                              date_created__gte=window_start,
                              date_created__lt=today_start)
                      .exclude(business_contact_number='')
                      .exclude(business_contact_number=None)
                      .order_by('date_created'))

        base_url = (getattr(settings, 'SITE_URL', '') or 'https://ezzydelivery.qa').rstrip('/')

        sent = skipped = failed = 0
        for inquiry in candidates:
            phone = (inquiry.business_contact_number or '').strip()
            label = f'#{inquiry.pk} {(inquiry.business_name or "—")[:28]}'

            if not options['allow_any_country'] and not is_plausible_qatar_number(phone):
                self.stdout.write(f'  skip  {label:<34} {phone}  (not a Qatar mobile)')
                skipped += 1
                continue

            if sent >= options['limit']:
                self.stdout.write(self.style.WARNING(
                    f'  limit of {options["limit"]} reached — {candidates.count() - sent - skipped} '
                    f'candidate(s) left for the next run'))
                break

            resume_url = f'{base_url}/3pl/inquiry/resume/{inquiry.quote_token}/'

            if dry_run:
                self.stdout.write(f'  WOULD SEND  {label:<34} {phone}  {resume_url}')
                sent += 1
                continue

            try:
                result = send_inquiry_resume_nudge(
                    phone, (inquiry.business_name or '').strip(), resume_url)
            except Exception:
                logger.exception('Resume nudge failed for PricingEnquiry %s', inquiry.pk)
                result = {'success': False, 'error': 'exception'}

            if result.get('success'):
                # Stamped only on a real send, so a failure is retried tomorrow
                # rather than silently dropped.
                inquiry.resume_nudge_sent_at = timezone.now()
                inquiry.save(update_fields=['resume_nudge_sent_at'])
                self.stdout.write(self.style.SUCCESS(f'  sent  {label:<34} {phone}'))
                sent += 1
            else:
                self.stdout.write(self.style.ERROR(
                    f'  FAIL  {label:<34} {phone}  {result.get("error", "unknown")}'))
                failed += 1

        verb = 'would send' if dry_run else 'sent'
        self.stdout.write(self.style.SUCCESS(
            f'{verb}: {sent}   skipped: {skipped}   failed: {failed}'
            f'   (window {window_start:%d %b} → {today_start:%d %b} Qatar)'))
