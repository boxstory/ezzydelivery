# Purpose: Set is_profile_completed=True on profiles whose required fields are all filled but whose stored flag drifted behind.
# Used by: manual run — `python manage.py sync_profile_completion [--dry-run]`.
# Notes: Only ever sets the flag True. Never clears it, so staff approvals that force it True are left untouched.

from django.core.management.base import BaseCommand

from core.models import Profile


class Command(BaseCommand):
    help = "Sync is_profile_completed with get_profile_completion_percentage() for profiles already at 100%."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report what would change without saving.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        stale = Profile.objects.filter(is_profile_completed=False)
        total = stale.count()
        updated = 0

        for profile in stale.iterator():
            if profile.get_profile_completion_percentage() != 100:
                continue
            updated += 1
            if not dry_run:
                profile.is_profile_completed = True
                profile.save(update_fields=['is_profile_completed', 'updated_at'])

        prefix = 'Would mark' if dry_run else 'Marked'
        self.stdout.write(
            f"{prefix} {updated} of {total} profile(s) flagged incomplete as complete "
            f"({total - updated} genuinely have missing fields)."
        )
