# Purpose: One-time/rerunnable backfill of CRM Leads from existing PricingEnquiry and WhatsAppInquiry rows.
# Used by: manual run at deploy time (python manage.py backfill_crm_leads [--dry-run] [--include-incomplete]).
# Notes: Idempotent — lead creation is get_or_create on the OneToOne link, so re-runs create nothing new.

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ('Create CRM Lead rows for existing pricing inquiries (complete only, '
            'unless --include-incomplete) and WhatsApp quick inquiries. Safe to re-run.')

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would be created without writing.')
        parser.add_argument('--include-incomplete', action='store_true',
                            help='Also backfill incomplete (abandoned mid-form) pricing inquiries.')

    def handle(self, *args, **options):
        from crm.services import (create_lead_from_pricing_inquiry,
                                  create_lead_from_whatsapp_inquiry)
        from webpages.models import PricingEnquiry, WhatsAppInquiry

        dry_run = options['dry_run']

        pricing_qs = PricingEnquiry.objects.all()
        if not options['include_incomplete']:
            pricing_qs = pricing_qs.filter(is_complete=True)
        pricing_qs = pricing_qs.filter(lead__isnull=True).order_by('pk')

        wa_qs = WhatsAppInquiry.objects.filter(lead__isnull=True).order_by('pk')

        if dry_run:
            self.stdout.write(
                f'[dry-run] Would create {pricing_qs.count()} lead(s) from pricing '
                f'inquiries and {wa_qs.count()} from WhatsApp inquiries.'
            )
            return

        created_pricing = sum(
            1 for inquiry in pricing_qs.iterator()
            if create_lead_from_pricing_inquiry(inquiry)[1]
        )
        created_wa = sum(
            1 for inquiry in wa_qs.iterator()
            if create_lead_from_whatsapp_inquiry(inquiry)[1]
        )
        self.stdout.write(self.style.SUCCESS(
            f'Created {created_pricing} lead(s) from pricing inquiries, '
            f'{created_wa} from WhatsApp inquiries.'
        ))
