from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone


class UserRole(models.TextChoices):
    SITE_ENGINEER = 'SITE_ENGINEER', 'Site Engineer'
    ADMIN = 'ADMIN', 'Admin'
    MANAGEMENT = 'MANAGEMENT', 'Management'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.SITE_ENGINEER)
    designation = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    assigned_sites = models.ManyToManyField('Site', blank=True, related_name='assigned_engineers')

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"

    @property
    def is_site_engineer(self):
        return self.role == UserRole.SITE_ENGINEER

    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN or self.user.is_superuser

    @property
    def is_management(self):
        return self.role == UserRole.MANAGEMENT or self.role == UserRole.ADMIN or self.user.is_superuser


class Site(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('ON_HOLD', 'On Hold'),
        ('COMPLETED', 'Completed'),
    ]

    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=50, unique=True)
    location = models.CharField(max_length=255)
    client_name = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Employee(models.Model):
    employee_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Configured daily rate in INR")
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Configured hourly rate in INR")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.designation} ({self.employee_id})"


class SiteReport(models.Model):
    class ReportStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Submitted'
        APPROVED = 'APPROVED', 'Approved'
        RETURNED = 'RETURNED', 'Returned for Correction'

    class SiteStatus(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        NEAR_COMPLETION = 'NEAR_COMPLETION', 'Near Completion'
        ON_HOLD = 'ON_HOLD', 'On Hold'
        COMPLETED = 'COMPLETED', 'Completed'
        MATERIAL_SHORTAGE = 'MATERIAL_SHORTAGE', 'Material Shortage'
        RAIN_DELAY = 'RAIN_DELAY', 'Rain / Weather Delay'

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name='reports')
    report_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=ReportStatus.choices, default=ReportStatus.DRAFT)
    site_status = models.CharField(max_length=30, choices=SiteStatus.choices, default=SiteStatus.IN_PROGRESS)

    reported_by_name = models.CharField(max_length=150)
    reported_by_designation = models.CharField(max_length=100)
    reported_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='filed_reports')

    company_employees_on_site = models.TextField(blank=True, help_text="Summary of company staff & supervisors present on site")
    work_done_today = models.TextField(help_text="Detailed description of work accomplished today")
    remarks = models.TextField(blank=True, help_text="Observations, site challenges, safety or material notes")

    # Calculated financial totals (persisted for reporting, derived from child entries)
    total_manpower_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_machinery_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_employee_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_site_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_manpower_count = models.PositiveIntegerField(default=0)

    # Workflow & Audit trail
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='submitted_reports')
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_reports')
    rejection_remarks = models.TextField(blank=True, help_text="Feedback or corrections required from Site Engineer")

    allow_duplicate = models.BooleanField(default=False, help_text="Explicit admin permission allowing a duplicate report on the same site and date")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-report_date', '-created_at']

    def __str__(self):
        return f"{self.site.name} Report - {self.report_date} [{self.get_status_display()}]"

    def clean(self):
        super().clean()
        # Business rule: Prevent duplicate reports for same site & date unless explicitly allowed by admin
        if not self.allow_duplicate:
            existing = SiteReport.objects.filter(site=self.site, report_date=self.report_date)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError({
                    'report_date': f"A report already exists for site '{self.site.name}' on {self.report_date}. Duplicate reports are not allowed without admin authorization."
                })

    def recalculate_totals(self, save=True):
        """Derive and persist all site cost summaries strictly from validated child entries."""
        manpower_items = list(self.manpower_entries.all())
        machinery_items = list(self.machinery_entries.all())
        employee_items = list(self.employee_visits.all())

        m_cost = sum((item.total_cost for item in manpower_items), Decimal('0.00'))
        m_count = sum((item.worker_count for item in manpower_items), 0)

        mac_cost = sum((item.rental_cost for item in machinery_items), Decimal('0.00'))
        emp_cost = sum((item.allocated_cost for item in employee_items), Decimal('0.00'))

        self.total_manpower_cost = m_cost
        self.total_manpower_count = m_count
        self.total_machinery_cost = mac_cost
        self.total_employee_cost = emp_cost
        self.total_site_cost = m_cost + mac_cost + emp_cost

        if save:
            self.save(update_fields=[
                'total_manpower_cost',
                'total_manpower_count',
                'total_machinery_cost',
                'total_employee_cost',
                'total_site_cost',
                'updated_at'
            ])
        return self.total_site_cost


class ManpowerCategory(models.TextChoices):
    LABOUR = 'Labour', 'Labour'
    MASON = 'Mason', 'Mason'
    PAINTER = 'Painter', 'Painter'
    OTHER_CONTRACTOR = 'Other Contractor', 'Other Contractor'


