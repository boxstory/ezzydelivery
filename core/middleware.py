"""
Custom middleware for EzzyDelivery
"""
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from django.conf import settings
from django.db import connection
from collections import Counter
from urllib.parse import quote
import logging
import time

from core import signup_origin

logger = logging.getLogger(__name__)
query_logger = logging.getLogger('queries')


class CloudflareIPMiddleware:
	"""
	Extracts real client IP from Cloudflare headers and sets REMOTE_ADDR.
	This is required for django-ratelimit to work correctly with reverse proxies.
	Cloudflare sets CF-Connecting-IP to the real client IP.
	"""
	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		# Try Cloudflare's CF-Connecting-IP first (most reliable)
		ip = request.META.get('HTTP_CF_CONNECTING_IP')

		# Fallback to X-Forwarded-For (take first IP if multiple)
		if not ip:
			forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
			if forwarded_for:
				# X-Forwarded-For can be "ip1, ip2, ip3" - take the first one
				ip = forwarded_for.split(',')[0].strip()

		# Set REMOTE_ADDR if we found an IP
		if ip:
			request.META['REMOTE_ADDR'] = ip

		response = self.get_response(request)
		return response


class SessionTimeoutMiddleware:
    """
    Idle-logout for STAFF users only.

    Staff share office machines, so their session dies after
    settings.STAFF_SESSION_IDLE_TIMEOUT with no activity.

    Drivers and business clients are on personal phones, where an idle timeout
    buys nothing and costs a re-login on the road. They ride SESSION_COOKIE_AGE
    (rolling, because SESSION_SAVE_EVERY_REQUEST is True), and drivers get an
    effectively unlimited expiry on top so the fleet PWA stays signed in.

    How the staff path works:
    1. Tracks last activity time in session
    2. On each request, checks whether the idle window has elapsed
    3. If expired, logs out user and redirects to login with message
    4. If not expired, updates last activity time
    """

    # Effectively "no timeout" for drivers (1 year). Refreshed on every request
    # because SESSION_SAVE_EVERY_REQUEST is True.
    DRIVER_SESSION_AGE = 60 * 60 * 24 * 365

    # A profile can gain is_driver mid-session (an application is approved while
    # the applicant is still logged in), so the cached answer is re-checked this
    # often rather than trusted for the life of the session.
    DRIVER_CACHE_TTL = 600  # 10 minutes

    def __init__(self, get_response):
        self.get_response = get_response

    @property
    def timeout_duration(self):
        return timedelta(seconds=getattr(settings, 'STAFF_SESSION_IDLE_TIMEOUT', 86400))

    def _is_driver(self, request):
        """Return True if the authenticated user is a driver (cached on session).

        The cache carries a timestamp. Caching the answer forever meant a user
        who became a driver after logging in stayed classified as a non-driver
        for the whole session — and so kept the staff idle timeout instead of
        the long-lived driver session.
        """
        now = time.time()
        cached = request.session.get('_is_driver')
        checked_at = request.session.get('_is_driver_at')
        if cached is not None and isinstance(checked_at, (int, float)):
            if now - checked_at < self.DRIVER_CACHE_TTL:
                return cached

        is_driver = False
        try:
            profile = getattr(request.user, 'profile', None)
            is_driver = bool(profile and profile.is_driver)
        except Exception:
            is_driver = False

        request.session['_is_driver'] = is_driver
        request.session['_is_driver_at'] = now
        return is_driver

    def __call__(self, request):
        # Skip timeout check for anonymous users
        if not request.user.is_authenticated:
            response = self.get_response(request)
            return response

        # Drivers have no inactivity timeout. Keep their session long-lived so
        # Django's SESSION_COOKIE_AGE doesn't log them out either.
        if self._is_driver(request):
            request.session.set_expiry(self.DRIVER_SESSION_AGE)
            return self.get_response(request)

        # Clients: no idle timeout, just the rolling SESSION_COOKIE_AGE window.
        # Reset an expiry left behind by a driver-era session so a demoted
        # driver doesn't keep the 1-year cookie.
        if not request.user.is_staff:
            if request.session.get_expiry_age() > settings.SESSION_COOKIE_AGE:
                request.session.set_expiry(None)
            return self.get_response(request)

        # --- staff only, from here down ---

        # Skip timeout check for login/logout URLs to avoid redirect loops
        exempt_urls = [
            reverse('account_login'),
            reverse('account_logout'),
            '/accounts/login/',
            '/accounts/logout/',
        ]

        if request.path in exempt_urls:
            response = self.get_response(request)
            return response

        # Get last activity time from session
        last_activity = request.session.get('last_activity')

        if last_activity:
            # Convert string back to datetime if needed
            if isinstance(last_activity, str):
                last_activity = timezone.datetime.fromisoformat(last_activity)

            # Make timezone aware if naive
            if timezone.is_naive(last_activity):
                last_activity = timezone.make_aware(last_activity)

            # Check whether the idle window has elapsed
            time_since_activity = timezone.now() - last_activity

            if time_since_activity > self.timeout_duration:
                # Session expired - logout user
                messages.warning(
                    request,
                    'Your session has expired due to inactivity. Please login again.'
                )
                logout(request)

                # Store the next URL to redirect after login
                next_url = request.get_full_path()
                return redirect(f"{reverse('account_login')}?next={next_url}")

        # Update last activity time in session
        request.session['last_activity'] = timezone.now().isoformat()

        response = self.get_response(request)
        return response


