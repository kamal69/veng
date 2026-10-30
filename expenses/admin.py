from django.contrib import admin
from .models import (
    CashEmployee, OpeningBalance, ExpenseSite, ExpenseCategory,
    CashTransaction, EmployeeTransfer, ExpenseAuditLog
)


class OpeningBalanceInline(admin.TabularInline):
    model = OpeningBalance
    extra = 1


@admin.register(CashEmployee)
class CashEmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'designation', 'phone', 'cached_balance', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'designation', 'phone', 'upi_id')
    inlines = [OpeningBalanceInline]


@admin.register(ExpenseSite)
class ExpenseSiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'location', 'is_active', 'created_at')
    search_fields = ('name', 'code', 'location')
    list_filter = ('is_active',)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'group_type', 'is_active')
    list_filter = ('group_type', 'is_active')
    search_fields = ('name',)


@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_date', 'employee', 'txn_type', 'amount', 'site', 'category', 'running_balance')
    list_filter = ('txn_type', 'transaction_date', 'employee', 'site', 'category')
    search_fields = ('particulars', 'cash_in_source', 'cash_out_recipient', 'voucher_no')
    date_hierarchy = 'transaction_date'


@admin.register(EmployeeTransfer)
class EmployeeTransferAdmin(admin.ModelAdmin):
    list_display = ('transfer_date', 'sender', 'receiver', 'amount', 'payment_mode', 'reference_no')
    list_filter = ('payment_mode', 'transfer_date', 'sender', 'receiver')
    search_fields = ('reference_no', 'remarks')


@admin.register(ExpenseAuditLog)
class ExpenseAuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'action', 'employee', 'user')
    list_filter = ('action', 'timestamp')