class ManpowerType(models.TextChoices):
    PERMANENT = 'Permanent', 'Permanent'
    CHOWK = 'Chowk', 'Chowk'
    CONTRACTOR = 'Contractor', 'Contractor'
    OTHER = 'Other', 'Other'


class ManpowerEntry(models.Model):
    site_report = models.ForeignKey(SiteReport, on_delete=models.CASCADE, related_name='manpower_entries')
    category = models.CharField(max_length=50, choices=ManpowerCategory.choices)
    type = models.CharField(max_length=50, choices=ManpowerType.choices)
    worker_count = models.PositiveIntegerField(help_text="Number of workers")
    rate_per_head = models.DecimalField(max_digits=10, decimal_places=2, help_text="Daily rate per head (INR)")
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Total = Count × Rate")
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name_plural = 'Manpower entries'

    def clean(self):
        super().clean()
        if self.worker_count <= 0:
            raise ValidationError({'worker_count': "Number of workers must be at least 1."})
        if self.rate_per_head < Decimal('0.00'):
            raise ValidationError({'rate_per_head': "Rate cannot be negative."})

    def save(self, *args, **kwargs):
        # Formula: Total = Number × Rate per Head
        self.total_cost = Decimal(self.worker_count) * Decimal(self.rate_per_head)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category} ({self.type}): {self.worker_count} @ ₹{self.rate_per_head} = ₹{self.total_cost}"


class MachineryOwnership(models.TextChoices):
    COMPANY_OWNED = 'COMPANY_OWNED', 'Company Owned'
    RENTAL = 'RENTAL', 'Rental'


class MachineryBillingBasis(models.TextChoices):
    HOUR = 'HOUR', 'Hour'
    DAY = 'DAY', 'Day'


class MachineryEntry(models.Model):
    site_report = models.ForeignKey(SiteReport, on_delete=models.CASCADE, related_name='machinery_entries')
    machine_name = models.CharField(max_length=150, help_text="e.g. JCB Excavator, Concrete Mixer, Vibrator, Crane")
    ownership = models.CharField(max_length=20, choices=MachineryOwnership.choices, default=MachineryOwnership.RENTAL)
    remarks = models.CharField(max_length=255, blank=True)

    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('1.00'))
    billing_basis = models.CharField(max_length=10, choices=MachineryBillingBasis.choices, default=MachineryBillingBasis.DAY)
    usage_value = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('1.00'), help_text="Hours or Days used")
    rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Rent per Hour or Rent per Day")
    rental_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Hourly: Qty × Hours × Rate; Daily: Qty × Days × Rate. Zero for Company Owned.")
    internal_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Optional internal tracking cost")

    class Meta:
        verbose_name_plural = 'Machinery entries'

    def clean(self):
        super().clean()
        if self.quantity <= Decimal('0.00'):
            raise ValidationError({'quantity': "Quantity must be greater than zero."})
        if self.usage_value < Decimal('0.00'):
            raise ValidationError({'usage_value': "Usage cannot be negative."})
        if self.rate < Decimal('0.00'):
            raise ValidationError({'rate': "Rate cannot be negative."})

    def save(self, *args, **kwargs):
        # Business rule: For company-owned machinery, rental cost defaults to zero.
        if self.ownership == MachineryOwnership.COMPANY_OWNED:
            self.rental_cost = Decimal('0.00')
        else:
            # Hourly formula: Quantity × Hours × Rate per Hour
            # Daily formula: Quantity × Days × Rate per Day
            self.rental_cost = (Decimal(self.quantity) * Decimal(self.usage_value) * Decimal(self.rate)).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.machine_name} ({self.get_ownership_display()}): ₹{self.rental_cost}"


class VisitType(models.TextChoices):
    FULL_DAY = 'FULL_DAY', 'Full Day'
    HALF_DAY = 'HALF_DAY', 'Half Day'
    HOURLY = 'HOURLY', 'Hourly'
    NO_COST = 'NO_COST', 'No Cost'