class SessionWarningMiddleware:
    """
    Middleware to inject session timeout warning into dashboard pages.
    Stores time_remaining on the request so templates can read it directly,
    avoiding expensive HTML decode/encode on every response.

    Staff only: they are the only users with an idle timeout to warn about, and
    `last_activity` is only maintained for them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Pre-compute session time remaining and stash on request
        # Templates can use {{ request.session_time_remaining }} if needed
        if request.user.is_authenticated and request.user.is_staff and 'dashboard' in request.path:
            last_activity = request.session.get('last_activity')
            if last_activity:
                if isinstance(last_activity, str):
                    last_activity = timezone.datetime.fromisoformat(last_activity)
                if timezone.is_naive(last_activity):
                    last_activity = timezone.make_aware(last_activity)
                elapsed = (timezone.now() - last_activity).total_seconds()
                idle_timeout = getattr(settings, 'STAFF_SESSION_IDLE_TIMEOUT', 86400)
                request.session_time_remaining = max(0, int(idle_timeout - elapsed))

        return self.get_response(request)


class NoCacheAuthMiddleware:
    """
    Prevents browser bfcache from storing auth pages (login, logout, signup,
    password reset). Without this, navigating to /accounts/login/ can serve a
    stale cached page that was rendered before CSS changes take effect — and a
    replayed page carries a dead csrfmiddlewaretoken with no Set-Cookie, which
    the user meets as "Page Expired" with no way out. no-store also tells the
    PWA service worker not to keep a copy.
    """

    AUTH_PATHS = ('/accounts/login/', '/accounts/logout/', '/accounts/signup/')
    AUTH_PREFIXES = ('/password/',)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path in self.AUTH_PATHS or request.path.startswith(self.AUTH_PREFIXES):
            response['Cache-Control'] = 'no-store'
        return response


class QueryInspectorMiddleware:
    """
    Middleware to detect and log duplicate SQL queries per request.
    Only active when DEBUG=True. Helps identify N+1 query problems.

    Output example:
    [DUPLICATE QUERIES] GET /business/register/
    Total: 5 queries | Duplicates: 2
      - 2x: SELECT ... FROM "core_profile" WHERE ...
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only run in DEBUG mode
        if not settings.DEBUG:
            return self.get_response(request)

        # Skip static files and debug toolbar requests
        skip_paths = ['/static/', '/__debug__/', '/media/']
        if any(request.path.startswith(p) for p in skip_paths):
            return self.get_response(request)

        # Reset query log before request
        connection.queries_log.clear()

        response = self.get_response(request)

        # Analyze queries after response
        queries = connection.queries
        if queries:
            self._log_duplicates(request, queries)

        return response

    def _log_duplicates(self, request, queries):
        """Analyze queries and log any duplicates."""
        # Extract just the SQL statements
        sql_statements = [q['sql'] for q in queries]

        # Count occurrences of each query
        query_counts = Counter(sql_statements)

        # Find duplicates (queries that appear more than once)
        duplicates = {sql: count for sql, count in query_counts.items() if count > 1}

        if duplicates:
            total_queries = len(queries)
            duplicate_count = sum(count - 1 for count in duplicates.values())

            # Build log message
            log_lines = [
                f"\n{'='*60}",
                f"[DUPLICATE QUERIES] {request.method} {request.path}",
                f"Total: {total_queries} queries | Duplicates: {duplicate_count}",
            ]

            for sql, count in duplicates.items():
                # Truncate long queries for readability
                truncated_sql = sql[:150] + '...' if len(sql) > 150 else sql
                log_lines.append(f"  - {count}x: {truncated_sql}")

            log_lines.append('='*60)

            # Log to both console and query log file
            log_message = '\n'.join(log_lines)
            query_logger.warning(log_message)


