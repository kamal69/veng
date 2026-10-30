from django.db import migrations
from decimal import Decimal

def sync_19260_transfer(apps, schema_editor):
    CashEmployee = apps.get_model('expenses', 'CashEmployee')
    CashTransaction = apps.get_model('expenses', 'CashTransaction')
    EmployeeTransfer = apps.get_model('expenses', 'EmployeeTransfer')

    bipin = CashEmployee.objects.filter(name__icontains='Bipin').first()
    divyansh = CashEmployee.objects.filter(name__icontains='Divyansh').first()

    if not bipin or not divyansh:
        return

    # Find Bipin's debit of 19260
    bipin_txn = CashTransaction.objects.filter(
        employee=bipin,
        amount=Decimal('19260.00'),
        transaction_date='2026-04-01'
    ).first()

    if bipin_txn:
        bipin_txn.linked_employee = divyansh
        bipin_txn.txn_type = 'TRANSFER_OUT'
        bipin_txn.cash_out_recipient = 'Divyansh Paytm'
        bipin_txn.save()

    # Find or create Divyansh's incoming credit of 19260 on 2026-04-01
    div_txn = CashTransaction.objects.filter(
        employee=divyansh,
        amount=Decimal('19260.00'),
        transaction_date='2026-04-01'
    ).first()

    if not div_txn:
        # Check if ID 548 exists or first cash_in on 2026-04-01
        div_first_in = CashTransaction.objects.filter(
            employee=divyansh,
            transaction_date='2026-04-01',
            txn_type__in=['TRANSFER_IN', 'CASH_IN']
        ).first()

        if div_first_in:
            div_first_in.amount = Decimal('19260.00')
            div_first_in.txn_type = 'TRANSFER_IN'
            div_first_in.cash_in_source = 'Bipin Paytm'
            div_first_in.linked_employee = bipin
            div_first_in.particulars = 'Transfer received from Bipin (Paytm)'
            div_first_in.save()
            div_txn = div_first_in

    if div_txn:
        div_txn.linked_employee = bipin
        div_txn.txn_type = 'TRANSFER_IN'
        div_txn.cash_in_source = 'Bipin Paytm'
        div_txn.save()

    # Create or update EmployeeTransfer
    if bipin_txn and div_txn:
        EmployeeTransfer.objects.get_or_create(
            debit_transaction=bipin_txn,
            defaults={
                'sender': bipin,
                'receiver': divyansh,
                'amount': Decimal('19260.00'),
                'transfer_date': bipin_txn.transaction_date,
                'payment_mode': 'Paytm',
                'credit_transaction': div_txn,
                'remarks': 'Transferred from Bipin to Divyansh via Paytm'
            }
        )

def noop_reverse(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('expenses', '0002_cashtransaction_linked_employee_and_more'),
    ]

    operations = [
        migrations.RunPython(sync_19260_transfer, noop_reverse),
    ]
