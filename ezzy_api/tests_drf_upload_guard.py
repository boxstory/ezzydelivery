# Purpose: Prove the installed DRF enforces DATA_UPLOAD_MAX_MEMORY_SIZE on request.data.
# Used by: manage.py test ezzy_api.tests_drf_upload_guard (temporary upgrade probe).
# Notes: DRF 3.15.2 parsed the body regardless of the limit — an unauthenticated DoS on any
#        API view. This asserts the 3.17 behaviour, so a downgrade would fail loudly.

import json

from django.test import TestCase, override_settings
from django.core.exceptions import RequestDataTooBig
from rest_framework.test import APIRequestFactory
from rest_framework.request import Request
from rest_framework.parsers import JSONParser


class UploadLimitIsEnforced(TestCase):
    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1024)
    def test_oversized_json_body_is_refused(self):
        body = json.dumps({'padding': 'x' * 50_000})
        raw = APIRequestFactory().post(
            '/api/probe/', body, content_type='application/json')
        request = Request(raw, parsers=[JSONParser()])

        with self.assertRaises(RequestDataTooBig):
            request.data

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=1024)
    def test_a_small_body_still_parses(self):
        """The guard must not break ordinary traffic."""
        raw = APIRequestFactory().post(
            '/api/probe/', json.dumps({'ok': 1}), content_type='application/json')
        self.assertEqual(Request(raw, parsers=[JSONParser()]).data, {'ok': 1})
