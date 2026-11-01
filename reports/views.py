import json
from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError

from .models import (
    Site, Employee, SiteReport, ManpowerEntry, MachineryEntry,
    EmployeeSiteVisit, ReportAuditLog, UserProfile, UserRole,
    ManpowerCategory, ManpowerType, MachineryOwnership, MachineryBillingBasis, VisitType,
    MaterialPurchase, MaterialPaymentMode
)
from .services import ReportService
from .excel_export import export_single_report_to_excel, export_bulk_reports_to_excel
from .permissions import admin_required, management_required, site_engineer_or_admin_required
from .forms import SiteForm, EmployeeForm, UserProfileForm, ReturnReportForm, MaterialPurchaseForm


# -------------------------------------------------------------
# AUTHENTICATION VIEWS
# -------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password. Please try again.")
    else:
        form = AuthenticationForm()

    return render(request, 'auth/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')


@login_required
def profile_view(request):
    profile = getattr(request.user, 'profile', None)
    return render(request, 'auth/profile.html', {
        'profile': profile,
        'user': request.user,
    })


# -------------------------------------------------------------
# DASHBOARD VIEW
# -------------------------------------------------------------

@login_required
def dashboard_view(request):
    today = timezone.localdate()

    # Filter parameters
    site_id = request.GET.get('site_id', '')
    date_filter = request.GET.get('date_filter', 'today')  # today, week, month, custom
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')

    base_reports = SiteReport.objects.all()

    # Role filter: if Site Engineer, show their assigned sites or authored reports by default
    user_profile = getattr(request.user, 'profile', None)
    if user_profile and user_profile.is_site_engineer:
        assigned = user_profile.assigned_sites.all()
        if assigned.exists():
            base_reports = base_reports.filter(Q(site__in=assigned) | Q(reported_by_user=request.user))

    # Apply Site filter
    if site_id:
        base_reports = base_reports.filter(site_id=site_id)

    # Date range calculation
    if date_filter == 'today':
        range_start = today
        range_end = today
    elif date_filter == 'week':
        range_start = today - timedelta(days=7)
        range_end = today
    elif date_filter == 'month':
        range_start = today - timedelta(days=30)
        range_end = today
    elif date_filter == 'custom' and start_date_str and end_date_str:
        try:
            range_start = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            range_end = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            range_start = today - timedelta(days=7)
            range_end = today
    else:
        range_start = today - timedelta(days=7)
        range_end = today

    # KPI 1: Active Sites
    active_sites_count = Site.objects.filter(status='ACTIVE').count()

    # KPI 2 & 3: Today's Total Manpower & Cost
    today_reports = base_reports.filter(report_date=today)
    today_stats = today_reports.aggregate(
        total_cost=Sum('total_site_cost'),
        total_workers=Sum('total_manpower_count'),
        manpower_cost=Sum('total_manpower_cost'),
        machinery_cost=Sum('total_machinery_cost'),
        employee_cost=Sum('total_employee_cost'),
    )
    today_total_cost = today_stats['total_cost'] or Decimal('0.00')
    today_total_manpower = today_stats['total_workers'] or 0

    # KPI 4: Pending Reports
    pending_reports_count = base_reports.filter(status=SiteReport.ReportStatus.SUBMITTED).count()

    # Pending review list (for Admin / Management)
    pending_reports = base_reports.filter(status=SiteReport.ReportStatus.SUBMITTED).order_by('-submitted_at')[:6]

    # Site-wise Cost Comparison (for filtered date range)
    range_reports = base_reports.filter(report_date__gte=range_start, report_date__lte=range_end)
    site_costs = range_reports.values('site__name').annotate(
        site_total=Sum('total_site_cost'),
        mp_total=Sum('total_manpower_cost'),
        mac_total=Sum('total_machinery_cost'),
        emp_total=Sum('total_employee_cost'),
        reports_count=Count('id')
    ).order_by('-site_total')

    site_chart_labels = [sc['site__name'] for sc in site_costs]
    site_chart_values = [float(sc['site_total'] or 0) for sc in site_costs]

    # Trend: daily costs over the last 7 days
    trend_labels = []
    trend_values = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_cost = base_reports.filter(report_date=day).aggregate(s=Sum('total_site_cost'))['s'] or 0
        trend_labels.append(day.strftime("%d %b"))
        trend_values.append(float(day_cost))

    # Cost breakdown for filtered range
    range_totals = range_reports.aggregate(
        mp=Sum('total_manpower_cost'),
        mac=Sum('total_machinery_cost'),
        emp=Sum('total_employee_cost'),
        tot=Sum('total_site_cost')
    )
    manpower_share = float(range_totals['mp'] or 0)
    machinery_share = float(range_totals['mac'] or 0)
    employee_share = float(range_totals['emp'] or 0)

    # Recent reports
    recent_reports = base_reports.order_by('-report_date', '-created_at')[:8]

    # Sites dropdown list
    sites = Site.objects.all()

    context = {
        'active_sites_count': active_sites_count,
        'today_total_manpower': today_total_manpower,
        'today_total_cost': today_total_cost,
        'pending_reports_count': pending_reports_count,
        'pending_reports': pending_reports,
        'recent_reports': recent_reports,
        'sites': sites,
        'selected_site_id': site_id,
        'date_filter': date_filter,
        'start_date': range_start.strftime('%Y-%m-%d'),
        'end_date': range_end.strftime('%Y-%m-%d'),
        'today_date': today,
        # Chart JSON data
        'site_chart_labels': json.dumps(site_chart_labels),
        'site_chart_values': json.dumps(site_chart_values),
        'trend_labels': json.dumps(trend_labels),
        'trend_values': json.dumps(trend_values),
        'cost_composition': json.dumps([manpower_share, machinery_share, employee_share]),
        'site_costs': site_costs,
    }
    return render(request, 'reports/dashboard.html', context)


# -------------------------------------------------------------
# DAILY SITE REPORTS LIST & CRUD
# -------------------------------------------------------------

