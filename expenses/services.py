from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.utils import timezone
from .models import (
    CashEmployee, OpeningBalance, ExpenseSite, ExpenseCategory,
    CashTransaction, EmployeeTransfer, ExpenseAuditLog
)


class AccountingService:
    """Core accounting engine for Employee Cash & Expense Management."""

    @staticmethod
    def get_or_create_site(site_name):
        """Normalizes and gets or creates an ExpenseSite."""
        if not site_name or not str(site_name).strip():
            return None
        cleaned = str(site_name).strip()
        # Normalization alias mapping
        mapping = {
            'rock rose sec 20 chd': 'Rock Rose Sector 20 Chandigarh',
            'rock rose sec 20 chandigarh': 'Rock Rose Sector 20 Chandigarh',
            'rock rose': 'Rock Rose Sector 20 Chandigarh',
            'tepla': 'Tepla Project',
            'vrk': 'VRK Banquet',
            'vrk banquet': 'VRK Banquet',
            'mohinder , lalru': 'Mohinder, Lalru',
            'mohindar ,lalru': 'Mohinder, Lalru',
            'vikas engg': 'Vikas Engg (Head Office)',
            'vikas engg (store)': 'Vikas Engg (Store)',
            'birumal jairam amloh': 'Birumal Jairam, Amloh',
            'guru teg bahadur, anandpur sahib': 'Guru Teg Bahadur, Anandpur Sahib',
            'home': 'Home / Office Management',
        }
        canonical = mapping.get(cleaned.lower(), cleaned)
        site, _ = ExpenseSite.objects.get_or_create(name=canonical)
        return site

    @staticmethod
    def get_or_create_category(cat_name):
        """Normalizes and gets or creates an ExpenseCategory."""
        if not cat_name or not str(cat_name).strip():
            return None
        cleaned = str(cat_name).strip()
        mapping = {
            'vech. running & maint.': ('Vehicle Running & Maintenance', ExpenseCategory.GroupType.VEHICLE),
            'veh. running & maint.': ('Vehicle Running & Maintenance', ExpenseCategory.GroupType.VEHICLE),
            'veh running & maint.': ('Vehicle Running & Maintenance', ExpenseCategory.GroupType.VEHICLE),
            'petrol': ('Petrol / Fuel', ExpenseCategory.GroupType.VEHICLE),
            'diesel for machinary': ('Diesel for Machinery', ExpenseCategory.GroupType.VEHICLE),
            'misc. exp': ('Miscellaneous Expenses', ExpenseCategory.GroupType.MISC),
            'misc exp.': ('Miscellaneous Expenses', ExpenseCategory.GroupType.MISC),
            'other exp.': ('Miscellaneous Expenses', ExpenseCategory.GroupType.MISC),
            'labour': ('Labour Payments', ExpenseCategory.GroupType.LABOUR),
            'masson': ('Masonry Payments', ExpenseCategory.GroupType.LABOUR),
            'travelling': ('Travelling Expenses', ExpenseCategory.GroupType.TRAVELLING),
            'material purchase': ('Material Purchase', ExpenseCategory.GroupType.MATERIAL),
            'freight': ('Freight & Carriage', ExpenseCategory.GroupType.FREIGHT),
            'food': ('Food & Refreshment', ExpenseCategory.GroupType.FOOD),
            'contractor pay': ('Contractor Payments', ExpenseCategory.GroupType.CONTRACTOR),
            'employee salary': ('Advance Salary / Personal', ExpenseCategory.GroupType.SALARY),
            'office exp.': ('Office Expenses & Stamp Duty', ExpenseCategory.GroupType.OFFICE),
            'home': ('Home / Personal Advance', ExpenseCategory.GroupType.HOME),
        }
        entry = mapping.get(cleaned.lower())
        if entry:
            canonical, group = entry
        else:
            canonical, group = cleaned, ExpenseCategory.GroupType.MISC

        cat, _ = ExpenseCategory.objects.get_or_create(
            name=canonical,
            defaults={'group_type': group}
        )
        return cat

    @classmethod
    @transaction.atomic
    def recalculate_employee_ledger(cls, employee):
        """
        Recalculates chronological running balances for an employee's ledger.
        Formula:
          Previous Balance + Cash In (or Transfer In) - Expenses - Cash Out (or Transfer Out)
        """
        # Get opening balance (earliest or 2026-27)
        op_obj = employee.opening_balances.first()
        current_bal = op_obj.amount if op_obj else Decimal('0.00')

        txns = list(employee.transactions.all().order_by('transaction_date', 'id'))
        for txn in txns:
            if txn.txn_type in (CashTransaction.TxnType.CASH_IN, CashTransaction.TxnType.TRANSFER_IN):
                current_bal += txn.amount
            elif txn.txn_type in (CashTransaction.TxnType.EXPENSE, CashTransaction.TxnType.CASH_OUT, CashTransaction.TxnType.TRANSFER_OUT):
                current_bal -= txn.amount
            txn.running_balance = current_bal

        if txns:
            CashTransaction.objects.bulk_update(txns, ['running_balance'], batch_size=500)

        employee.cached_balance = current_bal
        employee.save(update_fields=['cached_balance'])
        return current_bal

    @classmethod
    @transaction.atomic
    def create_cash_in(cls, employee, amount, date, source="", remarks="", user=None):
        """Records cash received from company, ATM, or bank."""
        amount = Decimal(str(amount))
        txn = CashTransaction.objects.create(
            employee=employee,
            transaction_date=date,
            txn_type=CashTransaction.TxnType.CASH_IN,
            amount=amount,
            cash_in_source=source,
            remarks=remarks,
            created_by=user
        )
        cls.recalculate_employee_ledger(employee)
        ExpenseAuditLog.objects.create(
            employee=employee, transaction=txn, action='CASH_IN_CREATED',
            user=user, notes=f"Recorded Cash In ₹{amount:,.2f} from {source}"
        )
        return txn

    @classmethod
    @transaction.atomic
    def create_expense(cls, employee, amount, date, site=None, category=None, particulars="", voucher_no="", remarks="", user=None):
        """Records an actual site or office expense."""
        amount = Decimal(str(amount))
        txn = CashTransaction.objects.create(
            employee=employee,
            transaction_date=date,
            txn_type=CashTransaction.TxnType.EXPENSE,
            amount=amount,
            site=site,
            category=category,
            particulars=particulars,
            voucher_no=voucher_no,
            remarks=remarks,
            created_by=user
        )
        cls.recalculate_employee_ledger(employee)
        ExpenseAuditLog.objects.create(
            employee=employee, transaction=txn, action='EXPENSE_CREATED',
            user=user, notes=f"Recorded Expense ₹{amount:,.2f} at {site} ({category})"
        )
        return txn

    @classmethod
    @transaction.atomic
    def create_cash_out(cls, employee, amount, date, recipient="", remarks="", particulars="", user=None):
        """Records payment made to external person/vendor."""
        amount = Decimal(str(amount))
        txn = CashTransaction.objects.create(
            employee=employee,
            transaction_date=date,
            txn_type=CashTransaction.TxnType.CASH_OUT,
            amount=amount,
            cash_out_recipient=recipient,
            particulars=particulars,
            remarks=remarks,
            created_by=user
        )
        cls.recalculate_employee_ledger(employee)
        ExpenseAuditLog.objects.create(
            employee=employee, transaction=txn, action='CASH_OUT_CREATED',
            user=user, notes=f"Recorded Cash Out ₹{amount:,.2f} to {recipient}"
        )
        return txn

    @classmethod
    @transaction.atomic
    def create_employee_transfer(cls, sender, receiver, amount, date, payment_mode="Paytm", reference_no="", remarks="", user=None):
        """
        Creates an internal transfer between two employees atomically:
          - Debit transaction in sender ledger
          - Credit transaction in receiver ledger
          - Linked by EmployeeTransfer record
        """
        if sender == receiver:
            raise ValueError("Sender and receiver cannot be the same employee.")
        
        amount = Decimal(str(amount))
        
        # 1. Debit in sender ledger
        debit_txn = CashTransaction.objects.create(
            employee=sender,
            transaction_date=date,
            txn_type=CashTransaction.TxnType.TRANSFER_OUT,
            amount=amount,
            cash_out_recipient=f"{receiver.name} ({payment_mode})",
            particulars=f"Transfer to {receiver.name} via {payment_mode}" + (f" (Ref: {reference_no})" if reference_no else ""),
            remarks=remarks,
            created_by=user
        )

        # 2. Credit in receiver ledger
        credit_txn = CashTransaction.objects.create(
            employee=receiver,
            transaction_date=date,
            txn_type=CashTransaction.TxnType.TRANSFER_IN,
            amount=amount,
            cash_in_source=f"{sender.name} ({payment_mode})",
            particulars=f"Received from {sender.name} via {payment_mode}" + (f" (Ref: {reference_no})" if reference_no else ""),
            remarks=remarks,
            created_by=user
        )

        # 3. Transfer record
        transfer = EmployeeTransfer.objects.create(
            sender=sender,
            receiver=receiver,
            amount=amount,
            transfer_date=date,
            payment_mode=payment_mode,
            reference_no=reference_no,
            remarks=remarks,
            debit_transaction=debit_txn,
            credit_transaction=credit_txn,
            created_by=user
        )

        # Recalculate both ledgers
        cls.recalculate_employee_ledger(sender)
        cls.recalculate_employee_ledger(receiver)

        ExpenseAuditLog.objects.create(
            employee=sender, transaction=debit_txn, action='TRANSFER_EXECUTED',
            user=user, notes=f"Transferred ₹{amount:,.2f} from {sender.name} to {receiver.name}"
        )
        return transfer

    @classmethod
    def get_dashboard_summary(cls, start_date=None, end_date=None):
        """Aggregates all company-level financial figures accurately."""
        q_filter = Q()
        if start_date:
            q_filter &= Q(transaction_date__gte=start_date)
        if end_date:
            q_filter &= Q(transaction_date__lte=end_date)

        # Total Cash In from external/bank sources (excluding internal transfers)
        total_cash_in = CashTransaction.objects.filter(
            q_filter, txn_type=CashTransaction.TxnType.CASH_IN
        ).aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

        # Total Real Expenses incurred on sites & office
        total_expenses = CashTransaction.objects.filter(
            q_filter, txn_type=CashTransaction.TxnType.EXPENSE
        ).aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

        # Total Cash Out to external parties
        total_cash_out = CashTransaction.objects.filter(
            q_filter, txn_type=CashTransaction.TxnType.CASH_OUT
        ).aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

        # Total Internal Transfers (for transparency)
        total_transfers = EmployeeTransfer.objects.filter(
            transfer_date__gte=start_date if start_date else '1900-01-01',
            transfer_date__lte=end_date if end_date else '2100-01-01'
        ).aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

        # Employee-wise summary list
        employees = CashEmployee.objects.filter(is_active=True).prefetch_related('opening_balances')
        emp_summary = []
        total_emp_balance = Decimal('0.00')
        negative_balance_count = 0

        for emp in employees:
            op = emp.opening_balances.first()
            op_amount = op.amount if op else Decimal('0.00')
            
            c_in = emp.transactions.filter(
                q_filter, txn_type__in=[CashTransaction.TxnType.CASH_IN, CashTransaction.TxnType.TRANSFER_IN]
            ).aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

            exp = emp.transactions.filter(
                q_filter, txn_type=CashTransaction.TxnType.EXPENSE
            ).aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

            c_out = emp.transactions.filter(
                q_filter, txn_type__in=[CashTransaction.TxnType.CASH_OUT, CashTransaction.TxnType.TRANSFER_OUT]
            ).aggregate(tot=Sum('amount'))['tot'] or Decimal('0.00')

            cur_bal = emp.cached_balance
            total_emp_balance += cur_bal
            if cur_bal < 0:
                negative_balance_count += 1

            emp_summary.append({
                'employee': emp,
                'opening_balance': op_amount,
                'cash_in': c_in,
                'expenses': exp,
                'cash_out': c_out,
                'current_balance': cur_bal,
                'is_negative': cur_bal < 0,
            })

        # Site-wise spending ranking
        site_expenses = (
            CashTransaction.objects.filter(q_filter, txn_type=CashTransaction.TxnType.EXPENSE, site__isnull=False)
            .values('site__name')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')[:10]
        )

        # Category-wise spending ranking
        category_expenses = (
            CashTransaction.objects.filter(q_filter, txn_type=CashTransaction.TxnType.EXPENSE, category__isnull=False)
            .values('category__name')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')[:10]
        )

        return {
            'total_cash_in': total_cash_in,
            'total_expenses': total_expenses,
            'total_cash_out': total_cash_out,
            'total_transfers': total_transfers,
            'total_emp_balance': total_emp_balance,
            'negative_balance_count': negative_balance_count,
            'employee_summary': emp_summary,
            'site_expenses': site_expenses,
            'category_expenses': category_expenses,
        }
