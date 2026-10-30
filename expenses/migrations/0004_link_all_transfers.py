from django.db import migrations
from decimal import Decimal

def link_all_transfers(apps, schema_editor):
    CashEmployee = apps.get_model('expenses', 'CashEmployee')
    CashTransaction = apps.get_model('expenses', 'CashTransaction')
    EmployeeTransfer = apps.get_model('expenses', 'EmployeeTransfer')

    employees = {e.name.lower(): e for e in CashEmployee.objects.all()}

    # 1. Exact amount matches on same date
    for t in CashTransaction.objects.filter(txn_type__in=['TRANSFER_OUT', 'CASH_OUT'], linked_employee__isnull=True):
        recip = (t.cash_out_recipient or '').lower()
        for name, emp in employees.items():
            if emp.id != t.employee_id and name in recip:
                credit = CashTransaction.objects.filter(
                    employee=emp,
                    transaction_date=t.transaction_date,
                    amount=t.amount,
                    txn_type__in=['TRANSFER_IN', 'CASH_IN'],
                    linked_employee__isnull=True
                ).first()
                if credit:
                    t.linked_employee = emp
                    t.txn_type = 'TRANSFER_OUT'
                    t.save(update_fields=['linked_employee', 'txn_type'])

                    credit.linked_employee = t.employee
                    credit.txn_type = 'TRANSFER_IN'
                    credit.save(update_fields=['linked_employee', 'txn_type'])

                    EmployeeTransfer.objects.get_or_create(
                        debit_transaction=t,
                        defaults={
                            'sender': t.employee,
                            'receiver': emp,
                            'amount': t.amount,
                            'transfer_date': t.transaction_date,
                            'payment_mode': 'Paytm' if 'paytm' in recip else ('ATM' if 'atm' in recip else 'Cash'),
                            'credit_transaction': credit,
                            'remarks': f"Transfer from {t.employee.name} to {emp.name}"
                        }
                    )
                break

    # 2. Also link remaining where recipient clearly names staff member
    for t in CashTransaction.objects.filter(txn_type__in=['TRANSFER_OUT', 'CASH_OUT'], linked_employee__isnull=True):
        recip = (t.cash_out_recipient or '').lower()
        for name, emp in employees.items():
            if emp.id != t.employee_id and name in recip:
                t.linked_employee = emp
                t.txn_type = 'TRANSFER_OUT'
                t.save(update_fields=['linked_employee', 'txn_type'])
                break

    # 3. Also link remaining incoming transactions where source clearly names staff member
    for c in CashTransaction.objects.filter(txn_type__in=['TRANSFER_IN', 'CASH_IN'], linked_employee__isnull=True):
        src = (c.cash_in_source or '').lower()
        for name, emp in employees.items():
            if emp.id != c.employee_id and name in src:
                c.linked_employee = emp
                c.txn_type = 'TRANSFER_IN'
                c.save(update_fields=['linked_employee', 'txn_type'])
                break

def noop_reverse(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0003_sync_bipin_divyansh_19260'),
    ]

    operations = [
        migrations.RunPython(link_all_transfers, noop_reverse),
    ]
