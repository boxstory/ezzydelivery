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
import logging

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
    Middleware to automatically logout users after 1 day of inactivity

    How it works:
    1. Tracks last activity time in session
    2. On each request, checks if 1 day has passed since last activity
    3. If expired, logs out user and redirects to login with message
    4. If not expired, updates last activity time
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Timeout duration: 1 day = 86400 seconds
        self.timeout_duration = timedelta(days=1)

    def __call__(self, request):
        # Skip timeout check for anonymous users
        if not request.user.is_authenticated:
            response = self.get_response(request)
            return response

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

            # Check if session has expired (1 day of inactivity)
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
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Pre-compute session time remaining and stash on request
        # Templates can use {{ request.session_time_remaining }} if needed
        if request.user.is_authenticated and 'dashboard' in request.path:
            last_activity = request.session.get('last_activity')
            if last_activity:
                if isinstance(last_activity, str):
                    last_activity = timezone.datetime.fromisoformat(last_activity)
                if timezone.is_naive(last_activity):
                    last_activity = timezone.make_aware(last_activity)
                elapsed = (timezone.now() - last_activity).total_seconds()
                request.session_time_remaining = max(0, int(86400 - elapsed))

        return self.get_response(request)


class NoCacheAuthMiddleware:
    """
    Prevents browser bfcache from storing auth pages (login, logout, signup).
    Without this, navigating to /accounts/login/ can serve a stale cached page
    that was rendered before CSS changes take effect.
    """

    AUTH_PATHS = ('/accounts/login/', '/accounts/logout/', '/accounts/signup/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path in self.AUTH_PATHS:
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


class SecurityHeadersMiddleware:
    """
    Add Content-Security-Policy and Permissions-Policy headers.
    Improves security posture which Google factors into rankings.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content-Security-Policy (report-only to avoid breaking things)
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
                "https://cdn.jsdelivr.net https://code.jquery.com "
                "https://cdn.lordicon.com https://unpkg.com "
                "https://cdn.sheetjs.com https://cdnjs.cloudflare.com "
                "https://cdn.datatables.net "
                "https://static.cloudflareinsights.com "
                "https://www.googletagmanager.com https://www.google-analytics.com "
                "https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/ "
                "https://accounts.google.com/gsi/client; "
                "style-src 'self' 'unsafe-inline' "
                "https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com "
                "https://cdn.sheetjs.com https://cdnjs.cloudflare.com "
                "https://cdn.datatables.net https://accounts.google.com; "
                "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
                "img-src 'self' data: blob: https:; "
                "connect-src 'self' https://www.google-analytics.com https://unpkg.com "
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
                "camera=(), "
                "microphone=(), "
                "payment=(), "
                "usb=()"
            )

        return response
