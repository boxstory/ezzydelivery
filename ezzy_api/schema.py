"""
Custom OpenAPI Schema Generator with User-Type Based Filtering
=============================================================

API Schema behavior:
- Unauthenticated: No access
- Driver endpoints: Completely hidden from documentation for ALL users
- Clients (is_business): Only store/integration endpoints
- Staff (is_staff): Only internal staff endpoints
- Superadmin: All endpoints EXCEPT driver (driver always hidden)
"""

from drf_spectacular.openapi import AutoSchema
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ClientApiKeyScheme(OpenApiAuthenticationExtension):
    """Teaches drf-spectacular how to document ClientApiKeyAuthentication,
    silencing the W001 'could not resolve authenticator' warnings and
    rendering an API-key security scheme in the OpenAPI docs."""
    target_class = 'ezzy_api.authentication.ClientApiKeyAuthentication'
    name = 'ClientApiKey'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Client API key as "Bearer <key>" or via the X-API-Key header.',
        }


class UserTypeFilteredSchema(AutoSchema):
    """
    Custom schema that tags endpoints with required user type.
    Used to filter schema generation by user role.
    """

    def get_tags(self):
        tags = super().get_tags() or []
        path = self.path

        # Tag endpoints by user type requirement
        if path.startswith('/api/business/'):
            tags = ['Business/Store'] + tags
        elif path.startswith('/api/integrations/') or path.startswith('/api/webhooks/'):
            tags = ['Business/Store'] + tags
        elif 'workforce' in path.lower() or 'orders/verification' in path:
            tags = ['Staff Only'] + tags

        return tags


class UserTypeFilteredSchemaGenerator(SchemaGenerator):
    """
    Custom schema generator that filters endpoints and removes driver endpoints.
    Filters remaining endpoints based on authenticated user's role.
    """

    def get_schema(self, public=False):
        """
        Generate schema, optionally filtered by user role.
        Removes all driver endpoints from schema for all users.

        Args:
            public: If True, return empty schema (no public access)
        """
        schema = super().get_schema(public=public)

        # Remove ALL driver endpoints from schema - completely hidden from documentation
        driver_paths = [path for path in schema.get('paths', {}).keys() if path.startswith('/api/driver/')]
        for path in driver_paths:
            schema['paths'].pop(path, None)

        # If request is available and user is unauthenticated, restrict heavily
        if hasattr(self, '_request') and self._request:
            user = getattr(self._request, 'user', None)

            if not user or not user.is_authenticated:
                # No schema for unauthenticated users
                schema['paths'] = {}
                return schema

            profile = getattr(user, 'profile', None)
            paths_to_remove = []

            # Filter based on user type
            for path in schema.get('paths', {}).keys():
                should_remove = False

                # Business/Stores: only store and integration endpoints
                if profile and profile.is_business and not profile.is_staff:
                    if not (path.startswith('/api/business/') or
                            path.startswith('/api/integrations/') or
                            path.startswith('/api/webhooks/') or
                            path.startswith('/api/api-keys/') or
                            '/api/orders/' in path and 'verify' not in path and 'pending' not in path):
                        should_remove = True

                # Staff: only staff endpoints and internal operations
                elif profile and profile.is_staff and not profile.is_superadmin:
                    if path.startswith('/api/business/'):
                        should_remove = True

                # Superadmin: see everything except driver endpoints (should_remove stays False)

                if should_remove:
                    paths_to_remove.append(path)

            # Remove filtered paths
            for path in paths_to_remove:
                schema['paths'].pop(path, None)

        return schema
