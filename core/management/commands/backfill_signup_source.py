# Purpose: Fill signup_source for accounts created before origin tracking existed, by inferring it from what the account became.
# Used by: one-off manual run — `python manage.py backfill_signup_source [--dry-run]`.
# Notes: Everything it writes is flagged signup_source_inferred=True; profiles already stamped by the middleware are left alone.

from django.core.management.base import BaseCommand

from core import signup_origin
from core.models import Profile


class Command(BaseCommand):
    help = "Infer signup_source for existing profiles from their driver / business / team records."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report what would change without saving.')

    def handle(self, *args, **options):
        from business.models import Business, BusinessTeamProfile
        from fleet.models import Driver

        dry_run = options['dry_run']

        driver_users = set(Driver.objects.values_list('user_id', flat=True))
        business_users = set(Business.objects.values_list('user_id', flat=True))
        team_users = set(BusinessTeamProfile.objects.values_list('user_id', flat=True))

        # Only touch rows nothing has attributed yet — never overwrite a tracked signup.
        pending = Profile.objects.filter(
            signup_source=signup_origin.SOURCE_UNKNOWN,
            signup_source_inferred=False,
        )

        total = pending.count()
        counts = {}
        updated = 0
        for profile in list(pending):
            if profile.user_id in driver_users or profile.is_driver:
                source = signup_origin.SOURCE_DRIVER
            elif profile.user_id in business_users or profile.is_business:
                source = signup_origin.SOURCE_BUSINESS
            elif profile.user_id in team_users:
                source = signup_origin.SOURCE_TEAM
            else:
                # No role at all — nothing to infer from, leave it Unknown.
                continue

            counts[source] = counts.get(source, 0) + 1
            updated += 1
            if not dry_run:
                profile.signup_source = source
                profile.signup_source_inferred = True
                profile.save(update_fields=['signup_source', 'signup_source_inferred', 'updated_at'])

        prefix = 'Would update' if dry_run else 'Updated'
        self.stdout.write(f"{prefix} {updated} profile(s) of {total} unattributed:")
        for source, count in sorted(counts.items()):
            self.stdout.write(f"  {source}: {count}")
