"""
Purpose: Tests for the Marketing Overview at /workforce/marketing/ — its queues, tiles, chart, the links they point at, and the redirect that sends a marketing-only account there from the staff home.
Used by: python manage.py test workforce.tests_dashboard_marketing
Notes: Marketing has its own page rather than a department block on the staff dashboard, which stays the Operations/Finance console. The link crawl is the load-bearing test: every /workforce/ href this page renders must open for a marketing-only account, or a tile lands the user on "You don't have access".
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.departments import FIN, MKT, OPS
from crm import services as crm_services
from crm.models import Lead
from workforce.tests_departments import DepartmentTestMixin


class MarketingOverviewTests(DepartmentTestMixin, TestCase):
    """What a marketing-only account gets at /workforce/marketing/."""

    url = 'workforce:wf_marketing_overview'

    def setUp(self):
        self.today = timezone.localdate()
        self.entry = crm_services.initial_stage_key(Lead.CATEGORY_BUSINESS)
        self.driver_entry = crm_services.initial_stage_key(Lead.CATEGORY_DRIVER)

    def _lead(self, **kwargs):
        kwargs.setdefault('category', Lead.CATEGORY_BUSINESS)
        kwargs.setdefault('stage', self.entry)
        kwargs.setdefault('company_name', 'Acme Trading')
        return Lead.objects.create(**kwargs)

    def test_the_overview_carries_the_whole_marketing_console(self):
        user, _ = self.make_staff('mktdash', [MKT])
        page = self.login_as(user).get(reverse(self.url))
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()

        for marker in ('Marketing Overview', 'Lead Queues', 'New Business Leads',
                       'New Driver Applicants', 'Business Follow-ups Due',
                       'Unassigned Business Leads', 'Pricing Inquiries (New)',
                       'Interested Drivers (New)', 'Live Driver Offers',
                       'Client Leads (Last 10 Days)', 'Driver Leads (Last 10 Days)',
                       'Latest Lead Activity', 'Business Pipeline', 'Win Rate (30d)'):
            self.assertIn(marker, body, f'marketing overview is missing "{marker}"')

        # One chart per board, each container present exactly once.
        self.assertEqual(body.count('id="mko_chart_business"'), 1)
        self.assertEqual(body.count('id="mko_chart_driver"'), 1)
        # None of the Operations desk's figures belong on this page.
        for leaked in ('ToDo Status', 'Ready to Pickup', 'Orders &amp; Deliveries Trend',
                       'Latest Updated Orders', 'COD with Fleet'):
            self.assertNotIn(leaked, body, f'marketing overview shows Operations content: "{leaked}"')

    def test_no_template_comment_leaks_onto_the_page(self):
        """A multi-line `{# … #}` is not a comment in Django — it renders. One of
        these became a stray grid item and displaced both columns of this page, so
        the rule is pinned here rather than left to a careful reader."""
        user, _ = self.make_staff('mktcomment', [MKT])
        body = self.login_as(user).get(reverse(self.url)).content.decode()
        self.assertNotIn('{#', body)
        self.assertNotIn('#}', body)
        self.assertNotIn('{% comment', body)

    def test_the_two_columns_are_the_only_children_of_the_grid(self):
        """A text node between the grid and its columns takes a grid cell of its own
        and pushes the right column onto a second row — which is how the leak above
        showed up on screen."""
        import re

        user, _ = self.make_staff('mktgrid', [MKT])
        body = self.login_as(user).get(reverse(self.url)).content.decode()
        grid = body[body.index('class="mko__grid"'):body.index('class="mko__card-head"')]
        # Nothing but whitespace, comments and the first column opener in between.
        between = re.sub(r'<!--.*?-->', '', grid.split('>', 1)[1].split('<div class="mko__col">')[0])
        self.assertEqual(between.strip(), '', f'stray content inside .mko__grid: {between.strip()[:120]!r}')

    def test_staff_home_is_the_operations_console_only(self):
        """The marketing blocks left /workforce/ — it must still be whole for ops,
        and must not have kept a copy of the lead console."""
        user, _ = self.make_staff('opsdash', [OPS, FIN])
        page = self.login_as(user).get(reverse('workforce:wf_dashboard'))
        self.assertEqual(page.status_code, 200)
        body = page.content.decode()
        for marker in ('ToDo Status', 'Ready to Pickup', 'Orders &amp; Deliveries Trend',
                       'Latest Updated Orders', 'COD with Fleet'):
            self.assertIn(marker, body, f'operations dashboard lost "{marker}"')
        for moved in ('Lead Queues', 'Client Leads (Last 10 Days)', 'Latest Lead Activity'):
            self.assertNotIn(moved, body, f'"{moved}" is still on the staff home')

    def test_marketing_only_staff_are_redirected_from_the_staff_home(self):
        """Every block on /workforce/ is ops/finance now, so marketing must not be
        dropped on an empty page."""
        user, _ = self.make_staff('mktredir', [MKT])
        page = self.login_as(user).get(reverse('workforce:wf_dashboard'))
        self.assertRedirects(page, reverse(self.url))

    def test_staff_holding_both_desks_keep_the_staff_home(self):
        """The common case today — both live accounts hold all three desks, so the
        redirect must not fire for them."""
        user, _ = self.make_staff('alldesks', [OPS, FIN, MKT])
        page = self.login_as(user).get(reverse('workforce:wf_dashboard'))
        self.assertEqual(page.status_code, 200)
        self.assertIn('ToDo Status', page.content.decode())

    def test_queue_counts_are_the_marketing_numbers(self):
        self._lead()                                                      # new business
        self._lead(stage=self.driver_entry, category=Lead.CATEGORY_DRIVER,
                   company_name='', contact_name='Driver One')            # new driver
        self._lead(company_name='Due Co', next_followup_at=self.today)    # due today
        self._lead(company_name='Late Co',
                   next_followup_at=self.today - timedelta(days=3))       # overdue

        user, _ = self.make_staff('mktcounts', [MKT])
        ctx = self.login_as(user).get(reverse(self.url)).context

        self.assertEqual(ctx['mkt_new_business'], 3)
        self.assertEqual(ctx['mkt_new_driver'], 1)
        # Due counts today and earlier; overdue is strictly earlier.
        self.assertEqual(ctx['mkt_due_business'], 2)
        self.assertEqual(ctx['mkt_overdue_business'], 1)
        self.assertEqual(ctx['mkt_unassigned_business'], 3)
        # Both boards together — the tile is the desk's whole intake for the day.
        self.assertEqual(ctx['mkt_leads_today'], 4)
        self.assertEqual(len(ctx['mkt_trend']['series']), 2)
        self.assertEqual(len(ctx['mkt_trend']['series'][0]['data']), 10)

    def test_merged_leads_are_not_counted_twice(self):
        parent = self._lead(company_name='Parent Co')
        self._lead(company_name='Absorbed Co', merged_into=parent,
                   merged_at=timezone.now())

        user, _ = self.make_staff('mktmerge', [MKT])
        ctx = self.login_as(user).get(reverse(self.url)).context
        self.assertEqual(ctx['mkt_new_business'], 1)

    def test_win_rate_reads_the_boards_own_outcome_columns(self):
        won = crm_services.outcome_stage_keys('won', Lead.CATEGORY_BUSINESS)
        lost = crm_services.outcome_stage_keys('lost', Lead.CATEGORY_BUSINESS)
        if not (won and lost):
            self.skipTest('business board has no outcome columns seeded')
        closed = timezone.now() - timedelta(days=2)
        self._lead(company_name='Won Co', stage=won[0], closed_at=closed)
        self._lead(company_name='Won Two', stage=won[0], closed_at=closed)
        self._lead(company_name='Lost Co', stage=lost[0], closed_at=closed)
        # Decided long ago — outside the 30-day window, so it must not move the rate.
        self._lead(company_name='Old Loss', stage=lost[0],
                   closed_at=timezone.now() - timedelta(days=90))

        user, _ = self.make_staff('mktwin', [MKT])
        ctx = self.login_as(user).get(reverse(self.url)).context
        self.assertEqual(ctx['mkt_won_30d'], 2)
        self.assertEqual(ctx['mkt_lost_30d'], 1)
        self.assertEqual(ctx['mkt_win_rate_30d'], 67)

    def test_every_link_on_the_overview_opens_for_marketing(self):
        """A tile that lands on "You don't have access" is worse than no tile."""
        import re

        user, _ = self.make_staff('mktlinks', [MKT])
        client = self.login_as(user)
        body = client.get(reverse(self.url)).content.decode()
        # The whole page is marketing's, so every workforce href on it is one of ours.
        targets = sorted({
            href for href in re.findall(r'href="(/workforce/[^"]+)"', body)
        })
        self.assertTrue(targets, 'no workforce links found on the marketing overview')
        for href in targets:
            with self.subTest(href=href):
                # follow=True because the sidebar's Staff Dashboard link legitimately
                # forwards this desk back here; what matters is that no link dead-ends
                # on a permission refusal.
                response = client.get(href, follow=True)
                self.assertEqual(
                    response.status_code, 200,
                    f'{href} returned {response.status_code} for a marketing account',
                )


class FollowupFilterTests(DepartmentTestMixin, TestCase):
    """?overdue=due — the filter the dashboard's Follow-ups rows link to."""

    def setUp(self):
        self.today = timezone.localdate()
        self.entry = crm_services.initial_stage_key(Lead.CATEGORY_BUSINESS)
        self.due = Lead.objects.create(
            company_name='Due Today', stage=self.entry, next_followup_at=self.today)
        self.late = Lead.objects.create(
            company_name='Overdue Co', stage=self.entry,
            next_followup_at=self.today - timedelta(days=5))
        self.later = Lead.objects.create(
            company_name='Next Week', stage=self.entry,
            next_followup_at=self.today + timedelta(days=5))
        user, _ = self.make_staff('mktfilter', [MKT])
        self.client_ = self.login_as(user)

    def _names(self, query):
        page = self.client_.get(reverse('workforce:crm_leads_list') + query)
        self.assertEqual(page.status_code, 200)
        return {lead.company_name for lead in page.context['page_obj']}

    def test_due_includes_today(self):
        self.assertEqual(self._names('?overdue=due'), {'Due Today', 'Overdue Co'})

    def test_overdue_still_excludes_today(self):
        self.assertEqual(self._names('?overdue=1'), {'Overdue Co'})

    def test_closed_cards_are_never_a_chore(self):
        closed = crm_services.closed_stage_keys(Lead.CATEGORY_BUSINESS)
        if not closed:
            self.skipTest('business board has no terminal columns seeded')
        self.late.stage = closed[0]
        self.late.save(update_fields=['stage'])
        self.assertEqual(self._names('?overdue=due'), {'Due Today'})

    def test_an_unknown_value_narrows_nothing(self):
        self.assertEqual(
            self._names('?overdue=bogus'),
            {'Due Today', 'Overdue Co', 'Next Week'},
        )
