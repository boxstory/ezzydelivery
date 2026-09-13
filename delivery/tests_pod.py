# Purpose: Tests for the per-client proof-of-delivery rule — resolution, the API gate, the partial gate.
# Used by: python manage.py test delivery.tests_pod

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from delivery import pod
from ezzy_api import models as ezzy_api_models
from fleet import models as fleet_models
from orders import models as orders_models

User = get_user_model()

# A 1x1 GIF — the smallest thing that survives the image validator on the upload path.
TINY_GIF = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
)


def a_photo(name='proof.gif'):
    return SimpleUploadedFile(name, TINY_GIF, content_type='image/gif')


class PodBaseTestCase(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='podbiz', password='x')
        owner_profile = core_models.Profile.objects.create(
            user=owner, first_name='Pod', last_name='Biz', phone=71111111)
        self.business = business_models.Business.objects.create(
            business_id=910, user=owner, profile=owner_profile,
            business_name='Proof Client', business_code='POD001',
            business_status='active',
        )

        self.driver_user = User.objects.create_user(username='poddriver', password='x')
        driver_profile = core_models.Profile.objects.create(
            user=self.driver_user, first_name='Pod', last_name='Driver', phone=72222222,
            is_driver=True)   # @driver_required on the fleet views reads this flag
        self.driver = fleet_models.Driver.objects.create(
            driver_id=9100, user=self.driver_user, profile=driver_profile,
            driver_code='PODD1', driver_phone='30000001', driver_whatsapp='30000001',
            driver_languages='english', driver_license_number='PODLIC1',
            driver_status='approved',
        )

        self.order = orders_models.Order.objects.create(
            business=self.business, client_order_code='POD-1',
            customer_name='Cust', customer_phone='55555555',
            customer_address='Somewhere', dl_zone=55,
        )
        self.task = delivery_models.DeliveryTask.objects.create(
            order=self.order, business=self.business, driver=self.driver,
            dl_task_number='POD-TASK-1', dl_task_status='out_for_delivery',
            dl_task_publish=True, dl_price=20,
        )

    def require(self, delivered=False, failed=False, kind='photo'):
        self.business.pod_required_delivered = delivered
        self.business.pod_required_failed = failed
        self.business.pod_kind = kind
        self.business.save(update_fields=[
            'pod_required_delivered', 'pod_required_failed', 'pod_kind'])
        self.task.refresh_from_db()


class PodRequirementTestCase(PodBaseTestCase):
    def test_nothing_required_by_default(self):
        for outcome in ('delivered', 'partial_delivery', 'failed'):
            self.assertIsNone(pod.requirement_for(self.task, outcome))
            self.assertIsNone(pod.missing(self.task, outcome))

    def test_delivered_rule_covers_partial(self):
        self.require(delivered=True, kind='photo')
        self.assertEqual(pod.requirement_for(self.task, 'delivered'), 'photo')
        self.assertEqual(pod.requirement_for(self.task, 'partial_delivery'), 'photo')
        self.assertIsNone(pod.requirement_for(self.task, 'failed'))

    def test_failed_rule_is_photo_even_when_kind_is_signature(self):
        # Nobody is standing there to sign for a parcel they did not take.
        self.require(failed=True, kind='signature')
        self.assertEqual(pod.requirement_for(self.task, 'failed'), 'photo')

    def test_both_needs_each_part(self):
        self.require(delivered=True, kind='both')
        self.assertIn('photo', pod.missing(self.task, 'delivered', {'signature'}))
        self.assertIn('signature', pod.missing(self.task, 'delivered', {'photo'}))
        self.assertIsNone(pod.missing(self.task, 'delivered', {'photo', 'signature'}))

    def test_existing_delivery_proof_satisfies_the_rule(self):
        self.require(delivered=True, kind='photo')
        self.assertIsNotNone(pod.missing(self.task, 'delivered'))
        delivery_models.DeliveryProof.objects.create(
            delivery_task=self.task, proof_type='photo', photo=a_photo())
        self.assertIsNone(pod.missing(self.task, 'delivered'))

    def test_existing_task_document_satisfies_the_rule(self):
        # The two stores are written by different endpoints; both have to count.
        self.require(delivered=True, kind='photo')
        ezzy_api_models.TaskDocument.objects.create(
            task=self.task, document_type='delivery_proof', document_file=a_photo())
        self.assertIsNone(pod.missing(self.task, 'delivered'))

    def test_signature_document_does_not_pass_for_a_photo(self):
        self.require(delivered=True, kind='photo')
        ezzy_api_models.TaskDocument.objects.create(
            task=self.task, document_type='signature', document_file=a_photo())
        self.assertIsNotNone(pod.missing(self.task, 'delivered'))

    def test_barcode_scan_is_not_proof_of_handover(self):
        self.require(delivered=True, kind='photo')
        delivery_models.DeliveryProof.objects.create(
            delivery_task=self.task, proof_type='barcode_scan', photo=a_photo())
        self.assertIsNotNone(pod.missing(self.task, 'delivered'))

    def test_business_falls_back_to_the_order(self):
        self.require(delivered=True, kind='photo')
        self.task.business = None
        self.task.save(update_fields=['business'])
        self.assertEqual(pod.requirement_for(self.task, 'delivered'), 'photo')

    def test_supplied_kinds_reads_the_upload_keys(self):
        self.assertEqual(pod.supplied_kinds({'delivery_proof': 1}), {'photo'})
        self.assertEqual(pod.supplied_kinds({'signature': 1}), {'signature'})
        self.assertEqual(
            pod.supplied_kinds({'photo': 1, 'signature': 1}), {'photo', 'signature'})
        self.assertEqual(pod.supplied_kinds({}), set())


