# Purpose: Pull full WhatsApp chat history from WAHA for CRM leads that have a synced WhatsAppContact
#          (so the phone genuinely has a WhatsApp presence) but no WhatsAppMessage rows locally yet.
# Used by: manual run (python manage.py backfill_lead_wa_chats [--source pricing_inquiry|all] [--dry-run]).
#          Safe to re-run — upsert_message dedupes on waha_message_id.
# Notes: Some contacts' chats are indexed by WhatsApp LID rather than phone JID (privacy mode) — this
#        tries "<lid>@lid" first (if a WhatsAppContact resolved one), then "<phone>@c.us" as a fallback.
#        A phone-based chatId can resolve fine in WAHA while every message inside is still stamped with
#        an unmapped LID (no WhatsAppContact row yet) — when that happens this re-points the lead's
#        override at the LID actually seen in the messages, not the phone we searched with.

import random
import time

from django.core.management.base import BaseCommand
from django.db.models import Q

from crm import services as crm_services
from crm.models import Lead


class Command(BaseCommand):
    help = ('Backfill WhatsApp chat history for CRM leads with a matching WhatsAppContact '
            'but no synced WhatsAppMessage rows yet.')

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, default=Lead.SOURCE_PRICING,
                             help="Lead source to scan (default: pricing_inquiry). Use 'all' for every source.")
        parser.add_argument('--dry-run', action='store_true',
                             help='Report which leads would be checked without calling WAHA.')
        parser.add_argument('--min-sleep', type=float, default=1.5)
        parser.add_argument('--max-sleep', type=float, default=3.5)

    def handle(self, *args, **opts):
        from django.conf import settings

        from whatsapp.models import WhatsAppContact
        from whatsapp.waha_backfill import pull_chat_history
        from workforce.crm_views import _annotate_wa_chats

        source = opts['source']
        qs = Lead.objects.exclude(phone='')
        if source != 'all':
            qs = qs.filter(source=source)
        leads = list(qs)
        _annotate_wa_chats(leads)
        candidates = [lead for lead in leads if not lead.has_wa_chat]

        self.stdout.write(
            f'{len(leads)} lead(s) scanned (source={source}), '
            f'{len(candidates)} without a matched chat yet.'
        )

        session = settings.WAHA_DEFAULT_SESSION
        checked = connected = inserted_total = lid_resolved = 0

        for lead in candidates:
            phone = crm_services.normalize_phone(lead.phone)
            override = crm_services.normalize_phone(lead.wa_chat_override or '')
            base = override or phone
            if not base:
                continue
            variants = crm_services._phone_variants(base)

            contact = (
                WhatsAppContact.objects
                .filter(Q(phone__in=list(variants)) | Q(lid=base))
                .exclude(lid='')
                .first()
            )
            chat_id_candidates = []
            if contact:
                chat_id_candidates.append(f'{contact.lid}@lid')
            elif len(base) >= 12:
                chat_id_candidates.append(f'{base}@lid')
            best_variant = next((v for v in variants if len(v) in (8, 11)), base)
            chat_id_candidates.append(f'{best_variant}@c.us')

            checked += 1
            if opts['dry_run']:
                self.stdout.write(f'lead {lead.pk} ({lead.phone}): would try {chat_id_candidates}')
                continue

            for chat_id in chat_id_candidates:
                try:
                    seen, inserted, counterparties = pull_chat_history(chat_id, session=session)
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f'lead {lead.pk}: {chat_id} failed: {e}'))
                    continue
                if seen:
                    connected += 1
                    inserted_total += inserted
                    note = ''
                    lid_counterparties = {c for c in counterparties if c.endswith('@lid')}
                    if lid_counterparties:
                        resolved_lid = next(iter(lid_counterparties)).replace('@lid', '')
                        if resolved_lid and resolved_lid != lead.wa_chat_override:
                            lead.wa_chat_override = resolved_lid[:50]
                            lead.save(update_fields=['wa_chat_override', 'updated_at'])
                            lid_resolved += 1
                            note = f' [unmapped LID resolved: {resolved_lid}]'
                    self.stdout.write(
                        f'lead {lead.pk} ({lead.phone}): connected via {chat_id} '
                        f'({seen} messages, {inserted} new){note}'
                    )
                    break

            time.sleep(random.uniform(opts['min_sleep'], opts['max_sleep']))

        self.stdout.write(self.style.SUCCESS(
            f'done. checked={checked} newly_connected={connected} '
            f'unmapped_lid_resolved={lid_resolved} messages_inserted={inserted_total}'
        ))
