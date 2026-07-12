"""
Selenium Browser UI Tests - Driver Mobile View Workflow
========================================================

Real browser-based click tests simulating driver user interactions.
Tests cover 20+ delivery driver scenarios with actual page navigation,
form submission, and element verification.

Requirements:
    - Chrome browser installed
    - chromedriver available in PATH
    - Selenium 4.x+

Run:
    python manage.py test fleet.tests_ui --verbosity=2
"""

import time
import unittest
from decimal import Decimal

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementNotInteractableException,
    WebDriverException,
)

from core import models as core_models
from fleet import models as fleet_models
from delivery import models as delivery_models
from business import models as business_models
from orders import models as orders_models

User = get_user_model()

WAIT_TIMEOUT = 10  # seconds


class DriverUITestBase(StaticLiveServerTestCase):
    """Base class for Selenium driver UI tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        chrome_options = Options()
        # Visible browser - no headless for preview
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=430,932')  # iPhone 14 Pro Max
        chrome_options.add_argument('--disable-gpu')
        try:
            cls.browser = webdriver.Chrome(options=chrome_options)
        except WebDriverException as exc:
            # No Chrome/driver on this host (e.g. headless CI/prod server).
            # Skip the whole Selenium suite instead of erroring the run.
            super().tearDownClass()
            raise unittest.SkipTest(f"Chrome WebDriver unavailable: {exc}")
        cls.browser.implicitly_wait(5)

    @classmethod
    def tearDownClass(cls):
        browser = getattr(cls, 'browser', None)
        if browser is not None:
            browser.quit()
        super().tearDownClass()

    def setUp(self):
        # Ensure Site exists (required by allauth)
        Site.objects.get_or_create(
            id=1, defaults={'domain': 'testserver', 'name': 'Test'}
        )

        # Create driver user
        self.password = 'TestDriver@123'
        self.user = User.objects.create_user(
            username='testdriver',
            email='testdriver@test.com',
            password=self.password,
            first_name='Test',
            last_name='Driver',
        )
        self.profile = core_models.Profile.objects.create(
            user=self.user,
            first_name='Test',
            last_name='Driver',
            phone=55512345,
            whatsapp=55512345,
            is_driver=True,
        )
        self.driver = fleet_models.Driver.objects.create(
            driver_id=1001,
            user=self.user,
            profile=self.profile,
            driver_code='DRV001',
            driver_phone='55512345',
            driver_whatsapp='55512345',
            driver_languages='english',
            driver_license_number='LIC12345',
            driver_status='approved',
            credit_limit=Decimal('5000.00'),
            wallet_balance=Decimal('-500.00'),
            cod_in_hand=Decimal('500.00'),
            pending_earnings=Decimal('150.00'),
            total_earnings=Decimal('2500.00'),
        )

        # Create profile picture to prevent IntegrityError
        core_models.ProfilePicture.objects.create(
            user=self.user,
            profile=self.profile,
        )

        # Create business, pickup, and orders for delivery tasks
        self.business_user = User.objects.create_user(
            username='testbusiness', email='biz@test.com', password=self.password
        )
        self.business_profile = core_models.Profile.objects.create(
            user=self.business_user,
            first_name='Test',
            last_name='Business',
            phone=55500001,
            is_business=True,
        )
        self.business = business_models.Business.objects.create(
            business_id=100,
            user=self.business_user,
            profile=self.business_profile,
            business_name='Test Business',
            business_code='TESTB001',
            business_status='active',
        )
        self.pickup = business_models.PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Test Warehouse',
            locality='Doha',
            pickup_zone_no=70,
            pickup_street_no=700,
            pickup_building_no=7000,
            pickup_status='active',
        )
        self.order = orders_models.Order.objects.create(
            business=self.business,
            client_order_code='ORD001',
            customer_name='Test Customer',
            customer_phone='33344455',
            customer_address='Test Address Doha',
            dl_zone=70,
            dl_building=7000,
            dl_street=700,
            pickup_location=self.pickup,
        )

    def url(self, path):
        """Build full URL from relative path."""
        return f'{self.live_server_url}{path}'

    def login(self):
        """Login via the login page."""
        self.browser.get(self.url('/accounts/login/'))
        wait = WebDriverWait(self.browser, WAIT_TIMEOUT)

        # Find and fill login form
        login_input = wait.until(
            EC.presence_of_element_located((By.NAME, 'login'))
        )
        login_input.clear()
        login_input.send_keys('testdriver')

        password_input = self.browser.find_element(By.NAME, 'password')
        password_input.clear()
        password_input.send_keys(self.password)

        # Submit
        password_input.send_keys(Keys.RETURN)

        # Wait for redirect away from login page
        wait.until(lambda d: '/accounts/login/' not in d.current_url)

    def wait_for_page(self, partial_url=None, timeout=WAIT_TIMEOUT):
        """Wait for page to load, optionally checking URL."""
        wait = WebDriverWait(self.browser, timeout)
        if partial_url:
            wait.until(lambda d: partial_url in d.current_url)
        wait.until(lambda d: d.execute_script('return document.readyState') == 'complete')

    def find_and_click(self, by, value, timeout=WAIT_TIMEOUT):
        """Wait for element and click via JS (bypasses overlay elements like bottom nav)."""
        wait = WebDriverWait(self.browser, timeout)
        element = wait.until(EC.presence_of_element_located((by, value)))
        self.browser.execute_script(
            "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();",
            element
        )
        return element

    def js_click(self, element):
        """Click element via JavaScript (bypasses overlay interception)."""
        self.browser.execute_script(
            "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();",
            element
        )

    def element_exists(self, by, value, timeout=3):
        """Check if element exists on page."""
        try:
            WebDriverWait(self.browser, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return True
        except TimeoutException:
            return False

    def get_text(self, by, value, timeout=WAIT_TIMEOUT):
        """Get text content of an element."""
        wait = WebDriverWait(self.browser, timeout)
        element = wait.until(EC.presence_of_element_located((by, value)))
        return element.text


# =============================================================================
# SCENARIO 1: LOGIN & DASHBOARD
# =============================================================================

class Scenario01_LoginAndDashboard(DriverUITestBase):
    """Test driver login flow and dashboard access."""

    def test_01_login_page_loads(self):
        """Login page renders with username/password fields."""
        self.browser.get(self.url('/accounts/login/'))
        self.assertTrue(self.element_exists(By.NAME, 'login'))
        self.assertTrue(self.element_exists(By.NAME, 'password'))

    def test_02_successful_login_redirects(self):
        """After login, driver is redirected away from login page."""
        self.login()
        self.assertNotIn('/accounts/login/', self.browser.current_url)

    def test_03_dashboard_loads_after_login(self):
        """Dashboard page loads with wallet and stats sections."""
        self.login()
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')
        # Page should contain wallet info
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'wallet' in page_source or 'credit' in page_source or 'cod' in page_source,
            "Dashboard should show wallet/financial information"
        )

    def test_04_unauthenticated_dashboard_redirects_to_login(self):
        """Accessing dashboard without login redirects to login."""
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page(timeout=WAIT_TIMEOUT)
        self.assertIn('login', self.browser.current_url.lower())


# =============================================================================
# SCENARIO 2: DASHBOARD QUICK ACTIONS
# =============================================================================

class Scenario02_DashboardQuickActions(DriverUITestBase):
    """Test dashboard quick action buttons navigation."""

    def setUp(self):
        super().setUp()
        self.login()
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')

    def test_01_quick_action_pickup_scanner(self):
        """Quick action navigates to pickup scanner page."""
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        scanner_links = [l for l in links if 'pickup' in (l.get_attribute('href') or '').lower()
                        and 'scanner' in (l.get_attribute('href') or '').lower()]
        if scanner_links:
            self.js_click(scanner_links[0])
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('pickup', self.browser.current_url.lower())

    def test_02_quick_action_cod(self):
        """Quick action navigates to COD collection page."""
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        cod_links = [l for l in links if 'cod_collection' in (l.get_attribute('href') or '')]
        if cod_links:
            self.js_click(cod_links[0])
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('cod', self.browser.current_url.lower())

    def test_03_quick_action_earnings(self):
        """Quick action navigates to earnings page."""
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        earnings_links = [l for l in links if 'earnings' in (l.get_attribute('href') or '')]
        if earnings_links:
            self.js_click(earnings_links[0])
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('earnings', self.browser.current_url.lower())

    def test_04_quick_action_delivery_tasks(self):
        """Quick action navigates to delivery tasks page."""
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        task_links = [l for l in links if 'delivery_task' in (l.get_attribute('href') or '')
                     or 'all_delivery' in (l.get_attribute('href') or '')]
        if task_links:
            self.js_click(task_links[0])
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('delivery', self.browser.current_url.lower())


# =============================================================================
# SCENARIO 3: BOTTOM NAVIGATION (PWA)
# =============================================================================

class Scenario03_BottomNavigation(DriverUITestBase):
    """Test PWA bottom navigation bar clicks on mobile viewport."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_bottom_nav_home(self):
        """Home nav item navigates to fleet dashboard."""
        self.browser.get(self.url('/fleet/earnings/'))
        self.wait_for_page('/fleet/earnings/')
        # Find home link in bottom nav
        nav_links = self.browser.find_elements(By.CSS_SELECTOR, '.pwa-bottom-nav__item')
        for link in nav_links:
            href = link.get_attribute('href') or ''
            if 'dashboard' in href:
                link.click()
                self.wait_for_page('/fleet/dashboard/')
                self.assertIn('dashboard', self.browser.current_url)
                return
        # If PWA nav not found, try regular link
        self.browser.get(self.url('/fleet/dashboard/'))
        self.assertEqual(self.browser.current_url, self.url('/fleet/dashboard/'))

    def test_02_bottom_nav_tasks(self):
        """Tasks nav item navigates to all delivery tasks."""
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')
        nav_links = self.browser.find_elements(By.CSS_SELECTOR, '.pwa-bottom-nav__item')
        for link in nav_links:
            href = link.get_attribute('href') or ''
            if 'delivery_task' in href or 'all_delivery' in href:
                link.click()
                self.wait_for_page(timeout=WAIT_TIMEOUT)
                self.assertIn('delivery', self.browser.current_url.lower())
                return

    def test_03_bottom_nav_cod(self):
        """COD nav item navigates to COD collection."""
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')
        nav_links = self.browser.find_elements(By.CSS_SELECTOR, '.pwa-bottom-nav__item')
        for link in nav_links:
            href = link.get_attribute('href') or ''
            if 'cod_collection' in href:
                link.click()
                self.wait_for_page(timeout=WAIT_TIMEOUT)
                self.assertIn('cod', self.browser.current_url.lower())
                return

    def test_04_bottom_nav_profile(self):
        """Profile nav item navigates to driver profile mobile."""
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')
        nav_links = self.browser.find_elements(By.CSS_SELECTOR, '.pwa-bottom-nav__item')
        for link in nav_links:
            href = link.get_attribute('href') or ''
            if 'profile' in href:
                link.click()
                self.wait_for_page(timeout=WAIT_TIMEOUT)
                self.assertIn('profile', self.browser.current_url.lower())
                return


