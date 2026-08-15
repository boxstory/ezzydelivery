# Purpose: Unit tests for crm.services — lead creation idempotency, stage sync, WA promote dedup, convert/link-to-business, and the staff-managed LeadStage board columns.
# Used by: python manage.py test crm
# Notes: LeadStage rows come from the 0006 seed migration, so tests read them rather than building columns; each stage test clears the stage cache first because it is process-wide.

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from business.models import Business
from webpages.models import PricingEnquiry, WhatsAppInquiry

from . import services, stage_rules
from .models import STAGE_CACHE_KEY, Lead, LeadActivity, LeadStage


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
        # The bare 8-digit variant of the same Qatar number is the same lead
        _, created_variant = services.create_lead_from_wa_number('50000001')
        self.assertFalse(created_variant)
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

    def test_link_lead_to_business_marks_won_and_logs_user(self):
        user = User.objects.create_user('staff3', is_staff=True)
        business = Business.objects.create(
            business_id=123456, business_name='Pearl Trading', business_status='pending',
        )
        lead = Lead.objects.create(source=Lead.SOURCE_MANUAL, company_name='Pearl Trading')

        linked, error = services.link_lead_to_business(lead, business, user)
        self.assertTrue(linked)
        self.assertEqual(error, '')
        lead.refresh_from_db()
        self.assertEqual(lead.converted_business_id, business.pk)
        self.assertEqual(lead.stage, Lead.STAGE_WON)
        conversion = lead.activities.filter(activity_type=LeadActivity.TYPE_CONVERSION).first()
        self.assertIsNotNone(conversion)
        self.assertEqual(conversion.created_by, user)

        # Re-linking the same pair is a no-op success; a different business is refused
        linked_again, _ = services.link_lead_to_business(lead, business, user)
        self.assertTrue(linked_again)
        other = Business.objects.create(
            business_id=123457, business_name='Other Shop', business_status='pending',
        )
        linked_other, error_other = services.link_lead_to_business(lead, other, user)
        self.assertFalse(linked_other)
        self.assertIn('already linked', error_other)


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


class LeadStageSeedTests(TestCase):
    """The 14 seeded columns must reproduce the previously hardcoded boards."""

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)

    def test_driver_board_columns_labels_and_order(self):
        columns = LeadStage.board_columns(Lead.CATEGORY_DRIVER)
        self.assertEqual(
            [(s.key, s.label) for s in columns],
            [('new', 'New Application'), ('contacted', 'Applied'), ('on_hold', 'Incomplete'),
             ('quoted', 'Uploads Completed'), ('negotiating', 'Under Review'),
             ('won', 'Approved'), ('lost', 'Rejected')],
        )

    def test_business_board_columns_unchanged(self):
        columns = LeadStage.board_columns(Lead.CATEGORY_BUSINESS)
        self.assertEqual([(s.key, s.label) for s in columns], Lead.STAGE_CHOICES)

    def test_terminal_flags_and_window(self):
        self.assertEqual(LeadStage.closed_keys(Lead.CATEGORY_DRIVER), {'won', 'lost'})
        self.assertEqual(LeadStage.closed_keys(Lead.CATEGORY_BUSINESS), {'won', 'lost'})
        approved = LeadStage.objects.get(category=Lead.CATEGORY_DRIVER, key='won')
        self.assertEqual(approved.hide_after_days, 30)
        self.assertEqual(approved.write_back, 'verified')

    def test_exactly_one_driver_fallback(self):
        fallbacks = LeadStage.objects.filter(category=Lead.CATEGORY_DRIVER, is_fallback=True)
        self.assertEqual([s.key for s in fallbacks], ['on_hold'])

    def test_seeded_columns_are_undeletable_system_rows(self):
        self.assertEqual(LeadStage.objects.filter(is_system=True).count(), 14)

    def test_stage_label_is_board_specific(self):
        driver = Lead.objects.create(category=Lead.CATEGORY_DRIVER, stage=Lead.STAGE_WON)
        business = Lead.objects.create(category=Lead.CATEGORY_BUSINESS, stage=Lead.STAGE_WON)
        self.assertEqual(driver.stage_label, 'Approved')
        self.assertEqual(business.stage_label, 'Won')
        self.assertEqual(driver.stage_swatch, 'forest')


class StubProfile:
    def __init__(self, verification_status):
        self.verification_status = verification_status


class StubDriver:
    """Just enough of fleet.Driver for the rule evaluator."""

    def __init__(self, verification_status='', driver_status='pending'):
        self.profile = StubProfile(verification_status)
        self.driver_status = driver_status
        self.dl_task_count = 0


