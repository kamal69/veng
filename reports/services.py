from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import (
    SiteReport, ManpowerEntry, MachineryEntry, EmployeeSiteVisit,
    ReportAuditLog, Employee, Site, VisitType, MachineryOwnership, MachineryBillingBasis,
    ReportToolEntry
)


class ReportService:
    @staticmethod
    @transaction.atomic
    def save_report(
        user,
        report_data,
        manpower_rows,
        machinery_rows,
        employee_rows=None,
        submit_action='save_draft',
        existing_report=None,
        tool_rows=None,
    ):
        """
        Atomically validates and saves a SiteReport and all its child rows
        (Manpower, Machinery, Employee Visits, and Tools Used), recalculates summaries,
        and logs audit trail.
        """
        employee_rows = employee_rows or []
        tool_rows = tool_rows or []
        site_id = report_data.get('site')
        report_date = report_data.get('report_date')
        site = Site.objects.get(pk=site_id)
        allow_duplicate = bool(report_data.get('allow_duplicate', False))

        # Check duplicate report rule
        if not allow_duplicate:
            dup_qs = SiteReport.objects.filter(site=site, report_date=report_date)
            if existing_report:
                dup_qs = dup_qs.exclude(pk=existing_report.pk)
            if dup_qs.exists():
                existing_rep = dup_qs.first()
                # If there is an existing draft or returned report, update it seamlessly
                if existing_rep.status in [SiteReport.ReportStatus.DRAFT, SiteReport.ReportStatus.RETURNED]:
                    existing_report = existing_rep
                else:
                    is_admin = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin)
                    if is_admin:
                        existing_report = existing_rep
                    else:
                        raise ValidationError(
                            f"A report for '{site.name}' on {report_date} already exists (#{existing_rep.id} - {existing_rep.get_status_display()}). "
                            "Please edit the existing report or check 'Allow Duplicate Report' to submit an additional separate entry."
                        )

        target_status = SiteReport.ReportStatus.SUBMITTED if submit_action == 'submit' else SiteReport.ReportStatus.DRAFT

        # If editing an existing report
        if existing_report:
            # Check permissions: if submitted/approved, non-admins cannot edit
            is_admin = user.is_superuser or (hasattr(user, 'profile') and user.profile.is_admin)
            if existing_report.status == SiteReport.ReportStatus.APPROVED and not is_admin:
                raise ValidationError("Approved reports cannot be modified.")

            report = existing_report
            report.site = site
            report.report_date = report_date
            report.site_status = report_data.get('site_status', report.site_status)
            report.reported_by_name = report_data.get('reported_by_name', report.reported_by_name)
            report.reported_by_designation = report_data.get('reported_by_designation', report.reported_by_designation)
            report.company_employees_on_site = report_data.get('company_employees_on_site', '')
            report.work_done_today = report_data.get('work_done_today', '')
            report.remarks = report_data.get('remarks', '')
            report.allow_duplicate = allow_duplicate

            if submit_action == 'submit' and report.status != SiteReport.ReportStatus.SUBMITTED:
                report.status = SiteReport.ReportStatus.SUBMITTED
                report.submitted_at = timezone.now()
                report.submitted_by = user
            elif submit_action == 'save_draft' and report.status == SiteReport.ReportStatus.RETURNED:
                report.status = SiteReport.ReportStatus.DRAFT

            report.save()
            action_name = 'SUBMITTED' if submit_action == 'submit' else 'UPDATED'
        else:
            report = SiteReport(
                site=site,
                report_date=report_date,
                status=target_status,
                site_status=report_data.get('site_status', SiteReport.SiteStatus.IN_PROGRESS),
                reported_by_name=report_data.get('reported_by_name', user.get_full_name() or user.username),
                reported_by_designation=report_data.get('reported_by_designation', getattr(getattr(user, 'profile', None), 'designation', 'Site Engineer')),
                reported_by_user=user,
                company_employees_on_site=report_data.get('company_employees_on_site', ''),
                work_done_today=report_data.get('work_done_today', ''),
                remarks=report_data.get('remarks', ''),
                allow_duplicate=allow_duplicate,
            )
            if submit_action == 'submit':
                report.submitted_at = timezone.now()
                report.submitted_by = user
            report.save()
            action_name = 'CREATED_AND_SUBMITTED' if submit_action == 'submit' else 'CREATED'

        # Delete old child rows to re-synchronize cleanly
        report.manpower_entries.all().delete()
        report.machinery_entries.all().delete()
        report.employee_visits.all().delete()
        report.tool_entries.all().delete()

        # 1. Process Manpower entries
        for row in manpower_rows:
            cat = row.get('category', '').strip()
            t_type = row.get('type', '').strip()
            count = int(row.get('worker_count', 0) or 0)
            rate = Decimal(str(row.get('rate_per_head', '0') or '0'))
            remarks = row.get('remarks', '').strip()

            if count > 0:
                manpower = ManpowerEntry(
                    site_report=report,
                    category=cat,
                    type=t_type,
                    worker_count=count,
                    rate_per_head=rate,
                    remarks=remarks
                )
                manpower.full_clean()
                manpower.save()

        # 2. Process Machinery entries
        for row in machinery_rows:
            machine_name = row.get('machine_name', '').strip()
            if not machine_name:
                continue
            ownership = row.get('ownership', MachineryOwnership.RENTAL)
            billing_basis = row.get('billing_basis', MachineryBillingBasis.DAY)
            qty = Decimal(str(row.get('quantity', '1') or '1'))
            usage = Decimal(str(row.get('usage_value', '1') or '1'))
            rate = Decimal(str(row.get('rate', '0') or '0'))
            remarks = row.get('remarks', '').strip()
            internal_cost = Decimal(str(row.get('internal_cost', '0') or '0'))

            machinery = MachineryEntry(
                site_report=report,
                machine_name=machine_name,
                ownership=ownership,
                billing_basis=billing_basis,
                quantity=qty,
                usage_value=usage,
                rate=rate,
                remarks=remarks,
                internal_cost=internal_cost
            )
            machinery.full_clean()
            machinery.save()

        # 3. Process Employee visits
        # Track employee allocations in this current batch to avoid in-form duplicates too
        seen_employee_days = {}

        for row in employee_rows:
            emp_id = row.get('employee_id')
            if not emp_id:
                continue
            employee = Employee.objects.get(pk=emp_id)
            v_type = row.get('visit_type', VisitType.FULL_DAY)
            hours = Decimal(str(row.get('hours_spent', '0') or '0'))
            remarks = row.get('remarks', '').strip()
            applied_rate = Decimal(str(row.get('applied_rate', '0') or '0'))

            # If applied_rate was not provided or 0, snapshot current master rate
            if applied_rate <= Decimal('0.00'):
                applied_rate = employee.hourly_rate if v_type == VisitType.HOURLY else employee.daily_rate

            # Check intra-form duplicates
            day_fraction = Decimal('1.0') if v_type == VisitType.FULL_DAY else (Decimal('0.5') if v_type == VisitType.HALF_DAY else Decimal('0.0'))
            current_allocated = seen_employee_days.get(employee.pk, Decimal('0.0'))
            if day_fraction > Decimal('0.0'):
                if current_allocated + day_fraction > Decimal('1.0'):
                    raise ValidationError(
                        f"Employee '{employee.name}' has been assigned more than 1.0 day allocation within this report."
                    )
                seen_employee_days[employee.pk] = current_allocated + day_fraction

            visit = EmployeeSiteVisit(
                site_report=report,
                employee=employee,
                designation_snapshot=employee.designation,
                visit_type=v_type,
                hours_spent=hours,
                applied_rate=applied_rate,
                remarks=remarks
            )
            # full_clean enforces cross-site validation on the same date
            visit.full_clean()
            visit.save()

        # 4. Process Tools Used at Site Today
        for row in tool_rows:
            t_name = row.get('tool_name', '').strip()
            if not t_name:
                continue
            qty = int(row.get('quantity', 1) or 1)
            used_by = row.get('used_by', '').strip()
            remarks = row.get('remarks', '').strip()

            ReportToolEntry.objects.create(
                site_report=report,
                tool_name=t_name,
                quantity=qty if qty > 0 else 1,
                used_by=used_by,
                remarks=remarks
            )

        # Recalculate totals
        report.recalculate_totals(save=True)

        # Audit log
        ReportAuditLog.objects.create(
            site_report=report,
            action=action_name,
            performed_by=user,
            notes=f"Report {action_name.lower()} with total cost ₹{report.total_site_cost:,.2f}"
        )

        return report

    @staticmethod
    @transaction.atomic
    def approve_report(report, user):
        report.status = SiteReport.ReportStatus.APPROVED
        report.approved_at = timezone.now()
        report.approved_by = user
        report.rejection_remarks = ''
        report.save(update_fields=['status', 'approved_at', 'approved_by', 'rejection_remarks', 'updated_at'])

        ReportAuditLog.objects.create(
            site_report=report,
            action='APPROVED',
            performed_by=user,
            notes=f"Report officially approved by {user.get_full_name() or user.username}."
        )
        return report

    @staticmethod
    @transaction.atomic
    def return_report(report, user, remarks):
        report.status = SiteReport.ReportStatus.RETURNED
        report.rejection_remarks = remarks
        report.save(update_fields=['status', 'rejection_remarks', 'updated_at'])

        ReportAuditLog.objects.create(
            site_report=report,
            action='RETURNED',
            performed_by=user,
            notes=f"Returned for correction: {remarks}"
        )
        return report

    @staticmethod
    @transaction.atomic
    def submit_report(report, user):
        report.status = SiteReport.ReportStatus.SUBMITTED
        report.submitted_at = timezone.now()
        report.submitted_by = user
        report.save(update_fields=['status', 'submitted_at', 'submitted_by', 'updated_at'])

        ReportAuditLog.objects.create(
            site_report=report,
            action='SUBMITTED',
            performed_by=user,
            notes=f"Submitted for approval by {user.get_full_name() or user.username}."
        )
        return report