@login_required
def report_list_view(request):
    reports = SiteReport.objects.select_related('site', 'reported_by_user', 'approved_by').all()

    # Filters
    site_id = request.GET.get('site_id', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    q = request.GET.get('q', '').strip()

    if site_id:
        reports = reports.filter(site_id=site_id)
    if status:
        reports = reports.filter(status=status)
    if date_from:
        reports = reports.filter(report_date__gte=date_from)
    if date_to:
        reports = reports.filter(report_date__lte=date_to)
    if q:
        reports = reports.filter(
            Q(site__name__icontains=q) |
            Q(reported_by_name__icontains=q) |
            Q(work_done_today__icontains=q)
        )

    # Aggregates for filtered result
    stats = reports.aggregate(
        total_cost=Sum('total_site_cost'),
        total_workers=Sum('total_manpower_count')
    )

    paginator = Paginator(reports, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    sites = Site.objects.all()

    context = {
        'page_obj': page_obj,
        'sites': sites,
        'selected_site': site_id,
        'selected_status': status,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': q,
        'filtered_total_cost': stats['total_cost'] or Decimal('0.00'),
        'filtered_total_workers': stats['total_workers'] or 0,
        'statuses': SiteReport.ReportStatus.choices,
    }
    return render(request, 'reports/report_list.html', context)


@login_required
def report_detail_view(request, pk):
    report = get_object_or_404(
        SiteReport.objects.select_related('site', 'reported_by_user', 'approved_by', 'submitted_by'),
        pk=pk
    )
    manpower_entries = report.manpower_entries.all()
    machinery_entries = report.machinery_entries.all()
    employee_visits = report.employee_visits.select_related('employee').all()
    tool_entries = report.tool_entries.all()
    audit_logs = report.audit_logs.select_related('performed_by').all()

    # Permission checks
    user_profile = getattr(request.user, 'profile', None)
    is_admin = request.user.is_superuser or (user_profile and user_profile.is_admin)
    is_management = is_admin or (user_profile and user_profile.is_management)
    can_edit = (report.status != SiteReport.ReportStatus.APPROVED) or is_admin
    can_submit = (report.status in [SiteReport.ReportStatus.DRAFT, SiteReport.ReportStatus.RETURNED])
    can_approve = is_management and report.status == SiteReport.ReportStatus.SUBMITTED
    can_return = is_management and report.status in [SiteReport.ReportStatus.SUBMITTED, SiteReport.ReportStatus.APPROVED]

    # Site Cash Expenses & DPR Reconciliation
    from expenses.models import CashTransaction, ExpenseSite, ExpenseCategory
    exp_site = ExpenseSite.objects.filter(name__iexact=report.site.name).first()
    if exp_site:
        site_cash_txns = CashTransaction.objects.filter(
            site=exp_site,
            transaction_date=report.report_date
        ).select_related('employee', 'category')
    else:
        site_cash_txns = CashTransaction.objects.none()

    actual_labour_paid = site_cash_txns.filter(
        Q(category__group_type=ExpenseCategory.GroupType.LABOUR) |
        Q(particulars__icontains='labour') |
        Q(particulars__icontains='majdoor') |
        Q(particulars__icontains='mason') |
        Q(particulars__icontains='mistri')
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    actual_machinery_paid = site_cash_txns.filter(
        Q(category__group_type__in=[ExpenseCategory.GroupType.MACHINERY, ExpenseCategory.GroupType.VEHICLE]) |
        Q(particulars__icontains='machin') |
        Q(particulars__icontains='diesel') |
        Q(particulars__icontains='fuel') |
        Q(particulars__icontains='jcb')
    ).exclude(
        Q(category__group_type=ExpenseCategory.GroupType.LABOUR) |
        Q(particulars__icontains='labour')
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    actual_total_cash_spent = site_cash_txns.aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    actual_other_paid = actual_total_cash_spent - actual_labour_paid - actual_machinery_paid
    if actual_other_paid < Decimal('0.00'):
        actual_other_paid = Decimal('0.00')

    labour_variance = actual_labour_paid - report.total_manpower_cost
    machinery_variance = actual_machinery_paid - report.total_rental_cost
    total_variance = actual_total_cash_spent - report.total_site_cost

    return render(request, 'reports/report_detail.html', {
        'report': report,
        'manpower_entries': manpower_entries,
        'machinery_entries': machinery_entries,
        'employee_visits': employee_visits,
        'tool_entries': tool_entries,
        'audit_logs': audit_logs,
        'site_cash_txns': site_cash_txns,
        'actual_labour_paid': actual_labour_paid,
        'actual_machinery_paid': actual_machinery_paid,
        'actual_other_paid': actual_other_paid,
        'actual_total_cash_spent': actual_total_cash_spent,
        'labour_variance': labour_variance,
        'machinery_variance': machinery_variance,
        'total_variance': total_variance,
        'can_edit': can_edit,
        'can_submit': can_submit,
        'can_approve': can_approve,
        'can_return': can_return,
        'is_admin': is_admin,
        'return_form': ReturnReportForm(),
    })


@login_required
def report_create_view(request):
    """
    Renders dynamic daily report form and handles saving as Draft or Submit.
    """
    if request.method == 'POST':
        action = request.POST.get('action', 'save_draft')  # 'save_draft' or 'submit'
        report_data = {
            'site': request.POST.get('site'),
            'report_date': request.POST.get('report_date'),
            'site_status': request.POST.get('site_status'),
            'reported_by_name': request.POST.get('reported_by_name'),
            'reported_by_designation': request.POST.get('reported_by_designation'),
            'company_employees_on_site': request.POST.get('company_employees_on_site', ''),
            'work_done_today': request.POST.get('work_done_today', ''),
            'remarks': request.POST.get('remarks', ''),
            'allow_duplicate': request.POST.get('allow_duplicate') == '1',
        }

        # Parse Manpower rows
        manpower_rows = []
        categories = request.POST.getlist('manpower_category[]')
        types = request.POST.getlist('manpower_type[]')
        counts = request.POST.getlist('manpower_count[]')
        rates = request.POST.getlist('manpower_rate[]')
        remarks_list = request.POST.getlist('manpower_remarks[]')

        for i in range(len(categories)):
            if i < len(counts) and counts[i]:
                manpower_rows.append({
                    'category': categories[i],
                    'type': types[i] if i < len(types) else '',
                    'worker_count': counts[i],
                    'rate_per_head': rates[i] if i < len(rates) else '0',
                    'remarks': remarks_list[i] if i < len(remarks_list) else '',
                })

        # Parse Machinery rows
        machinery_rows = []
        machines = request.POST.getlist('machine_name[]')
        ownerships = request.POST.getlist('machine_ownership[]')
        quantities = request.POST.getlist('machine_quantity[]')
        billing_bases = request.POST.getlist('machine_billing_basis[]')
        usages = request.POST.getlist('machine_usage[]')
        machinery_rates = request.POST.getlist('machine_rate[]')
        machinery_remarks = request.POST.getlist('machine_remarks[]')

        for i in range(len(machines)):
            m_name = machines[i].strip() if i < len(machines) else ''
            m_rate = machinery_rates[i].strip() if i < len(machinery_rates) else ''
            m_usage = usages[i].strip() if i < len(usages) else ''
            m_rem = machinery_remarks[i].strip() if i < len(machinery_remarks) else ''
            has_usage = bool(m_usage and m_usage not in ('0', '0.0', '0.00'))
            has_rate = bool(m_rate and m_rate not in ('0', '0.0', '0.00'))
            if m_name or has_usage or has_rate or m_rem:
                machinery_rows.append({
                    'machine_name': m_name if m_name else "Site Machinery / Equipment",
                    'ownership': ownerships[i] if i < len(ownerships) else 'RENTAL',
                    'quantity': quantities[i] if (i < len(quantities) and quantities[i]) else '1',
                    'billing_basis': billing_bases[i] if i < len(billing_bases) else 'HOUR',
                    'usage_value': m_usage if m_usage else '0',
                    'rate': m_rate if m_rate else '0',
                    'remarks': m_rem,
                })

        # Parse Employee Visits rows
        employee_rows = []
        emp_ids = request.POST.getlist('employee_id[]')
        visit_types = request.POST.getlist('visit_type[]')
        hours_list = request.POST.getlist('hours_spent[]')
        applied_rates = request.POST.getlist('applied_rate[]')
        emp_remarks = request.POST.getlist('employee_remarks[]')

        for i in range(len(emp_ids)):
            if emp_ids[i]:
                employee_rows.append({
                    'employee_id': emp_ids[i],
                    'visit_type': visit_types[i] if i < len(visit_types) else 'FULL_DAY',
                    'hours_spent': hours_list[i] if i < len(hours_list) else '0',
                    'applied_rate': applied_rates[i] if i < len(applied_rates) else '0',
                    'remarks': emp_remarks[i] if i < len(emp_remarks) else '',
                })

        # Parse Tools Used rows
        tool_rows = []
        t_names = request.POST.getlist('tool_name[]')
        t_qtys = request.POST.getlist('tool_quantity[]')
        t_users = request.POST.getlist('tool_used_by[]')
        t_remarks = request.POST.getlist('tool_remarks[]')

        for i in range(len(t_names)):
            if t_names[i].strip():
                tool_rows.append({
                    'tool_name': t_names[i].strip(),
                    'quantity': t_qtys[i] if i < len(t_qtys) and t_qtys[i] else 1,
                    'used_by': t_users[i].strip() if i < len(t_users) else '',
                    'remarks': t_remarks[i].strip() if i < len(t_remarks) else '',
                })

        try:
            report = ReportService.save_report(
                user=request.user,
                report_data=report_data,
                manpower_rows=manpower_rows,
                machinery_rows=machinery_rows,
                employee_rows=employee_rows,
                submit_action=action,
                tool_rows=tool_rows,
            )
            verb = "submitted for approval" if action == 'submit' else "saved as draft"
            messages.success(request, f"Daily Site Report successfully {verb}!")
            return redirect('report_detail', pk=report.pk)
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                err_text = "; ".join([f"{k.replace('_', ' ').title()}: {', '.join(v)}" for k, v in e.message_dict.items()])
            elif hasattr(e, 'messages'):
                err_text = "; ".join(e.messages)
            else:
                err_text = str(e)
            messages.error(request, f"Validation Error: {err_text}")
        except Exception as e:
            messages.error(request, f"Error saving report: {str(e)}")

    # GET request: prepare form options
    user_profile = getattr(request.user, 'profile', None)
    default_name = request.user.get_full_name() or request.user.username
    default_desig = user_profile.designation if user_profile else 'Site Engineer'

    sites = Site.objects.filter(status='ACTIVE')
    employees = Employee.objects.filter(is_active=True).order_by('name')

    # Employee serialized data for client-side JS auto-fill
    employees_json = json.dumps([
        {
            'id': emp.id,
            'name': emp.name,
            'designation': emp.designation,
            'daily_rate': float(emp.daily_rate),
            'hourly_rate': float(emp.hourly_rate),
        }
        for emp in employees
    ])

    context = {
        'sites': sites,
        'employees': employees,
        'employees_json': employees_json,
        'default_name': default_name,
        'default_designation': default_desig,
        'today_date': timezone.localdate().strftime('%Y-%m-%d'),
        'categories': ManpowerCategory.choices,
        'types': ManpowerType.choices,
        'site_statuses': SiteReport.SiteStatus.choices,
        'machinery_ownerships': MachineryOwnership.choices,
        'billing_bases': MachineryBillingBasis.choices,
        'visit_types': VisitType.choices,
        'is_admin': request.user.is_superuser or (user_profile and user_profile.is_admin),
    }
    return render(request, 'reports/report_form.html', context)


@login_required
def report_edit_view(request, pk):
    report = get_object_or_404(SiteReport, pk=pk)
    user_profile = getattr(request.user, 'profile', None)
    is_admin = request.user.is_superuser or (user_profile and user_profile.is_admin)

    # Permission check: cannot edit approved reports unless admin
    if report.status == SiteReport.ReportStatus.APPROVED and not is_admin:
        messages.error(request, "Approved reports are locked and cannot be edited.")
        return redirect('report_detail', pk=report.pk)

    if request.method == 'POST':
        action = request.POST.get('action', 'save_draft')
        report_data = {
            'site': request.POST.get('site'),
            'report_date': request.POST.get('report_date'),
            'site_status': request.POST.get('site_status'),
            'reported_by_name': request.POST.get('reported_by_name'),
            'reported_by_designation': request.POST.get('reported_by_designation'),
            'company_employees_on_site': request.POST.get('company_employees_on_site', ''),
            'work_done_today': request.POST.get('work_done_today', ''),
            'remarks': request.POST.get('remarks', ''),
            'allow_duplicate': request.POST.get('allow_duplicate') == '1',
        }

        # Parse Manpower rows
        manpower_rows = []
        categories = request.POST.getlist('manpower_category[]')
        types = request.POST.getlist('manpower_type[]')
        counts = request.POST.getlist('manpower_count[]')
        rates = request.POST.getlist('manpower_rate[]')
        remarks_list = request.POST.getlist('manpower_remarks[]')

        for i in range(len(categories)):
            if i < len(counts) and counts[i]:
                manpower_rows.append({
                    'category': categories[i],
                    'type': types[i] if i < len(types) else '',
                    'worker_count': counts[i],
                    'rate_per_head': rates[i] if i < len(rates) else '0',
                    'remarks': remarks_list[i] if i < len(remarks_list) else '',
                })

        # Parse Machinery rows
        machinery_rows = []
        machines = request.POST.getlist('machine_name[]')
        ownerships = request.POST.getlist('machine_ownership[]')
        quantities = request.POST.getlist('machine_quantity[]')
        billing_bases = request.POST.getlist('machine_billing_basis[]')
        usages = request.POST.getlist('machine_usage[]')
        machinery_rates = request.POST.getlist('machine_rate[]')
        machinery_remarks = request.POST.getlist('machine_remarks[]')

        for i in range(len(machines)):
            m_name = machines[i].strip() if i < len(machines) else ''
            m_rate = machinery_rates[i].strip() if i < len(machinery_rates) else ''
            m_usage = usages[i].strip() if i < len(usages) else ''
            m_rem = machinery_remarks[i].strip() if i < len(machinery_remarks) else ''
            has_usage = bool(m_usage and m_usage not in ('0', '0.0', '0.00'))
            has_rate = bool(m_rate and m_rate not in ('0', '0.0', '0.00'))
            if m_name or has_usage or has_rate or m_rem:
                machinery_rows.append({
                    'machine_name': m_name if m_name else "Site Machinery / Equipment",
                    'ownership': ownerships[i] if i < len(ownerships) else 'RENTAL',
                    'quantity': quantities[i] if (i < len(quantities) and quantities[i]) else '1',
                    'billing_basis': billing_bases[i] if i < len(billing_bases) else 'HOUR',
                    'usage_value': m_usage if m_usage else '0',
                    'rate': m_rate if m_rate else '0',
                    'remarks': m_rem,
                })

        # Parse Employee Visits rows
        employee_rows = []
        emp_ids = request.POST.getlist('employee_id[]')
        visit_types = request.POST.getlist('visit_type[]')
        hours_list = request.POST.getlist('hours_spent[]')
        applied_rates = request.POST.getlist('applied_rate[]')
        emp_remarks = request.POST.getlist('employee_remarks[]')

        for i in range(len(emp_ids)):
            if emp_ids[i]:
                employee_rows.append({
                    'employee_id': emp_ids[i],
                    'visit_type': visit_types[i] if i < len(visit_types) else 'FULL_DAY',
                    'hours_spent': hours_list[i] if i < len(hours_list) else '0',
                    'applied_rate': applied_rates[i] if i < len(applied_rates) else '0',
                    'remarks': emp_remarks[i] if i < len(emp_remarks) else '',
                })

        # Parse Tools Used rows
        tool_rows = []
        t_names = request.POST.getlist('tool_name[]')
        t_qtys = request.POST.getlist('tool_quantity[]')
        t_users = request.POST.getlist('tool_used_by[]')
        t_remarks = request.POST.getlist('tool_remarks[]')

        for i in range(len(t_names)):
            if t_names[i].strip():
                tool_rows.append({
                    'tool_name': t_names[i].strip(),
                    'quantity': t_qtys[i] if i < len(t_qtys) and t_qtys[i] else 1,
                    'used_by': t_users[i].strip() if i < len(t_users) else '',
                    'remarks': t_remarks[i].strip() if i < len(t_remarks) else '',
                })

        try:
            saved_report = ReportService.save_report(
                user=request.user,
                report_data=report_data,
                manpower_rows=manpower_rows,
                machinery_rows=machinery_rows,
                employee_rows=employee_rows,
                submit_action=action,
                existing_report=report,
                tool_rows=tool_rows,
            )
            verb = "submitted for approval" if action == 'submit' else "updated successfully"
            messages.success(request, f"Daily Site Report {verb}!")
            return redirect('report_detail', pk=saved_report.pk)
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                err_text = "; ".join([f"{k.replace('_', ' ').title()}: {', '.join(v)}" for k, v in e.message_dict.items()])
            elif hasattr(e, 'messages'):
                err_text = "; ".join(e.messages)
            else:
                err_text = str(e)
            messages.error(request, f"Validation Error: {err_text}")
        except Exception as e:
            messages.error(request, f"Error updating report: {str(e)}")

    # GET
    sites = Site.objects.all()
    employees = Employee.objects.filter(is_active=True).order_by('name')

    employees_json = json.dumps([
        {
            'id': emp.id,
            'name': emp.name,
            'designation': emp.designation,
            'daily_rate': float(emp.daily_rate),
            'hourly_rate': float(emp.hourly_rate),
        }
        for emp in employees
    ])

    context = {
        'report': report,
        'sites': sites,
        'employees': employees,
        'employees_json': employees_json,
        'categories': ManpowerCategory.choices,
        'types': ManpowerType.choices,
        'site_statuses': SiteReport.SiteStatus.choices,
        'machinery_ownerships': MachineryOwnership.choices,
        'billing_bases': MachineryBillingBasis.choices,
        'visit_types': VisitType.choices,
        'is_admin': is_admin,
        'is_edit': True,
    }
    return render(request, 'reports/report_form.html', context)


@login_required
def report_submit_view(request, pk):
    report = get_object_or_404(SiteReport, pk=pk)
    if request.method == 'POST':
        ReportService.submit_report(report, request.user)
        messages.success(request, f"Report for '{report.site.name}' on {report.report_date} has been submitted for approval.")
    return redirect('report_detail', pk=pk)


@login_required
@management_required
def report_approve_view(request, pk):
    report = get_object_or_404(SiteReport, pk=pk)
    if request.method == 'POST':
        ReportService.approve_report(report, request.user)
        messages.success(request, f"Report for '{report.site.name}' on {report.report_date} has been APPROVED.")
    return redirect('report_detail', pk=pk)


@login_required
@management_required
def report_return_view(request, pk):
    report = get_object_or_404(SiteReport, pk=pk)
    if request.method == 'POST':
        form = ReturnReportForm(request.POST)
        if form.is_valid():
            remarks = form.cleaned_data['rejection_remarks']
            ReportService.return_report(report, request.user, remarks)
            messages.warning(request, f"Report returned for correction. Site Engineer notified.")
        else:
            messages.error(request, "Please enter remarks explaining why the report is being returned.")
    return redirect('report_detail', pk=pk)


@login_required
def report_delete_view(request, pk):
    report = get_object_or_404(SiteReport, pk=pk)
    user_profile = getattr(request.user, 'profile', None)
    is_admin = request.user.is_superuser or (user_profile and user_profile.is_admin)

    # Site engineer can only delete draft reports they created
    if not is_admin:
        if report.status != SiteReport.ReportStatus.DRAFT or report.reported_by_user != request.user:
            messages.error(request, "You can only delete your own draft reports.")
            return redirect('report_detail', pk=pk)

    if request.method == 'POST':
        site_name = report.site.name
        report_date = report.report_date
        report.delete()
        messages.success(request, f"Draft report for '{site_name}' on {report_date} was deleted.")
        return redirect('report_list')

    return render(request, 'reports/report_confirm_delete.html', {'report': report})


@login_required
def report_print_view(request, pk):
    """
    Renders dedicated print view for clean paper/PDF output.
    """
    report = get_object_or_404(
        SiteReport.objects.select_related('site', 'reported_by_user', 'approved_by'),
        pk=pk
    )
    return render(request, 'reports/report_print.html', {
        'report': report,
        'manpower_entries': report.manpower_entries.all(),
        'machinery_entries': report.machinery_entries.all(),
        'employee_visits': report.employee_visits.select_related('employee').all(),
        'generated_at': timezone.now(),
    })


@login_required
def report_excel_export_view(request, pk):
    report = get_object_or_404(
        SiteReport.objects.select_related('site', 'reported_by_user', 'approved_by'),
        pk=pk
    )
    excel_stream = export_single_report_to_excel(report)
    filename = f"DSR_{report.site.code}_{report.report_date.strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        excel_stream.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def reports_bulk_excel_export_view(request):
    reports = SiteReport.objects.select_related('site', 'reported_by_user').all()

    site_id = request.GET.get('site_id', '')
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if site_id:
        reports = reports.filter(site_id=site_id)
    if status:
        reports = reports.filter(status=status)
    if date_from:
        reports = reports.filter(report_date__gte=date_from)
    if date_to:
        reports = reports.filter(report_date__lte=date_to)

    excel_stream = export_bulk_reports_to_excel(reports)
    filename = f"Consolidated_Site_Reports_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        excel_stream.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# -------------------------------------------------------------
# MASTER DATA MANAGEMENT VIEWS (ADMIN ONLY)
# -------------------------------------------------------------

@login_required
def site_list_view(request):
    sites = Site.objects.annotate(
        reports_count=Count('reports'),
        total_spent=Sum('reports__total_site_cost')
    ).all()
    user_profile = getattr(request.user, 'profile', None)
    is_admin = request.user.is_superuser or (user_profile and user_profile.is_admin)
    return render(request, 'master/site_list.html', {'sites': sites, 'is_admin': is_admin})


@login_required
def site_detail_view(request, pk):
    """
    Detailed work timeline & cost analytics for a specific site.
    Shows day-by-day 'Kis din kya kaam hua', manpower, machinery,
    employee visits, tools used, and week/month/year aggregation.
    """
    site = get_object_or_404(Site, pk=pk)
    
    # Filter parameters
    period = request.GET.get('period', 'all')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    today = timezone.localdate()
    reports_qs = site.reports.prefetch_related(
        'manpower_entries', 'machinery_entries', 'employee_visits__employee', 'tool_entries'
    ).order_by('-report_date')

    # Apply quick period filters
    if period == 'this_week':
        start_of_week = today - timedelta(days=today.weekday())
        reports_qs = reports_qs.filter(report_date__gte=start_of_week, report_date__lte=today)
    elif period == 'this_month':
        reports_qs = reports_qs.filter(report_date__year=today.year, report_date__month=today.month)
    elif period == 'last_month':
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        reports_qs = reports_qs.filter(report_date__year=last_month_end.year, report_date__month=last_month_end.month)
    elif period == 'this_year':
        reports_qs = reports_qs.filter(report_date__year=today.year)
    elif period == 'custom':
        if date_from:
            reports_qs = reports_qs.filter(report_date__gte=date_from)
        if date_to:
            reports_qs = reports_qs.filter(report_date__lte=date_to)

    if date_from and period != 'custom':
        reports_qs = reports_qs.filter(report_date__gte=date_from)
    if date_to and period != 'custom':
        reports_qs = reports_qs.filter(report_date__lte=date_to)

    if status_filter:
        reports_qs = reports_qs.filter(status=status_filter)

    if query:
        reports_qs = reports_qs.filter(
            Q(work_done_today__icontains=query) |
            Q(reported_by_name__icontains=query) |
            Q(remarks__icontains=query)
        )

    # Aggregates for the filtered reports
    aggregates = reports_qs.aggregate(
        total_cost=Sum('total_site_cost'),
        total_manpower_cost=Sum('total_manpower_cost'),
        total_machinery_cost=Sum('total_machinery_cost'),
        total_employee_cost=Sum('total_employee_cost'),
        total_workers=Sum('total_manpower_count'),
    )

    total_cost = aggregates['total_cost'] or Decimal('0.00')
    total_manpower_cost = aggregates['total_manpower_cost'] or Decimal('0.00')
    total_machinery_cost = aggregates['total_machinery_cost'] or Decimal('0.00')
    total_employee_cost = aggregates['total_employee_cost'] or Decimal('0.00')
    total_workers = aggregates['total_workers'] or 0
    days_reported_count = reports_qs.count()

    # Monthly breakdown for this site (Year/Month aggregation)
    monthly_summary = (
        site.reports
        .values('report_date__year', 'report_date__month')
        .annotate(
            month_cost=Sum('total_site_cost'),
            month_workers=Sum('total_manpower_count'),
            reports_count=Count('id')
        )
        .order_by('-report_date__year', '-report_date__month')
    )

    user_profile = getattr(request.user, 'profile', None)
    is_admin = request.user.is_superuser or (user_profile and user_profile.is_admin)

    context = {
        'site': site,
        'reports': reports_qs,
        'total_cost': total_cost,
        'total_manpower_cost': total_manpower_cost,
        'total_machinery_cost': total_machinery_cost,
        'total_employee_cost': total_employee_cost,
        'total_workers': total_workers,
        'days_reported_count': days_reported_count,
        'monthly_summary': monthly_summary,
        'period': period,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': query,
        'status_filter': status_filter,
        'statuses': SiteReport.ReportStatus.choices,
        'is_admin': is_admin,
    }
    return render(request, 'reports/site_detail.html', context)


@login_required
@admin_required
def site_create_view(request):
    if request.method == 'POST':
        form = SiteForm(request.POST)
        if form.is_valid():
            site = form.save()
            messages.success(request, f"Site '{site.name}' added successfully.")
            return redirect('site_list')
    else:
        form = SiteForm()
    return render(request, 'master/site_form.html', {'form': form, 'title': 'Add New Site'})


@login_required
@admin_required
def site_edit_view(request, pk):
    site = get_object_or_404(Site, pk=pk)
    if request.method == 'POST':
        form = SiteForm(request.POST, instance=site)
        if form.is_valid():
            form.save()
            messages.success(request, f"Site '{site.name}' updated successfully.")
            return redirect('site_list')
    else:
        form = SiteForm(instance=site)
    return render(request, 'master/site_form.html', {'form': form, 'site': site, 'title': f'Edit Site: {site.name}'})


@login_required
@admin_required
def employee_list_view(request):
    employees = Employee.objects.annotate(visits_count=Count('site_visits')).all()
    return render(request, 'master/employee_list.html', {'employees': employees})


@login_required
@admin_required
def employee_create_view(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save()
            messages.success(request, f"Employee '{employee.name}' registered successfully.")
            return redirect('employee_list')
    else:
        form = EmployeeForm()
    return render(request, 'master/employee_form.html', {'form': form, 'title': 'Register New Employee'})


@login_required
@admin_required
def employee_edit_view(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, f"Employee '{employee.name}' updated successfully.")
            return redirect('employee_list')
    else:
        form = EmployeeForm(instance=employee)
    return render(request, 'master/employee_form.html', {'form': form, 'employee': employee, 'title': f'Edit Employee: {employee.name}'})


@login_required
@admin_required
def user_list_view(request):
    users = User.objects.select_related('profile').all().order_by('-date_joined')
    return render(request, 'master/user_list.html', {'users': users})


@login_required
@admin_required
def user_create_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        password = request.POST.get('password')
        role = request.POST.get('role', UserRole.SITE_ENGINEER)
        designation = request.POST.get('designation', '')
        phone = request.POST.get('phone', '')
        assigned_sites = request.POST.getlist('assigned_sites')

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already taken.")
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password or 'Vikas@123'
            )
            if role == UserRole.ADMIN:
                user.is_staff = True
                user.save(update_fields=['is_staff'])

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.designation = designation
            profile.phone = phone
            profile.save()
            if assigned_sites:
                profile.assigned_sites.set(assigned_sites)

            messages.success(request, f"User '{username}' created successfully.")
            return redirect('user_list')
    sites = Site.objects.all()
    return render(request, 'master/user_form.html', {
        'sites': sites,
        'roles': UserRole.choices,
        'title': 'Create New User'
    })


@login_required
@admin_required
def user_edit_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    if request.method == 'POST':
        target_user.first_name = request.POST.get('first_name', '')
        target_user.last_name = request.POST.get('last_name', '')
        target_user.email = request.POST.get('email', '')
        new_password = request.POST.get('password')
        if new_password:
            target_user.set_password(new_password)

        role = request.POST.get('role', profile.role)
        target_user.is_staff = (role == UserRole.ADMIN)
        target_user.save()

        profile.role = role
        profile.designation = request.POST.get('designation', '')
        profile.phone = request.POST.get('phone', '')
        profile.save()

        assigned_sites = request.POST.getlist('assigned_sites')
        profile.assigned_sites.set(assigned_sites)

        messages.success(request, f"User '{target_user.username}' updated successfully.")
        return redirect('user_list')

    sites = Site.objects.all()
    user_assigned_site_ids = list(profile.assigned_sites.values_list('id', flat=True))

    return render(request, 'master/user_form.html', {
        'target_user': target_user,
        'profile': profile,
        'sites': sites,
        'roles': UserRole.choices,
        'user_assigned_site_ids': user_assigned_site_ids,
        'title': f'Edit User: {target_user.username}'
    })


# -------------------------------------------------------------
# REST / JSON API ENDPOINTS FOR FRONTEND INTERACTIVITY
# -------------------------------------------------------------

@login_required
def api_employee_detail(request, pk):
    """Returns employee rates and designation for live autofill."""
    emp = get_object_or_404(Employee, pk=pk)
    return JsonResponse({
        'id': emp.id,
        'name': emp.name,
        'designation': emp.designation,
        'daily_rate': float(emp.daily_rate),
        'hourly_rate': float(emp.hourly_rate),
        'phone': emp.phone,
    })


@login_required
def api_check_duplicate_report(request):
    """
    Check if a report already exists for site_id and date.
    Returns {exists: bool, report_id: int|None}
    """
    site_id = request.GET.get('site_id')
    date_str = request.GET.get('date')
    exclude_id = request.GET.get('exclude_id')

    if not site_id or not date_str:
        return JsonResponse({'exists': False})

    qs = SiteReport.objects.filter(site_id=site_id, report_date=date_str)
    if exclude_id and exclude_id.isdigit():
        qs = qs.exclude(pk=int(exclude_id))

    exists = qs.exists()
    existing_rep = qs.first() if exists else None

    return JsonResponse({
        'exists': exists,
        'report_id': existing_rep.id if existing_rep else None,
        'status': existing_rep.get_status_display() if existing_rep else None,
    })


@login_required
def api_check_employee_visit(request):
    """
    Checks if an employee has already been allocated a visit on a date at other sites.
    """
    emp_id = request.GET.get('employee_id')
    date_str = request.GET.get('date')
    visit_type = request.GET.get('visit_type', VisitType.FULL_DAY)
    exclude_report_id = request.GET.get('exclude_report_id')

    if not emp_id or not date_str:
        return JsonResponse({'valid': True})

    other_visits = EmployeeSiteVisit.objects.filter(
        employee_id=emp_id,
        site_report__report_date=date_str
    )
    if exclude_report_id and exclude_report_id.isdigit():
        other_visits = other_visits.exclude(site_report_id=int(exclude_report_id))

    has_full_day = other_visits.filter(visit_type=VisitType.FULL_DAY).exists()
    half_day_count = other_visits.filter(visit_type=VisitType.HALF_DAY).count()

    valid = True
    msg = ""

    if visit_type == VisitType.FULL_DAY and (has_full_day or half_day_count > 0):
        valid = False
        sites_list = ", ".join([v.site_report.site.name for v in other_visits if v.visit_type in (VisitType.FULL_DAY, VisitType.HALF_DAY)])
        msg = f"Employee is already allocated on {date_str} at: {sites_list}. Cannot allocate Full Day again."
    elif visit_type == VisitType.HALF_DAY and (has_full_day or half_day_count >= 2):
        valid = False
        sites_list = ", ".join([v.site_report.site.name for v in other_visits if v.visit_type in (VisitType.FULL_DAY, VisitType.HALF_DAY)])
        msg = f"Employee has already reached daily allocation (1.0 day) on {date_str} at: {sites_list}."

    return JsonResponse({
        'valid': valid,
        'message': msg
    })


@login_required
def api_daily_report_summary(request):
    """
    JSON API called dynamically from Expense modals to cross-verify and autofill Daily Report data.
    """
    import datetime
    site_id = request.GET.get('site_id')
    site_name = request.GET.get('site_name')
    date_str = request.GET.get('date')

    if not date_str:
        return JsonResponse({'has_report': False, 'message': 'Date is required'})

    try:
        req_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'has_report': False, 'message': 'Invalid date format'})

    from expenses.models import ExpenseSite
    site = None
    if site_id and site_id.isdigit():
        exp_site = ExpenseSite.objects.filter(id=int(site_id)).first()
        if exp_site:
            site = Site.objects.filter(name__iexact=exp_site.name).first()
        if not site:
            site = Site.objects.filter(id=int(site_id)).first()

    if not site and site_name:
        site = Site.objects.filter(name__iexact=site_name.strip()).first()

    if not site:
        return JsonResponse({'has_report': False, 'message': 'Site not found'})

    report = SiteReport.objects.filter(site=site, report_date=req_date).first()
    if not report:
        return JsonResponse({
            'has_report': False,
            'site_name': site.name,
            'date': str(req_date),
            'message': f"No Daily Report found for {site.name} on {req_date}."
        })

    manpower_list = []
    for m in report.manpower_entries.all():
        manpower_list.append({
            'category': m.category,
            'type': m.type,
            'count': m.worker_count,
            'rate': float(m.rate_per_head),
            'total': float(m.total_cost),
        })

    machinery_list = []
    for mac in report.machinery_entries.all():
        machinery_list.append({
            'name': mac.machine_name,
            'basis': mac.billing_basis,
            'usage': float(mac.usage_value),
            'rate': float(mac.rate),
            'total': float(mac.rental_cost),
        })

    return JsonResponse({
        'has_report': True,
        'report_id': report.id,
        'site_name': site.name,
        'date': str(report.report_date),
        'work_done_today': report.work_done_today or '',
        'remarks': report.remarks or '',
        'total_workers': report.total_manpower_count,
        'manpower_cost': float(report.total_manpower_cost),
        'manpower_list': manpower_list,
        'total_machinery': report.machinery_entries.count(),
        'machinery_cost': float(report.total_rental_cost),
        'machinery_list': machinery_list,
        'total_site_cost': float(report.total_site_cost),
        'status': report.status,
    })


@login_required
def site_reconciliation_view(request):
    """
    Unified Site Expense vs Daily Report (DPR) Audit & Reconciliation View.
    Cross-checks whether daily reported work, labour count, and machinery match cash paid.
    """
    import datetime
    from expenses.models import CashTransaction, ExpenseSite, ExpenseCategory
    from django.db.models import Sum, Q

    selected_site_id = request.GET.get('site_id', '').strip()
    start_date_str = request.GET.get('start_date', '').strip()
    end_date_str = request.GET.get('end_date', '').strip()
    status_filter = request.GET.get('status', '').strip().upper()

    # Sites list
    report_sites = Site.objects.all().order_by('name')

    # Date defaults: last 30 days if not provided
    today = timezone.localdate()
    default_start = today - datetime.timedelta(days=30)
    try:
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else default_start
    except ValueError:
        start_date = default_start

    try:
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
    except ValueError:
        end_date = today

    # Query reports
    reports_qs = SiteReport.objects.filter(
        report_date__gte=start_date,
        report_date__lte=end_date
    ).select_related('site', 'reported_by_user')

    if selected_site_id and selected_site_id.isdigit():
        reports_qs = reports_qs.filter(site_id=int(selected_site_id))

    # Query cash transactions
    txns_qs = CashTransaction.objects.filter(
        transaction_date__gte=start_date,
        transaction_date__lte=end_date,
        txn_type=CashTransaction.TxnType.EXPENSE,
        site__isnull=False
    ).select_related('site', 'employee', 'category')

    if selected_site_id and selected_site_id.isdigit():
        site_obj = Site.objects.filter(id=int(selected_site_id)).first()
        if site_obj:
            exp_site_obj = ExpenseSite.objects.filter(name__iexact=site_obj.name).first()
            if exp_site_obj:
                txns_qs = txns_qs.filter(site=exp_site_obj)
            else:
                txns_qs = txns_qs.none()

    # Collect all unique (site_name_normalized, date) keys
    reconciliation_dict = {}

    for rep in reports_qs:
        key = (rep.site.name.strip().lower(), rep.report_date)
        reconciliation_dict[key] = {
            'site_name': rep.site.name,
            'date': rep.report_date,
            'report': rep,
            'dpr_work': rep.work_done_today or '',
            'dpr_workers': rep.total_manpower_count,
            'dpr_manpower_cost': rep.total_manpower_cost,
            'dpr_machines_count': rep.machinery_entries.count(),
            'dpr_machinery_cost': rep.total_rental_cost,
            'dpr_total_cost': rep.total_site_cost,
            'actual_labour_paid': Decimal('0.00'),
            'actual_machinery_paid': Decimal('0.00'),
            'actual_other_paid': Decimal('0.00'),
            'actual_total_paid': Decimal('0.00'),
            'cash_txns': [],
            'status': 'REPORT_ONLY',
        }

    for txn in txns_qs:
        key = (txn.site.name.strip().lower(), txn.transaction_date)
        if key not in reconciliation_dict:
            reconciliation_dict[key] = {
                'site_name': txn.site.name,
                'date': txn.transaction_date,
                'report': None,
                'dpr_work': '',
                'dpr_workers': 0,
                'dpr_manpower_cost': Decimal('0.00'),
                'dpr_machines_count': 0,
                'dpr_machinery_cost': Decimal('0.00'),
                'dpr_total_cost': Decimal('0.00'),
                'actual_labour_paid': Decimal('0.00'),
                'actual_machinery_paid': Decimal('0.00'),
                'actual_other_paid': Decimal('0.00'),
                'actual_total_paid': Decimal('0.00'),
                'cash_txns': [],
                'status': 'EXPENSE_WITHOUT_REPORT',
            }

        item = reconciliation_dict[key]
        item['cash_txns'].append(txn)
        item['actual_total_paid'] += txn.amount

        # Categorize
        grp = txn.category.group_type if txn.category else ''
        part = (txn.particulars or '').lower()
        if grp == ExpenseCategory.GroupType.LABOUR or 'labour' in part or 'majdoor' in part or 'mason' in part or 'mistri' in part:
            item['actual_labour_paid'] += txn.amount
        elif grp in [ExpenseCategory.GroupType.MACHINERY, ExpenseCategory.GroupType.VEHICLE] or 'machin' in part or 'diesel' in part or 'fuel' in part or 'jcb' in part:
            item['actual_machinery_paid'] += txn.amount
        else:
            item['actual_other_paid'] += txn.amount

    # Classify status & calculate variances
    records = []
    tot_dpr_cost = Decimal('0.00')
    tot_cash_spent = Decimal('0.00')
    count_matched = 0
    count_discrepancy = 0
    count_expense_no_report = 0
    count_report_no_expense = 0

    for key, item in reconciliation_dict.items():
        has_rep = item['report'] is not None
        has_cash = len(item['cash_txns']) > 0

        tot_dpr_cost += item['dpr_total_cost']
        tot_cash_spent += item['actual_total_paid']

        variance = item['actual_total_paid'] - item['dpr_total_cost']
        item['total_variance'] = variance
        item['labour_diff'] = item['actual_labour_paid'] - item['dpr_manpower_cost']
        item['machinery_diff'] = item['actual_machinery_paid'] - item['dpr_machinery_cost']

        if has_rep and has_cash:
            if abs(variance) < Decimal('1.00'):
                item['status'] = 'MATCHED'
                count_matched += 1
            else:
                item['status'] = 'VARIANCE'
                count_discrepancy += 1
        elif has_rep and not has_cash:
            item['status'] = 'REPORT_ONLY'
            count_report_no_expense += 1
        else:
            item['status'] = 'EXPENSE_WITHOUT_REPORT'
            count_expense_no_report += 1

        if not status_filter or item['status'] == status_filter:
            records.append(item)

    # Sort chronologically descending
    records.sort(key=lambda x: (x['date'], x['site_name']), reverse=True)

    context = {
        'records': records,
        'report_sites': report_sites,
        'selected_site_id': selected_site_id,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'status_filter': status_filter,
        'tot_dpr_cost': tot_dpr_cost,
        'tot_cash_spent': tot_cash_spent,
        'net_variance': tot_cash_spent - tot_dpr_cost,
        'count_matched': count_matched,
        'count_discrepancy': count_discrepancy,
        'count_expense_no_report': count_expense_no_report,
        'count_report_no_expense': count_report_no_expense,
        'page_title': 'Site Expense & Daily Report Audit Reconciliation',
    }
    return render(request, 'reports/site_reconciliation.html', context)


# -------------------------------------------------------------
# MATERIAL INWARD & PURCHASE REGISTER VIEWS
# -------------------------------------------------------------

@login_required
def material_list_view(request):
    """
    Lists all material inward and purchase records with filters, KPI stats and pagination.
    """
    site_id = request.GET.get('site_id', '').strip()
    party = request.GET.get('party', '').strip()
    material = request.GET.get('material', '').strip()
    mode = request.GET.get('mode', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    q = request.GET.get('q', '').strip()

    qs = MaterialPurchase.objects.select_related('site', 'created_by').all()

    if site_id and site_id.isdigit():
        qs = qs.filter(site_id=int(site_id))

    if party:
        qs = qs.filter(party_name__icontains=party)

    if material:
        qs = qs.filter(material_name__icontains=material)

    if mode:
        qs = qs.filter(payment_mode=mode)

    if date_from:
        try:
            d_from = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(material_date__gte=d_from)
        except ValueError:
            pass

    if date_to:
        try:
            d_to = datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(material_date__lte=d_to)
        except ValueError:
            pass

    if q:
        qs = qs.filter(
            Q(material_name__icontains=q) |
            Q(party_name__icontains=q) |
            Q(bill_no__icontains=q) |
            Q(purchased_by__icontains=q) |
            Q(payment_by__icontains=q) |
            Q(site_name_text__icontains=q) |
            Q(site__name__icontains=q) |
            Q(remark__icontains=q)
        )

    # Compute KPI totals before pagination
    total_count = qs.count()
    aggregates = qs.aggregate(
        tot_net=Sum('net_amount'),
        tot_taxable=Sum('taxable_value'),
        tot_gst=Sum('total_gst'),
    )
    total_net = aggregates['tot_net'] or Decimal('0.00')
    total_taxable = aggregates['tot_taxable'] or Decimal('0.00')
    total_gst = aggregates['tot_gst'] or Decimal('0.00')

    # Pending credit purchases (where payment date is null or mode is CREDIT)
    credit_pending = qs.filter(
        Q(payment_mode=MaterialPaymentMode.CREDIT) | Q(payment_date__isnull=True)
    ).aggregate(s=Sum('net_amount'))['s'] or Decimal('0.00')

    # Suggestions for filters
    all_sites = Site.objects.all().order_by('name')
    distinct_materials = MaterialPurchase.objects.values_list('material_name', flat=True).distinct()[:25]
    distinct_parties = MaterialPurchase.objects.exclude(party_name__in=['', 'N/A']).values_list('party_name', flat=True).distinct()[:25]

    paginator = Paginator(qs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'materials': page_obj.object_list,
        'total_count': total_count,
        'total_net': total_net,
        'total_taxable': total_taxable,
        'total_gst': total_gst,
        'credit_pending': credit_pending,
        'all_sites': all_sites,
        'distinct_materials': distinct_materials,
        'distinct_parties': distinct_parties,
        'selected_site': site_id,
        'selected_party': party,
        'selected_material': material,
        'selected_mode': mode,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': q,
        'page_title': 'Material Inward & Purchases Register',
    }
    return render(request, 'reports/material_list.html', context)


@login_required
def material_create_view(request):
    """
    Renders material entry form and handles saving new record.
    """
    if request.method == 'POST':
        form = MaterialPurchaseForm(request.POST)
        if form.is_valid():
            mat = form.save(commit=False)
            mat.created_by = request.user
            mat.save()
            messages.success(request, f"Material purchase of {mat.material_name} (₹{mat.net_amount:,.2f}) recorded successfully!")
            return redirect('material_list')
        else:
            messages.error(request, "Please correct the errors in the form below.")
    else:
        initial = {'material_date': timezone.localdate()}
        site_id = request.GET.get('site_id')
        if site_id and site_id.isdigit():
            initial['site'] = int(site_id)
        form = MaterialPurchaseForm(initial=initial)

    # Suggestion lists for datalists
    materials_list = MaterialPurchase.objects.values_list('material_name', flat=True).distinct()[:30]
    parties_list = MaterialPurchase.objects.exclude(party_name__in=['', 'N/A']).values_list('party_name', flat=True).distinct()[:30]
    units_list = ['FT', 'CFT', 'KG', 'TON', 'BAGS', 'PC', 'NOS', 'LTR', 'SQFT', 'MTR', 'TRIP']
    staff_list = Employee.objects.filter(is_active=True).values_list('name', flat=True)[:30]

    return render(request, 'reports/material_form.html', {
        'form': form,
        'is_edit': False,
        'materials_list': materials_list,
        'parties_list': parties_list,
        'units_list': units_list,
        'staff_list': staff_list,
        'page_title': 'Add Material Inward / Purchase Entry',
    })


@login_required
def material_edit_view(request, pk):
    """
    Handles editing existing material purchase record.
    """
    mat = get_object_or_404(MaterialPurchase, pk=pk)

    if request.method == 'POST':
        form = MaterialPurchaseForm(request.POST, instance=mat)
        if form.is_valid():
            form.save()
            messages.success(request, f"Updated material purchase record for {mat.material_name} successfully.")
            return redirect('material_list')
        else:
            messages.error(request, "Please correct the errors in the form below.")
    else:
        form = MaterialPurchaseForm(instance=mat)

    materials_list = MaterialPurchase.objects.values_list('material_name', flat=True).distinct()[:30]
    parties_list = MaterialPurchase.objects.exclude(party_name__in=['', 'N/A']).values_list('party_name', flat=True).distinct()[:30]
    units_list = ['FT', 'CFT', 'KG', 'TON', 'BAGS', 'PC', 'NOS', 'LTR', 'SQFT', 'MTR', 'TRIP']
    staff_list = Employee.objects.filter(is_active=True).values_list('name', flat=True)[:30]

    return render(request, 'reports/material_form.html', {
        'form': form,
        'material': mat,
        'is_edit': True,
        'materials_list': materials_list,
        'parties_list': parties_list,
        'units_list': units_list,
        'staff_list': staff_list,
        'page_title': f'Edit Material Purchase: {mat.material_name}',
    })


@login_required
def material_delete_view(request, pk):
    """
    Deletes material purchase entry.
    """
    mat = get_object_or_404(MaterialPurchase, pk=pk)
    if request.method == 'POST':
        name = mat.material_name
        amt = mat.net_amount
        mat.delete()
        messages.success(request, f"Material purchase of {name} (₹{amt:,.2f}) deleted successfully.")
        return redirect('material_list')

    return render(request, 'reports/material_confirm_delete.html', {'material': mat})


@login_required
def material_export_excel_view(request):
    """
    Exports filtered material purchases to Excel (.xlsx) matching exact spreadsheet columns.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    site_id = request.GET.get('site_id', '').strip()
    party = request.GET.get('party', '').strip()
    material = request.GET.get('material', '').strip()
    mode = request.GET.get('mode', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    q = request.GET.get('q', '').strip()

    qs = MaterialPurchase.objects.select_related('site').all()

    if site_id and site_id.isdigit():
        qs = qs.filter(site_id=int(site_id))
    if party:
        qs = qs.filter(party_name__icontains=party)
    if material:
        qs = qs.filter(material_name__icontains=material)
    if mode:
        qs = qs.filter(payment_mode=mode)
    if date_from:
        try:
            d_from = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(material_date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(material_date__lte=d_to)
        except ValueError:
            pass
    if q:
        qs = qs.filter(
            Q(material_name__icontains=q) |
            Q(party_name__icontains=q) |
            Q(bill_no__icontains=q) |
            Q(purchased_by__icontains=q) |
            Q(payment_by__icontains=q) |
            Q(site_name_text__icontains=q) |
            Q(site__name__icontains=q)
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MATERIAL REGISTER"

    headers = [
        "Site name", "Material Date", "Payment Date", "PARTY NAME", "MATERIAL NAME",
        "BILL.NO.", "PURCHSED BY", "PAYMENT BY", "CASH/CREDIT/ CHEQUE.",
        "QUANTITY", "MEASURING UNIT", "RATE", "TAXABLE VALUE",
        "CGST", "UTGST/SGST", "IGST", "TOTAL GST", "NET AMOUNT", "Remark"
    ]

    header_font = Font(name="Calibri", size=10, bold=True, color="000000")
    header_fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    date_header_fill = PatternFill(start_color="BDD7EE", end_color="BDD7EE", fill_type="solid") # Soft blue matching screenshot
    net_header_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid") # Soft orange matching screenshot
    thin_border = Border(
        left=Side(style='thin', color='B0B0B0'),
        right=Side(style='thin', color='B0B0B0'),
        top=Side(style='thin', color='B0B0B0'),
        bottom=Side(style='thin', color='B0B0B0')
    )

    ws.append(headers)
    for col_idx, col_name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
        if col_name in ["Material Date", "Payment Date"]:
            cell.fill = date_header_fill
        elif col_name == "NET AMOUNT":
            cell.fill = net_header_fill
        else:
            cell.fill = header_fill

    ws.row_dimensions[1].height = 28

    data_font = Font(name="Calibri", size=10)
    for m in qs:
        row_vals = [
            m.site_name_display,
            m.material_date.strftime("%d.%m.%Y") if m.material_date else "",
            m.payment_date.strftime("%d.%m.%Y") if m.payment_date else "",
            m.party_name or "N/A",
            m.material_name,
            m.bill_no or "N/A",
            m.purchased_by or "",
            m.payment_by or "",
            m.payment_mode,
            float(m.quantity) if m.quantity else 0,
            m.measuring_unit,
            float(m.rate) if m.rate else 0,
            float(m.taxable_value) if m.taxable_value else 0,
            float(m.cgst) if m.cgst else "",
            float(m.sgst) if m.sgst else "",
            float(m.igst) if m.igst else "",
            float(m.total_gst) if m.total_gst else "",
            float(m.net_amount) if m.net_amount else 0,
            m.remark or "",
        ]
        ws.append(row_vals)
        cur_row = ws.max_row
        ws.row_dimensions[cur_row].height = 20
        for col_idx in range(1, len(headers) + 1):
            c = ws.cell(row=cur_row, column=col_idx)
            c.font = data_font
            c.border = thin_border
            if headers[col_idx-1] == "NET AMOUNT":
                c.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
                c.number_format = '#,##0.00'
            elif headers[col_idx-1] in ["RATE", "TAXABLE VALUE", "CGST", "UTGST/SGST", "IGST", "TOTAL GST"]:
                if c.value != "":
                    c.number_format = '#,##0.00'

    # Auto-fit column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    today_str = timezone.localdate().strftime('%d-%m-%Y')
    response['Content-Disposition'] = f'attachment; filename="Material_Register_{today_str}.xlsx"'
    wb.save(response)
    return response