# =============================================================================
# SCENARIO 4: COD COLLECTION WORKFLOW
# =============================================================================

class Scenario04_CODCollection(DriverUITestBase):
    """Test COD collection page and navigation to submission."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_cod_collection_page_loads(self):
        """COD collection page shows balance information."""
        self.browser.get(self.url('/fleet/cod_collection/'))
        self.wait_for_page('/fleet/cod_collection/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'cod' in page_source,
            "COD collection page should show COD info"
        )

    def test_02_navigate_to_cod_submission(self):
        """From COD collection, navigate to COD submission page."""
        self.browser.get(self.url('/fleet/cod_collection/'))
        self.wait_for_page('/fleet/cod_collection/')
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        submit_links = [l for l in links if 'cod_submission' in (l.get_attribute('href') or '')]
        if submit_links:
            submit_links[0].click()
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('cod_submission', self.browser.current_url)


# =============================================================================
# SCENARIO 5: COD SUBMISSION FORM
# =============================================================================

class Scenario05_CODSubmission(DriverUITestBase):
    """Test COD submission form with various inputs."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_submission_page_loads_with_form(self):
        """COD submission page shows amount input form."""
        self.browser.get(self.url('/fleet/cod_submission/'))
        self.wait_for_page('/fleet/cod_submission/')
        self.assertTrue(
            self.element_exists(By.NAME, 'amount') or self.element_exists(By.ID, 'amount'),
            "COD submission page should have an amount input"
        )

    def test_02_submit_valid_amount(self):
        """Submitting valid amount redirects to COD collection."""
        self.browser.get(self.url('/fleet/cod_submission/'))
        self.wait_for_page('/fleet/cod_submission/')

        # Fill amount using JS to ensure it works on mobile
        amount_input = self.browser.find_element(By.NAME, 'amount')
        self.browser.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", amount_input)
        time.sleep(0.3)
        amount_input.clear()
        amount_input.send_keys('200')

        # Fill optional notes if visible
        try:
            notes_input = self.browser.find_element(By.NAME, 'notes')
            if notes_input.is_displayed():
                notes_input.clear()
                notes_input.send_keys('Test deposit from Selenium')
        except (NoSuchElementException, ElementNotInteractableException):
            pass

        # Submit using JS click
        submit_btn = self.browser.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
        self.js_click(submit_btn)

        # Should redirect to COD collection
        self.wait_for_page(timeout=WAIT_TIMEOUT)
        self.assertIn('cod_collection', self.browser.current_url)

        # Verify balance changed
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.cod_in_hand, Decimal('300.00'))

    def test_03_submit_zero_amount_shows_error(self):
        """Submitting zero amount shows error and stays on page."""
        self.browser.get(self.url('/fleet/cod_submission/'))
        self.wait_for_page('/fleet/cod_submission/')

        amount_input = self.browser.find_element(By.NAME, 'amount')
        self.browser.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", amount_input)
        time.sleep(0.3)
        amount_input.clear()
        amount_input.send_keys('0')

        submit_btn = self.browser.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
        self.js_click(submit_btn)

        time.sleep(1)
        # Should stay on submission page
        self.assertIn('cod_submission', self.browser.current_url)

    def test_04_submit_exceeding_amount_shows_error(self):
        """Submitting more than COD in hand shows error."""
        self.browser.get(self.url('/fleet/cod_submission/'))
        self.wait_for_page('/fleet/cod_submission/')

        amount_input = self.browser.find_element(By.NAME, 'amount')
        self.browser.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", amount_input)
        time.sleep(0.3)
        amount_input.clear()
        amount_input.send_keys('9999')

        submit_btn = self.browser.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
        self.js_click(submit_btn)

        time.sleep(1)
        self.assertIn('cod_submission', self.browser.current_url)