class DriverStatusCheckMiddleware:
    """
    Fix 18: Force logout drivers whose status is no longer approved.
    Only checks requests to /fleet/ paths to minimize overhead.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.path.startswith('/fleet/'):
            try:
                profile = getattr(request.user, 'profile', None)
                if profile and profile.is_driver:
                    from fleet.models import Driver
                    driver = Driver.objects.filter(user=request.user).first()
                    if driver and driver.driver_status not in ('approved', 'processing'):
                        logout(request)
                        return redirect('/accounts/login/')
            except Exception:
                pass
        return self.get_response(request)


class DriverDeviceMiddleware:
    """
    Enforces the one-device-per-driver rule.

    Costs two dict lookups for everyone else: the flags it reads are only ever
    written for drivers, and they live in the session the request already
    loaded, so there is no query on the hot path.

    Three jobs:
    1. A device that was retired when the driver signed in elsewhere is signed
       out here, with a message that says why.
    2. A device we have never confirmed is held at the verification page until a
       WhatsApp code (or an ops release) clears it.
    3. A freshly issued device token is written to its cookie on the way out.
    """

    # Paths a pending device is still allowed to reach: the gate itself, the way
    # back out, and the static assets both need to render.
    PENDING_ALLOWED_PREFIXES = (
        '/fleet/device/',
        '/accounts/logout/',
        '/accounts/login/',
        '/static/',
        '/media/',
        '/sw.js',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    AUTH_PREFIXES = ('/accounts/login/', '/accounts/logout/')

    def _pending_allowed(self, path):
        return path.startswith(self.PENDING_ALLOWED_PREFIXES)

    def _auth_path(self, path):
        return path.startswith(self.AUTH_PREFIXES)

    @staticmethod
    def _no_store(response):
        """A gate redirect must never be replayed from the browser cache.

        The gate and the dashboard point at each other: /fleet/dashboard/ sends a
        pending driver to /fleet/device/verify/, and once the device is confirmed
        or released the verify page sends them back. Both are plain 302s, so a
        browser is free to cache them — and then it can bounce between the two
        without ever reaching the server, which the driver meets as
        ERR_TOO_MANY_REDIRECTS long after the server state is correct, and which
        leaves no trace in the logs because no request arrives.
        """
        response['Cache-Control'] = 'no-store'
        return response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        from fleet.device_service import (
            SESSION_PENDING_DEVICE, SESSION_REVOKED, SESSION_SET_TOKEN,
            DEVICE_COOKIE, DEVICE_COOKIE_AGE, enforcement_enabled,
        )

        if not enforcement_enabled():
            return self.get_response(request)

        # 1. Retired by a sign-in on another device. The auth URLs are exempt:
        # intercepting them would swallow the POST of a driver signing back in,
        # bouncing them to an empty form instead of logging them in.
        if request.session.get(SESSION_REVOKED) and not self._auth_path(request.path):
            logout(request)
            # After logout(), not before — logout() flushes the session, which
            # would take a message stored there with it.
            messages.warning(
                request,
                'You were signed out because your account was signed in on another device. '
                'If that was not you, change your password and tell operations.'
            )
            return self._no_store(redirect(reverse('account_login')))

        # 2. Unconfirmed device — hold it at the gate.
        if request.session.get(SESSION_PENDING_DEVICE) and not self._pending_allowed(request.path):
            return self._no_store(redirect(reverse('fleet:device_verify')))

        response = self.get_response(request)

        # 3. Hand the new device its token. This runs before SessionMiddleware's
        # response phase (which is further out), so popping still gets saved.
        token = request.session.pop(SESSION_SET_TOKEN, None)
        if token:
            response.set_cookie(
                DEVICE_COOKIE, token,
                max_age=DEVICE_COOKIE_AGE,
                httponly=True,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite='Lax',
            )
        return response


class StaffDepartmentMiddleware:
    """
    Enforce staff department sub-roles across the whole /workforce/ tree.

    is_staff already decides who may enter the staff dashboard (via
    @staff_required on each view). This adds the second question — which desk —
    without touching 312 view functions: it reads the resolved URL name and
    checks it against core.departments.URL_DEPARTMENTS.

    Deliberate behaviours:
      - Super admins bypass everything.
      - Non-staff and anonymous users are left to @staff_required, which already
        produces the right redirect/JSON. This middleware never widens access.
      - An unclassified route is refused rather than allowed. workforce's
        department test asserts the map covers every route, so a new URL is
        caught in CI, not by a staff member losing a page in production.
      - A staff user with no department assigned can still reach the shared
        routes (dashboard, help, AJAX pickers) and is told to ask an admin.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = getattr(request, 'resolver_match', None)
        if not match:
            return None

        # Cheapest checks first: this runs on every request in the project, so
        # anonymous and public traffic must not pay for the override lookup.
        user = request.user
        if not user.is_authenticated:
            return None  # staff_required handles the login redirect

        from core.departments import (
            can_access, departments_for, is_overridden, is_route_enabled,
            DEPARTMENT_CHOICES, GATED_NAMESPACES)

        # The workforce tree is gated wholesale. Anywhere else is enforced only
        # once a super admin has explicitly classified the route, so classifying
        # a page outside /workforce/ is opt-in and never a silent lockout.
        if match.app_name not in GATED_NAMESPACES:
            if not is_overridden(match.url_name):
                return None

        # Not staff at all — @staff_required owns that rejection.
        profile = getattr(user, 'profile', None)
        if not (user.is_staff or (profile and profile.is_staff)):
            return None

        if can_access(user, match.url_name):
            return None

        if not is_route_enabled(match.url_name):
            logger.warning(
                "Staff user %s hit disabled page '%s'", user.id, match.url_name)
            return self._deny(
                request, "That page has been switched off by an administrator.")

        required = departments_for(match.url_name)
        if required is None:
            logger.error(
                "Workforce route '%s' (%s) is not classified in core/departments.py — refused",
                match.url_name, request.path,
            )
            reason = "This page has not been assigned to a department yet."
        else:
            labels = [label for code, label in DEPARTMENT_CHOICES if code in required]
            reason = "This page belongs to: %s." % ", ".join(labels)

        logger.warning(
            "Staff user %s blocked from '%s' (needs %s)",
            user.id, match.url_name, sorted(required) if required else 'classification',
        )
        return self._deny(request, reason)

    @staticmethod
    def _deny(request, reason):
        """JSON for AJAX callers, a redirect with a message for page loads."""
        wants_json = (
            request.headers.get('x-requested-with') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('accept', '')
        )
        if wants_json:
            from django.http import JsonResponse
            return JsonResponse(
                {'success': False, 'error': f"Department access required. {reason}"},
                status=403,
            )

        messages.error(
            request,
            f"You don't have access to that section. {reason} "
            "Ask a super admin to add the department to your staff role."
        )
        return redirect('workforce:wf_dashboard')


