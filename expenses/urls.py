from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    # Dashboard & Ledgers
    path('', views.expense_dashboard_view, name='dashboard'),
    path('ledgers/', views.ledger_list_view, name='ledger_list'),
    path('ledger/<int:emp_id>/', views.employee_ledger_view, name='employee_ledger'),
    
    # Transaction Actions
    path('ledger/<int:emp_id>/cash-in/', views.add_cash_in_view, name='add_cash_in'),
    path('ledger/<int:emp_id>/expense/', views.add_expense_view, name='add_expense'),
    path('ledger/<int:emp_id>/cash-out/', views.add_cash_out_view, name='add_cash_out'),
    path('transfer/', views.add_transfer_view, name='add_transfer'),
    path('transfers/', views.transfers_list_view, name='transfers_list'),
    path('transaction/<int:txn_id>/delete/', views.delete_transaction_view, name='delete_transaction'),
    
    # Reports
    path('sites/', views.site_reports_view, name='site_reports'),
    path('categories/', views.category_reports_view, name='category_reports'),
    
    # Exports
    path('ledger/<int:emp_id>/export/', views.export_ledger_excel_view, name='export_ledger_excel'),
    path('export/consolidated/', views.export_consolidated_excel_view, name='export_consolidated_excel'),
]
