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
