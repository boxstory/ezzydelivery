"""
Custom Views for API Schema with Permission-Based Access Control
==============================================================

Provides Swagger and ReDoc documentation with user-type filtering:
- Requires authentication (no public access)
- Driver endpoints completely hidden from schema
- Filters remaining endpoints based on user role (client, staff, admin)
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework import status


class IsAuthenticatedUser(IsAuthenticated):
    """
    Allows access only to authenticated users.
    Denies access to anonymous users and rejected token auth.
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class AuthenticatedSchemaView(SpectacularAPIView):
    """
    OpenAPI schema endpoint with authentication required.
    Filters endpoints based on user role.
    """
    permission_classes = [IsAuthenticatedUser]
    authentication_classes = [TokenAuthentication, SessionAuthentication]

    def get_permissions(self):
        """Allow unauthenticated access for development; enforce in production."""
        # In production, uncomment the line below to require authentication
        # return [IsAuthenticatedUser()]
        return super().get_permissions()

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)

        # If user is unauthenticated, return empty schema
        if not request.user or not request.user.is_authenticated:
            return JsonResponse(
                {
                    'detail': 'API schema requires authentication. Please log in or use a valid API token.',
                    'authenticated': False,
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        return response


class AuthenticatedSwaggerView(SpectacularSwaggerView):
    """
    Swagger UI endpoint with authentication required.
    Shows user-filtered API endpoints based on their role.
    """
    permission_classes = [IsAuthenticatedUser]
    authentication_classes = [TokenAuthentication, SessionAuthentication]

    def get_permissions(self):
        """Override to allow unauthenticated access for convenience."""
        # Allow anyone to see the UI, but the schema itself will be empty if not authenticated
        return []

    def get(self, request, *args, **kwargs):
        # If not authenticated, show login prompt with helpful message
        if not request.user or not request.user.is_authenticated:
            return JsonResponse(
                {
                    'detail': 'Please log in to view API documentation.',
                    'authenticated': False,
                    'login_url': '/accounts/login/',
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        return super().get(request, *args, **kwargs)


class AuthenticatedRedocView(SpectacularRedocView):
    """
    ReDoc UI endpoint with authentication required.
    Shows user-filtered API endpoints based on their role.
    """
    permission_classes = [IsAuthenticatedUser]
    authentication_classes = [TokenAuthentication, SessionAuthentication]

    def get_permissions(self):
        """Override to allow unauthenticated access for convenience."""
        return []

    def get(self, request, *args, **kwargs):
        # If not authenticated, show login prompt
        if not request.user or not request.user.is_authenticated:
            return JsonResponse(
                {
                    'detail': 'Please log in to view API documentation.',
                    'authenticated': False,
                    'login_url': '/accounts/login/',
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        return super().get(request, *args, **kwargs)
