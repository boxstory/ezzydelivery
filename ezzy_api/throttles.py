# Purpose: Custom DRF throttles for the client/driver API surface.
# Used by: ezzy_api.views.driver_login (login brute-force protection).
# Notes: Login throttle keys on client IP + submitted username so one attacker
#        IP cannot spray many accounts, and one account cannot be hammered.

from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Rate limit login attempts per (IP, username). Rate set by the
    'login' key in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']."""

    scope = 'login'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        username = ''
        if hasattr(request, 'data'):
            username = str(request.data.get('username', ''))[:150]
        return self.cache_format % {
            'scope': self.scope,
            'ident': f"{ident}:{username}",
        }
