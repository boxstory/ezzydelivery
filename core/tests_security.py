"""
Purpose: Regression tests for the input-hardening layer (safe_json, validators, form rate limits).
Used by: manage.py test core.tests_security
Notes: Rate-limit tests clear the 'ratelimit' cache alias in setUp — that is where django-ratelimit
       counters live (RATELIMIT_USE_CACHE), not the default cache.
"""
import json

from django.core.cache import cache, caches
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings

from core.json_utils import escape_json_string, safe_json
from core.validators import (
    MaxFileSizeValidator, safe_decimal, safe_int, sanitize_csv_cell,
    sanitize_csv_row, sanitize_text, validate_upload_file,
)


class _FakeUpload:
    def __init__(self, name, size):
        self.name = name
        self.size = size


class SafeJsonTests(TestCase):
    """A payload that closes the surrounding <script> must not survive."""

    def test_script_breakout_is_escaped(self):
        payload = {'driver_name': '</script><script>alert(1)</script>'}
        out = str(safe_json(payload))
        self.assertNotIn('</script>', out)
        self.assertNotIn('<', out)
        self.assertNotIn('>', out)

    def test_ampersand_is_escaped(self):
        self.assertNotIn('&', str(safe_json({'note': 'a & b'})))

    def test_output_still_parses_back_to_the_original(self):
        payload = [{'a': '</script>', 'b': 'x & y', 'c': '<tag>', 'd': 1, 'e': None}]
        self.assertEqual(json.loads(str(safe_json(payload))), payload)

    def test_line_separators_are_escaped(self):
        # U+2028 terminates a JS statement even inside a string literal.
        self.assertNotIn(' ', str(safe_json({'x': 'a b'})))

    def test_result_is_marked_safe_so_templates_do_not_double_escape(self):
        from django.template import Context, Template
        rendered = Template('{{ blob }}').render(Context({'blob': safe_json({'a': 1})}))
        self.assertEqual(rendered, '{"a": 1}')

    def test_escape_json_string_handles_preserialised_input(self):
        out = str(escape_json_string('{"a":"</script>"}'))
        self.assertNotIn('</script>', out)
        self.assertEqual(json.loads(out), {'a': '</script>'})

    def test_escape_json_string_handles_none(self):
        self.assertEqual(str(escape_json_string(None)), 'null')


class UploadValidatorTests(TestCase):

    def test_disallowed_extension_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_upload_file(_FakeUpload('shell.php', 100), ['pdf', 'jpg'], 5)

    def test_double_extension_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_upload_file(_FakeUpload('invoice.pdf.php', 100), ['pdf'], 5)

    def test_allowed_extension_passes_case_insensitively(self):
        upload = _FakeUpload('scan.PDF', 100)
        self.assertIs(validate_upload_file(upload, ['pdf'], 5), upload)

    def test_oversize_upload_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_upload_file(_FakeUpload('big.pdf', 20 * 1024 * 1024), ['pdf'], 5)

    def test_max_file_size_validator_is_deconstructible_for_migrations(self):
        path, args, kwargs = MaxFileSizeValidator(8).deconstruct()
        self.assertEqual(path, 'core.validators.MaxFileSizeValidator')
        self.assertEqual(MaxFileSizeValidator(8), MaxFileSizeValidator(8))
        self.assertNotEqual(MaxFileSizeValidator(8), MaxFileSizeValidator(5))

    def test_max_file_size_validator_rejects_oversize(self):
        with self.assertRaises(ValidationError):
            MaxFileSizeValidator(1)(_FakeUpload('a.png', 2 * 1024 * 1024))


