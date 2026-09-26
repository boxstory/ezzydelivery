"""
Purpose: One name per person — the Profile's name is mirrored onto the auth User row.
Used by: core.models.Profile.save() (every create and edit path), workforce.views.driver_detail
         (the staff identity drawer) and core.management.commands.sync_profile_names.
Notes: The Profile wins because that is the name staff and the applicant maintain — the same
       precedence fleet.models.Driver.driver_name already uses. The auth User only seeds a
       Profile that has no name of its own yet (a fresh Google signup), and auth.User's columns
       are 150 chars against the Profile's 255, so mirrored values are truncated.
"""

USER_NAME_MAX_LENGTH = 150  # auth.User.first_name / auth.User.last_name

NAME_FIELDS = ('first_name', 'last_name')


def clean_name(value):
    """Trim a name and cut it to what auth.User can store. None becomes ''."""
    return (value or '').strip()[:USER_NAME_MAX_LENGTH]


def touches_name(update_fields):
    """Does a save() with these update_fields write a name column?

    None means "every field", which is the common `profile.save()` call.
    """
    if update_fields is None:
        return True
    return any(field in update_fields for field in NAME_FIELDS)


def seed_profile_name_from_user(profile, user=None):
    """Fill a nameless Profile from the auth user it belongs to.

    Only ever adds: a Profile that already carries a first or last name keeps it,
    because that is the maintained value. Returns True when something was filled.
    """
    if (profile.first_name or '').strip() or (profile.last_name or '').strip():
        return False

    if user is None:
        if not profile.user_id:
            return False
        try:
            user = profile.user
        except Exception:  # user row gone or not loadable — nothing to seed from
            return False
    if user is None:
        return False

    first = clean_name(user.first_name)
    last = clean_name(user.last_name)
    if not first and not last:
        return False

    profile.first_name = first
    profile.last_name = last
    return True


def push_profile_name_to_user(profile):
    """Mirror the Profile's name onto its auth User row.

    Written as a filtered UPDATE so it costs one query and touches no rows when the
    two already agree. A Profile with no name at all is left alone rather than
    blanking a name the User does have.

    Returns the number of User rows written (0 or 1).
    """
    if not profile.user_id:
        return 0

    first = clean_name(profile.first_name)
    last = clean_name(profile.last_name)
    if not first and not last:
        return 0

    from django.contrib.auth import get_user_model

    written = (
        get_user_model().objects
        .filter(pk=profile.user_id)
        .exclude(first_name=first, last_name=last)
        .update(first_name=first, last_name=last)
    )

    # Keep an already-loaded User instance (request.user, driver.user) in step with
    # the row we just wrote, so the same request does not render the stale name.
    # Django parks a loaded relation in _state.fields_cache, not in __dict__.
    user_field = profile._meta.get_field('user')
    if user_field.is_cached(profile):
        cached = user_field.get_cached_value(profile)
        if cached is not None:
            cached.first_name = first
            cached.last_name = last

    return written
