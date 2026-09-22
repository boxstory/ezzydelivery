# Purpose: Lock the delivery task state machine's rules, including the returned-to-shipper terminal state.
# Used by: manage.py test delivery.tests_state_machine
# Notes: The module had no tests at all before this; delivery/signals.py reverts a refused transition
#        SILENTLY, so a gap here shows up in production as a status change that quietly does nothing.

from django.test import SimpleTestCase

from delivery.models import DeliveryTask
from delivery.state_machine import (
    DRIVER_TRANSITIONS, STAFF_TRANSITIONS, STATUS_STAGE,
    can_transition, get_allowed_transitions,
)

RETURNED = 'returned_to_shipper'


class StatusStageCoverageTests(SimpleTestCase):
    """The guard that would have caught this whole class of bug earlier."""

    def test_every_model_choice_has_a_stage(self):
        missing = [k for k, _ in DeliveryTask.DL_TASK_STATUS_CHOICES
                   if k not in STATUS_STAGE]
        self.assertEqual(
            missing, [],
            'These dl_task_status choices have no STATUS_STAGE entry, so every '
            'transition into them is refused and silently reverted: ' + ', '.join(missing))

    def test_every_driver_transition_target_is_a_known_status(self):
        unknown = set()
        for targets in DRIVER_TRANSITIONS.values():
            unknown |= {t for t in targets if t not in STATUS_STAGE}
        self.assertEqual(unknown, set())


class ReturnedToShipperTransitionTests(SimpleTestCase):

    def test_driver_can_return_from_every_stage_that_holds_goods(self):
        for origin in ('accepted', 'picked_up', 'start_ride', 'in_transit',
                       'out_for_delivery', 'contacted', 'non_reachable'):
            with self.subTest(origin=origin):
                ok, reason = can_transition(origin, RETURNED, actor='driver')
                self.assertTrue(ok, f'{origin} -> {RETURNED} refused: {reason}')

    def test_driver_cannot_return_a_task_they_never_picked_up(self):
        # Nothing is in the driver's hands at 'pending', so there is no parcel to
        # bring back — this would be a way to close a task they never accepted.
        ok, _ = can_transition('pending', RETURNED, actor='driver')
        self.assertFalse(ok)

    def test_failed_is_no_longer_a_dead_end_for_the_driver(self):
        # A driver who filed the failed attempt may still be carrying the parcel.
        ok, reason = can_transition('failed', RETURNED, actor='driver')
        self.assertTrue(ok, reason)

    def test_staff_may_return_a_task_already_closed_out(self):
        for origin in ('failed', 'non_reachable', 'dropsownlost'):
            with self.subTest(origin=origin):
                for actor in ('staff', 'admin'):
                    ok, reason = can_transition(origin, RETURNED, actor=actor)
                    self.assertTrue(ok, f'{actor} {origin} -> {RETURNED}: {reason}')

    def test_returned_is_terminal_for_everyone(self):
        for actor in ('driver', 'staff'):
            with self.subTest(actor=actor):
                self.assertEqual(get_allowed_transitions(RETURNED, actor=actor), set())
        for target in ('pending', 'delivered', 'cancelled', 'accepted'):
            with self.subTest(target=target):
                self.assertFalse(can_transition(RETURNED, target, actor='staff')[0])
                self.assertFalse(can_transition(RETURNED, target, actor='driver')[0])

    def test_staff_terminal_states_all_stay_closed(self):
        # Guards the hand-written tuple in _build_staff_transitions: a status added
        # to STATUS_STAGE at stage 8 but forgotten there stays open to sideways moves.
        for terminal in ('delivered', 'partial_delivery', RETURNED, 'failed',
                         'rejected', 'cancelled', 'dropsownlost'):
            with self.subTest(terminal=terminal):
                self.assertEqual(STAFF_TRANSITIONS[terminal], set())

    def test_admin_override_still_reaches_it(self):
        self.assertTrue(can_transition('for_review', RETURNED, actor='admin')[0])
