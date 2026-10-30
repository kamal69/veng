from django.contrib import admin
from .models import (
    UserProfile, Site, Employee, SiteReport,
    ManpowerEntry, MachineryEntry, EmployeeSiteVisit, ReportAuditLog, ReportToolEntry
)


class ManpowerEntryInline(admin.TabularInline):
    model = ManpowerEntry
    extra = 1


class MachineryEntryInline(admin.TabularInline):
    model = MachineryEntry
    extra = 1


class EmployeeSiteVisitInline(admin.TabularInline):
    model = EmployeeSiteVisit
    extra = 1


class ReportToolEntryInline(admin.TabularInline):
    model = ReportToolEntry
    extra = 1


class ReportAuditLogInline(admin.TabularInline):
    model = ReportAuditLog
    extra = 0
    readonly_fields = ('action', 'performed_by', 'timestamp', 'notes')
    can_delete = False


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'designation', 'phone')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'designation')


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'location', 'client_name', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'code', 'client_name')


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'name', 'designation', 'department', 'daily_rate', 'hourly_rate', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('employee_id', 'name', 'designation')


@admin.register(SiteReport)
class SiteReportAdmin(admin.ModelAdmin):
    list_display = ('site', 'report_date', 'status', 'reported_by_name', 'total_site_cost', 'total_manpower_count')
    list_filter = ('status', 'site_status', 'site', 'report_date')
    search_fields = ('site__name', 'reported_by_name', 'work_done_today')
    inlines = [ManpowerEntryInline, MachineryEntryInline, EmployeeSiteVisitInline, ReportToolEntryInline, ReportAuditLogInline]
