from .models import UserProfile, UserRole, SiteReport, Site


def user_role_context(request):
    """Provides current user role and notification counters across all views."""
    context = {
        'current_role': None,
        'is_admin': False,
        'is_management': False,
        'is_site_engineer': False,
        'user_profile': None,
        'pending_reports_count': 0,
        'total_active_sites': 0,
    }

    if request.user.is_authenticated:
        # Check or lazily create UserProfile if missing
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            role = UserRole.ADMIN if request.user.is_superuser else UserRole.SITE_ENGINEER
            profile = UserProfile.objects.create(
                user=request.user,
                role=role,
                designation='Administrator' if request.user.is_superuser else 'Site Engineer'
            )

        context['user_profile'] = profile
        context['current_role'] = profile.role
        context['is_admin'] = profile.is_admin
        context['is_management'] = profile.is_management
        context['is_site_engineer'] = profile.is_site_engineer

        if profile.is_admin or profile.is_management:
            context['pending_reports_count'] = SiteReport.objects.filter(status=SiteReport.ReportStatus.SUBMITTED).count()
        elif profile.is_site_engineer:
            context['pending_reports_count'] = SiteReport.objects.filter(
                reported_by_user=request.user,
                status=SiteReport.ReportStatus.RETURNED
            ).count()

        context['total_active_sites'] = Site.objects.filter(status='ACTIVE').count()

    return context
