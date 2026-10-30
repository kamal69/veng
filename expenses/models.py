import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class ExpenseSite(models.Model):
    """Normalized construction site / location for expense allocation."""
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ExpenseCategory(models.Model):
    """Normalized category for expense classification."""
    class GroupType(models.TextChoices):
        LABOUR = 'LABOUR', 'Labour & Masonry'
        MACHINERY = 'MACHINERY', 'Machinery & Equipment'
        VEHICLE = 'VEHICLE', 'Fuel & Vehicle Running'
        MATERIAL = 'MATERIAL', 'Material & Hardware'
        FOOD = 'FOOD', 'Food & Refreshments'
        OFFICE = 'OFFICE', 'Office & Stamp Duty'
        FREIGHT = 'FREIGHT', 'Freight & Carriage'
        TRAVELLING = 'TRAVELLING', 'Travelling'
        CONTRACTOR = 'CONTRACTOR', 'Contractor Payments'
        SALARY = 'SALARY', 'Advance Salary'
        HOME = 'HOME', 'Home / Personal'
        MISC = 'MISC', 'Miscellaneous'

    name = models.CharField(max_length=150, unique=True)
    group_type = models.CharField(max_length=30, choices=GroupType.choices, default=GroupType.MISC)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Expense Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_expense_head(self):
        """Returns standard high-level head: 'LABOUR', 'MACHINERY', or 'OTHER'."""
        name_l = self.name.lower()
        if self.group_type == self.GroupType.LABOUR or 'labour' in name_l or 'mason' in name_l:
            return 'LABOUR'
        elif self.group_type in [self.GroupType.MACHINERY, self.GroupType.VEHICLE] or 'machin' in name_l or 'diesel' in name_l or 'fuel' in name_l or 'vehicle' in name_l or 'oil' in name_l or 'petrol' in name_l:
            return 'MACHINERY'
        else:
            return 'OTHER'


