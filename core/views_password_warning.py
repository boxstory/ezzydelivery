"""
Purpose: Interstitial that asks a user with a weak password to change it, with 3 skips allowed.
Used by: core/urls.py (core:weak_password_warning), core/middleware.py (WeakPasswordWarningMiddleware)
Notes: Skipping is per-session AND capped across sessions — once the 3rd skip is used the option
       disappears and the middleware keeps returning the user here until the password changes.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

SNOOZE_SESSION_KEY = 'weak_password_snoozed'


@login_required
@require_http_methods(['GET', 'POST'])
def weak_password_warning(request):
    profile = getattr(request.user, 'profile', None)

    # Nothing to warn about — don't strand the user on this page.
    if profile is None or not profile.weak_password:
        return redirect('/dashboard/')

    max_skips = profile.WEAK_PASSWORD_MAX_SKIPS
    skips_left = max(0, max_skips - profile.weak_password_skips)

    if request.method == 'POST' and request.POST.get('action') == 'skip' and skips_left > 0:
        profile.weak_password_skips += 1
        profile.save(update_fields=['weak_password_skips'])
        request.session[SNOOZE_SESSION_KEY] = True
        # Host-check before honouring `next` — this is an auth-flow page, so an
        # unchecked redirect here is a ready-made credential-phishing hop. Same
        # guard core/views.py already applies to the identical parameter.
        from django.utils.http import url_has_allowed_host_and_scheme
        next_url = (request.POST.get('next') or '').strip()
        if not (next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure())):
            next_url = '/dashboard/'
        return redirect(next_url)

    return render(request, 'accounts/weak_password_warning.html', {
        'skips_used': profile.weak_password_skips,
        'skips_left': skips_left,
        'max_skips': max_skips,
        'next': request.GET.get('next', ''),
    })
