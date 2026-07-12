# Purpose: Tests for authenticated protected-media serving (X-Accel-Redirect gate).
# Used by: manage.py test core.tests_media
# Notes: Writes throwaway files under a temp MEDIA_ROOT so the auth checks run against
#        real paths without touching the real media dir.

import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from business import models as business_models
from core import models as core_models
from orders import models as orders_models

User = get_user_model()

_TMP_MEDIA = tempfile.mkdtemp(prefix='ezzy_media_test_')


def _mkfile(rel):
    full = os.path.join(_TMP_MEDIA, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'wb') as f:
        f.write(b'test-bytes')
    return full


def _mk_user_business(idx, username, is_staff=False):
    user = User.objects.create_user(username=username, password='pass12345')
    profile = core_models.Profile.objects.create(
        user=user, first_name='T', last_name='U', phone=40000000 + idx, is_staff=is_staff
    )
    business = business_models.Business.objects.create(
        business_id=idx, user=user, profile=profile,
        business_name=f'Biz {idx}', business_code=f'BC{idx}',
        business_phone='55500000', business_email=f'b{idx}@e.com',
    )
    return user, business


@override_settings(MEDIA_ROOT=_TMP_MEDIA)
class ProtectedMediaTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(_TMP_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.owner, self.biz = _mk_user_business(8001, 'media_owner')
        self.other, self.other_biz = _mk_user_business(8002, 'media_other')
        self.staff, _ = _mk_user_business(8003, 'media_staff', is_staff=True)
        _mkfile(f'shipping_labels/{self.biz.business_code}/LBL-1.png')

    def _get(self, user, path):
        self.client.force_login(user)
        return self.client.get(f'/media/{path}', SERVER_NAME='ezzydelivery.qa', secure=True)

    def test_unauthenticated_redirected_to_login(self):
        resp = self.client.get(
            f'/media/shipping_labels/{self.biz.business_code}/LBL-1.png',
            SERVER_NAME='ezzydelivery.qa', secure=True,
        )
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn('/accounts/login', resp['Location'])

    def test_owner_gets_x_accel_redirect(self):
        resp = self._get(self.owner, f'shipping_labels/{self.biz.business_code}/LBL-1.png')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['X-Accel-Redirect'],
            f'/__protected_media__/shipping_labels/{self.biz.business_code}/LBL-1.png',
        )

    def test_other_business_forbidden(self):
        resp = self._get(self.other, f'shipping_labels/{self.biz.business_code}/LBL-1.png')
        self.assertEqual(resp.status_code, 403)

    def test_staff_allowed(self):
        resp = self._get(self.staff, f'shipping_labels/{self.biz.business_code}/LBL-1.png')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('X-Accel-Redirect', resp)

    def test_missing_file_404(self):
        resp = self._get(self.staff, f'shipping_labels/{self.biz.business_code}/nope.png')
        self.assertEqual(resp.status_code, 404)

    def test_path_traversal_blocked(self):
        # Django collapses ../ in the URL path, so the request never resolves to
        # the protected-media pattern; the key property is that it is NOT served.
        resp = self._get(self.staff, 'shipping_labels/../../etc/passwd')
        self.assertIn(resp.status_code, (403, 404))

    def test_order_document_scoped_to_owning_business(self):
        order = orders_models.Order.objects.create(
            business=self.biz, order_number='MED-1', client_order_code='MED-1',
            customer_name='C', customer_phone='555', customer_address='Z1',
            order_status='to_review',
        )
        _mkfile(f'orders/{order.id}/documents/doc.pdf')
        self.assertEqual(self._get(self.owner, f'orders/{order.id}/documents/doc.pdf').status_code, 200)
        self.assertEqual(self._get(self.other, f'orders/{order.id}/documents/doc.pdf').status_code, 403)