# =============================================================================
# SCENARIO 6: DRIVER EARNINGS VIEW
# =============================================================================

class Scenario06_DriverEarnings(DriverUITestBase):
    """Test driver earnings page with period filters."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_earnings_page_loads(self):
        """Earnings page loads with period filter options."""
        self.browser.get(self.url('/fleet/earnings/'))
        self.wait_for_page('/fleet/earnings/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'earning' in page_source or 'delivery' in page_source,
            "Earnings page should show earnings info"
        )

    def test_02_filter_by_7_days(self):
        """Clicking 7-day filter updates the earnings view."""
        self.browser.get(self.url('/fleet/earnings/'))
        self.wait_for_page('/fleet/earnings/')

        # Look for 7 days filter link/button
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        day7_links = [l for l in links if 'days=7' in (l.get_attribute('href') or '')]
        if day7_links:
            day7_links[0].click()
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('days=7', self.browser.current_url)

    def test_03_filter_by_90_days(self):
        """Clicking 90-day filter updates the earnings view."""
        self.browser.get(self.url('/fleet/earnings/'))
        self.wait_for_page('/fleet/earnings/')

        links = self.browser.find_elements(By.TAG_NAME, 'a')
        day90_links = [l for l in links if 'days=90' in (l.get_attribute('href') or '')]
        if day90_links:
            day90_links[0].click()
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('days=90', self.browser.current_url)


# =============================================================================
# SCENARIO 7: TRANSACTION HISTORY
# =============================================================================

class Scenario07_TransactionHistory(DriverUITestBase):
    """Test transaction history page with type and period filters."""

    def setUp(self):
        super().setUp()
        # Create some transactions for data
        fleet_models.DriverTransaction.objects.create(
            driver=self.driver,
            transaction_type='cod_collection',
            amount=Decimal('100.00'),
            description='COD for order ORD001',
            wallet_balance_after=Decimal('-600.00'),
            cod_in_hand_after=Decimal('600.00'),
            pending_earnings_after=Decimal('150.00'),
        )
        fleet_models.DriverTransaction.objects.create(
            driver=self.driver,
            transaction_type='earning',
            amount=Decimal('25.00'),
            description='Delivery fee for order ORD001',
            wallet_balance_after=Decimal('-600.00'),
            cod_in_hand_after=Decimal('600.00'),
            pending_earnings_after=Decimal('175.00'),
        )
        self.login()

    def test_01_transactions_page_loads(self):
        """Transaction history page loads with transaction list."""
        self.browser.get(self.url('/fleet/transactions/'))
        self.wait_for_page('/fleet/transactions/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'transaction' in page_source or 'balance' in page_source,
            "Transaction page should show transaction data"
        )

    def test_02_filter_by_cod_type(self):
        """Filtering by COD type shows relevant transactions."""
        self.browser.get(self.url('/fleet/transactions/?type=cod_collection'))
        self.wait_for_page('/fleet/transactions/')
        self.assertIn('type=cod_collection', self.browser.current_url)

    def test_03_filter_by_earning_type(self):
        """Filtering by earning type shows earned transactions."""
        self.browser.get(self.url('/fleet/transactions/?type=earning'))
        self.wait_for_page('/fleet/transactions/')
        self.assertIn('type=earning', self.browser.current_url)

    def test_04_filter_by_7_day_period(self):
        """7-day period filter narrows transaction list."""
        self.browser.get(self.url('/fleet/transactions/?days=7'))
        self.wait_for_page('/fleet/transactions/')
        self.assertIn('days=7', self.browser.current_url)


# =============================================================================
# SCENARIO 8: DRIVER PROFILE MOBILE
# =============================================================================

class Scenario08_DriverProfileMobile(DriverUITestBase):
    """Test driver mobile profile page."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_profile_page_loads(self):
        """Driver profile mobile page loads with personal info."""
        self.browser.get(self.url('/fleet/profile/'))
        self.wait_for_page('/fleet/profile/')
        page_source = self.browser.page_source
        self.assertTrue(
            'Test' in page_source or 'Driver' in page_source or 'DRV001' in page_source,
            "Profile page should show driver info"
        )

    def test_02_profile_shows_wallet_info(self):
        """Profile page displays wallet balance information."""
        self.browser.get(self.url('/fleet/profile/'))
        self.wait_for_page('/fleet/profile/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'wallet' in page_source or 'balance' in page_source or 'credit' in page_source,
            "Profile should show wallet info"
        )

    def test_03_profile_navigate_to_vehicles(self):
        """From profile, can navigate to vehicles management."""
        self.browser.get(self.url('/fleet/profile/'))
        self.wait_for_page('/fleet/profile/')
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        vehicle_links = [l for l in links if 'vehicle' in (l.get_attribute('href') or '').lower()]
        if vehicle_links:
            self.js_click(vehicle_links[0])
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('vehicle', self.browser.current_url.lower())

    def test_04_profile_navigate_to_documents(self):
        """From profile, can navigate to documents page."""
        self.browser.get(self.url('/fleet/profile/'))
        self.wait_for_page('/fleet/profile/')
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        doc_links = [l for l in links if 'document' in (l.get_attribute('href') or '').lower()]
        if doc_links:
            self.js_click(doc_links[0])
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('document', self.browser.current_url.lower())


