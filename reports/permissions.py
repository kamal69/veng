from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from .models import UserRole


def role_required(*allowed_roles):
    """
    Decorator to restrict view access to users with specified roles.
    Superusers always have access.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            profile = getattr(request.user, 'profile', None)
            if not profile:
                messages.error(request, "Your account does not have an assigned role. Please contact Administrator.")
                return redirect('login')

            if profile.role in allowed_roles:
                return view_func(request, *args, **kwargs)

            messages.error(request, "You do not have permission to access this area.")
            return redirect('dashboard')
        return _wrapped_view
    return decorator


def admin_required(view_func):
    return role_required(UserRole.ADMIN)(view_func)


def management_required(view_func):
    return role_required(UserRole.ADMIN, UserRole.MANAGEMENT)(view_func)


def site_engineer_or_admin_required(view_func):
    return role_required(UserRole.ADMIN, UserRole.SITE_ENGINEER)(view_func)