class StageRuleTests(TestCase):
    """The rule evaluator must place drivers exactly where the old hardcoded
    driver_lead_target_stage did — this is the parity guard."""

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.stages = LeadStage.board_columns(Lead.CATEGORY_DRIVER)

    def target(self, driver, sections_done=False):
        with patch('workforce.views._driver_application_sections',
                   return_value=[{'done': sections_done}]):
            return stage_rules.target_stage_key(driver, self.stages)

    def test_legacy_mapping_reproduced(self):
        cases = [
            # (verification_status, driver_status, sections_done) -> stage key
            (('rejected', 'pending', False), 'lost'),
            (('verified', 'rejected', False), 'lost'),     # negative terminal wins
            (('verified', 'blocked', False), 'lost'),
            (('verified', 'suspended', False), 'lost'),
            (('verified', 'approved', False), 'won'),
            (('pending', 'approved', False), 'won'),       # driver_status alone
            (('under_review', 'pending', False), 'negotiating'),
            (('pending', 'pending', True), 'quoted'),      # uploads complete
            (('pending', 'pending', False), 'contacted'),
            (('incomplete', 'pending', False), 'on_hold'),
            (('', 'pending', False), 'on_hold'),           # no profile status -> fallback
            (('bogus', 'pending', False), 'on_hold'),      # unknown -> fallback
        ]
        for (verif, dstatus, done), expected in cases:
            with self.subTest(verif=verif, dstatus=dstatus, sections_done=done):
                driver = StubDriver(verif, dstatus)
                self.assertEqual(self.target(driver, done), expected)

    def test_no_driver_lands_in_new_application(self):
        self.assertEqual(stage_rules.target_stage_key(None, self.stages), 'new')

    def test_uploads_done_requires_a_submitted_application(self):
        # Every section complete but the form never submitted must NOT jump ahead.
        driver = StubDriver('incomplete', 'pending')
        self.assertEqual(self.target(driver, sections_done=True), 'on_hold')

    def test_manual_column_never_auto_filled(self):
        LeadStage.objects.create(category=Lead.CATEGORY_DRIVER, key='parked',
                                 label='Parked', position=99, auto_rules=[])
        stages = LeadStage.board_columns(Lead.CATEGORY_DRIVER)
        self.assertIn('parked', stage_rules.manual_stage_keys(stages))
        for verif in ('', 'incomplete', 'pending', 'under_review', 'verified', 'rejected'):
            driver = StubDriver(verif, 'pending')
            with patch('workforce.views._driver_application_sections',
                       return_value=[{'done': True}]):
                self.assertNotEqual(stage_rules.target_stage_key(driver, stages), 'parked')

    def test_rightmost_matching_column_wins(self):
        LeadStage.objects.create(category=Lead.CATEGORY_DRIVER, key='processing',
                                 label='Processing', position=99,
                                 auto_rules=['dstatus:processing'])
        stages = LeadStage.board_columns(Lead.CATEGORY_DRIVER)
        driver = StubDriver('pending', 'processing')
        with patch('workforce.views._driver_application_sections', return_value=[{'done': False}]):
            self.assertEqual(stage_rules.target_stage_key(driver, stages), 'processing')

    def test_unknown_rule_key_never_matches(self):
        stage = LeadStage.objects.create(category=Lead.CATEGORY_DRIVER, key='weird',
                                         label='Weird', position=99, auto_rules=['not:a:rule'])
        stages = LeadStage.board_columns(Lead.CATEGORY_DRIVER)
        driver = StubDriver('pending', 'pending')
        with patch('workforce.views._driver_application_sections', return_value=[{'done': False}]):
            self.assertNotEqual(stage_rules.target_stage_key(driver, stages), stage.key)


class StaffCreatedStageTests(TestCase):
    """A staff-created column has to behave like a built-in one."""

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)

    def test_cross_category_stage_is_rejected(self):
        LeadStage.objects.create(category=Lead.CATEGORY_DRIVER, key='processing',
                                 label='Processing', position=8,
                                 auto_rules=['dstatus:processing'])
        business = Lead.objects.create(category=Lead.CATEGORY_BUSINESS, company_name='X')
        with self.assertRaises(ValueError):
            services.set_lead_stage(business, 'processing')
        # ...but it is fine on the board that owns it
        driver = Lead.objects.create(category=Lead.CATEGORY_DRIVER, contact_name='D')
        services.set_lead_stage(driver, 'processing')
        self.assertEqual(driver.stage, 'processing')

    def test_new_stage_does_not_break_pricing_sync(self):
        """Regression: STAGE_TO_CRM_STATUS[new_stage] used to KeyError for any
        stage key that predated the dict."""
        LeadStage.objects.create(category=Lead.CATEGORY_BUSINESS, key='nurturing',
                                 label='Nurturing', position=8)
        inquiry = make_pricing_inquiry()
        lead, _ = services.create_lead_from_pricing_inquiry(inquiry)
        services.set_lead_stage(lead, 'nurturing')     # must not raise
        inquiry.refresh_from_db()
        self.assertEqual(lead.stage, 'nurturing')
        # A blank crm_status leaves the legacy inquiry status alone
        self.assertEqual(inquiry.crm_status, 'new')

    def test_terminal_staff_column_closes_the_lead(self):
        LeadStage.objects.create(category=Lead.CATEGORY_DRIVER, key='blocked',
                                 label='Blocked', position=8, is_closed=True,
                                 auto_rules=['dstatus:blocked'])
        lead = Lead.objects.create(category=Lead.CATEGORY_DRIVER, contact_name='D')
        services.set_lead_stage(lead, 'blocked')
        self.assertIsNotNone(lead.closed_at)
        self.assertFalse(lead.is_open)
        self.assertIn('blocked', services.closed_stage_keys(Lead.CATEGORY_DRIVER))
        self.assertIn('blocked', services.closed_stage_keys())