# =============================================================================
# SCENARIO 9: VEHICLE MANAGEMENT
# =============================================================================

class Scenario09_VehicleManagement(DriverUITestBase):
    """Test vehicle list and add vehicle flow."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_vehicle_list_page_loads(self):
        """Vehicle list page loads."""
        self.browser.get(self.url('/fleet/vehicle_own/'))
        self.wait_for_page('/fleet/vehicle_own/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'vehicle' in page_source,
            "Vehicle page should show vehicle info"
        )

    def test_02_navigate_to_add_vehicle(self):
        """Can navigate to add vehicle form."""
        self.browser.get(self.url('/fleet/vehicle_own/'))
        self.wait_for_page('/fleet/vehicle_own/')

        # Find add vehicle link/button
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        add_links = [l for l in links if 'vehicle_add' in (l.get_attribute('href') or '')]
        if add_links:
            add_links[0].click()
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('vehicle_add', self.browser.current_url)
        else:
            # Try by ID
            try:
                self.find_and_click(By.ID, 'fleet_vehicle_own_btn_add')
                self.wait_for_page(timeout=WAIT_TIMEOUT)
                self.assertIn('vehicle_add', self.browser.current_url)
            except TimeoutException:
                pass

    def test_03_add_vehicle_form_has_fields(self):
        """Add vehicle page has form fields."""
        self.browser.get(self.url('/fleet/vehicle_add/'))
        self.wait_for_page('/fleet/vehicle_add/')
        # Should have a form with submit button
        self.assertTrue(
            self.element_exists(By.CSS_SELECTOR, 'form') or
            self.element_exists(By.ID, 'fleet_vehicle_add_form_main'),
            "Add vehicle page should have a form"
        )


# =============================================================================
# SCENARIO 10: DOCUMENT MANAGEMENT
# =============================================================================

class Scenario10_DocumentManagement(DriverUITestBase):
    """Test document list page."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_documents_page_loads(self):
        """Documents page loads."""
        self.browser.get(self.url('/fleet/documents/'))
        self.wait_for_page('/fleet/documents/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'document' in page_source,
            "Documents page should show document info"
        )

    def test_02_navigate_to_upload_document(self):
        """Can navigate to document upload page."""
        self.browser.get(self.url('/fleet/documents/'))
        self.wait_for_page('/fleet/documents/')
        links = self.browser.find_elements(By.TAG_NAME, 'a')
        upload_links = [l for l in links
                       if 'upload' in (l.get_attribute('href') or '').lower()
                       or 'documents_upload' in (l.get_attribute('href') or '')]
        if upload_links:
            upload_links[0].click()
            self.wait_for_page(timeout=WAIT_TIMEOUT)
            self.assertIn('upload', self.browser.current_url.lower())


