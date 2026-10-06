"""
Purpose: Tests for the inbox panel's "EzzyDelivery account" section — the user / business on a chat's number or behind its connected lead.
Used by: python manage.py test whatsapp.tests_chat_accounts
Notes: A lid must never be phone-matched (it would invent a Qatar number); account data is CRM-login only, like leads.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from business.models import Business
from core.models import Profile
from crm.models import Lead
from fleet.models import Driver, DriverVehicle
from whatsapp import chat_panel


class ChatAccountsTests(TestCase):
    PHONE = '97455667788'

    def setUp(self):
        cache.clear()
        self.boss = User.objects.create_user('acctboss', is_staff=True, is_superuser=True)
        self.owner = User.objects.create_user('shopowner', email='owner@example.com')
        Profile.objects.create(user=self.owner, first_name='Mona', last_name='Saleh',
                               phone='+974 5566 7788', is_business=True)
        self.biz = Business.objects.create(business_id=990101, business_name='Pearl Trading',
                                           user=self.owner, business_status='active')

    def test_profile_phone_finds_the_client_and_their_business(self):
        cards = chat_panel.chat_accounts(self.PHONE, viewer=self.boss)
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card['name'], 'Mona Saleh')
        self.assertEqual(card['roles'], ['Client'])
        self.assertEqual(card['match'], ['Phone'])
        self.assertEqual(card['businesses'][0]['name'], 'Pearl Trading')
        self.assertEqual(card['businesses'][0]['url'], f'/workforce/sellers/{self.biz.business_id}/')
        self.assertEqual(card['verify_url'],
                         f'/workforce/verification/business/?search={self.biz.business_id}&status=all')
        self.assertEqual(card['verification_key'], 'incomplete')

    def test_verified_profile_has_no_verification_link(self):
        Profile.objects.filter(user=self.owner).update(verification_status='verified')
        card = chat_panel.chat_accounts(self.PHONE, viewer=self.boss)[0]
        self.assertEqual(card['verification_key'], 'verified')
        self.assertEqual(card['verify_url'], '')

    def test_business_number_without_an_owner_login(self):
        Business.objects.create(business_id=990102, business_name='Walk-in Store',
                                business_whatsapp='33445566')
        cards = chat_panel.chat_accounts('97433445566', viewer=self.boss)
        self.assertEqual([c['key'] for c in cards], ['b990102'])
        self.assertEqual(cards[0]['match'], ['Business number'])

    def test_driver_number_finds_the_driver(self):
        user = User.objects.create_user('rider77')
        Driver.objects.create(driver_id=9177, user=user, driver_phone='70001122',
                              driver_whatsapp='70001122', driver_languages='en', driver_status='approved')
        cards = chat_panel.chat_accounts('97470001122', viewer=self.boss)
        self.assertEqual(cards[0]['roles'], ['Driver'])
        self.assertEqual(cards[0]['driver']['url'], '/workforce/drivers/9177/')
        driver = Driver.objects.get(driver_id=9177)
        Profile.objects.create(user=driver.user, whatsapp='70001122')
        card = chat_panel.chat_accounts('97470001122', viewer=self.boss)[0]
        self.assertEqual(card['verify_url'],
                         f'/workforce/verification/drivers/?search={driver.driver_code or "rider77"}&status=all')

    def test_driver_row_carries_the_newest_vehicle_for_its_icon(self):
        user = User.objects.create_user('rider78')
        driver = Driver.objects.create(driver_id=9178, user=user, driver_phone='70001133',
                                       driver_whatsapp='70001133', driver_languages='en')
        card = chat_panel.chat_accounts('97470001133', viewer=self.boss)[0]
        self.assertEqual((card['driver']['vehicle_type'], card['driver']['vehicle']), ('', ''))

        DriverVehicle.objects.create(driver=driver, vehicle_type='bike')
        DriverVehicle.objects.create(driver=driver, vehicle_type='car')
        DriverVehicle.objects.create(driver=driver, vehicle_type='none')   # never an icon
        card = chat_panel.chat_accounts('97470001133', viewer=self.boss)[0]
        self.assertEqual((card['driver']['vehicle_type'], card['driver']['vehicle']), ('car', 'Car'))

    def test_plain_user_gets_the_user_verification_queue(self):
        shopper = User.objects.create_user('shopper5')
        Profile.objects.create(user=shopper, whatsapp='55001234', is_customer=True)
        card = chat_panel.chat_accounts('97455001234', viewer=self.boss)[0]
        self.assertEqual(card['verify_url'], '/workforce/verification/users/?q=shopper5&status=all')

    def test_converted_lead_reaches_the_business_without_a_phone(self):
        lead = Lead.objects.create(source=Lead.SOURCE_MANUAL, phone='11112222',
                                   company_name='Pearl', converted_business=self.biz)
        cards = chat_panel.chat_accounts('', [(lead, 'linked', 'Office')], viewer=self.boss)
        self.assertEqual(cards[0]['username'], 'shopowner')
        self.assertEqual(cards[0]['match'], [f'Lead #{lead.pk}'])

    def test_a_lid_is_never_phone_matched(self):
        # The lid's last 8 digits are this profile's number — still no match.
        Profile.objects.filter(user=self.owner).update(phone='14620132')
        self.assertEqual(chat_panel.chat_accounts('137903514620132', viewer=self.boss), [])

    def test_staff_links_need_the_seller_desk(self):
        clerk = User.objects.create_user('mktclerk', is_staff=True)
        Profile.objects.create(user=clerk, is_staff=True, dept_marketing=True)
        card = chat_panel.chat_accounts(self.PHONE, viewer=clerk)[0]
        self.assertEqual(card['businesses'][0]['url'], '')
        # Marketing does work the verification desk, so that shortcut stays.
        self.assertTrue(card['verify_url'])

    def test_verification_links_need_a_verification_desk(self):
        nobody = User.objects.create_user('nodesk2', is_staff=True)
        Profile.objects.create(user=nobody, is_staff=True)
        card = chat_panel.chat_accounts(self.PHONE, viewer=nobody)[0]
        self.assertEqual(card['verify_url'], '')

    def test_info_endpoint_only_shows_accounts_to_a_crm_login(self):
        params = {'info': 1, 'chatId': f'{self.PHONE}@c.us', 'session': 'default'}
        self.client.force_login(self.boss)
        j = self.client.get('/waha/wa-chats/', params, HTTP_HOST='ezzydelivery.qa', secure=True).json()
        self.assertEqual(j['accounts'][0]['name'], 'Mona Saleh')

        nobody = User.objects.create_user('nodesk', is_staff=True)
        Profile.objects.create(user=nobody, is_staff=True)
        from whatsapp.models import InboxSessionAccess
        InboxSessionAccess.objects.create(user=nobody, session='default')  # inbox number gate
        self.client.force_login(nobody)
        j = self.client.get('/waha/wa-chats/', params, HTTP_HOST='ezzydelivery.qa', secure=True).json()
        self.assertTrue(j['ok'])
        self.assertNotIn('accounts', j)