class StageManageViewTests(TestCase):
    """The /workforce/crm/stages/ guards."""

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.user = User.objects.create_user('stageadmin', password='x',
                                            is_staff=True, is_superuser=True)
        self.client.force_login(self.user)

    def post(self, path, data):
        data.setdefault('board', 'driver')
        return self.client.post(path, data, HTTP_HOST='ezzydelivery.qa', secure=True)

    def test_create_column(self):
        response = self.post('/workforce/crm/stages/save/', {
            'label': 'Processing', 'position': '8', 'dot_swatch': 'slate',
            'is_active': '1', 'auto_rules': ['dstatus:processing'],
        })
        self.assertEqual(response.status_code, 302)
        stage = LeadStage.objects.get(category='driver', key='processing')
        self.assertEqual(stage.auto_rules, ['dstatus:processing'])
        self.assertFalse(stage.is_system)
        self.assertTrue(stage.is_active)

    def test_duplicate_key_refused(self):
        self.post('/workforce/crm/stages/save/', {'label': 'Processing', 'position': '8'})
        self.post('/workforce/crm/stages/save/', {'label': 'Processing', 'position': '9'})
        self.assertEqual(
            LeadStage.objects.filter(category='driver', key='processing').count(), 1)

    def test_unknown_rule_is_dropped(self):
        self.post('/workforce/crm/stages/save/', {
            'label': 'Odd', 'position': '8', 'auto_rules': ['dstatus:processing', 'evil:rule'],
        })
        stage = LeadStage.objects.get(category='driver', key='odd')
        self.assertEqual(stage.auto_rules, ['dstatus:processing'])

    def test_system_column_cannot_be_deleted(self):
        stage = LeadStage.objects.get(category='driver', key='won')
        self.post('/workforce/crm/stages/delete/', {'stage_id': stage.pk})
        self.assertTrue(LeadStage.objects.filter(pk=stage.pk).exists())

    def test_occupied_column_needs_a_move_target(self):
        stage = LeadStage.objects.create(category='driver', key='parked',
                                         label='Parked', position=8)
        Lead.objects.create(category=Lead.CATEGORY_DRIVER, stage='parked', contact_name='D')

        self.post('/workforce/crm/stages/delete/', {'stage_id': stage.pk})
        self.assertTrue(LeadStage.objects.filter(pk=stage.pk).exists())

        self.post('/workforce/crm/stages/delete/',
                  {'stage_id': stage.pk, 'move_to': 'contacted'})
        self.assertFalse(LeadStage.objects.filter(pk=stage.pk).exists())
        self.assertEqual(Lead.objects.get(contact_name='D').stage, 'contacted')

    def test_fallback_is_unique_per_board(self):
        stage = LeadStage.objects.create(category='driver', key='parked',
                                         label='Parked', position=8)
        self.post('/workforce/crm/stages/save/', {
            'stage_id': stage.pk, 'label': 'Parked', 'position': '8', 'is_fallback': '1',
        })
        fallbacks = LeadStage.objects.filter(category='driver', is_fallback=True)
        self.assertEqual([s.key for s in fallbacks], ['parked'])

    def test_hiding_a_column_works(self):
        stage = LeadStage.objects.get(category='driver', key='on_hold')
        self.post('/workforce/crm/stages/save/', {
            'stage_id': stage.pk, 'label': 'Incomplete', 'position': '3',
            # 'is_active' omitted = unticked checkbox
        })
        stage.refresh_from_db()
        self.assertFalse(stage.is_active)
        self.assertNotIn('on_hold', [s.key for s in LeadStage.board_columns('driver')])

    def test_reorder(self):
        ids = [str(s.pk) for s in LeadStage.objects.filter(category='driver').order_by('position')]
        reversed_ids = list(reversed(ids))
        response = self.post('/workforce/crm/stages/reorder/', {'order': ','.join(reversed_ids)})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        ordered = [str(s.pk) for s in LeadStage.objects.filter(category='driver').order_by('position')]
        self.assertEqual(ordered, reversed_ids)

    def test_orphan_leads_get_an_unsorted_lane(self):
        Lead.objects.create(category=Lead.CATEGORY_DRIVER, stage='ghost', contact_name='Lost One')
        response = self.client.get('/workforce/crm/leads/board/drivers/',
                                   HTTP_HOST='ezzydelivery.qa', secure=True)
        labels = [c['label'] for c in response.context['columns']]
        self.assertIn('Unsorted', labels)
        unsorted = [c for c in response.context['columns'] if c['label'] == 'Unsorted'][0]
        self.assertFalse(unsorted['droppable'])
        self.assertEqual(unsorted['count'], 1)


class DriverStagePinTests(TestCase):
    """A staff move that contradicts the application status pins the card, so
    reconcile stops overriding it; a move that agrees keeps auto-filing."""

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        from core.models import Profile
        from fleet.models import Driver

        self.staff = User.objects.create_user('pinstaff', password='x',
                                              is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

        self.applicant = User.objects.create_user('applicant1', password='x')
        self.profile, _ = Profile.objects.get_or_create(
            user=self.applicant, defaults={'whatsapp': '97455667788'})
        self.profile.verification_status = 'under_review'
        self.profile.save()
        # driver_id is a manually-assigned PK (see core.views.join_driver), not an
        # AutoField, so tests must supply one.
        self.driver = Driver.objects.create(
            driver_id=9001, user=self.applicant, profile=self.profile,
            driver_phone='55667788', driver_whatsapp='55667788',
            driver_languages='en', driver_status='pending',
        )
        self.lead = Lead.objects.create(
            category=Lead.CATEGORY_DRIVER, source=Lead.SOURCE_MANUAL,
            phone='97455667788', contact_name='Applicant One',
            stage=Lead.STAGE_NEGOTIATING,
        )

    def move(self, stage):
        return self.client.post(
            f'/workforce/crm/leads/{self.lead.pk}/update-stage/', {'stage': stage},
            HTTP_HOST='ezzydelivery.qa', secure=True,
        )

    def test_conflicting_move_pins_and_survives_reconcile(self):
        # 'new' is filed only when no driver matches — this driver exists, so the
        # move disagrees with reality and must be pinned rather than reverted.
        response = self.move(Lead.STAGE_NEW)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertTrue(body['pinned'])
        self.assertIn('pinned here', body['warning'])

        self.lead.refresh_from_db()
        self.assertTrue(self.lead.stage_pinned)
        self.assertIsNotNone(self.lead.stage_pinned_at)

        services.reconcile_driver_leads()
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.stage, Lead.STAGE_NEW)   # not snapped back

    def test_unpin_hands_the_card_back_to_autofiling(self):
        self.move(Lead.STAGE_NEW)
        response = self.client.post(
            f'/workforce/crm/leads/{self.lead.pk}/unpin-stage/', {},
            HTTP_HOST='ezzydelivery.qa', secure=True,
        )
        self.assertTrue(response.json()['success'])
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.stage_pinned)

        services.reconcile_driver_leads()
        self.lead.refresh_from_db()
        # under_review -> the Under Review column reclaims it
        self.assertEqual(self.lead.stage, Lead.STAGE_NEGOTIATING)

    def test_write_back_move_sticks_without_pinning(self):
        """A column that rewrites the driver's status makes reality agree, so the
        card needs no pin and keeps tracking the application afterwards."""
        stage = LeadStage.objects.get(category=Lead.CATEGORY_DRIVER, key=Lead.STAGE_QUOTED)
        stage.write_back = 'pending'
        stage.confirm_text = 'send this driver back to the review queue'
        stage.save()

        with patch('workforce.views._driver_application_sections',
                   return_value=[{'done': True}]):
            body = self.move(Lead.STAGE_QUOTED).json()
            self.assertTrue(body['success'])
            self.assertFalse(body['pinned'])
            self.assertEqual(body['warning'], '')

            self.profile.refresh_from_db()
            self.assertEqual(self.profile.verification_status, 'pending')

            services.reconcile_driver_leads()
            self.lead.refresh_from_db()
            self.assertEqual(self.lead.stage, Lead.STAGE_QUOTED)
            self.assertFalse(self.lead.stage_pinned)

    def test_pinning_is_logged_on_the_timeline(self):
        self.move(Lead.STAGE_NEW)
        bodies = list(self.lead.activities.values_list('body', flat=True))
        self.assertTrue(any('Pinned' in b for b in bodies), bodies)

    def test_business_leads_are_never_pinned(self):
        business = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                       company_name='Acme', stage=Lead.STAGE_NEW)
        response = self.client.post(
            f'/workforce/crm/leads/{business.pk}/update-stage/', {'stage': Lead.STAGE_QUOTED},
            HTTP_HOST='ezzydelivery.qa', secure=True,
        )
        body = response.json()
        self.assertTrue(body['success'])
        self.assertFalse(body['pinned'])
        business.refresh_from_db()
        self.assertEqual(business.stage, Lead.STAGE_QUOTED)

    def test_write_back_column_always_gets_confirm_text(self):
        """A write-back column with a blank confirm text would approve a real driver
        with no dialog, because the board's guard is driven by that text."""
        response = self.client.post('/workforce/crm/stages/save/', {
            'board': 'driver', 'label': 'Cleared', 'position': '8',
            'write_back': 'verified', 'confirm_text': '',
        }, HTTP_HOST='ezzydelivery.qa', secure=True)
        self.assertEqual(response.status_code, 302)
        stage = LeadStage.objects.get(category='driver', key='cleared')
        self.assertTrue(stage.confirm_text)


