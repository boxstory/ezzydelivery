"""
Core Permission Decorators
==========================

Provides decorators for view-level access control based on user roles.

Usage:
    from core.decorators import staff_required

    @login_required
    @staff_required
    def workforce_view(request):
        ...
"""

import logging
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages

logger = logging.getLogger('core.permissions')


def staff_required(view_func=None, redirect_url=None):
    """
    Decorator to require staff access.

    Checks BOTH Django's User.is_staff AND Profile.is_staff for flexibility.
    Access is granted if EITHER field is True.

    Used for workforce/internal staff views.

    Usage:
        @login_required
        @staff_required
        def wf_dashboard(request):
            ...

        # With custom redirect
        @login_required
        @staff_required(redirect_url='core:main_dashboard')
        def staff_only_view(request):
            ...

    Args:
        view_func: The view function (when used without parentheses)
        redirect_url: URL name to redirect on failure (default: 'core:main_dashboard')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('account_login')

            # Check Django's built-in User.is_staff first
            if request.user.is_staff:
                return view_func(request, *args, **kwargs)

            # Check Profile.is_staff as fallback
            profile = getattr(request.user, 'profile', None)

            if not profile:
                logger.warning(f"User {request.user.id} has no profile")
                messages.error(request, "Profile not found.")
                return redirect(redirect_url or 'core:main_dashboard')

            if not profile.is_staff:
                logger.warning(
                    f"Non-staff user {request.user.id} attempted to access {view_func.__name__}"
                )
                messages.error(request, "You don't have permission to access this page.")
                return redirect(redirect_url or 'core:main_dashboard')

            return view_func(request, *args, **kwargs)

        return wrapper

    # Handle both @staff_required and @staff_required()
    if view_func is not None:
        return decorator(view_func)
    return decorator


def api_staff_required(view_func):
    """
    Decorator for API endpoints that returns JSON responses.

    Checks BOTH Django's User.is_staff AND Profile.is_staff for flexibility.
    Access is granted if EITHER field is True.

    Usage:
        @login_required
        @api_staff_required
        def staff_api_endpoint(request):
            ...
    """
    from django.http import JsonResponse

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required'
            }, status=401)

        # Check Django's built-in User.is_staff first
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)

        # Check Profile.is_staff as fallback
        profile = getattr(request.user, 'profile', None)

        if not profile or not profile.is_staff:
            return JsonResponse({
                'success': False,
                'error': 'Staff access required'
            }, status=403)

        return view_func(request, *args, **kwargs)

    return wrapper


def business_required(view_func=None, redirect_url=None):
    """
    Decorator to require business/client access.

    Allows access for:
    - Business owners (Profile.is_business=True)
    - Team members (active BusinessTeamProfile)

    Usage:
        @login_required
        @business_required
        def business_dashboard(request):
            ...

    Args:
        view_func: The view function (when used without parentheses)
        redirect_url: URL name to redirect on failure (default: 'core:main_dashboard')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('account_login')

            profile = getattr(request.user, 'profile', None)

            if not profile:
                logger.warning(f"User {request.user.id} has no profile")
                messages.error(request, "Profile not found.")
                return redirect(redirect_url or 'core:main_dashboard')

            # Check if business owner
            if profile.is_business:
                return view_func(request, *args, **kwargs)

            # Check if team member using business.decorators helper
            from business.decorators import get_user_business_access
            business, access_type, team_profile = get_user_business_access(request.user, request)

            if business and access_type in ('owner', 'team_member'):
                # Inject business context into request for convenience
                request.current_business = business
                request.access_type = access_type
                request.team_profile = team_profile
                return view_func(request, *args, **kwargs)

            logger.warning(
                f"Non-business user {request.user.id} attempted to access {view_func.__name__}"
            )
            messages.error(request, "You don't have permission to access this page.")
            return redirect(redirect_url or 'core:main_dashboard')

        return wrapper

    if view_func is not None:
        return decorator(view_func)
    return decorator


def driver_required(view_func=None, redirect_url=None):
    """
    Decorator to require driver access (Profile.is_driver=True).

    Used for driver/fleet dashboard views. Only users with is_driver=True
    on their Profile can access views with this decorator.

    Usage:
        @login_required
        @driver_required
        def driver_dashboard(request):
            ...

    Args:
        view_func: The view function (when used without parentheses)
        redirect_url: URL name to redirect on failure (default: 'core:main_dashboard')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('account_login')

            profile = getattr(request.user, 'profile', None)

            if not profile:
                logger.warning(f"User {request.user.id} has no profile")
                messages.error(request, "Profile not found.")
                return redirect(redirect_url or 'core:main_dashboard')

            if not profile.is_driver:
                logger.warning(
                    f"Non-driver user {request.user.id} attempted to access {view_func.__name__}"
                )
                messages.error(request, "You don't have permission to access this page.")
                return redirect(redirect_url or 'core:main_dashboard')

            return view_func(request, *args, **kwargs)

        return wrapper

    if view_func is not None:
        return decorator(view_func)
    return decorator


def api_business_required(view_func):
    """
    Decorator for business API endpoints that returns JSON responses.

    Allows access for:
    - Business owners (Profile.is_business=True)
    - Team members (active BusinessTeamProfile)
    """
    from django.http import JsonResponse

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required'
            }, status=401)

        profile = getattr(request.user, 'profile', None)

        if not profile:
            return JsonResponse({
                'success': False,
                'error': 'Profile not found'
            }, status=403)

        # Check if business owner
        if profile.is_business:
            return view_func(request, *args, **kwargs)

        # Check if team member
        from business.decorators import get_user_business_access
        business, access_type, team_profile = get_user_business_access(request.user, request)

        if business and access_type in ('owner', 'team_member'):
            request.current_business = business
            request.access_type = access_type
            request.team_profile = team_profile
            return view_func(request, *args, **kwargs)

        return JsonResponse({
            'success': False,
            'error': 'Business access required'
        }, status=403)

    return wrapper


def api_driver_required(view_func):
    """
    Decorator for driver API endpoints that returns JSON responses.
    """
    from django.http import JsonResponse

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': 'Authentication required'
            }, status=401)

        profile = getattr(request.user, 'profile', None)

        if not profile or not profile.is_driver:
            return JsonResponse({
                'success': False,
                'error': 'Driver access required'
            }, status=403)

        return view_func(request, *args, **kwargs)

    return wrapper