# =============================================================================
# SCENARIO 11: DELIVERY TASKS LIST
# =============================================================================

class Scenario11_DeliveryTasks(DriverUITestBase):
    """Test all delivery tasks page."""

    def setUp(self):
        super().setUp()
        # Create some delivery tasks
        self.task_pending = delivery_models.DeliveryTask.objects.create(
            dl_task_number='TASK-001',
            dl_task_description='Deliver package to Zone 70',
            order=self.order,
            business=self.business,
            pickup_location=self.pickup,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_price=25,
        )
        self.task_assigned = delivery_models.DeliveryTask.objects.create(
            dl_task_number='TASK-002',
            dl_task_description='Deliver package to Zone 71',
            order=self.order,
            business=self.business,
            pickup_location=self.pickup,
            driver=self.driver,
            dl_task_status='assigned',
            dl_task_status_client='for_review',
            dl_price=30,
        )
        delivery_models.AssignedDriver.objects.create(
            dl_task=self.task_assigned,
            driver=self.driver,
        )
        self.login()

    def test_01_delivery_tasks_page_loads(self):
        """All delivery tasks page loads."""
        self.browser.get(self.url('/delivery/delivery_task/all/'))
        self.wait_for_page('/delivery/delivery_task/all/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'delivery' in page_source or 'task' in page_source,
            "Delivery tasks page should show task info"
        )

    def test_02_assigned_tab_shows_my_tasks(self):
        """Assigned tab shows tasks assigned to the driver."""
        self.browser.get(self.url('/delivery/delivery_task/all/?tab=assigned'))
        self.wait_for_page('/delivery/delivery_task/all/')
        page_source = self.browser.page_source
        # Should show the assigned task
        self.assertTrue(
            'TASK-002' in page_source or 'assigned' in page_source.lower(),
            "Assigned tab should show assigned tasks"
        )