class DriverWriteBackAuthorizationTests(TestCase):
    """A column that rewrites a driver's verification status is an Operations
    decision — the CRM board must not be a way around that desk."""

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        from core.models import Profile
        from fleet.models import Driver

        self.applicant = User.objects.create_user('wbapplicant', password='x')
        self.profile, _ = Profile.objects.get_or_create(
            user=self.applicant, defaults={'whatsapp': '97455990011'})
        self.profile.verification_status = 'pending'
        self.profile.save()
        Driver.objects.create(
            driver_id=9002, user=self.applicant, profile=self.profile,
            driver_phone='55990011', driver_whatsapp='55990011',
            driver_languages='en', driver_status='pending',
        )
        self.lead = Lead.objects.create(
            category=Lead.CATEGORY_DRIVER, phone='97455990011',
            contact_name='WB Applicant', stage=Lead.STAGE_CONTACTED,
        )

    def _staff(self, username, **depts):
        from core.models import Profile
        user = User.objects.create_user(username, password='x', is_staff=True)
        profile, _ = Profile.objects.get_or_create(user=user)
        for field, value in depts.items():
            setattr(profile, field, value)
        profile.save()
        return user

    def _approve(self, user):
        client = self.client
        client.force_login(user)
        return client.post(
            f'/workforce/crm/leads/{self.lead.pk}/update-stage/', {'stage': Lead.STAGE_WON},
            HTTP_HOST='ezzydelivery.qa', secure=True,
        )

    def test_marketing_only_staff_cannot_approve_a_driver(self):
        marketer = self._staff('mktonly', dept_marketing=True)
        response = self._approve(marketer)
        self.assertEqual(response.status_code, 403)
        self.assertIn('Operations desk', response.json()['error'])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.verification_status, 'pending')   # untouched
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.stage, Lead.STAGE_CONTACTED)         # not moved

    def test_operations_staff_can_approve(self):
        ops = self._staff('opsonly', dept_operations=True)
        response = self._approve(ops)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.verification_status, 'verified')

    def test_marketing_can_still_move_non_writeback_columns(self):
        marketer = self._staff('mktonly2', dept_marketing=True)
        self.client.force_login(marketer)
        response = self.client.post(
            f'/workforce/crm/leads/{self.lead.pk}/update-stage/', {'stage': Lead.STAGE_NEW},
            HTTP_HOST='ezzydelivery.qa', secure=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    def test_writeback_miss_is_reported_not_hidden(self):
        """A lead with no driver behind it must not report a silent success."""
        orphan = Lead.objects.create(
            category=Lead.CATEGORY_DRIVER, phone='97400000000',
            contact_name='No Driver', stage=Lead.STAGE_CONTACTED,
        )
        ops = self._staff('opsonly2', dept_operations=True)
        self.client.force_login(ops)
        response = self.client.post(
            f'/workforce/crm/leads/{orphan.pk}/update-stage/', {'stage': Lead.STAGE_WON},
            HTTP_HOST='ezzydelivery.qa', secure=True,
        )
        body = response.json()
        self.assertTrue(body['success'])
        self.assertIsNone(body['synced_driver'])
        self.assertIn('nothing was sent to an applicant', body['warning'])


class WhatsAppSecretTests(TestCase):
    """Auth codes must never be stored, and a platform account's conversation must
    not be openable from the CRM."""

    def test_own_auth_template_is_redacted(self):
        from whatsapp.secrets import redact_text
        body = ('🔐 *EZZY Delivery - Password Reset*\n\n'
                'Your password reset verification code is:\n\n*817183*\n\nThis code expires.')
        clean, changed = redact_text(body)
        self.assertTrue(changed)
        self.assertNotIn('817183', clean)
        self.assertIn('Password Reset', clean)       # context kept for staff

    def test_ordinary_message_with_a_number_is_left_alone(self):
        """Regression: 'a one-time payment of *QAR 900*' had its price destroyed."""
        from whatsapp.secrets import redact_text
        body = ('This requires a collaboration agreement with a one-time payment of '
                '*QAR 900 covering 3 months*.')
        clean, changed = redact_text(body)
        self.assertFalse(changed)
        self.assertIn('900', clean)

    def test_encoded_media_body_is_left_alone(self):
        """Regression: '2Fa' inside a base64 location payload matched, and substituting
        inside the blob would corrupt it."""
        from whatsapp.secrets import redact_text
        body = 'A' * 120 + '2Fa' + 'B' * 120 + '1234'
        clean, changed = redact_text(body)
        self.assertFalse(changed)
        self.assertEqual(clean, body)

    def test_raw_payload_is_redacted_too(self):
        from whatsapp.secrets import redact_payload
        body = 'EZZY Delivery password reset verification code is: *445566*'
        payload = {'body': body, '_data': {'body': body}, 'id': 'abc'}
        clean, changed = redact_payload(payload, body)
        self.assertTrue(changed)
        self.assertNotIn('445566', str(clean))

    def test_platform_account_chat_is_refused(self):
        from core.models import Profile
        owner = User.objects.create_user('chatowner', password='x')
        Profile.objects.update_or_create(user=owner, defaults={'whatsapp': '97455443322'})
        from django.core.cache import cache as dj_cache
        dj_cache.delete('crm_platform_account_numbers_v1')

        staff = User.objects.create_user('chatstaff', password='x',
                                        is_staff=True, is_superuser=True)
        self.client.force_login(staff)
        response = self.client.get(
            '/workforce/crm/whatsapp-inbox/chat/?sender=97455443322',
            HTTP_HOST='ezzydelivery.qa', secure=True,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn('EzzyDelivery account', response.json()['error'])


class LeadWhatsAppNumberPickerTests(TestCase):
    """The lead page runs on one of several WhatsApp numbers. Which one is a
    staff choice that must survive a reload — and must not silently move a
    client's replies onto a different sender."""

    SESSIONS = [
        {'name': 'default', 'status': 'WORKING', 'phone': '97466451589', 'push_name': 'Ezzy Delivery'},
        {'name': 'Ezzy6000', 'status': 'WORKING', 'phone': '97460003432', 'push_name': 'Carty'},
    ]

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.lead = Lead.objects.create(
            category=Lead.CATEGORY_DRIVER, phone='97455112233', contact_name='Picker Driver',
        )
        self.staff = User.objects.create_user(
            'pickerstaff', password='x', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def _get(self, query=''):
        with patch('whatsapp.sessions.list_sessions', return_value=self.SESSIONS):
            return self.client.get(
                f'/workforce/crm/leads/{self.lead.pk}/{query}',
                HTTP_HOST='ezzydelivery.qa', secure=True,
            )

    def test_untouched_lead_lands_on_the_house_number(self):
        response = self._get()
        self.assertEqual(response.context['wa_session'], 'default')

    def test_untouched_lead_does_not_override_the_section_route(self):
        """Landing on a tab is not a decision — the composer must keep using the
        Auto Triggers route until someone actually picks a number."""
        self.assertEqual(self._get().context['wa_send_session'], '')

    def test_picking_a_number_is_remembered_and_drives_the_composer(self):
        chosen = self._get('?session=Ezzy6000')
        self.assertEqual(chosen.context['wa_session'], 'Ezzy6000')
        self.assertEqual(chosen.context['wa_send_session'], 'Ezzy6000')

        self.lead.refresh_from_db()
        self.assertEqual(self.lead.wa_session, 'Ezzy6000')
        self.assertEqual(self._get().context['wa_session'], 'Ezzy6000')   # survives reload

    def test_all_numbers_is_a_read_view_not_a_sender(self):
        """'All numbers' merges the thread, but nothing can be sent "from all"."""
        response = self._get(f'?session={Lead.WA_SESSION_ALL}')
        self.assertEqual(response.context['wa_session'], '')
        self.assertEqual(response.context['wa_send_session'], '')
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.wa_session, Lead.WA_SESSION_ALL)

    def test_a_number_we_do_not_own_is_ignored(self):
        """A stray ?session= must never reach WAHA — normalize() would quietly
        turn it into the default session and send from the wrong line."""
        response = self._get('?session=../etc')
        self.assertEqual(response.context['wa_session'], 'default')
        self.assertEqual(response.context['wa_send_session'], '')
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.wa_session, '')

    def test_remembering_a_tab_does_not_touch_updated_at(self):
        """updated_at drives the follow-up digests — it means "the lead moved",
        not "someone opened the page"."""
        before = Lead.objects.get(pk=self.lead.pk).updated_at
        self._get('?session=Ezzy6000')
        self.assertEqual(Lead.objects.get(pk=self.lead.pk).updated_at, before)


class RoutedSendNumberOverrideTests(TestCase):
    """whatsapp_send_routed accepts an explicit number. It has to be checked
    against the numbers we actually own, not merely normalised."""

    SESSIONS = [
        {'name': 'default', 'status': 'WORKING', 'phone': '97466451589', 'push_name': 'Ezzy'},
        {'name': 'Ezzy6000', 'status': 'WORKING', 'phone': '97460003432', 'push_name': 'Carty'},
    ]

    def setUp(self):
        self.staff = User.objects.create_user(
            'sendstaff', password='x', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def _get(self, query):
        with patch('whatsapp.sessions.list_sessions', return_value=self.SESSIONS):
            return self.client.get(
                f'/workforce/whatsapp/send-routed/?{query}',
                HTTP_HOST='ezzydelivery.qa', secure=True,
            )

    def test_override_reports_the_picked_number_on_waha(self):
        body = self._get('section=crm_leads&session=default').json()
        self.assertTrue(body['success'])
        self.assertEqual(body['session'], 'default')
        self.assertEqual(body['sender_number'], '97466451589')
        self.assertEqual(body['channel'], 'waha')

    def test_unknown_number_is_refused_not_normalised(self):
        response = self._get('section=crm_leads&session=nope')
        self.assertEqual(response.status_code, 400)
        self.assertIn('nope', response.json()['error'])

    def test_path_traversal_in_the_session_name_is_refused(self):
        response = self._get('section=crm_leads&session=../../etc/passwd')
        self.assertEqual(response.status_code, 400)

    def test_no_override_keeps_the_section_route(self):
        body = self._get('section=crm_leads').json()
        self.assertTrue(body['success'])
        self.assertEqual(body['session'], '')

    def test_the_picked_number_is_what_actually_gets_sent(self):
        from core.whatsapp_utils import send_routed_message
        with patch('whatsapp.waha_views.send_waha_text',
                   return_value=(True, {'message_id': 'x'})) as send:
            send_routed_message('crm_leads', '97455112233', 'hi', session='Ezzy6000')
        self.assertEqual(send.call_args.kwargs['session'], 'Ezzy6000')


class DriverBindingTests(TestCase):
    """Lead.driver is the authoritative link. Phone matching only finds a driver
    once, and refuses to guess when a number belongs to more than one applicant."""

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        from core.models import Profile
        from fleet.models import Driver

        self.drivers = []
        # Two applicants with the SAME last-8 digits — a duplicate registration, the
        # exact shape that had one card serving two people in production.
        for i, (username, phone) in enumerate([
            ('dup_a', '66430977'), ('dup_b', '009766430977'),
        ]):
            user = User.objects.create_user(username, password='x')
            profile, _ = Profile.objects.get_or_create(
                user=user, defaults={'whatsapp': phone})
            profile.verification_status = 'pending'
            profile.save()
            self.drivers.append(Driver.objects.create(
                driver_id=9100 + i, user=user, profile=profile,
                driver_phone=phone, driver_whatsapp=phone,
                driver_languages='en', driver_status='pending',
            ))

    def test_ambiguous_phone_refuses_to_guess(self):
        lead = Lead.objects.create(category=Lead.CATEGORY_DRIVER, phone='97466430977')
        self.assertEqual(len(services.driver_candidates_for_lead(lead)), 2)
        self.assertIsNone(services._driver_for_lead(lead))

    def test_fk_wins_over_phone_matching(self):
        lead = Lead.objects.create(category=Lead.CATEGORY_DRIVER, phone='97466430977',
                                   driver=self.drivers[1])
        resolved = services._driver_for_lead(lead)
        self.assertEqual(resolved.pk, self.drivers[1].pk)

    def test_reconcile_gives_every_driver_its_own_card(self):
        """Regression: two drivers sharing a number both bound to one lead, leaving a
        real applicant with no card at all."""
        Lead.objects.create(category=Lead.CATEGORY_DRIVER, phone='97466430977')
        with patch('workforce.views._driver_application_sections', return_value=[{'done': False}]):
            services.reconcile_driver_leads()
        for driver in self.drivers:
            self.assertEqual(
                Lead.objects.filter(driver=driver).count(), 1,
                f'driver {driver.pk} should have exactly one card',
            )

    def test_lid_does_not_contribute_a_match_key(self):
        """A 15-digit WhatsApp LID lives in the same field as a phone; taking its last
        8 digits invented a key that could collide with a real number."""
        self.assertEqual(services._driver_match_keys('126882678862076'), set())
        self.assertEqual(services._driver_match_keys('66430977'), {'66430977'})
        self.assertEqual(services._driver_match_keys('97466430977'), {'66430977'})


class StageConfigGuardTests(TestCase):
    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.staff = User.objects.create_user('cfgstaff', password='x',
                                              is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def post(self, path, data):
        data.setdefault('board', 'driver')
        return self.client.post(path, data, HTTP_HOST='ezzydelivery.qa', secure=True)

    def test_sole_fallback_cannot_be_removed(self):
        fallback = LeadStage.objects.get(category='driver', is_fallback=True)
        self.post('/workforce/crm/stages/save/', {
            'stage_id': fallback.pk, 'label': fallback.label,
            'position': fallback.position, 'is_active': '1',
            # is_fallback omitted = unticked
        })
        fallback.refresh_from_db()
        self.assertTrue(fallback.is_fallback, 'the board must keep a catch-all')

    def test_new_column_lands_before_the_outcome_columns(self):
        """Rules match right-to-left, so a column created at the far end would
        silently outrank Approved/Rejected."""
        approved = LeadStage.objects.get(category='driver', key='won')
        self.post('/workforce/crm/stages/save/', {
            'label': 'Processing', 'position': '99',
            'auto_rules': ['dstatus:processing'],
        })
        created = LeadStage.objects.get(category='driver', key='processing')
        approved.refresh_from_db()
        self.assertLess(created.position, approved.position)

    def test_outcome_column_may_sit_at_the_end(self):
        self.post('/workforce/crm/stages/save/', {
            'label': 'Blocked', 'position': '99', 'is_closed': '1',
            'auto_rules': ['dstatus:blocked'],
        })
        created = LeadStage.objects.get(category='driver', key='blocked')
        self.assertEqual(created.position, 99)


class ReportsFunnelTests(TestCase):
    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.staff = User.objects.create_user('repstaff', password='x',
                                              is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def test_funnel_is_split_per_board(self):
        """Regression: both boards were merged into one column set, so 'Quoted' and
        'Uploads Completed' were added together under whichever label came first."""
        Lead.objects.create(category=Lead.CATEGORY_BUSINESS, stage=Lead.STAGE_QUOTED)
        Lead.objects.create(category=Lead.CATEGORY_DRIVER, stage=Lead.STAGE_QUOTED)

        response = self.client.get('/workforce/crm/reports/',
                                   HTTP_HOST='ezzydelivery.qa', secure=True)
        funnels = {f['category']: f for f in response.context['funnels']}
        self.assertEqual(set(funnels), {'business', 'driver'})

        business = {r['label']: r['count'] for r in funnels['business']['rows']}
        driver = {r['label']: r['count'] for r in funnels['driver']['rows']}
        self.assertEqual(business['Quoted'], 1)
        self.assertEqual(driver['Uploads Completed'], 1)
        self.assertNotIn('Uploads Completed', business)
        self.assertNotIn('Quoted', driver)


class LeadMergeTests(TestCase):
    """Two cards in one: the same prospect arriving twice becomes one board card
    holding both, without destroying either row."""

    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.staff = User.objects.create_user('mergestaff', password='x',
                                              is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)
        self.wa = Lead.objects.create(
            category=Lead.CATEGORY_BUSINESS, source=Lead.SOURCE_WA_INBOUND,
            phone='97455000123', contact_name='Same Person', stage=Lead.STAGE_NEW,
        )

    def _post(self, path, data):
        return self.client.post(path, data, HTTP_HOST='ezzydelivery.qa', secure=True)

    def test_candidate_matched_across_phone_formats(self):
        other = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                    source=Lead.SOURCE_PRICING, phone='55000123')
        self.assertIn(other, services.duplicate_candidates(self.wa))

    def test_merge_keeps_both_rows_and_both_sources(self):
        pricing = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                      source=Lead.SOURCE_PRICING, phone='55000123',
                                      company_name='Same Person Co')
        ok, error = services.merge_leads(self.wa, pricing, self.staff)
        self.assertTrue(ok, error)

        self.wa.refresh_from_db(); pricing.refresh_from_db()
        self.assertEqual(pricing.merged_into_id, self.wa.pk)
        self.assertTrue(Lead.objects.filter(pk=pricing.pk).exists())   # not destroyed
        self.assertEqual([b['key'] for b in self.wa.source_badges],
                         [Lead.SOURCE_WA_INBOUND, Lead.SOURCE_PRICING])
        # Blanks filled from the absorbed card, own values untouched
        self.assertEqual(self.wa.company_name, 'Same Person Co')
        self.assertEqual(self.wa.contact_name, 'Same Person')

    def test_merged_child_disappears_from_the_board_but_parent_stays(self):
        pricing = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                      source=Lead.SOURCE_PRICING, phone='55000123')
        services.merge_leads(self.wa, pricing, self.staff)
        response = self.client.get('/workforce/crm/leads/board/',
                                   HTTP_HOST='ezzydelivery.qa', secure=True)
        ids = {l.pk for col in response.context['columns'] for l in col['leads']}
        self.assertIn(self.wa.pk, ids)
        self.assertNotIn(pricing.pk, ids)

    def test_unmerge_puts_it_back(self):
        pricing = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                      source=Lead.SOURCE_PRICING, phone='55000123')
        services.merge_leads(self.wa, pricing, self.staff)
        ok, error = services.unmerge_lead(pricing, self.staff)
        self.assertTrue(ok, error)
        pricing.refresh_from_db()
        self.assertIsNone(pricing.merged_into_id)

    def test_cross_board_merge_is_refused(self):
        driver_lead = Lead.objects.create(category=Lead.CATEGORY_DRIVER,
                                          source=Lead.SOURCE_WA_INBOUND, phone='55000123')
        ok, error = services.merge_leads(self.wa, driver_lead, self.staff)
        self.assertFalse(ok)
        self.assertIn('different boards', error)

    def test_merge_into_self_is_refused(self):
        ok, error = services.merge_leads(self.wa, self.wa, self.staff)
        self.assertFalse(ok)

    def test_tree_stays_one_level_deep(self):
        """Merging a card that already holds children lifts them to the new parent, so
        a card never hides another card's children."""
        mid = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                  source=Lead.SOURCE_PRICING, phone='55000123')
        leaf = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                   source=Lead.SOURCE_WA_FORM, phone='55000123')
        services.merge_leads(mid, leaf, self.staff)
        services.merge_leads(self.wa, mid, self.staff)
        leaf.refresh_from_db(); mid.refresh_from_db()
        self.assertEqual(leaf.merged_into_id, self.wa.pk)
        self.assertEqual(mid.merged_into_id, self.wa.pk)
        self.assertEqual(self.wa.merged_children.count(), 2)

    def test_pricing_inquiry_auto_merges_into_an_existing_whatsapp_card(self):
        inquiry = make_pricing_inquiry(business_contact_number='974 5500 0123')
        lead, created = services.create_lead_from_pricing_inquiry(inquiry)
        self.assertTrue(created)
        lead.refresh_from_db()
        self.assertEqual(lead.merged_into_id, self.wa.pk)
        self.assertEqual([b['key'] for b in Lead.objects.get(pk=self.wa.pk).source_badges],
                         [Lead.SOURCE_WA_INBOUND, Lead.SOURCE_PRICING])

    def test_merged_child_is_left_out_of_the_followup_digest(self):
        from datetime import timedelta
        from django.utils import timezone as dj_tz
        yesterday = dj_tz.localdate() - timedelta(days=1)
        pricing = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                      source=Lead.SOURCE_PRICING, phone='55000123',
                                      next_followup_at=yesterday)
        services.merge_leads(self.wa, pricing, self.staff)
        due = [l for leads in services.build_followup_digest().values() for l in leads]
        self.assertNotIn(pricing, due)

    def test_merge_endpoint_and_unmerge_endpoint(self):
        pricing = Lead.objects.create(category=Lead.CATEGORY_BUSINESS,
                                      source=Lead.SOURCE_PRICING, phone='55000123')
        response = self._post(f'/workforce/crm/leads/{self.wa.pk}/merge/',
                              {'duplicate_id': pricing.pk})
        self.assertTrue(response.json()['success'])
        response = self._post(f'/workforce/crm/leads/{self.wa.pk}/unmerge/',
                              {'child_id': pricing.pk})
        self.assertTrue(response.json()['success'])

    def test_unmerge_refuses_a_card_that_is_not_a_child(self):
        stranger = Lead.objects.create(category=Lead.CATEGORY_BUSINESS, phone='97400001111')
        response = self._post(f'/workforce/crm/leads/{self.wa.pk}/unmerge/',
                              {'child_id': stranger.pk})
        self.assertEqual(response.status_code, 400)