class SignupOriginMiddleware:
    """
    Remember how an anonymous visitor arrived so the signup can be attributed.

    Records first-touch (landing path, off-site referrer, utm tags) once per
    anonymous session and upgrades the source whenever the visitor opens an
    intent page such as the driver join link. Logged-in visitors are only
    recorded on those intent pages, so a normal browsing session costs one
    session read and writes only when something actually changed.
    core/views.py:profile_add stamps the result onto the new Profile.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'GET':
            try:
                signup_origin.capture(
                    request, first_touch=not request.user.is_authenticated)
            except Exception:
                logger.exception("SignupOriginMiddleware failed for %s", request.path)
        return self.get_response(request)


class WeakPasswordWarningMiddleware:
    """
    Send users whose password failed the strength rules to the change-password nudge.

    Only ordinary HTML page loads are intercepted — never POSTs, AJAX, the API, static
    files, or the auth pages themselves — so a redirect loop cannot strand anyone, and
    logging out is always reachable. Skipping snoozes the warning for the session;
    Profile.WEAK_PASSWORD_MAX_SKIPS caps how many times that is allowed in total.
    """

    EXEMPT_PREFIXES = (
        '/static/', '/media/', '/private-media/', '/api/', '/admin/', '/accounts/',
        '/password/', '/waha/', '/__debug__/', '/favicon',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'WEAK_PASSWORD_WARNING_ENABLED', True)

    def __call__(self, request):
        if self.enabled and self._should_warn(request):
            target = reverse('core:weak_password_warning')
            if request.path != target:
                return redirect(f"{target}?next={quote(request.get_full_path())}")
        return self.get_response(request)

    def _should_warn(self, request):
        if request.method != 'GET' or not request.user.is_authenticated:
            return False
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return False
        if 'text/html' not in request.headers.get('accept', ''):
            return False
        if request.path.startswith(self.EXEMPT_PREFIXES):
            return False
        if request.session.get('weak_password_snoozed'):
            return False

        profile = getattr(request.user, 'profile', None)
        return bool(profile and profile.weak_password)


class SecurityHeadersMiddleware:
    """
    Add Content-Security-Policy and Permissions-Policy headers.
    Improves security posture which Google factors into rankings.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content-Security-Policy.
        #
        # 'unsafe-inline' stays for now: several hundred templates carry inline
        # <script> blocks, and dropping it needs a per-response nonce threaded
        # through every one of them. 'unsafe-eval' is gone — nothing in this
        # project calls eval() or new Function(), and neither do the pinned CDN
        # libraries, so it only widened the blast radius of an injected string.
        #
        # api.mapbox.com was never on this list, so the customer address-confirmation
        # page (the only template that loads mapbox-gl) had its map blocked from
        # the day this header shipped. mapbox-gl v2 needs script+style+connect and
        # a blob: worker, but not unsafe-eval.
        #
        # object-src/base-uri/form-action are the three directives that do NOT
        # fall back to default-src in older engines, so they are stated outright:
        # they block Flash/PDF plugin embeds, <base href> hijacking of every
        # relative URL on the page, and form exfiltration to an attacker's host.
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "script-src 'self' 'unsafe-inline' "
                "https://api.mapbox.com "
                "https://cdn.jsdelivr.net https://code.jquery.com "
                "https://cdn.lordicon.com https://unpkg.com "
                "https://cdn.sheetjs.com https://cdnjs.cloudflare.com "
                "https://cdn.datatables.net "
                "https://static.cloudflareinsights.com "
                "https://www.googletagmanager.com https://www.google-analytics.com "
                "https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/ "
                "https://accounts.google.com/gsi/client; "
                "style-src 'self' 'unsafe-inline' "
                "https://api.mapbox.com "
                "https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com "
                "https://cdn.sheetjs.com https://cdnjs.cloudflare.com "
                "https://cdn.datatables.net https://accounts.google.com; "
                "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
                "img-src 'self' data: blob: https:; "
                "media-src 'self' data: blob: mediastream:; "
                "worker-src 'self' blob:; "
                "connect-src 'self' https://api.mapbox.com https://events.mapbox.com "
                "https://www.google-analytics.com https://unpkg.com "
                "https://*.basemaps.cartocdn.com https://www.google.com/recaptcha/ "
                "https://cdn.jsdelivr.net https://cdn.datatables.net "
                "https://accounts.google.com; "
                "frame-src 'self' https://www.google.com https://accounts.google.com; "
                "frame-ancestors 'self'"
            )

        # Permissions-Policy
        if 'Permissions-Policy' not in response:
            response['Permissions-Policy'] = (
                "geolocation=(self), "
                "camera=(self), "   # driver PWA barcode/QR scanners need getUserMedia
                "microphone=(), "
                "payment=(), "
                "usb=()"
            )

        return response