class CsvSanitisationTests(TestCase):

    def test_formula_prefixes_are_neutralised(self):
        for raw in ('=1+1', '+1', '-1', '@SUM(A1)', '\t=cmd', '  =cmd'):
            self.assertTrue(sanitize_csv_cell(raw).startswith("'"), raw)

    def test_ordinary_text_is_untouched(self):
        self.assertEqual(sanitize_csv_cell('Ahmed Ali'), 'Ahmed Ali')

    def test_non_strings_keep_their_type(self):
        self.assertEqual(sanitize_csv_cell(42), 42)
        self.assertIsNone(sanitize_csv_cell(None))

    def test_row_helper_applies_to_every_cell(self):
        self.assertEqual(sanitize_csv_row(['=a', 'b', 3]), ["'=a", 'b', 3])


class CoercionTests(TestCase):

    def test_unparseable_input_falls_back_instead_of_raising(self):
        self.assertEqual(safe_int('abc', default=30), 30)
        self.assertEqual(safe_int(None, default=7), 7)
        self.assertEqual(safe_int('', default=7), 7)

    def test_bounds_are_clamped(self):
        self.assertEqual(safe_int('9999', default=50, maximum=200), 200)
        self.assertEqual(safe_int('-5', default=0, minimum=1), 1)

    def test_decimal_variant(self):
        self.assertEqual(safe_decimal('12.5'), 12.5)
        self.assertIsNone(safe_decimal('nonsense'))
        self.assertEqual(safe_decimal('999', maximum=100), 100)


class TextSanitisationTests(TestCase):

    def test_control_characters_are_stripped(self):
        self.assertEqual(sanitize_text('Ah\x00med\x07'), 'Ahmed')

    def test_zero_width_characters_are_stripped(self):
        self.assertEqual(sanitize_text('Ah​med'), 'Ahmed')

    def test_bidi_override_is_stripped(self):
        self.assertEqual(sanitize_text('file‮gnp.exe'), 'filegnp.exe')

    def test_newlines_survive_by_default(self):
        self.assertEqual(sanitize_text('line1\nline2'), 'line1\nline2')

    def test_whitespace_collapse_is_opt_in(self):
        self.assertEqual(sanitize_text('a   b', collapse_whitespace=True), 'a b')

    def test_non_strings_pass_through(self):
        self.assertEqual(sanitize_text(5), 5)


@override_settings(ALLOWED_HOSTS=['testserver'])
class PublicFormRateLimitTests(TestCase):
    """The public marketing forms must stop accepting after the hourly cap."""

    def setUp(self):
        # Counters live in the dedicated 'ratelimit' alias, not the default cache.
        cache.clear()
        caches['ratelimit'].clear()
        self.client = Client()

    def tearDown(self):
        cache.clear()
        caches['ratelimit'].clear()

    def test_contact_form_stops_saving_past_the_cap(self):
        from webpages.models import ContactUs
        payload = {'full_name': 'Spam Bot', 'email': 'spam@example.com',
                   'mobile': '55555555', 'purpose': ['o'], 'message': 'buy now'}
        for _ in range(9):
            self.client.post('/contactus/', payload, HTTP_CF_CONNECTING_IP='203.0.113.9')
        saved = ContactUs.objects.filter(full_name='Spam Bot').count()
        self.assertEqual(saved, 5, f'rate limit let {saved} submissions through, expected 5')

    def test_a_different_ip_gets_its_own_budget(self):
        from webpages.models import ContactUs
        payload = {'full_name': 'Other Visitor', 'email': 'x@example.com',
                   'mobile': '55555556', 'purpose': ['o'], 'message': 'hello'}
        for _ in range(6):
            self.client.post('/contactus/', payload, HTTP_CF_CONNECTING_IP='203.0.113.10')
        self.client.post('/contactus/', dict(payload, full_name='Fresh IP'),
                         HTTP_CF_CONNECTING_IP='198.51.100.4')
        self.assertEqual(ContactUs.objects.filter(full_name='Fresh IP').count(), 1)

    def test_get_requests_are_not_counted(self):
        for _ in range(20):
            response = self.client.get('/contactus/', HTTP_CF_CONNECTING_IP='203.0.113.11')
        self.assertEqual(response.status_code, 200)


