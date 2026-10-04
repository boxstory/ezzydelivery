# Purpose: Tests for the shared staff driver filter pool (workforce.views.driver_filter_choices).
# Used by: manage.py test workforce.tests_driver_filter
# Notes: Guards the two ways the picker has already lost real drivers — a device row that is
#        pending or revoked mid re-verification, and a driver who was never issued one at all.

from django.test import TestCase

from fleet import models as fleet_models
from workforce.tests_views import WorkforceTestMixin
from workforce.views import (
    driver_filter_choices,
    driver_filter_labels,
)


class DriverFilterChoicesTests(WorkforceTestMixin, TestCase):
    """Who the driver picker offers, and who it must never drop."""

    def _device(self, driver, status):
        return fleet_models.DriverDevice.objects.create(
            user=driver.user, device_token=f'tok{driver.driver_id}{status}',
            status=status)

    def _ids(self, **kwargs):
        return {d.driver_id for d in driver_filter_choices(**kwargs)}

    def test_approved_driver_listed_without_any_device(self):
        """Fleet size, not app sign-in, is what puts a name in the picker."""
        driver = self.create_driver(code='NOAPP1')
        self.assertIn(driver.driver_id, self._ids())

    def test_driver_mid_device_reverification_still_listed(self):
        """Signing in on a new handset revokes the old row and leaves the new
        one pending — the driver must not vanish from the filter meanwhile."""
        driver = self.create_driver(code='REVER1')
        self._device(driver, fleet_models.DriverDevice.STATUS_REVOKED)
        self._device(driver, fleet_models.DriverDevice.STATUS_PENDING)
        self.assertIn(driver.driver_id, self._ids())

    def test_blocked_driver_with_tasks_still_listed(self):
        """A blocked account keeps the jobs it already ran, and those rows are
        on the list — so the filter has to be able to name it."""
        business = self.create_business(bid=9601, code='DFB1')
        pickup = self.create_pickup_location(business)
        order = self.create_order(business, pickup_location=pickup)
        driver = self.create_driver(status='blocked', code='BLKD1')
        self.create_delivery_task(order, driver=driver)
        self.assertIn(driver.driver_id, self._ids())

    def test_pending_applicant_without_tasks_not_listed(self):
        """804 applicants are not the fleet; only approved or already-working
        drivers belong in the pool."""
        applicant = self.create_driver(status='pending', code='APPL1')
        self.assertNotIn(applicant.driver_id, self._ids())

    def test_picked_driver_is_readmitted_and_named(self):
        """A driver on the querystring stays in the select whatever their
        state, or the next submit silently discards the applied filter."""
        applicant = self.create_driver(status='pending', code='APPL2')
        picked = str(applicant.driver_id)
        choices = driver_filter_choices(include_ids=[picked])
        self.assertIn(applicant.driver_id, {d.driver_id for d in choices})
        self.assertEqual(
            driver_filter_labels([picked], choices),
            [f'{applicant.user.first_name} {applicant.user.last_name}'.strip()])

    def test_has_app_reports_a_live_sign_in(self):
        """App access is reported on the option, never used to hide a name."""
        with_app = self.create_driver(code='HASAPP')
        self._device(with_app, fleet_models.DriverDevice.STATUS_ACTIVE)
        without = self.create_driver(code='NOAPP2')
        flags = {d.driver_id: d.has_app for d in driver_filter_choices()}
        self.assertTrue(flags[with_app.driver_id])
        self.assertFalse(flags[without.driver_id])

    def test_no_duplicate_rows_for_a_driver_with_many_devices(self):
        """One active device and several revoked ones used to multiply the
        rows; the pool is built with EXISTS for that reason."""
        driver = self.create_driver(code='MANYDV')
        for seq, status in enumerate((fleet_models.DriverDevice.STATUS_REVOKED,
                                      fleet_models.DriverDevice.STATUS_REVOKED,
                                      fleet_models.DriverDevice.STATUS_ACTIVE)):
            fleet_models.DriverDevice.objects.create(
                user=driver.user, status=status,
                device_token=f'tokm{driver.driver_id}-{seq}')
        listed = [d.driver_id for d in driver_filter_choices()]
        self.assertEqual(listed.count(driver.driver_id), 1)
