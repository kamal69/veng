import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from expenses.models import (
    CashEmployee, OpeningBalance, ExpenseSite, ExpenseCategory,
    CashTransaction, EmployeeTransfer
)
from expenses.services import AccountingService


class AccountingServiceTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_test', password='password123', is_staff=True)
        self.emp_bipin = CashEmployee.objects.create(name='Bipin', designation='Accountant')
        self.emp_divyansh = CashEmployee.objects.create(name='Divyansh', designation='Engineer')
        
        # Opening balances
        OpeningBalance.objects.create(
            employee=self.emp_bipin, financial_year='2026-27',
            amount=Decimal('-174186.00'), effective_date=datetime.date(2026, 4, 1)
        )
        OpeningBalance.objects.create(
            employee=self.emp_divyansh, financial_year='2026-27',
            amount=Decimal('-108438.00'), effective_date=datetime.date(2026, 4, 1)
        )

        self.site = ExpenseSite.objects.create(name='Tepla Project')
        self.category = ExpenseCategory.objects.create(name='Labour Payments', group_type=ExpenseCategory.GroupType.LABOUR)

    def test_opening_balance_and_ledger_formula(self):
        # Initial recalculation
        bal = AccountingService.recalculate_employee_ledger(self.emp_bipin)
        self.assertEqual(bal, Decimal('-174186.00'))

        # Cash In ₹50,000
        AccountingService.create_cash_in(
            employee=self.emp_bipin, amount=Decimal('50000.00'),
            date=datetime.date(2026, 4, 2), source='VEW ATM', user=self.user
        )
        self.emp_bipin.refresh_from_db()
        # -174186 + 50000 = -124186
        self.assertEqual(self.emp_bipin.cached_balance, Decimal('-124186.00'))

        # Expense ₹10,000
        AccountingService.create_expense(
            employee=self.emp_bipin, amount=Decimal('10000.00'),
            date=datetime.date(2026, 4, 3), site=self.site, category=self.category,
            particulars='Site worker payment', user=self.user
        )
        self.emp_bipin.refresh_from_db()
        # -124186 - 10000 = -134186
        self.assertEqual(self.emp_bipin.cached_balance, Decimal('-134186.00'))

        # Cash Out ₹5,000
        AccountingService.create_cash_out(
            employee=self.emp_bipin, amount=Decimal('5000.00'),
            date=datetime.date(2026, 4, 4), recipient='Material vendor', user=self.user
        )
        self.emp_bipin.refresh_from_db()
        # -134186 - 5000 = -139186
        self.assertEqual(self.emp_bipin.cached_balance, Decimal('-139186.00'))

    def test_atomic_internal_transfer(self):
        # Bipin transfers ₹20,000 to Divyansh via Paytm
        bipin_start = AccountingService.recalculate_employee_ledger(self.emp_bipin)
        divyansh_start = AccountingService.recalculate_employee_ledger(self.emp_divyansh)

        transfer = AccountingService.create_employee_transfer(
            sender=self.emp_bipin,
            receiver=self.emp_divyansh,
            amount=Decimal('20000.00'),
            date=datetime.date(2026, 4, 5),
            payment_mode='Paytm',
            reference_no='PAYTM12345',
            remarks='Funds for site labour',
            user=self.user
        )

        self.emp_bipin.refresh_from_db()
        self.emp_divyansh.refresh_from_db()

        # Sender debited by 20,000
        self.assertEqual(self.emp_bipin.cached_balance, bipin_start - Decimal('20000.00'))
        # Receiver credited by 20,000
        self.assertEqual(self.emp_divyansh.cached_balance, divyansh_start + Decimal('20000.00'))

        # Verify linked transactions
        self.assertIsNotNone(transfer.debit_transaction)
        self.assertIsNotNone(transfer.credit_transaction)
        self.assertEqual(transfer.debit_transaction.txn_type, CashTransaction.TxnType.TRANSFER_OUT)
        self.assertEqual(transfer.credit_transaction.txn_type, CashTransaction.TxnType.TRANSFER_IN)

    def test_same_sender_receiver_prevented(self):
        with self.assertRaises(ValueError):
            AccountingService.create_employee_transfer(
                sender=self.emp_bipin, receiver=self.emp_bipin,
                amount=Decimal('5000.00'), date=datetime.date(2026, 4, 6)
            )

    def test_dashboard_summary(self):
        # Add Cash In to Bipin ₹1,00,000
        AccountingService.create_cash_in(
            employee=self.emp_bipin, amount=Decimal('100000.00'),
            date=datetime.date(2026, 4, 2), source='Company Bank'
        )
        # Add Expense to Divyansh ₹30,000
        AccountingService.create_expense(
            employee=self.emp_divyansh, amount=Decimal('30000.00'),
            date=datetime.date(2026, 4, 3), site=self.site, category=self.category, particulars='Labour'
        )

        summary = AccountingService.get_dashboard_summary()
        self.assertEqual(summary['total_cash_in'], Decimal('100000.00'))
        self.assertEqual(summary['total_expenses'], Decimal('30000.00'))


class ExpensesViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='admin', password='adminpassword')
        self.client.login(username='admin', password='adminpassword')
        self.employee = CashEmployee.objects.create(name='TestEmp', designation='Tester')
        OpeningBalance.objects.create(
            employee=self.employee, financial_year='2026-27',
            amount=Decimal('5000.00'), effective_date=datetime.date(2026, 4, 1)
        )
        AccountingService.recalculate_employee_ledger(self.employee)

    def test_dashboard_view_status_code(self):
        response = self.client.get(reverse('expenses:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Employee Cash')

    def test_ledger_list_view(self):
        response = self.client.get(reverse('expenses:ledger_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TestEmp')

    def test_employee_ledger_view(self):
        response = self.client.get(reverse('expenses:employee_ledger', args=[self.employee.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TestEmp')

    def test_excel_export_ledger(self):
        response = self.client.get(reverse('expenses:export_ledger_excel', args=[self.employee.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    def test_excel_export_consolidated(self):
        response = self.client.get(reverse('expenses:export_consolidated_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
