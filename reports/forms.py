from decimal import Decimal
from django import forms
from django.contrib.auth.models import User
from .models import Site, Employee, UserProfile, UserRole, SiteReport


class SiteForm(forms.ModelForm):
    class Meta:
        model = Site
        fields = ['name', 'code', 'location', 'client_name', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Metro Line 3 Pier 42'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. SITE-ML3-42'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Western Expressway, Andheri'}),
            'client_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. MMRDA'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['employee_id', 'name', 'designation', 'department', 'phone', 'daily_rate', 'hourly_rate', 'is_active']
        widgets = {
            'employee_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. EMP-101'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Quality Engineer, Project Manager'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Civil, Mechanical, Safety'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+91 98765 43210'}),
            'daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(required=False, widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to keep unchanged'}))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = UserProfile
        fields = ['role', 'designation', 'phone', 'assigned_sites']
        widgets = {
            'role': forms.Select(attrs={'class': 'form-select'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'assigned_sites': forms.SelectMultiple(attrs={'class': 'form-select', 'size': '5'}),
        }


class ReturnReportForm(forms.Form):
    rejection_remarks = forms.CharField(
        label="Reason for Return / Required Corrections",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Specify the issues that need to be corrected by the site engineer...'})
    )


class MaterialPurchaseForm(forms.ModelForm):
    class Meta:
        from .models import MaterialPurchase
        model = MaterialPurchase
        fields = [
            'site', 'site_name_text', 'material_date', 'payment_date',
            'party_name', 'material_name', 'bill_no',
            'purchased_by', 'payment_by', 'payment_mode',
            'quantity', 'measuring_unit', 'rate',
            'taxable_value', 'cgst', 'sgst', 'igst', 'total_gst', 'net_amount',
            'remark'
        ]
        widgets = {
            'site': forms.Select(attrs={'class': 'form-select', 'id': 'id_site'}),
            'site_name_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional manual site name if not in list'}),
            'material_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'id_material_date'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'id': 'id_payment_date'}),
            'party_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Shiva Stone Crusher, Swastik Entp, Singh Entp', 'id': 'id_party_name', 'list': 'party_suggestions'}),
            'material_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Gatka, Sand, TMT Steel 12mm, Cement', 'id': 'id_material_name', 'list': 'material_suggestions', 'required': 'required'}),
            'bill_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 228/2026-27 or N/A', 'id': 'id_bill_no'}),
            'purchased_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Divyansh, Bipin, Vikas Engineering', 'id': 'id_purchased_by', 'list': 'staff_suggestions'}),
            'payment_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Divyansh, Vikas Engineering (blank if pending)', 'id': 'id_payment_by', 'list': 'staff_suggestions'}),
            'payment_mode': forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_mode'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_quantity', 'placeholder': '0.00'}),
            'measuring_unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'FT, CFT, KG, TON, PC, BAGS', 'id': 'id_measuring_unit', 'list': 'unit_suggestions'}),
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_rate', 'placeholder': '0.00'}),
            'taxable_value': forms.NumberInput(attrs={'class': 'form-control fw-bold', 'step': '0.01', 'id': 'id_taxable_value', 'placeholder': '0.00'}),
            'cgst': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_cgst', 'placeholder': '0.00'}),
            'sgst': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_sgst', 'placeholder': '0.00'}),
            'igst': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_igst', 'placeholder': '0.00'}),
            'total_gst': forms.NumberInput(attrs={'class': 'form-control fw-semibold', 'step': '0.01', 'id': 'id_total_gst', 'placeholder': '0.00'}),
            'net_amount': forms.NumberInput(attrs={'class': 'form-control fw-bold fs-5 text-primary', 'step': '0.01', 'id': 'id_net_amount', 'placeholder': '0.00'}),
            'remark': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Yes, No, Bill pending, Verified', 'id': 'id_remark'}),
        }