class CashEmployee(models.Model):
    """Employee holding company cash and maintaining individual expense ledger."""
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cash_account')
    name = models.CharField(max_length=120, unique=True)
    employee_code = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    designation = models.CharField(max_length=120, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    cached_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def recalculate_balance(self, save=True):
        """
        Calculates employee current balance:
        Opening Balance + Total Cash In - Total Expenses - Total Cash Out
        """
        # Sum opening balances
        op_bal = self.opening_balances.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        # Total Cash In (direct cash in + incoming transfers)
        cash_in = self.transactions.filter(
            txn_type__in=[CashTransaction.TxnType.CASH_IN, CashTransaction.TxnType.TRANSFER_IN]
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        # Total Expenses
        expenses = self.transactions.filter(
            txn_type=CashTransaction.TxnType.EXPENSE
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        # Total Cash Out (direct cash out to external persons + outgoing transfers)
        cash_out = self.transactions.filter(
            txn_type__in=[CashTransaction.TxnType.CASH_OUT, CashTransaction.TxnType.TRANSFER_OUT]
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

        closing = op_bal + cash_in - expenses - cash_out
        self.cached_balance = closing
        if save:
            self.save(update_fields=['cached_balance'])
        return closing

    def get_expense_breakdown(self, start_date=None, end_date=None):
        """
        Returns breakdown of actual expenses spent by this employee:
        - labour: total INR spent on Labour (wages, masonry, labour payments)
        - machinery: total INR spent on Machinery & Equipment / Fuel / Vehicles
        - other: total INR spent on Other Charges (materials, site office, etc.)
        - total_expenses: total expenses
        - cash_received: total cash inflow + transfers in
        - balance: current balance
        """
        exp_qs = self.transactions.filter(txn_type=CashTransaction.TxnType.EXPENSE)
        if start_date:
            exp_qs = exp_qs.filter(transaction_date__gte=start_date)
        if end_date:
            exp_qs = exp_qs.filter(transaction_date__lte=end_date)

        labour_qs = exp_qs.filter(
            models.Q(category__group_type=ExpenseCategory.GroupType.LABOUR) |
            models.Q(particulars__icontains='labour') |
            models.Q(particulars__icontains='majdoor')
        )
        labour_sum = labour_qs.aggregate(s=models.Sum('amount'))['s'] or Decimal('0.00')

        machinery_qs = exp_qs.filter(
            models.Q(category__group_type__in=[ExpenseCategory.GroupType.MACHINERY, ExpenseCategory.GroupType.VEHICLE]) |
            models.Q(particulars__icontains='machin') |
            models.Q(particulars__icontains='diesel') |
            models.Q(particulars__icontains='jcb')
        ).exclude(id__in=labour_qs.values_list('id', flat=True))
        machinery_sum = machinery_qs.aggregate(s=models.Sum('amount'))['s'] or Decimal('0.00')

        total_exp = exp_qs.aggregate(s=models.Sum('amount'))['s'] or Decimal('0.00')
        other_sum = total_exp - labour_sum - machinery_sum
        if other_sum < Decimal('0.00'):
            other_sum = Decimal('0.00')

        cash_in_sum = self.transactions.filter(
            txn_type__in=[CashTransaction.TxnType.CASH_IN, CashTransaction.TxnType.TRANSFER_IN]
        ).aggregate(s=models.Sum('amount'))['s'] or Decimal('0.00')

        return {
            'labour': labour_sum,
            'machinery': machinery_sum,
            'other': other_sum,
            'total_expenses': total_exp,
            'cash_received': cash_in_sum,
            'balance': self.cached_balance,
        }


class OpeningBalance(models.Model):
    """Opening cash balance for an employee at start of a financial period."""
    employee = models.ForeignKey(CashEmployee, on_delete=models.CASCADE, related_name='opening_balances')
    financial_year = models.CharField(max_length=20, default='2026-27')
    amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Can be negative if employee is in debit")
    effective_date = models.DateField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ('employee', 'financial_year')
        ordering = ['effective_date']

    def __str__(self):
        return f"{self.employee.name} - {self.financial_year}: {self.amount}"


class CashTransaction(models.Model):
    """Central ledger for all employee cash movements, expenses, and transfers."""
    class TxnType(models.TextChoices):
        CASH_IN = 'CASH_IN', 'Cash In / Received'
        EXPENSE = 'EXPENSE', 'Site / Office Expense'
        CASH_OUT = 'CASH_OUT', 'Cash Out / External Payment'
        TRANSFER_OUT = 'TRANSFER_OUT', 'Transfer Out (To Employee)'
        TRANSFER_IN = 'TRANSFER_IN', 'Transfer In (From Employee)'

    transaction_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    transaction_date = models.DateField(db_index=True)
    employee = models.ForeignKey(CashEmployee, on_delete=models.CASCADE, related_name='transactions', db_index=True)
    txn_type = models.CharField(max_length=20, choices=TxnType.choices, db_index=True)
    
    # Financial amount (always positive in record; sign is determined by txn_type)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    
    # Cash In details
    cash_in_source = models.CharField(max_length=255, blank=True, null=True, help_text="e.g. VEW ATM, Bipin Kumar, Bank")
    
    # Expense details
    site = models.ForeignKey(ExpenseSite, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    particulars = models.TextField(blank=True, help_text="Description of work, item or payment")
    voucher_no = models.CharField(max_length=100, blank=True, help_text="Voucher / Bill number if applicable")
    
    # Cash Out / Transfer details
    cash_out_recipient = models.CharField(max_length=255, blank=True, null=True, help_text="Recipient name or vendor")
    linked_employee = models.ForeignKey(
        CashEmployee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='linked_transactions',
        help_text="If expense or cash was given to another employee, links to their account"
    )
    
    # Running balance snapshot (calculated chronologically)
    running_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    
    # Excel provenance (for audit against original EMP EXP 26-27.xlsx)
    excel_sheet_ref = models.CharField(max_length=50, blank=True)
    excel_row_ref = models.IntegerField(null=True, blank=True)
    
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['transaction_date', 'id']
        indexes = [
            models.Index(fields=['employee', 'transaction_date']),
            models.Index(fields=['site', 'transaction_date']),
            models.Index(fields=['category', 'transaction_date']),
            models.Index(fields=['txn_type', 'transaction_date']),
        ]

    def __str__(self):
        return f"{self.transaction_date} | {self.employee.name} | {self.txn_type} | ₹{self.amount:,.2f}"

    @property
    def expense_head(self):
        """Categorizes expense into 'LABOUR', 'MACHINERY', or 'OTHER'."""
        if self.category:
            return self.category.get_expense_head()
        txt = (self.particulars or '').lower()
        if 'labour' in txt or 'majdoor' in txt or 'beldar' in txt or 'mason' in txt:
            return 'LABOUR'
        if 'machin' in txt or 'diesel' in txt or 'fuel' in txt or 'jcb' in txt or 'crane' in txt:
            return 'MACHINERY'
        return 'OTHER'


class EmployeeTransfer(models.Model):
    """
    Linked transfer between two employees.
    Automatically generates:
      1. TRANSFER_OUT transaction in sender's ledger (Debit)
      2. TRANSFER_IN transaction in receiver's ledger (Credit)
    """
    sender = models.ForeignKey(CashEmployee, on_delete=models.CASCADE, related_name='transfers_sent')
    receiver = models.ForeignKey(CashEmployee, on_delete=models.CASCADE, related_name='transfers_received')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    transfer_date = models.DateField(default=timezone.now)
    payment_mode = models.CharField(max_length=80, default='Paytm', help_text="Paytm, Cash, ATM, Bank Transfer, UPI")
    reference_no = models.CharField(max_length=120, blank=True)
    remarks = models.TextField(blank=True)
    
    debit_transaction = models.OneToOneField(
        CashTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfer_out_parent'
    )
    credit_transaction = models.OneToOneField(
        CashTransaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfer_in_parent'
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transfer ₹{self.amount:,.2f}: {self.sender.name} -> {self.receiver.name} on {self.transfer_date}"


class ExpenseAuditLog(models.Model):
    """Audit log tracking creates, edits, and deletions."""
    action = models.CharField(max_length=50)
    employee = models.ForeignKey(CashEmployee, on_delete=models.SET_NULL, null=True, blank=True)
    transaction = models.ForeignKey(CashTransaction, on_delete=models.SET_NULL, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.action} by {self.user}"
