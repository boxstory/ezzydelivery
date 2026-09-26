"""
Purpose: Opportunity slots must never confirm more drivers than they have places, and raising a hand must be idempotent.
Used by: manage.py test fleet.tests_opportunities
Notes: Capacity is the one rule two ops could each read as satisfied at the same moment, so it is enforced
       under a row lock in fleet/opportunities.py — these tests pin the behaviour, not the lock itself.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Profile
from fleet.models import (
    Driver,
    DriverOpportunity,
    DriverOpportunityInterest,
    DriverOpportunitySlot,
)
from fleet.opportunities import (
    SLOT_FULL_CODE,
    SLOT_PAST_CODE,
    SLOT_CLOSED_CODE,
    express_interest,
    open_slots_for,
    set_interest_status,
    withdraw_interest,
)


def make_driver(username, driver_id, slabs=''):
    user = get_user_model().objects.create_user(
        username=username, email=f'{username}@example.com', password='Str0ngPass!99')
    profile, _ = Profile.objects.get_or_create(user=user)
    profile.is_driver = True
    profile.save()
    return Driver.objects.create(
        driver_id=driver_id,
        user=user,
        profile=profile,
        driver_code=f'OPP{driver_id}',
        driver_phone='97412345678',
        driver_whatsapp='97412345678',
        driver_languages='english',
        driver_status='approved',
        work_time_slabs=slabs,
    )


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class OpportunityInterestTests(TestCase):
    """Raising a hand, taking it back, and the capacity ceiling."""

    def setUp(self):
        self.driver = make_driver('oppdriver', 9931)
        self.other = make_driver('oppdriver2', 9932)

        self.posting = DriverOpportunity.objects.create(
            title='Evening riders — Lusail',
            status='open',
            published_at=timezone.now(),
        )
        start = timezone.now() + timedelta(days=2)
        self.slot = DriverOpportunitySlot.objects.create(
            opportunity=self.posting,
            starts_at=start,
            ends_at=start + timedelta(hours=6),
            time_slab='evening',
            capacity=1,
        )

    def test_slot_code_is_generated(self):
        self.assertTrue(self.slot.slot_code.startswith('OPP-'))

    def test_interest_is_idempotent(self):
        """Tapping Interested twice is one row, not two."""
        express_interest(self.driver, self.slot)
        express_interest(self.driver, self.slot)
        self.assertEqual(
            DriverOpportunityInterest.objects.filter(
                slot=self.slot, driver=self.driver).count(), 1)

    def test_withdrawn_interest_is_revived_not_duplicated(self):
        """A driver changing their mind twice should not litter the ops queue."""
        express_interest(self.driver, self.slot)
        withdraw_interest(self.driver, self.slot)
        interest, reason = express_interest(self.driver, self.slot)

        self.assertIsNone(reason)
        self.assertEqual(interest.status, 'interested')
        self.assertEqual(
            DriverOpportunityInterest.objects.filter(
                slot=self.slot, driver=self.driver).count(), 1)

    def test_past_slot_refuses_interest(self):
        start = timezone.now() - timedelta(hours=3)
        past = DriverOpportunitySlot.objects.create(
            opportunity=self.posting, starts_at=start, ends_at=start + timedelta(hours=2))
        interest, reason = express_interest(self.driver, past)

        self.assertIsNone(interest)
        self.assertEqual(reason, SLOT_PAST_CODE)

    def test_closed_posting_refuses_interest(self):
        """A draft posting is not on the board, so its slots are not either."""
        DriverOpportunity.objects.filter(pk=self.posting.pk).update(status='closed')
        self.slot.refresh_from_db()
        interest, reason = express_interest(self.driver, self.slot)

        self.assertIsNone(interest)
        self.assertEqual(reason, SLOT_CLOSED_CODE)

    # --- capacity --------------------------------------------------------

    def test_confirmation_consumes_a_place(self):
        interest, _ = express_interest(self.driver, self.slot)
        set_interest_status(interest, 'confirmed')

        self.slot.refresh_from_db()
        self.assertEqual(self.slot.confirmed_count, 1)
        self.assertEqual(self.slot.places_left, 0)

    def test_slot_flips_to_full_when_capacity_is_reached(self):
        interest, _ = express_interest(self.driver, self.slot)
        set_interest_status(interest, 'confirmed')

        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, 'full')

    def test_confirmation_cannot_exceed_capacity(self):
        """The second confirmation on a one-place slot must be refused."""
        first, _ = express_interest(self.driver, self.slot)
        second, _ = express_interest(self.other, self.slot)

        set_interest_status(first, 'confirmed')
        second, reason = set_interest_status(second, 'confirmed')

        self.assertEqual(reason, SLOT_FULL_CODE)
        second.refresh_from_db()
        self.assertEqual(second.status, 'interested')

    def test_shortlisting_does_not_take_a_seat(self):
        """A maybe is not a place — two can be shortlisted for one slot."""
        first, _ = express_interest(self.driver, self.slot)
        second, _ = express_interest(self.other, self.slot)
        set_interest_status(first, 'shortlisted')
        set_interest_status(second, 'shortlisted')

        self.slot.refresh_from_db()
        self.assertEqual(self.slot.confirmed_count, 0)
        self.assertEqual(self.slot.places_left, 1)

    def test_declining_a_confirmed_driver_reopens_the_slot(self):
        interest, _ = express_interest(self.driver, self.slot)
        set_interest_status(interest, 'confirmed')
        set_interest_status(interest, 'declined')

        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, 'open')
        self.assertEqual(self.slot.places_left, 1)

    def test_driver_cannot_withdraw_once_confirmed(self):
        """Once ops have counted them in, changing it is a conversation."""
        interest, _ = express_interest(self.driver, self.slot)
        set_interest_status(interest, 'confirmed')
        withdraw_interest(self.driver, self.slot)

        interest.refresh_from_db()
        self.assertEqual(interest.status, 'confirmed')

    # --- RiderShift materialisation --------------------------------------

    def test_no_rider_shift_without_a_pickup_location(self):
        """RiderShift needs a location, so a confirmation stands on its own."""
        interest, _ = express_interest(self.driver, self.slot)
        set_interest_status(interest, 'confirmed')

        interest.refresh_from_db()
        self.assertIsNone(interest.rider_shift)

    # --- the board -------------------------------------------------------

    def test_board_lists_open_slots(self):
        slots = open_slots_for(self.driver)
        self.assertIn(self.slot.pk, [s.pk for s in slots])

    def test_board_puts_matching_hours_first(self):
        """The whole point of the board is not having to read forty rows."""
        start = timezone.now() + timedelta(days=1)
        morning = DriverOpportunitySlot.objects.create(
            opportunity=self.posting, starts_at=start,
            ends_at=start + timedelta(hours=6), time_slab='morning')

        # This driver works evenings, so the later evening slot must outrank the
        # earlier morning one.
        evening_driver = make_driver('eveningdriver', 9933, slabs='evening')
        slots = open_slots_for(evening_driver)

        self.assertEqual(slots[0].pk, self.slot.pk)
        self.assertIn(morning.pk, [s.pk for s in slots])

    def test_board_excludes_draft_postings(self):
        DriverOpportunity.objects.filter(pk=self.posting.pk).update(status='draft')
        self.assertEqual(len(open_slots_for(self.driver)), 0)

    def test_board_is_empty_without_a_driver(self):
        self.assertEqual(len(open_slots_for(None)), 0)


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class StaffOpportunityConsoleTests(TestCase):
    """The ops half: publishing a posting, adding shifts, deciding on a raised hand."""

    PASSWORD = 'Str0ngPass!99'

    def setUp(self):
        from django.test import Client
        from django.urls import reverse

        self.reverse = reverse
        staff = get_user_model().objects.create_user(
            username='oppops', email='oppops@example.com',
            password=self.PASSWORD, is_staff=True)
        staff_profile, _ = Profile.objects.get_or_create(user=staff)
        staff_profile.is_staff = True
        staff_profile.is_superadmin = True
        staff_profile.save()
        self.staff = staff

        self.client = Client()
        self.client.force_login(staff)

        self.driver = make_driver('consoledriver', 9941)
        self.posting = DriverOpportunity.objects.create(
            title='Weekend riders', status='open', published_at=timezone.now())
        start = timezone.now() + timedelta(days=3)
        self.slot = DriverOpportunitySlot.objects.create(
            opportunity=self.posting, starts_at=start,
            ends_at=start + timedelta(hours=5), capacity=1)

    def test_list_page_loads(self):
        response = self.client.get(self.reverse('workforce:wf_opportunities'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Weekend riders')

    def test_detail_page_loads(self):
        response = self.client.get(
            self.reverse('workforce:wf_opportunity_detail', args=[self.posting.pk]))
        self.assertEqual(response.status_code, 200)

    def test_new_posting_form_loads(self):
        response = self.client.get(self.reverse('workforce:wf_opportunity_new'))
        self.assertEqual(response.status_code, 200)

    def test_creating_a_posting_stamps_published_at(self):
        """Publishing is the moment the board starts showing it."""
        response = self.client.post(self.reverse('workforce:wf_opportunity_new'), {
            'title': 'Night riders — Al Wakrah',
            'description': 'Overnight parcel runs',
            'status': 'open',
        })
        self.assertEqual(response.status_code, 302)

        created = DriverOpportunity.objects.get(title='Night riders — Al Wakrah')
        self.assertEqual(created.status, 'open')
        self.assertIsNotNone(created.published_at)
        self.assertEqual(created.created_by, self.staff)

    def test_a_draft_posting_is_not_stamped(self):
        self.client.post(self.reverse('workforce:wf_opportunity_new'), {
            'title': 'Draft posting', 'status': 'draft',
        })
        created = DriverOpportunity.objects.get(title='Draft posting')
        self.assertIsNone(created.published_at)

    def test_adding_a_shift(self):
        start = timezone.localtime(timezone.now() + timedelta(days=5))
        response = self.client.post(
            self.reverse('workforce:wf_opportunity_slot_save', args=[self.posting.pk]), {
                'starts_at': start.strftime('%Y-%m-%dT%H:%M'),
                'ends_at': (start + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
                'time_slab': 'evening',
                'capacity': '3',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.posting.slots.count(), 2)

    def test_a_shift_that_ends_before_it_starts_is_refused(self):
        """The model carries a CheckConstraint; the view must not hand staff a 500."""
        start = timezone.localtime(timezone.now() + timedelta(days=5))
        response = self.client.post(
            self.reverse('workforce:wf_opportunity_slot_save', args=[self.posting.pk]), {
                'starts_at': start.strftime('%Y-%m-%dT%H:%M'),
                'ends_at': (start - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'),
                'capacity': '1',
            })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.posting.slots.count(), 1)

    def test_confirming_a_driver_from_the_console(self):
        interest, _ = express_interest(self.driver, self.slot)
        response = self.client.post(
            self.reverse('workforce:wf_opportunity_interest_decide', args=[interest.pk]),
            {'status': 'confirmed'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        interest.refresh_from_db()
        self.assertEqual(interest.status, 'confirmed')
        self.assertEqual(interest.decided_by, self.staff)

    def test_console_refuses_to_overfill_a_slot(self):
        other = make_driver('consoledriver2', 9942)
        first, _ = express_interest(self.driver, self.slot)
        second, _ = express_interest(other, self.slot)
        set_interest_status(first, 'confirmed')

        response = self.client.post(
            self.reverse('workforce:wf_opportunity_interest_decide', args=[second.pk]),
            {'status': 'confirmed'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], SLOT_FULL_CODE)

    def test_a_shift_with_a_confirmed_driver_cannot_be_deleted(self):
        interest, _ = express_interest(self.driver, self.slot)
        set_interest_status(interest, 'confirmed')

        self.client.post(
            self.reverse('workforce:wf_opportunity_slot_delete', args=[self.slot.pk]))
        self.assertTrue(
            DriverOpportunitySlot.objects.filter(pk=self.slot.pk).exists())

    def test_an_empty_shift_can_be_deleted(self):
        self.client.post(
            self.reverse('workforce:wf_opportunity_slot_delete', args=[self.slot.pk]))
        self.assertFalse(
            DriverOpportunitySlot.objects.filter(pk=self.slot.pk).exists())

    def test_non_staff_cannot_reach_the_console(self):
        from django.test import Client

        outsider = get_user_model().objects.create_user(
            username='oppoutsider', email='oppoutsider@example.com', password=self.PASSWORD)
        Profile.objects.get_or_create(user=outsider)

        client = Client()
        client.force_login(outsider)
        response = client.get(self.reverse('workforce:wf_opportunities'))
        self.assertNotEqual(response.status_code, 200)