class WhatsAppInboxTests(TestCase):
    """The inbox lists senders by the id WhatsApp delivered them under — an
    @lid for almost everyone — while showing the resolved phone. Both the
    search box and the "is this even a message" filter have to work in those
    terms, not in stored-id terms."""

    LID = '57544525500615'
    PHONE = '97451020251'
    SESSIONS = [{'name': 'default', 'status': 'WORKING',
                 'phone': '97466451589', 'push_name': 'Ezzy'}]

    def setUp(self):
        from whatsapp.models import WhatsAppContact, WhatsAppMessage
        self.staff = User.objects.create_user('inboxstaff', password='x',
                                              is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)
        WhatsAppContact.objects.create(session='default', phone=self.PHONE, lid=self.LID,
                                       saved_name='Lid Sender')
        self.msg = WhatsAppMessage.objects.create(
            waha_message_id='inbox-test-1', session='default', direction='inbound',
            from_number=f'{self.LID}@lid', to_number='97466451589',
            body='Hello, do you deliver?', message_type='text',
        )

    def _get(self, **params):
        with patch('whatsapp.sessions.list_sessions', return_value=self.SESSIONS), \
             patch('whatsapp.waha_views.fetch_waha_session_status', return_value=None), \
             patch('whatsapp.wa_chats_view._lid_map', return_value={}):
            return self.client.get('/workforce/crm/whatsapp-inbox/', params,
                                   HTTP_HOST='ezzydelivery.qa', secure=True)

    def test_search_by_the_number_shown_on_the_row_finds_the_lid_sender(self):
        """Regression: searching 51020251 — the number the row displays — hit
        only the raw stored id and returned 'No unknown senders'."""
        for term in ('51020251', '97451020251', '+974 5102 0251'):
            response = self._get(search=term)
            self.assertContains(response, self.LID, msg_prefix=f'search={term}')
            self.assertNotContains(response, 'No unknown senders',
                                   msg_prefix=f'search={term}')

    def test_search_by_the_raw_lid_still_works(self):
        self.assertContains(self._get(search=self.LID), self.LID)

    def test_search_by_contact_name_finds_the_sender(self):
        self.assertContains(self._get(search='Lid Sender'), self.LID)

    def test_search_for_a_stranger_reports_nothing(self):
        self.assertContains(self._get(search='55009999'), 'No unknown senders')

    def test_system_notification_does_not_invent_a_sender(self):
        """Asking WAHA whether a number exists generates an e2e_notification.
        Storing that would queue someone for triage who never wrote to us."""
        from whatsapp.models import WhatsAppMessage
        self.msg.delete()
        WhatsAppMessage.objects.create(
            waha_message_id='inbox-test-2', session='default', direction='inbound',
            from_number=f'{self.LID}@lid', to_number='97466451589',
            body='', message_type='system',
        )
        self.assertContains(self._get(), 'No unknown senders')

    def test_webhook_drops_system_events_before_they_are_stored(self):
        from whatsapp.waha_views import is_system_event
        self.assertTrue(is_system_event({'_data': {'type': 'e2e_notification'}}))
        self.assertTrue(is_system_event({'_data': {'type': 'notification_template'}}))
        # A missed call or a deleted message is a real person reaching us.
        self.assertFalse(is_system_event({'_data': {'type': 'call_log'}}))
        self.assertFalse(is_system_event({'_data': {'type': 'revoked'}}))
        self.assertFalse(is_system_event({'_data': {'type': 'chat'}}))


