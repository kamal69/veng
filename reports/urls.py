from django.urls import path
from . import views

urlpatterns = [
    # Dashboard & Root
    path('', views.dashboard_view, name='dashboard'),

    # Daily Site Reports
    path('reports/', views.report_list_view, name='report_list'),
    path('reports/new/', views.report_create_view, name='report_create'),
    path('reports/<int:pk>/', views.report_detail_view, name='report_detail'),
    path('reports/<int:pk>/edit/', views.report_edit_view, name='report_edit'),
    path('reports/<int:pk>/submit/', views.report_submit_view, name='report_submit'),
    path('reports/<int:pk>/approve/', views.report_approve_view, name='report_approve'),
    path('reports/<int:pk>/return/', views.report_return_view, name='report_return'),
    path('reports/<int:pk>/delete/', views.report_delete_view, name='report_delete'),
    path('reports/<int:pk>/print/', views.report_print_view, name='report_print'),
    path('reports/<int:pk>/excel/', views.report_excel_export_view, name='report_excel_export'),
    path('reports/export/excel/', views.reports_bulk_excel_export_view, name='reports_bulk_excel_export'),

    # Material Purchases & Procurement Register
    path('materials/', views.material_list_view, name='material_list'),
    path('materials/new/', views.material_create_view, name='material_create'),
    path('materials/<int:pk>/edit/', views.material_edit_view, name='material_edit'),
    path('materials/<int:pk>/delete/', views.material_delete_view, name='material_delete'),
    path('materials/export/excel/', views.material_export_excel_view, name='material_export_excel'),

    # Master Data: Sites & Site Work History
    path('sites/<int:pk>/', views.site_detail_view, name='site_detail'),
    path('master/sites/', views.site_list_view, name='site_list'),
    path('master/sites/new/', views.site_create_view, name='site_create'),
    path('master/sites/<int:pk>/', views.site_detail_view, name='site_detail_alt'),
    path('master/sites/<int:pk>/edit/', views.site_edit_view, name='site_edit'),

    # Master Data: Employees
    path('master/employees/', views.employee_list_view, name='employee_list'),
    path('master/employees/new/', views.employee_create_view, name='employee_create'),
    path('master/employees/<int:pk>/edit/', views.employee_edit_view, name='employee_edit'),

    # Master Data: Users & Roles
    path('master/users/', views.user_list_view, name='user_list'),
    path('master/users/new/', views.user_create_view, name='user_create'),
    path('master/users/<int:pk>/edit/', views.user_edit_view, name='user_edit'),

    # Profile
    path('profile/', views.profile_view, name='profile'),

    # Site Expense & Daily Report Audit Reconciliation
    path('audit/reconciliation/', views.site_reconciliation_view, name='site_reconciliation'),

    # JSON APIs for frontend dynamic calculations and checks
    path('api/employees/<int:pk>/', views.api_employee_detail, name='api_employee_detail'),
    path('api/check-duplicate-report/', views.api_check_duplicate_report, name='api_check_duplicate_report'),
    path('api/check-employee-visit/', views.api_check_employee_visit, name='api_check_employee_visit'),
    path('api/daily-report-summary/', views.api_daily_report_summary, name='api_daily_report_summary'),
]
