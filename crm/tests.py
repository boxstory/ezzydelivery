# Purpose: Unit tests for crm.services — lead creation idempotency, stage sync, WA promote dedup, convert-to-business.
# Used by: python manage.py test crm

from django.contrib.auth.models import User
from django.test import TestCase

from business.models import Business
from webpages.models import PricingEnquiry, WhatsAppInquiry

from . import services
from .models import Lead, LeadActivity


def make_pricing_inquiry(**overrides):
    defaults = dict(
        full_name='Ali Hassan',
        business_name='Doha Sweets',
        business_contact_number='+974 5555-1234',
        product_category='Food',
        is_complete=True,
    )
    defaults.update(overrides)
    return PricingEnquiry.objects.create(**defaults)


class LeadCreationTests(TestCase):
    def test_create_from_pricing_inquiry_idempotent(self):
        inquiry = make_pricing_inquiry()
        lead1, created1 = services.create_lead_from_pricing_inquiry(inquiry)
        lead2, created2 = services.create_lead_from_pricing_inquiry(inquiry)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(lead1.pk, lead2.pk)
        self.assertEqual(lead1.source, Lead.SOURCE_PRICING)
        self.assertEqual(lead1.phone, '97455551234')
        self.assertEqual(lead1.stage, Lead.STAGE_NEW)
        self.assertEqual(lead1.activities.count(), 1)

    def test_crm_status_maps_to_stage(self):
        inquiry = make_pricing_inquiry(crm_status='converted')
        lead, _ = services.create_lead_from_pricing_inquiry(inquiry)
        self.assertEqual(lead.stage, Lead.STAGE_WON)

    def test_create_from_whatsapp_inquiry(self):
        inquiry = WhatsAppInquiry.objects.create(
            company_name='Lusail Gifts', contact_person='Sara',
            contact_number='97466660000', product_category='Gifts',
            product_name='Boxes', additional_info='Bulk orders',
        )
        lead, created = services.create_lead_from_whatsapp_inquiry(inquiry)
        self.assertTrue(created)
        self.assertEqual(lead.source, Lead.SOURCE_WA_FORM)
        self.assertIn('Boxes', lead.notes)
        _, created2 = services.create_lead_from_whatsapp_inquiry(inquiry)
        self.assertFalse(created2)

    def test_wa_number_promote_dedupes_open_lead(self):
        lead1, created1 = services.create_lead_from_wa_number('974 5000 0001')
        lead2, created2 = services.create_lead_from_wa_number('97450000001')
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(lead1.pk, lead2.pk)
        # A closed lead does not block a new one
        services.set_lead_stage(lead1, Lead.STAGE_LOST)
        lead3, created3 = services.create_lead_from_wa_number('97450000001')
        self.assertTrue(created3)
        self.assertNotEqual(lead1.pk, lead3.pk)


class StageSyncTests(TestCase):
    def test_set_stage_syncs_pricing_status_and_logs(self):
        inquiry = make_pricing_inquiry()
        lead, _ = services.create_lead_from_pricing_inquiry(inquiry)
        services.set_lead_stage(lead, Lead.STAGE_CONTACTED)
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.crm_status, 'contacted')
        self.assertTrue(lead.activities.filter(
            activity_type=LeadActivity.TYPE_STAGE_CHANGE).exists())
        self.assertIsNotNone(lead.stage_changed_at)
        self.assertIsNone(lead.closed_at)
        services.set_lead_stage(lead, Lead.STAGE_LOST)
        self.assertIsNotNone(lead.closed_at)

    def test_invalid_stage_rejected(self):
        lead = Lead.objects.create(source=Lead.SOURCE_MANUAL, company_name='X')
        with self.assertRaises(ValueError):
            services.set_lead_stage(lead, 'bogus')

    def test_sync_from_pricing_status_no_backwrite(self):
        inquiry = make_pricing_inquiry()
        lead, _ = services.create_lead_from_pricing_inquiry(inquiry)
        inquiry.crm_status = 'quoted'
        inquiry.save(update_fields=['crm_status'])
        services.sync_lead_from_pricing_status(inquiry)
        lead.refresh_from_db()
        self.assertEqual(lead.stage, Lead.STAGE_QUOTED)


class ConvertTests(TestCase):
    def test_convert_creates_pending_business_and_is_idempotent(self):
        user = User.objects.create_user('staff1', is_staff=True)
        inquiry = make_pricing_inquiry(website_url='https://dohasweets.qa')
        lead, _ = services.create_lead_from_pricing_inquiry(inquiry)

        business, created = services.convert_lead_to_business(lead)
        self.assertTrue(created)
        self.assertEqual(business.business_status, 'pending')
        self.assertEqual(business.business_name, 'Doha Sweets')
        self.assertEqual(business.business_phone, '97455551234')
        self.assertEqual(business.business_website, 'https://dohasweets.qa')
        self.assertTrue(100000 <= business.business_id <= 999999)

        lead.refresh_from_db()
        self.assertEqual(lead.stage, Lead.STAGE_WON)
        self.assertEqual(lead.converted_business_id, business.business_id)
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.crm_status, 'converted')

        business2, created2 = services.convert_lead_to_business(lead, user)
        self.assertFalse(created2)
        self.assertEqual(business2.pk, business.pk)
        self.assertEqual(Business.objects.count(), 1)


class DigestTests(TestCase):
    def test_digest_groups_and_dry_run(self):
        from datetime import timedelta
        from django.utils import timezone

        from core.models import Profile

        user = User.objects.create_user('staff2', is_staff=True)
        Profile.objects.get_or_create(user=user, defaults={'whatsapp': '97477770000'})

        yesterday = timezone.localdate() - timedelta(days=1)
        Lead.objects.create(source=Lead.SOURCE_MANUAL, company_name='A',
                            next_followup_at=yesterday, assigned_to=user)
        Lead.objects.create(source=Lead.SOURCE_MANUAL, company_name='B',
                            next_followup_at=yesterday)  # unassigned -> admin
        Lead.objects.create(source=Lead.SOURCE_MANUAL, company_name='C',
                            next_followup_at=yesterday, stage=Lead.STAGE_WON)  # closed, excluded

        grouped = services.build_followup_digest()
        self.assertEqual(len(grouped.get(user, [])), 1)
        self.assertEqual(len(grouped.get(None, [])), 1)

        result = services.send_followup_digests(dry_run=True)
        self.assertEqual(result['sent'], 0)
        self.assertEqual(len(result['recipients']), 2)