class WhatsAppIngestRedactionTests(TestCase):
    """The redaction must fire in the real ingest functions, not just the helper.

    Regression: upsert_message passed the ALREADY-REDACTED body to redact_payload,
    whose "is there a code here?" check then found none, so it skipped the payload and
    left the verification code sitting in raw_payload.
    """

    AUTH_BODY = ('🔐 *EZZY Delivery - Password Reset*\n\nYour password reset verification '
                 'code is:\n\n*991234*\n\nThis code expires in 10 minutes.')

    def _payload(self, waha_id, body):
        return {
            'id': waha_id, 'fromMe': True, 'from': '97466451589@c.us',
            'to': '97455112233@c.us', 'body': body, 'timestamp': 1770000000,
            '_data': {'type': 'chat', 'body': body},
        }

    def test_backfill_redacts_body_and_raw_payload(self):
        from whatsapp.management.commands.backfill_waha import upsert_message
        obj, created = upsert_message(
            self._payload('TEST_AUTH_1', self.AUTH_BODY), 'default', '97455112233@c.us')
        self.assertTrue(created)
        obj.refresh_from_db()
        self.assertNotIn('991234', obj.body)
        self.assertNotIn('991234', str(obj.raw_payload))
        self.assertIn('[code hidden]', obj.body)
        # The wording survives so staff can still tell what kind of message it was
        self.assertIn('Password Reset', obj.body)

    def test_backfill_leaves_an_ordinary_message_alone(self):
        from whatsapp.management.commands.backfill_waha import upsert_message
        body = 'Hi, my order 4521 is late'
        obj, _ = upsert_message(self._payload('TEST_PLAIN_1', body), 'default',
                                '97455112233@c.us')
        obj.refresh_from_db()
        self.assertEqual(obj.body, body)
        self.assertIn('4521', str(obj.raw_payload))
