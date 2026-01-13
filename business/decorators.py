"""
Business Permission Decorators and Utilities
=============================================

Provides decorators for view-level permission enforcement.
This is separate from Django's is_staff/is_superuser (internal workforce).

Usage:
    from business.decorators import business_permission_required
    from business.permissions import BusinessPermissions

    @login_required
    @business_permission_required(BusinessPermissions.ORDER_CREATE)
    def add_order(request):
        business = request.current_business  # Injected by decorator
        ...

Access Types:
    - 'owner': User is the business owner (Business.user)
    - 'team_member': User is a team member (BusinessTeamProfile)

The decorator injects these into the request object:
    - request.current_business: The Business object
    - request.access_type: 'owner' or 'team_member'
    - request.team_profile: BusinessTeamProfile or None
"""

import logging
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse

from business.models import Business, BusinessTeamProfile
from business.permissions import TeamRoles

logger = logging.getLogger('business.permissions')


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_user_business_access(user):
    """
    Get the business and access type for a user.

    Checks if the user is a business owner first, then checks if they
    are an active team member. This determines their access level.

    Args:
        user: Django User object

    Returns:
        tuple: (business, access_type, team_profile)
        - business: Business object or None
        - access_type: 'owner', 'team_member', or None
        - team_profile: BusinessTeamProfile object or None (for team members)
    """
    if not user.is_authenticated:
        return None, None, None

    # Check if user is a business owner
    owner_business = Business.objects.filter(user=user).first()
    if owner_business:
        return owner_business, 'owner', None

    # Check if user is an active team member
    team_profile = BusinessTeamProfile.objects.select_related('business').filter(
        user=user,
        team_status='active'
    ).first()

    if team_profile:
        return team_profile.business, 'team_member', team_profile

    return None, None, None


def user_has_business_permission(user, permission_code, business=None):
    """
    Check if user has a specific permission for a business.

    Args:
        user: Django User object
        permission_code: Permission code string from BusinessPermissions
        business: Optional Business object (if None, uses user's business)

    Returns:
        bool: True if user has permission
    """
    user_business, access_type, team_profile = get_user_business_access(user)

    if not user_business:
        return False

    # If specific business provided, verify match
    if business and user_business.business_id != business.business_id:
        return False

    # Owners have all permissions
    if access_type == 'owner':
        return True

    # Team members check via profile
    if access_type == 'team_member' and team_profile:
        return team_profile.has_permission(permission_code)

    return False


# =============================================================================
# VIEW DECORATORS
# =============================================================================

def business_permission_required(permission_code, redirect_url=None):
    """
    Decorator to check if user has required business permission.

    Checks if the user is a business owner (full access) or a team member
    with the specified permission. Injects business context into request.

    Usage:
        @login_required
        @business_permission_required(BusinessPermissions.ORDER_CREATE)
        def add_order(request):
            business = request.current_business
            ...

    Args:
        permission_code: Required permission code from BusinessPermissions
        redirect_url: URL to redirect on failure (default: business_dashboard)

    Injects into request:
        - current_business: Business object
        - access_type: 'owner' or 'team_member'
        - team_profile: BusinessTeamProfile or None
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('account_login')

            business, access_type, team_profile = get_user_business_access(request.user)

            if not business:
                logger.warning(f"User {request.user.id} has no business access")
                messages.error(request, "No business associated with your account.")
                return redirect(redirect_url or 'core:main_dashboard')

            # Check permission
            has_perm = False
            if access_type == 'owner':
                has_perm = True
            elif access_type == 'team_member' and team_profile:
                has_perm = team_profile.has_permission(permission_code)

            if not has_perm:
                logger.warning(
                    f"User {request.user.id} denied access to {view_func.__name__} "
                    f"(missing permission: {permission_code})"
                )
                messages.error(request, "You don't have permission to perform this action.")
                return redirect(redirect_url or 'business:business_dashboard')

            # Inject business and team_profile into request for convenience
            request.current_business = business
            request.team_profile = team_profile
            request.access_type = access_type

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def business_permissions_required(permission_codes, require_all=True, redirect_url=None):
    """
    Decorator to check multiple permissions.

    Args:
        permission_codes: List of permission codes
        require_all: If True, all permissions required. If False, any one is sufficient.
        redirect_url: URL to redirect on failure
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('account_login')

            business, access_type, team_profile = get_user_business_access(request.user)

            if not business:
                messages.error(request, "No business associated with your account.")
                return redirect(redirect_url or 'core:main_dashboard')

            # Check permissions
            has_perm = False
            if access_type == 'owner':
                has_perm = True
            elif access_type == 'team_member' and team_profile:
                if require_all:
                    has_perm = team_profile.has_all_permissions(permission_codes)
                else:
                    has_perm = team_profile.has_any_permission(permission_codes)

            if not has_perm:
                logger.warning(
                    f"User {request.user.id} denied access to {view_func.__name__} "
                    f"(missing permissions: {permission_codes})"
                )
                messages.error(request, "You don't have permission to perform this action.")
                return redirect(redirect_url or 'business:business_dashboard')

            request.current_business = business
            request.team_profile = team_profile
            request.access_type = access_type

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def business_owner_required(redirect_url=None):
    """
    Decorator to require business owner access (no team members).

    Used for sensitive operations like business settings, billing, etc.
    Only the business owner (Business.user) can access views with this decorator.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('account_login')

            business, access_type, _ = get_user_business_access(request.user)

            if access_type != 'owner':
                logger.warning(
                    f"User {request.user.id} denied owner-only access to {view_func.__name__}"
                )
                messages.error(request, "Only business owners can perform this action.")
                return redirect(redirect_url or 'business:business_dashboard')

            request.current_business = business
            request.access_type = access_type
            request.team_profile = None

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def business_manager_or_owner_required(redirect_url=None):
    """
    Decorator to require manager or owner access.

    Allows both business owners and team members with 'manager' role.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('account_login')

            business, access_type, team_profile = get_user_business_access(request.user)

            if not business:
                messages.error(request, "No business associated with your account.")
                return redirect(redirect_url or 'core:main_dashboard')

            # Check if owner or manager
            is_authorized = False
            if access_type == 'owner':
                is_authorized = True
            elif access_type == 'team_member' and team_profile:
                is_authorized = team_profile.team_role == TeamRoles.MANAGER

            if not is_authorized:
                logger.warning(
                    f"User {request.user.id} denied manager access to {view_func.__name__}"
                )
                messages.error(request, "Only managers can perform this action.")
                return redirect(redirect_url or 'business:business_dashboard')

            request.current_business = business
            request.team_profile = team_profile
            request.access_type = access_type

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