class PodCompleteApiTestCase(PodBaseTestCase):
    """The gate that counts: a direct post must not close a task without proof."""

    url_name = '/api/driver/tasks/{}/complete/'

    def setUp(self):
        super().setUp()
        self.client.force_login(self.driver_user)
        self.url = self.url_name.format(self.task.id)

    def test_delivered_blocked_without_proof(self):
        self.require(delivered=True, kind='photo')
        response = self.client.post(self.url, {'status': 'delivered'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('proof of delivery', response.json()['error'].lower())
        self.task.refresh_from_db()
        self.assertEqual(self.task.dl_task_status, 'out_for_delivery')

    def test_delivered_allowed_with_photo(self):
        self.require(delivered=True, kind='photo')
        response = self.client.post(
            self.url, {'status': 'delivered', 'delivery_proof': a_photo()})
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.dl_task_status, 'delivered')

    def test_delivered_needs_the_signature_too(self):
        self.require(delivered=True, kind='both')
        response = self.client.post(
            self.url, {'status': 'delivered', 'delivery_proof': a_photo()})
        self.assertEqual(response.status_code, 400)
        self.assertIn('signature', response.json()['error'].lower())

        response = self.client.post(self.url, {
            'status': 'delivered',
            'delivery_proof': a_photo(),
            'signature': a_photo('sign.gif'),
        })
        self.assertEqual(response.status_code, 200, response.content)

    def test_failed_blocked_without_photo(self):
        self.require(failed=True)
        response = self.client.post(
            self.url, {'status': 'failed', 'failure_reason': 'customer_refused'})
        self.assertEqual(response.status_code, 400)
        self.task.refresh_from_db()
        self.assertEqual(self.task.dl_task_status, 'out_for_delivery')

    def test_failed_allowed_with_photo(self):
        self.require(failed=True)
        response = self.client.post(self.url, {
            'status': 'failed',
            'failure_reason': 'customer_refused',
            'delivery_proof': a_photo(),
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.task.refresh_from_db()
        self.assertEqual(self.task.dl_task_status, 'failed')

    def test_failed_not_blocked_by_the_delivered_rule(self):
        self.require(delivered=True, kind='photo')
        response = self.client.post(
            self.url, {'status': 'failed', 'failure_reason': 'customer_refused'})
        self.assertEqual(response.status_code, 200, response.content)

    def test_no_rule_no_proof_still_closes(self):
        response = self.client.post(self.url, {'status': 'delivered'})
        self.assertEqual(response.status_code, 200, response.content)


class PodPartialDeliveryTestCase(PodBaseTestCase):
    """Partial is a hand-over too, so it must not be the way around the rule."""

    def setUp(self):
        super().setUp()
        self.item = orders_models.OrderItem.objects.create(
            order=self.order, quantity=2, unit_price=10)
        self.client.force_login(self.driver_user)
        self.url = f'/fleet/tasks/{self.task.id}/partial-delivery/'

    def _post(self):
        return self.client.post(
            self.url,
            data={'items': [{'order_item_id': self.item.id, 'qty_returned': 1}],
                  'actual_cod': 0},
            content_type='application/json',
        )

    def test_blocked_without_proof(self):
        self.require(delivered=True, kind='photo')
        payload = self._post().json()
        self.assertFalse(payload['success'])
        self.assertIn('proof of delivery', payload['error'].lower())
        self.task.refresh_from_db()
        self.assertEqual(self.task.dl_task_status, 'out_for_delivery')

    def test_allowed_once_the_proof_is_filed(self):
        self.require(delivered=True, kind='photo')
        delivery_models.DeliveryProof.objects.create(
            delivery_task=self.task, proof_type='photo', photo=a_photo())
        self.assertTrue(self._post().json()['success'])

    def test_not_blocked_when_no_rule_is_set(self):
        self.assertTrue(self._post().json()['success'])


class PodUploadEndpointTestCase(PodBaseTestCase):
    """The proof endpoint the partial sheet uploads through before submitting."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.driver_user)
        self.url = f'/fleet/task/{self.task.id}/proof/upload/'

    def test_upload_counts_as_proof(self):
        self.require(delivered=True, kind='photo')
        response = self.client.post(self.url, {'photo': a_photo(), 'proof_type': 'photo'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(pod.missing(self.task, 'delivered'))

    def test_unknown_proof_type_stores_as_photo(self):
        # An unrecognised value would never match the check that reads these back.
        response = self.client.post(self.url, {'photo': a_photo(), 'proof_type': 'nonsense'})
        self.assertEqual(response.status_code, 200, response.content)
        proof = delivery_models.DeliveryProof.objects.get(delivery_task=self.task)
        self.assertEqual(proof.proof_type, 'photo')

    def test_signature_upload_is_kept_apart_from_a_photo(self):
        self.require(delivered=True, kind='photo')
        self.client.post(self.url, {'photo': a_photo('s.gif'), 'proof_type': 'signature'})
        self.assertIsNotNone(pod.missing(self.task, 'delivered'))
        self.assertEqual(pod.existing_kinds(self.task), {'signature'})