class SanitizedFormMixinTests(TestCase):
    """The mixin must clean text without disturbing secrets or multi-value fields."""

    def test_control_characters_never_reach_cleaned_data(self):
        from webpages.forms import ContactForm
        form = ContactForm(data={'full_name': 'Ah\x00med', 'email': 'a@b.com',
                                 'mobile': '55123456', 'purpose': ['o'], 'message': 'hi'})
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data['full_name'], 'Ahmed')

    def test_multi_value_fields_survive_the_querydict_copy(self):
        from django.http import QueryDict
        from webpages.forms import ContactForm
        data = QueryDict(mutable=True)
        data.update({'full_name': 'A', 'email': 'a@b.com', 'mobile': '55123456', 'message': 'hi'})
        data.setlist('purpose', ['o', 'fb'])
        form = ContactForm(data)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data['purpose'], ['o', 'fb'])

    def test_passwords_are_never_touched(self):
        from core.forms import CustomSignupForm
        secret = '  Sp ace Pass\x01word  '
        form = CustomSignupForm(data={'username': 'u', 'email': 'a@b.com',
                                      'password1': secret, 'password2': secret})
        form.is_valid()
        self.assertEqual(form.data['password1'], secret)

    def test_an_unbound_form_is_left_alone(self):
        from webpages.forms import ContactForm
        self.assertFalse(ContactForm().is_bound)


class FleetFormAllowlistTests(TestCase):
    """fields='__all__' used to expose every column the model grows."""

    def test_operational_columns_are_not_assignable(self):
        from fleet.forms import DriverJoinForm
        exposed = set(DriverJoinForm().fields)
        for protected in ('driver_status', 'wallet_balance', 'credit_limit', 'cod_in_hand',
                          'total_earnings', 'driver_meta', 'to_be_notified'):
            self.assertNotIn(protected, exposed)

    def test_posting_a_protected_field_is_ignored(self):
        from fleet.forms import DriverJoinForm
        form = DriverJoinForm(data={
            'driver_phone': '55123456', 'driver_whatsapp': '55123456',
            'driver_languages': 'english', 'driver_bio': 'hi',
            'driver_meta': '{"registration_location": "spoofed"}',
        })
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertNotIn('driver_meta', form.cleaned_data)

    def test_phone_is_normalised(self):
        from fleet.forms import DriverJoinForm
        form = DriverJoinForm(data={
            'driver_phone': '+974 5512-3456', 'driver_whatsapp': '(974) 5512 3456',
            'driver_languages': 'english', 'driver_bio': 'hi'})
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data['driver_phone'], '55123456')
        self.assertEqual(form.cleaned_data['driver_whatsapp'], '55123456')

    def test_invalid_qatar_prefix_is_rejected(self):
        from fleet.forms import DriverJoinForm
        form = DriverJoinForm(data={'driver_phone': '12345678', 'driver_languages': 'english'})
        self.assertFalse(form.is_valid())
        self.assertIn('driver_phone', form.errors)

    def test_plate_number_rejects_markup(self):
        from fleet.forms import DriverVehicleForm
        form = DriverVehicleForm(data={'vehicle_type': 'car', 'vehicle_no': '<script>x</script>'})
        self.assertFalse(form.is_valid())
        self.assertIn('vehicle_no', form.errors)


class SsrfGuardTests(TestCase):
    """The merchant store URL is fetched by our own server."""

    def _error(self, url):
        from business.forms import businessApiSettingsForm
        form = businessApiSettingsForm(data={'api_type': 'woocommerce', 'site_api_url': url})
        form.is_valid()
        return form.errors.get('site_api_url')

    def test_internal_targets_are_rejected(self):
        for url in ('http://127.0.0.1:8000/admin/',
                    'http://169.254.169.254/latest/meta-data/',
                    'http://192.168.1.1/',
                    'http://10.0.0.5/',
                    'file:///etc/passwd'):
            self.assertIsNotNone(self._error(url), f'{url} should have been rejected')

    def test_a_real_store_url_is_accepted(self):
        self.assertIsNone(self._error('https://myshop.myshopify.com'))

    def test_a_bare_hostname_gets_https_assumed(self):
        self.assertIsNone(self._error('myshop.myshopify.com'))


