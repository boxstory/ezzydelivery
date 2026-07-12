# Purpose: DRF permission enforcing ClientApiKey read/write/admin scopes.
# Used by: REST_FRAMEWORK DEFAULT_PERMISSION_CLASSES (global) + admin checks in views.
# Notes: Only constrains requests authenticated via a ClientApiKey. Session/token
#        (the human business owner) and anonymous requests pass through untouched.

from rest_framework.permissions import BasePermission, SAFE_METHODS


class ApiKeyScopePermission(BasePermission):
    """
    Method-based scope gate for client API keys:
      - safe methods (GET/HEAD/OPTIONS) require the 'read' scope
      - unsafe methods (POST/PUT/PATCH/DELETE) require the 'write' scope

    Endpoints that manage API keys additionally require 'admin' — enforced
    explicitly in those views via ``require_admin_scope`` since a generic
    method check cannot distinguish them.
    """
    message = 'Your API key does not have the required scope for this action.'

    def has_permission(self, request, view):
        # Import here to avoid app-registry import ordering issues.
        from ezzy_api.models import ClientApiKey
        api_key = getattr(request, 'auth', None)
        if not isinstance(api_key, ClientApiKey):
            return True  # not client-key auth (owner session / token / anon)
        required = ClientApiKey.SCOPE_READ if request.method in SAFE_METHODS else ClientApiKey.SCOPE_WRITE
        return api_key.has_scope(required)


def require_admin_scope(request):
    """Return an error string if a client-key request lacks 'admin', else None.

    No-op for owner session / token auth (request.auth is not a ClientApiKey).
    """
    from ezzy_api.models import ClientApiKey
    api_key = getattr(request, 'auth', None)
    if isinstance(api_key, ClientApiKey) and not api_key.has_scope(ClientApiKey.SCOPE_ADMIN):
        return 'This API key lacks the admin scope required to manage API keys.'
    return None
