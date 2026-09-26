"""
Purpose: Reconcile rows whose Profile name and auth User name drifted apart before they were synced.
Used by: staff, once, after deploying core/name_sync.py — new writes stay in step on their own.
Notes: The Profile wins, matching core.name_sync; a Profile with no name of its own is seeded
       from the User instead. Run with --dry-run first, it prints every row it would change.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from core import name_sync
from core.models import Profile


class Command(BaseCommand):
    help = "Make each Profile and its auth User agree on one name (the Profile's)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would change without writing anything.',
        )
        parser.add_argument(
            '--drivers-only', action='store_true',
            help='Only reconcile profiles that have a Driver record.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        profiles = Profile.objects.select_related('user').order_by('pk')
        if options['drivers_only']:
            # Driver.profile is a ForeignKey, so the join can repeat a profile row.
            profiles = profiles.filter(driver__isnull=False).distinct()

        User = get_user_model()
        to_user = []      # Profile name mirrored onto the User
        to_profile = []   # nameless Profile seeded from the User
        skipped = 0

        for profile in profiles.iterator(chunk_size=500):
            user = profile.user
            if user is None:
                skipped += 1
                continue

            user_name = f"{user.first_name} {user.last_name}".strip()
            profile_first = name_sync.clean_name(profile.first_name)
            profile_last = name_sync.clean_name(profile.last_name)
            profile_name = f"{profile_first} {profile_last}".strip()

            if not profile_name:
                if user_name:
                    to_profile.append((profile, user_name))
                else:
                    skipped += 1
                continue

            if (user.first_name, user.last_name) != (profile_first, profile_last):
                to_user.append((profile, user_name, profile_name))

        for profile, user_name, profile_name in to_user:
            self.stdout.write(
                f"  user #{profile.user_id} profile #{profile.pk}: "
                f"{user_name or '(blank)'!r} -> {profile_name!r}"
            )
        for profile, user_name in to_profile:
            self.stdout.write(
                f"  profile #{profile.pk} (no name) <- user #{profile.user_id} {user_name!r}"
            )

        self.stdout.write(
            f"{len(to_user)} user row(s) to rewrite, {len(to_profile)} profile(s) to seed, "
            f"{skipped} skipped (no name anywhere)."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run — nothing written.'))
            return

        with transaction.atomic():
            for profile, _user_name, _profile_name in to_user:
                name_sync.push_profile_name_to_user(profile)
            for profile, _user_name in to_profile:
                profile.first_name = name_sync.clean_name(profile.user.first_name)
                profile.last_name = name_sync.clean_name(profile.user.last_name)
                profile.save(update_fields=['first_name', 'last_name', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(
            f"Synced {len(to_user)} user row(s) and {len(to_profile)} profile(s)."
        ))