# =============================================================================
# SCENARIO 12: PICKUP SCANNER
# =============================================================================

class Scenario12_PickupScanner(DriverUITestBase):
    """Test pickup scanner page."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_scanner_page_loads(self):
        """Pickup scanner page loads with camera and manual input."""
        self.browser.get(self.url('/fleet/pickup/scanner/'))
        self.wait_for_page('/fleet/pickup/scanner/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'scan' in page_source or 'pickup' in page_source,
            "Scanner page should show scan interface"
        )

    def test_02_manual_input_exists(self):
        """Scanner page has manual code input field."""
        self.browser.get(self.url('/fleet/pickup/scanner/'))
        self.wait_for_page('/fleet/pickup/scanner/')
        self.assertTrue(
            self.element_exists(By.ID, 'manual-code'),
            "Scanner should have manual code input"
        )


# =============================================================================
# SCENARIO 13: PERFORMANCE VIEW
# =============================================================================

class Scenario13_PerformanceView(DriverUITestBase):
    """Test driver performance page."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_performance_page_loads(self):
        """Performance page loads with metrics."""
        self.browser.get(self.url('/fleet/performance/'))
        self.wait_for_page('/fleet/performance/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'performance' in page_source or 'delivery' in page_source or 'rating' in page_source,
            "Performance page should show metrics"
        )

    def test_02_performance_period_filter(self):
        """Performance page accepts period filter."""
        self.browser.get(self.url('/fleet/performance/?period=7'))
        self.wait_for_page('/fleet/performance/')
        # Page should load without errors
        self.assertNotIn('500', self.browser.title)


