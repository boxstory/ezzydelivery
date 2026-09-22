# Purpose: Read recent untriaged CRM WhatsApp conversations and REPORT who looks like a driver applicant or a business prospect. Reporting only by default — it does not create leads.
# Used by: run by hand for a read on the inbox. NOT on cron: a conversation is no longer allowed to create a CRM card.
# Notes: Filing from a conversation is switched off deliberately — a lead is created when the person submits the driver join form or the pricing enquiry, never because they messaged us. --promote restores the old auto-filing for a one-off run and must be passed on purpose.

import time

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from crm import wa_inbox, wa_triage
from crm.models import Lead


class Command(BaseCommand):
    help = ('Report which recent unknown WhatsApp senders look like drivers or businesses. '
            'Creates nothing unless --promote is passed.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=7,
            help='Only senders whose last message is within this many days (default 7). '
                 'Keeps the historic backlog in the inbox for manual triage.')
        parser.add_argument(
            '--limit', type=int, default=60,
            help='Most senders to classify in one run (default 60). Caps the AI spend.')
        parser.add_argument(
            '--min-confidence', type=float, default=wa_triage.DEFAULT_MIN_CONFIDENCE,
            help='Confidence needed to file a lead (default %.2f). Anything lower stays '
                 'in the inbox.' % wa_triage.DEFAULT_MIN_CONFIDENCE)
        parser.add_argument(
            '--session', default='',
            help='Limit to one WAHA session (one of our numbers). Default: all of them.')
        parser.add_argument(
            '--promote', action='store_true',
            help='Actually file confident senders onto a board. OFF by default: a lead '
                 'belongs to someone who filled the driver join form or the pricing '
                 'enquiry, not to everyone who sent us a message.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Deprecated — reporting is now the default. Kept so old invocations '
                 'still run.')
        parser.add_argument(
            '--no-cache', action='store_true',
            help='Re-read conversations even if a verdict is already cached.')
        parser.add_argument(
            '--sleep', type=float, default=2.0,
            help='Seconds to pause between AI calls (default 2). The chat provider '
                 'rate-limits bursts; pausing keeps a run from burning the quota.')
        parser.add_argument('--quiet', action='store_true', help='Only print the summary line.')

    def handle(self, *args, **options):
        days = max(1, options['days'])
        limit = max(1, options['limit'])
        threshold = min(1.0, max(0.0, options['min_confidence']))
        # Reporting is the floor, not a flag: filing only happens when a human
        # explicitly asks for it on this run.
        dry_run = not options['promote'] or options['dry_run']
        verbose = not options['quiet']

        cutoff = timezone.now() - timedelta(days=days)
        rows = wa_inbox.collect_senders(session_filter=options['session'])
        recent = [r for r in rows if r.get('last_at') and r['last_at'] >= cutoff]

        if verbose:
            self.stdout.write(
                f'{len(rows)} untriaged senders, {len(recent)} active in the last {days} day(s).')

        driver_keys = wa_triage.driver_phone_keys()
        counts = {'driver': 0, 'business': 0, 'unclear': 0, 'skipped': 0, 'looked_at': 0}
        errors = 0
        # The chat provider answers 429 under load. A handful in a row means the
        # quota is gone for now, and hammering it only wastes the next run's budget.
        ai_failures = 0

        for row in recent:
            if counts['looked_at'] >= limit:
                if verbose:
                    self.stdout.write(f'Limit of {limit} reached — the rest wait for tomorrow.')
                break

            session = row['session']
            number = row['from_number']
            phone = wa_triage.promotable_phone(row.get('real_number') or number)
            if not phone:
                counts['skipped'] += 1
                self._say(verbose, f'  skip {row.get("real_number") or number}: '
                                   f'no callable number behind this sender id')
                continue

            # An open lead on this number is already flagged by the inbox itself.
            if row.get('existing_lead_id'):
                counts['skipped'] += 1
                self._say(verbose, f'  skip {phone}: lead #{row["existing_lead_id"]} is open')
                continue

            blocked = wa_triage.existing_board_record(phone, driver_keys=driver_keys)
            if blocked:
                counts['skipped'] += 1
                self._say(verbose, f'  skip {phone}: {blocked}')
                continue

            counts['looked_at'] += 1
            verdict = wa_triage.classify(
                session, number, last_at=row.get('last_at'),
                use_cache=not options['no_cache'],
            )
            category = verdict['category']
            confidence = verdict['confidence']

            if verdict['reason'].startswith(('AI error', 'AI unavailable')):
                ai_failures += 1
                counts['unclear'] += 1
                self._say(verbose, f'  leave {phone}: {verdict["reason"]}')
                if ai_failures >= 5:
                    self.stderr.write(
                        'AI refused 5 times in a row — stopping so the rest keep '
                        'their turn on the next run.')
                    break
                continue
            ai_failures = 0
            if not verdict['cached'] and options['sleep'] > 0:
                time.sleep(options['sleep'])

            if not category or confidence < threshold:
                counts['unclear'] += 1
                label = category or 'unknown'
                self._say(verbose, f'  leave {phone}: {label} @ {confidence:.0%} — '
                                   f'{verdict["reason"]}')
                continue

            board = 'driver' if category == Lead.CATEGORY_DRIVER else 'business'
            if dry_run:
                counts[board] += 1
                self._say(verbose, f'  WOULD file {phone} -> {board} @ {confidence:.0%} — '
                                   f'{verdict["reason"]}')
                continue

            try:
                lead, created = wa_triage.promote(
                    phone, category, verdict, session=session, from_number=number)
            except Exception as exc:
                errors += 1
                self.stderr.write(f'  FAILED {phone}: {exc}')
                continue

            if created:
                counts[board] += 1
                self._say(verbose, f'  filed {phone} -> {board} lead #{lead.pk} '
                                   f'@ {confidence:.0%} — {verdict["reason"]}')
            else:
                counts['skipped'] += 1
                self._say(verbose, f'  skip {phone}: lead #{lead.pk} already existed')

        summary = (
            'WA inbox triage: {business} business, {driver} driver, {unclear} left unclear, '
            '{skipped} already known ({looked_at} conversations read)'.format(**counts)
        )
        if errors:
            summary += f', {errors} failed'
        if dry_run:
            summary += (' [REPORT ONLY — nothing created; leads come from a submitted '
                        'form, pass --promote to override]')
        self.stdout.write(self.style.SUCCESS(summary))

    def _say(self, verbose, line):
        if verbose:
            self.stdout.write(line)