class SafeCsvWriterTests(TestCase):

    def test_formula_cells_are_neutralised_on_write(self):
        import io
        from core.exports import safe_csv_writer
        buf = io.StringIO()
        writer = safe_csv_writer(buf)
        writer.writerow(['=cmd|calc', 'Ahmed', 5])
        writer.writerows([['+HYPERLINK("x")', 'ok']])
        output = buf.getvalue()
        self.assertIn("'=cmd|calc", output)
        self.assertIn("'+HYPERLINK", output)
        self.assertIn('Ahmed', output)


class RegressionGuardTests(TestCase):
    """Regressions the hardening pass itself introduced — caught by council review."""

    def test_safe_json_is_not_applied_to_a_value_the_template_iterates(self):
        """R1: stage_keys must stay a list; {% for %} over a JSON string yields junk columns."""
        from workforce.views import AUTO_STAGE_KEYS
        from django.template import Context, Template
        rendered = Template('{% for k in stage_keys %}[{{ k }}]{% endfor %}').render(
            Context({'stage_keys': AUTO_STAGE_KEYS}))
        self.assertEqual(rendered.count('['), len(AUTO_STAGE_KEYS))
        self.assertIn('[ai_parse]', rendered)

    def test_zwnj_and_zwj_survive_sanitisation(self):
        """R2: ZWNJ is orthographic in Persian/Arabic; ZWJ builds emoji sequences."""
        self.assertEqual(sanitize_text('نمی‌خواهم'),
                         'نمی‌خواهم')
        self.assertEqual(sanitize_text('\U0001F468‍\U0001F469‍\U0001F467'),
                         '\U0001F468‍\U0001F469‍\U0001F467')

    def test_bidi_override_and_zero_width_space_are_still_stripped(self):
        self.assertEqual(sanitize_text('file‮gnp.exe'), 'filegnp.exe')
        self.assertEqual(sanitize_text('Ah​med'), 'Ahmed')
        self.assertEqual(sanitize_text('﻿Ahmed'), 'Ahmed')

    def test_every_qatar_dial_format_normalises_to_one(self):
        """R3: 00974 used to fall through unnormalised, creating a third stored format."""
        from core.validators import normalize_qatar_phone
        for raw in ('+974 5512-3456', '97455123456', '0097455123456',
                    '55123456', '(974) 5512 3456'):
            self.assertEqual(normalize_qatar_phone(raw), '55123456', raw)