class EmployeeSiteVisit(models.Model):
    site_report = models.ForeignKey(SiteReport, on_delete=models.CASCADE, related_name='employee_visits')
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='site_visits')
    designation_snapshot = models.CharField(max_length=100, help_text="Preserved designation at time of report")
    visit_type = models.CharField(max_length=20, choices=VisitType.choices, default=VisitType.FULL_DAY)
    hours_spent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'), help_text="Used when visit type is Hourly")
    applied_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Preserved master rate (daily or hourly) at time of report")
    allocated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Calculated cost for this visit")
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name_plural = 'Employee site visits'

    def clean(self):
        super().clean()
        # Prevent accidental duplicate/double-counting cost allocation across multiple sites on same day
        # Handled gracefully in save() by capping/zeroing duplicate cost if already billed at another site.
        pass

    def save(self, *args, **kwargs):
        # Auto-snapshot designation if not set
        if not self.designation_snapshot and self.employee:
            self.designation_snapshot = self.employee.designation

        # Check existing allocations for this employee on this date across other reports
        already_allocated_days = Decimal('0.0')
        other_site_names = []

        if self.site_report_id and self.employee_id and self.site_report.report_date:
            report_date = self.site_report.report_date
            other_visits = EmployeeSiteVisit.objects.filter(
                employee=self.employee,
                site_report__report_date=report_date
            )
            if self.pk:
                other_visits = other_visits.exclude(pk=self.pk)

            for ov in other_visits:
                if ov.visit_type == VisitType.FULL_DAY and ov.allocated_cost > Decimal('0.00'):
                    already_allocated_days += Decimal('1.0')
                    other_site_names.append(ov.site_report.site.name)
                elif ov.visit_type == VisitType.HALF_DAY and ov.allocated_cost > Decimal('0.00'):
                    already_allocated_days += Decimal('0.5')
                    other_site_names.append(ov.site_report.site.name)

        # Base rate lookup
        daily_rate = self.applied_rate or (self.employee.daily_rate if self.employee else Decimal('0.00'))
        hourly_rate = self.applied_rate or (self.employee.hourly_rate if self.employee else Decimal('0.00'))

        # Calculate allocated cost while preventing accidental duplicate cost allocation
        if self.visit_type == VisitType.NO_COST:
            self.allocated_cost = Decimal('0.00')
        elif self.visit_type == VisitType.FULL_DAY:
            self.applied_rate = daily_rate
            if already_allocated_days >= Decimal('1.0'):
                # Already fully billed elsewhere today: prevent duplicate cost
                self.allocated_cost = Decimal('0.00')
                note = f"[Duplicate cost prevented: Already billed at {', '.join(set(other_site_names))}]"
                if note not in self.remarks:
                    self.remarks = f"{self.remarks} {note}".strip()
            elif already_allocated_days >= Decimal('0.5'):
                # Half day already billed elsewhere: allocate only remaining half day
                self.allocated_cost = (Decimal(daily_rate) * Decimal('0.5')).quantize(Decimal('0.01'))
                note = f"[50% cost allocated: Remaining 50% already billed at {', '.join(set(other_site_names))}]"
                if note not in self.remarks:
                    self.remarks = f"{self.remarks} {note}".strip()
            else:
                self.allocated_cost = Decimal(daily_rate).quantize(Decimal('0.01'))

        elif self.visit_type == VisitType.HALF_DAY:
            self.applied_rate = daily_rate
            if already_allocated_days >= Decimal('1.0'):
                self.allocated_cost = Decimal('0.00')
                note = f"[Duplicate cost prevented: Daily allocation reached at {', '.join(set(other_site_names))}]"
                if note not in self.remarks:
                    self.remarks = f"{self.remarks} {note}".strip()
            else:
                self.allocated_cost = (Decimal(daily_rate) * Decimal('0.5')).quantize(Decimal('0.01'))

        elif self.visit_type == VisitType.HOURLY:
            self.applied_rate = hourly_rate
            if already_allocated_days >= Decimal('1.0'):
                self.allocated_cost = Decimal('0.00')
                note = f"[Duplicate cost prevented: Full daily allocation already billed at {', '.join(set(other_site_names))}]"
                if note not in self.remarks:
                    self.remarks = f"{self.remarks} {note}".strip()
            else:
                self.allocated_cost = (Decimal(self.hours_spent) * Decimal(hourly_rate)).quantize(Decimal('0.01'))

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.name} @ {self.site_report.site.name} ({self.get_visit_type_display()}): ₹{self.allocated_cost}"


class ReportAuditLog(models.Model):
    site_report = models.ForeignKey(SiteReport, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=50) # CREATED, EDITED, SUBMITTED, APPROVED, RETURNED
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        user_name = self.performed_by.username if self.performed_by else "System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.action} by {user_name}"


class ReportToolEntry(models.Model):
    site_report = models.ForeignKey(SiteReport, on_delete=models.CASCADE, related_name='tool_entries')
    tool_name = models.CharField(max_length=150, help_text="e.g. Cut-off Saw, Rotary Hammer Drill, Needle Vibrator, Angle Grinder")
    quantity = models.PositiveIntegerField(default=1, help_text="Number of units used")
    used_by = models.CharField(max_length=100, blank=True, help_text="Operator / Custodian / Subcontractor")
    remarks = models.CharField(max_length=255, blank=True, help_text="Work task or condition note")

    class Meta:
        verbose_name_plural = 'Report tool entries'

    def __str__(self):
        return f"{self.tool_name} (x{self.quantity}) @ {self.site_report.site.name}"



