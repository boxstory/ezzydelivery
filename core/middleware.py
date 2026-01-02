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


class SessionTimeoutMiddleware:
    """
    Middleware to automatically logout users after 1 hour of inactivity

    How it works:
    1. Tracks last activity time in session
    2. On each request, checks if 1 hour has passed since last activity
    3. If expired, logs out user and redirects to login with message
    4. If not expired, updates last activity time
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Timeout duration: 1 hour = 3600 seconds
        self.timeout_duration = timedelta(seconds=3600)

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

            # Check if session has expired (1 hour of inactivity)
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
    Middleware to inject session timeout warning into dashboard pages
    Adds a JavaScript variable with session expiry information
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only inject for authenticated users on dashboard pages
        if (request.user.is_authenticated and
            'dashboard' in request.path and
            response.get('Content-Type', '').startswith('text/html')):

            # Get last activity from session
            last_activity = request.session.get('last_activity')

            if last_activity:
                if isinstance(last_activity, str):
                    last_activity = timezone.datetime.fromisoformat(last_activity)

                if timezone.is_naive(last_activity):
                    last_activity = timezone.make_aware(last_activity)

                # Calculate time remaining (in seconds)
                time_since_activity = timezone.now() - last_activity
                time_remaining = 3600 - int(time_since_activity.total_seconds())

                # Inject session info into response
                if time_remaining > 0 and hasattr(response, 'content'):
                    session_script = f'''
                    <script>
                        // Session timeout configuration
                        window.SESSION_TIMEOUT = {time_remaining};
                        window.SESSION_WARNING_TIME = 300; // Show warning 5 minutes before timeout
                    </script>
                    '''

                    # Insert before closing </head> tag
                    content = response.content.decode('utf-8')
                    if '</head>' in content:
                        content = content.replace('</head>', session_script + '</head>')
                        response.content = content.encode('utf-8')

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