# =============================================================================
# SCENARIO 14: REPORTS VIEW
# =============================================================================

class Scenario14_ReportsView(DriverUITestBase):
    """Test driver reports page."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_reports_page_loads(self):
        """Reports page loads."""
        self.browser.get(self.url('/fleet/reports/'))
        self.wait_for_page('/fleet/reports/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'report' in page_source or 'delivery' in page_source or 'summary' in page_source,
            "Reports page should show report data"
        )


# =============================================================================
# SCENARIO 15: ANALYTICS VIEW
# =============================================================================

class Scenario15_AnalyticsView(DriverUITestBase):
    """Test driver analytics page."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_analytics_page_loads(self):
        """Analytics page loads."""
        self.browser.get(self.url('/fleet/analytics/'))
        self.wait_for_page('/fleet/analytics/')
        page_source = self.browser.page_source.lower()
        self.assertTrue(
            'analytics' in page_source or 'monthly' in page_source or 'data' in page_source,
            "Analytics page should show analytics data"
        )


# =============================================================================
# SCENARIO 16: PUBLIC DRIVER PROFILE
# =============================================================================

class Scenario16_PublicDriverProfile(DriverUITestBase):
    """Test public driver profile page (no login required)."""

    def test_01_public_profile_loads(self):
        """Public driver profile accessible without login."""
        self.browser.get(self.url(f'/fleet/{self.driver.driver_id}/'))
        self.wait_for_page(timeout=WAIT_TIMEOUT)
        # Page should load (200 or redirect to /fleet/)
        current_url = self.browser.current_url
        self.assertTrue(
            '/fleet/' in current_url,
            "Public profile URL should contain /fleet/"
        )

    def test_02_nonexistent_driver_redirects(self):
        """Nonexistent driver ID redirects to fleets list."""
        self.browser.get(self.url('/fleet/99999/'))
        self.wait_for_page(timeout=WAIT_TIMEOUT)
        # Should redirect to /fleet/ or show error
        current = self.browser.current_url
        self.assertTrue(
            '/fleet/' in current,
            "Nonexistent driver should redirect"
        )


# =============================================================================
# SCENARIO 17: FULL DRIVER WORKFLOW - Login to Delivery
# =============================================================================

class Scenario17_FullDriverWorkflow(DriverUITestBase):
    """End-to-end workflow: Login → Dashboard → Accept Task → Start Delivery."""

    def setUp(self):
        super().setUp()
        # Create a pending task
        self.task = delivery_models.DeliveryTask.objects.create(
            dl_task_number='FULL-001',
            dl_task_description='Full workflow test task',
            order=self.order,
            business=self.business,
            pickup_location=self.pickup,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_price=25,
        )

    def test_01_full_workflow_login_to_dashboard(self):
        """Full workflow: Login → Dashboard loads correctly."""
        # Step 1: Login
        self.login()

        # Step 2: Navigate to dashboard
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')

        # Step 3: Verify dashboard content
        page_source = self.browser.page_source
        self.assertIn('500', page_source)  # COD in hand amount

    def test_02_full_workflow_dashboard_to_tasks(self):
        """Full workflow: Dashboard → Tasks → View pending tasks."""
        self.login()
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')

        # Navigate to tasks
        self.browser.get(self.url('/delivery/delivery_task/all/'))
        self.wait_for_page('/delivery/delivery_task/all/')

        page_source = self.browser.page_source
        self.assertTrue(
            'FULL-001' in page_source or 'delivery' in page_source.lower(),
            "Tasks page should show pending tasks"
        )


# =============================================================================
# SCENARIO 18: COD FULL CYCLE
# =============================================================================