def business_access_required(redirect_url=None):
    """
    Decorator to require any business access (owner or team member).

    Use this for views that just need to verify the user has business access,
    without checking specific permissions.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('account_login')

            business, access_type, team_profile = get_user_business_access(request.user)

            if not business:
                messages.error(request, "No business associated with your account.")
                return redirect(redirect_url or 'core:main_dashboard')

            request.current_business = business
            request.team_profile = team_profile
            request.access_type = access_type

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


# =============================================================================
# AJAX/API DECORATORS
# =============================================================================

def api_business_permission_required(permission_code):
    """
    Decorator for API endpoints that returns JSON responses.

    Same as business_permission_required but returns JSON instead of redirects.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'success': False,
                    'error': 'Authentication required'
                }, status=401)

            business, access_type, team_profile = get_user_business_access(request.user)

            if not business:
                return JsonResponse({
                    'success': False,
                    'error': 'No business access'
                }, status=403)

            # Check permission
            has_perm = False
            if access_type == 'owner':
                has_perm = True
            elif access_type == 'team_member' and team_profile:
                has_perm = team_profile.has_permission(permission_code)

            if not has_perm:
                return JsonResponse({
                    'success': False,
                    'error': 'Permission denied'
                }, status=403)

            request.current_business = business
            request.team_profile = team_profile
            request.access_type = access_type

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


# =============================================================================
# CONTEXT PROCESSOR
# =============================================================================

def business_permissions_context(request):
    """
    Context processor to add permission info to all templates.

    Add to TEMPLATES['OPTIONS']['context_processors'] in settings.py:
        'business.decorators.business_permissions_context'

    Provides:
        - user_business: Business object or None
        - user_access_type: 'owner', 'team_member', or None
        - user_team_profile: BusinessTeamProfile or None
        - user_permissions: Set of permission codes
        - is_business_owner: Boolean
        - is_team_manager: Boolean

    Template Usage:
        {% if 'orders_create' in user_permissions %}
        <a href="{% url 'orders:add_order' %}">Add Order</a>
        {% endif %}

        {% if is_business_owner %}
        <a href="{% url 'business:settings' %}">Business Settings</a>
        {% endif %}
    """
    context = {
        'user_business': None,
        'user_access_type': None,
        'user_team_profile': None,
        'user_permissions': set(),
        'is_business_owner': False,
        'is_team_manager': False,
    }

    if hasattr(request, 'user') and request.user.is_authenticated:
        business, access_type, team_profile = get_user_business_access(request.user)

        if business:
            context['user_business'] = business
            context['user_access_type'] = access_type
            context['user_team_profile'] = team_profile
            context['is_business_owner'] = (access_type == 'owner')

            if access_type == 'owner':
                # Owners have all permissions
                from business.permissions import get_all_permission_codes
                context['user_permissions'] = set(get_all_permission_codes())
            elif team_profile:
                context['user_permissions'] = team_profile.get_effective_permissions()
                context['is_team_manager'] = team_profile.team_role == TeamRoles.MANAGER

    return context