class CouncilFindingTests(TestCase):
    """Fixes for findings raised by the adversarial council review."""

    def test_inquiry_preview_is_staff_gated(self):
        """A driver or rival seller must not be able to walk the lead table."""
        import inspect
        from webpages import views as webpages_views
        src = inspect.getsource(webpages_views.inquiry_preview)
        self.assertTrue(hasattr(webpages_views.inquiry_preview, '__wrapped__'))
        self.assertIn('Staff-gated', src)

    def test_order_serializer_locks_the_settlement_cluster(self):
        from ezzy_api.serializers import OrderSerializer
        fields = OrderSerializer().fields
        for name in ('business', 'cod_status_by_staff', 'cod_amount_locked',
                     'verification_status', 'address_verified', 'verified_by',
                     'address_verified_by', 'qnas_status', 'original_order_data',
                     'task_status'):
            self.assertTrue(fields[name].read_only, f'{name} is still client-writable')

    def test_client_still_controls_its_own_cod_declaration(self):
        """The lockdown must not take away what a client legitimately sets."""
        from ezzy_api.serializers import OrderSerializer
        fields = OrderSerializer().fields
        for name in ('cod_amount', 'cod_status_by_client', 'customer_name', 'customer_phone'):
            self.assertFalse(fields[name].read_only, f'{name} should stay client-writable')

    def test_wa_media_never_serves_active_content_types(self):
        from workforce.crm_views import _safe_media_type
        for hostile in ('text/html', 'image/svg+xml', 'application/xhtml+xml',
                        'text/html; charset=utf-8', 'application/javascript'):
            self.assertEqual(_safe_media_type(hostile), 'application/octet-stream', hostile)

    def test_wa_media_still_serves_real_attachments_inline(self):
        from workforce.crm_views import _safe_media_type
        self.assertEqual(_safe_media_type('image/jpeg'), 'image/jpeg')
        self.assertEqual(_safe_media_type('application/pdf'), 'application/pdf')
        self.assertEqual(_safe_media_type('audio/ogg; codecs=opus'), 'audio/ogg')

    def test_rate_limit_cache_is_shared_and_not_locmem(self):
        from django.conf import settings
        from django.core.cache import caches
        self.assertEqual(settings.RATELIMIT_USE_CACHE, 'ratelimit')
        self.assertNotIn('locmem', type(caches['ratelimit']).__module__.lower())

    def test_upload_filenames_are_rebuilt_not_trusted(self):
        from core.validators import IMAGE_EXTENSIONS, safe_upload_name
        name = safe_upload_name('../../pwn.html', IMAGE_EXTENSIONS, fallback_ext='jpg')
        self.assertNotIn('pwn', name)
        self.assertNotIn('/', name)
        self.assertTrue(name.endswith('.jpg'))
        self.assertTrue(safe_upload_name('photo.PNG', IMAGE_EXTENSIONS).endswith('.png'))

    def test_whatsapp_media_extensions_cover_what_is_actually_archived(self):
        """A narrower list would have broken voice-note archiving (166 .oga files)."""
        from core.validators import MEDIA_EXTENSIONS
        for ext in ('jpg', 'oga', 'pdf', 'mp4', 'webp', 'xlsx', 'csv'):
            self.assertIn(ext, MEDIA_EXTENSIONS)

    def test_warehouse_seller_access_stays_off_until_endpoints_are_scoped(self):
        from warehouse import views as wh
        self.assertFalse(wh.WAREHOUSE_SELLER_ACCESS_ENABLED)

    def test_warehouse_business_lookup_uses_the_real_model(self):
        """The old name raised ImportError into a bare except and returned None."""
        import inspect
        from warehouse import views as wh
        src = inspect.getsource(wh.get_cached_business_for_user)
        self.assertIn('BusinessTeamProfile', src)
        self.assertIn("team_status='active'", src)

    def test_env_writer_rejects_line_breaks(self):
        import inspect
        from workforce import views as wf_views
        self.assertIn('must not contain line breaks', inspect.getsource(wf_views))

    def test_prefixed_forms_honour_their_sanitize_config(self):
        from django.http import QueryDict
        from fleet.forms import DriverVehicleForm
        data = QueryDict(mutable=True)
        data.update({'veh-vehicle_type': 'car', 'veh-vehicle_no': '  AB   123  '})
        form = DriverVehicleForm(data, prefix='veh')
        form.is_valid()
        self.assertEqual(form.data.get('veh-vehicle_no'), 'AB 123')

    def test_international_phone_is_not_csv_quoted(self):
        self.assertEqual(sanitize_csv_cell('+97455123456'), '+97455123456')
        self.assertEqual(sanitize_csv_cell('+974 5512 3456'), '+974 5512 3456')

    def test_formula_cells_are_still_quoted(self):
        self.assertTrue(sanitize_csv_cell('+1+1').startswith("'"))
        self.assertTrue(sanitize_csv_cell('=cmd').startswith("'"))