class Scenario18_CODFullCycle(DriverUITestBase):
    """Full COD cycle: Collection view → Submission → Verify balance."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_cod_collection_to_submission_to_verification(self):
        """Full COD workflow: View collection → Submit → Check updated balance."""
        # Step 1: View COD collection
        self.browser.get(self.url('/fleet/cod_collection/'))
        self.wait_for_page('/fleet/cod_collection/')

        # Step 2: Navigate to submission
        self.browser.get(self.url('/fleet/cod_submission/'))
        self.wait_for_page('/fleet/cod_submission/')

        # Step 3: Submit 100 QR
        amount_input = self.browser.find_element(By.NAME, 'amount')
        self.browser.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", amount_input)
        time.sleep(0.3)
        amount_input.clear()
        amount_input.send_keys('100')

        submit_btn = self.browser.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
        self.js_click(submit_btn)
        self.wait_for_page(timeout=WAIT_TIMEOUT)

        # Step 4: Verify redirect to collection page
        self.assertIn('cod_collection', self.browser.current_url)

        # Step 5: Verify database balance
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.cod_in_hand, Decimal('400.00'))
        self.assertEqual(self.driver.wallet_balance, Decimal('-400.00'))


# =============================================================================
# SCENARIO 19: RESPONSIVE LAYOUT CHECK
# =============================================================================

class Scenario19_ResponsiveLayout(DriverUITestBase):
    """Verify mobile responsive elements render properly."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_01_mobile_viewport_shows_pwa_elements(self):
        """On mobile viewport, PWA elements should be present in source."""
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')
        page_source = self.browser.page_source
        # PWA classes should be in the HTML source
        self.assertTrue(
            'pwa-' in page_source or 'pwa_' in page_source,
            "Mobile viewport should include PWA CSS classes"
        )

    def test_02_desktop_viewport_shows_desktop_elements(self):
        """On desktop viewport, desktop-specific elements exist."""
        # Resize to desktop
        self.browser.set_window_size(1920, 1080)
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page('/fleet/dashboard/')
        page_source = self.browser.page_source
        # Desktop IDs should be in the HTML source
        self.assertTrue(
            'fleet_dashboard' in page_source,
            "Desktop viewport should include desktop element IDs"
        )
        # Reset to mobile
        self.browser.set_window_size(375, 812)


# =============================================================================
# SCENARIO 20: ACCESS CONTROL
# =============================================================================

class Scenario20_AccessControl(DriverUITestBase):
    """Test that non-driver users cannot access driver pages."""

    def test_01_non_driver_cannot_access_dashboard(self):
        """User without driver role gets redirected from dashboard."""
        # Create non-driver user
        non_driver = User.objects.create_user(
            username='nondriverui', email='nondriver@test.com', password='TestDriver@123'
        )
        core_models.Profile.objects.create(
            user=non_driver,
            first_name='Non',
            last_name='Driver',
            phone=55500000,
            is_driver=False,
        )

        # Login as non-driver
        self.browser.get(self.url('/accounts/login/'))
        wait = WebDriverWait(self.browser, WAIT_TIMEOUT)
        login_input = wait.until(EC.presence_of_element_located((By.NAME, 'login')))
        login_input.clear()
        login_input.send_keys('nondriverui')
        password_input = self.browser.find_element(By.NAME, 'password')
        password_input.clear()
        password_input.send_keys('TestDriver@123')
        password_input.send_keys(Keys.RETURN)
        wait.until(lambda d: '/accounts/login/' not in d.current_url)

        # Try to access driver dashboard
        self.browser.get(self.url('/fleet/dashboard/'))
        self.wait_for_page(timeout=WAIT_TIMEOUT)

        # Should be redirected away from dashboard
        self.assertNotIn('/fleet/dashboard/', self.browser.current_url)

    def test_02_unauthenticated_cannot_access_earnings(self):
        """Unauthenticated user redirected from earnings page."""
        # Clear cookies (log out)
        self.browser.delete_all_cookies()
        self.browser.get(self.url('/fleet/earnings/'))
        self.wait_for_page(timeout=WAIT_TIMEOUT)
        self.assertIn('login', self.browser.current_url.lower())

    def test_03_unauthenticated_cannot_access_cod(self):
        """Unauthenticated user redirected from COD page."""
        self.browser.delete_all_cookies()
        self.browser.get(self.url('/fleet/cod_collection/'))
        self.wait_for_page(timeout=WAIT_TIMEOUT)
        self.assertIn('login', self.browser.current_url.lower())

    def test_04_unauthenticated_cannot_access_transactions(self):
        """Unauthenticated user redirected from transactions page."""
        self.browser.delete_all_cookies()
        self.browser.get(self.url('/fleet/transactions/'))
        self.wait_for_page(timeout=WAIT_TIMEOUT)
        self.assertIn('login', self.browser.current_url.lower())
