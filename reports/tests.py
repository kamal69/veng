from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import (
    Site, Employee, SiteReport, ManpowerEntry, MachineryEntry,
    EmployeeSiteVisit, UserProfile, UserRole,
    ManpowerCategory, ManpowerType, MachineryOwnership, MachineryBillingBasis, VisitType
)
from .services import ReportService
from .excel_export import export_single_report_to_excel, export_bulk_reports_to_excel


class DailySiteReportCalculationsAndRulesTestCase(TestCase):
    def setUp(self):
        # Create users
        self.admin_user = User.objects.create_user(username='admin_user', password='password123')
        self.admin_profile = UserProfile.objects.create(user=self.admin_user, role=UserRole.ADMIN)

        self.engineer_user = User.objects.create_user(username='engineer_user', password='password123')
        self.engineer_profile = UserProfile.objects.create(user=self.engineer_user, role=UserRole.SITE_ENGINEER)

        self.manager_user = User.objects.create_user(username='manager_user', password='password123')
        self.manager_profile = UserProfile.objects.create(user=self.manager_user, role=UserRole.MANAGEMENT)

        # Create Site
        self.site = Site.objects.create(
            name="Mumbai Coastal Road Pier 22",
            code="SITE-MCR-22",
            location="Worli Sea Face",
            client_name="BMC",
            status="ACTIVE"
        )
        self.site_b = Site.objects.create(
            name="Trans Harbour Link Package 2",
            code="SITE-MTHL-02",
            location="Sewri Nhava",
            client_name="MMRDA",
            status="ACTIVE"
        )

        # Create Employee
        self.employee1 = Employee.objects.create(
            employee_id="EMP-TEST-01",
            name="Suresh Kulkarni",
            designation="Quality Manager",
            daily_rate=Decimal('3000.00'),
            hourly_rate=Decimal('400.00')
        )
        self.employee2 = Employee.objects.create(
            employee_id="EMP-TEST-02",
            name="Ramesh Gupta",
            designation="Safety Officer",
            daily_rate=Decimal('2000.00'),
            hourly_rate=Decimal('250.00')
        )

    def test_hourly_machinery_calculation(self):
        """Verify hourly machinery: Quantity × Hours × Rate per Hour."""
        report = SiteReport.objects.create(
            site=self.site,
            report_date=date(2026, 11, 1),
            reported_by_name="Test Engineer",
            reported_by_designation="Site Engineer",
            work_done_today="Foundation test"
        )

        entry = MachineryEntry.objects.create(
            site_report=report,
            machine_name="Hydraulic Excavator",
            ownership=MachineryOwnership.RENTAL,
            quantity=Decimal('2.00'),
            billing_basis=MachineryBillingBasis.HOUR,
            usage_value=Decimal('5.00'),
            rate=Decimal('1200.00')
        )
        # Expected: 2 * 5 * 1200.00 = 12,000.00
        self.assertEqual(entry.rental_cost, Decimal('12000.00'))

    def test_daily_machinery_calculation(self):
        """Verify daily machinery: Quantity × Days × Rate per Day."""
        report = SiteReport.objects.create(
            site=self.site,
            report_date=date(2026, 11, 2),
            reported_by_name="Test Engineer",
            reported_by_designation="Site Engineer",
            work_done_today="Pier testing"
        )

        entry = MachineryEntry.objects.create(
            site_report=report,
            machine_name="100T Mobile Crane",
            ownership=MachineryOwnership.RENTAL,
            quantity=Decimal('1.00'),
            billing_basis=MachineryBillingBasis.DAY,
            usage_value=Decimal('3.00'),
            rate=Decimal('15000.00')
        )
        # Expected: 1 * 3 * 15,000.00 = 45,000.00
        self.assertEqual(entry.rental_cost, Decimal('45000.00'))

    def test_company_owned_machinery_defaults_to_zero_rental(self):
        """For company-owned machinery, rental cost defaults to zero."""
        report = SiteReport.objects.create(
            site=self.site,
            report_date=date(2026, 11, 3),
            reported_by_name="Test Engineer",
            reported_by_designation="Site Engineer",
            work_done_today="Power generator test"
        )

        entry = MachineryEntry.objects.create(
            site_report=report,
            machine_name="Company Owned 125KVA Generator",
            ownership=MachineryOwnership.COMPANY_OWNED,
            quantity=Decimal('1.00'),
            billing_basis=MachineryBillingBasis.DAY,
            usage_value=Decimal('1.00'),
            rate=Decimal('4500.00'),
            internal_cost=Decimal('1500.00')
        )
        # Company owned must have rental_cost == 0.00
        self.assertEqual(entry.rental_cost, Decimal('0.00'))
        self.assertEqual(entry.internal_cost, Decimal('1500.00'))

    def test_multiple_manpower_rows_and_total_calculation(self):
        """Formula: Total = Number × Rate per Head. Test multiple rows & report subtotal."""
        report = SiteReport.objects.create(
            site=self.site,
            report_date=date(2026, 11, 4),
            reported_by_name="Test Engineer",
            reported_by_designation="Site Engineer",
            work_done_today="Reinforcement binding and shuttering"
        )

        # Row 1: 15 Labours @ 650 = 9,750.00
        m1 = ManpowerEntry.objects.create(
            site_report=report,
            category=ManpowerCategory.LABOUR,
            type=ManpowerType.CONTRACTOR,
            worker_count=15,
            rate_per_head=Decimal('650.00')
        )
        self.assertEqual(m1.total_cost, Decimal('9750.00'))

        # Row 2: 5 Masons @ 950 = 4,750.00
        m2 = ManpowerEntry.objects.create(
            site_report=report,
            category=ManpowerCategory.MASON,
            type=ManpowerType.CHOWK,
            worker_count=5,
            rate_per_head=Decimal('950.00')
        )
        self.assertEqual(m2.total_cost, Decimal('4750.00'))

        # Row 3: 4 Painters @ 800 = 3,200.00
        m3 = ManpowerEntry.objects.create(
            site_report=report,
            category=ManpowerCategory.PAINTER,
            type=ManpowerType.PERMANENT,
            worker_count=4,
            rate_per_head=Decimal('800.00')
        )
        self.assertEqual(m3.total_cost, Decimal('3200.00'))

        # Recalculate
        total = report.recalculate_totals()
        self.assertEqual(report.total_manpower_count, 24)
        self.assertEqual(report.total_manpower_cost, Decimal('17700.00'))
        self.assertEqual(report.total_site_cost, Decimal('17700.00'))

    def test_employee_visit_cost_allocations(self):
        """Test Full Day, Half Day, Hourly, and No Cost allocations."""
        report = SiteReport.objects.create(
            site=self.site,
            report_date=date(2026, 11, 5),
            reported_by_name="Test Engineer",
            reported_by_designation="Site Engineer",
            work_done_today="Safety and Quality checks"
        )

        # Full Day: daily_rate = 3000.00
        v_full = EmployeeSiteVisit.objects.create(
            site_report=report,
            employee=self.employee1,
            visit_type=VisitType.FULL_DAY,
        )
        self.assertEqual(v_full.allocated_cost, Decimal('3000.00'))

        # Half Day: 0.5 * 2000.00 = 1000.00
        v_half = EmployeeSiteVisit.objects.create(
            site_report=report,
            employee=self.employee2,
            visit_type=VisitType.HALF_DAY,
        )
        self.assertEqual(v_half.allocated_cost, Decimal('1000.00'))

        # Hourly: 3 hours * 400.00 = 1200.00
        emp3 = Employee.objects.create(
            employee_id="EMP-TEST-03",
            name="Consultant Anita",
            designation="Consultant",
            daily_rate=Decimal('4000.00'),
            hourly_rate=Decimal('500.00')
        )
        v_hourly = EmployeeSiteVisit.objects.create(
            site_report=report,
            employee=emp3,
            visit_type=VisitType.HOURLY,
            hours_spent=Decimal('3.00')
        )
        self.assertEqual(v_hourly.allocated_cost, Decimal('1500.00'))

        # No Cost: 0.00
        emp4 = Employee.objects.create(
            employee_id="EMP-TEST-04",
            name="Intern Rahul",
            designation="Trainee",
            daily_rate=Decimal('1000.00'),
            hourly_rate=Decimal('150.00')
        )
        v_nocost = EmployeeSiteVisit.objects.create(
            site_report=report,
            employee=emp4,
            visit_type=VisitType.NO_COST,
        )
        self.assertEqual(v_nocost.allocated_cost, Decimal('0.00'))

    def test_prevent_employee_visit_double_counting(self):
        """
        Business Rule: If an employee visits multiple sites on the same day,
        prevent accidental duplicate cost allocation.
        """
        report_date = date(2026, 11, 6)

        # Site A report with employee1 Full Day
        report_a = SiteReport.objects.create(
            site=self.site,
            report_date=report_date,
            reported_by_name="Engineer A",
            reported_by_designation="Site Engineer",
            work_done_today="Site A work"
        )
        EmployeeSiteVisit.objects.create(
            site_report=report_a,
            employee=self.employee1,
            visit_type=VisitType.FULL_DAY,
        )

        # Site B report on the SAME DATE trying to allocate employee1 as Full Day again
        report_b = SiteReport.objects.create(
            site=self.site_b,
            report_date=report_date,
            reported_by_name="Engineer B",
            reported_by_designation="Site Engineer",
            work_done_today="Site B work"
        )

        duplicate_visit = EmployeeSiteVisit(
            site_report=report_b,
            employee=self.employee1,
            visit_type=VisitType.FULL_DAY,
        )
        # Must raise ValidationError during full_clean
        with self.assertRaises(ValidationError):
            duplicate_visit.full_clean()

    def test_duplicate_report_prevention_for_same_site_and_date(self):
        """
        Business Rule: Prevent duplicate reports for the same site and reporting date
        unless explicitly allowed by an administrator.
        """
        report_date = date(2026, 11, 7)

        # Create report 1
        SiteReport.objects.create(
            site=self.site,
            report_date=report_date,
            reported_by_name="Engineer 1",
            reported_by_designation="Site Engineer",
            work_done_today="Morning progress"
        )

        # Attempt to create report 2 on same site and date without allow_duplicate
        report_duplicate = SiteReport(
            site=self.site,
            report_date=report_date,
            reported_by_name="Engineer 2",
            reported_by_designation="Site Engineer",
            work_done_today="Afternoon progress",
            allow_duplicate=False
        )

        with self.assertRaises(ValidationError):
            report_duplicate.full_clean()

        # If admin explicitly allows duplicate (allow_duplicate=True), clean passes
        report_duplicate.allow_duplicate = True
        report_duplicate.full_clean()  # should not raise ValidationError
        report_duplicate.save()
        self.assertIsNotNone(report_duplicate.pk)

    def test_report_service_atomic_save(self):
        """Test full ReportService atomic save with child entries and recalculation."""
        report_data = {
            'site': self.site.id,
            'report_date': date(2026, 11, 8),
            'site_status': SiteReport.SiteStatus.IN_PROGRESS,
            'reported_by_name': "Amit Verma",
            'reported_by_designation': "Site Engineer",
            'work_done_today': "Service integration test",
            'remarks': "All smooth",
        }
        manpower_rows = [
            {'category': 'Labour', 'type': 'Contractor', 'worker_count': 10, 'rate_per_head': '700.00'},
            {'category': 'Mason', 'type': 'Chowk', 'worker_count': 2, 'rate_per_head': '1000.00'},
        ]
        machinery_rows = [
            {'machine_name': 'JCB 3DX', 'ownership': 'RENTAL', 'quantity': '1', 'billing_basis': 'DAY', 'usage_value': '1', 'rate': '8500.00'}
        ]
        employee_rows = [
            {'employee_id': self.employee1.id, 'visit_type': 'HALF_DAY', 'hours_spent': '0', 'applied_rate': '3000.00'}
        ]

        report = ReportService.save_report(
            user=self.engineer_user,
            report_data=report_data,
            manpower_rows=manpower_rows,
            machinery_rows=machinery_rows,
            employee_rows=employee_rows,
            submit_action='submit'
        )

        self.assertEqual(report.status, SiteReport.ReportStatus.SUBMITTED)
        # Expected costs:
        # Manpower: (10*700) + (2*1000) = 7000 + 2000 = 9000.00
        # Machinery: 1 * 1 * 8500 = 8500.00
        # Employee: 0.5 * 3000 = 1500.00
        # Total: 9000 + 8500 + 1500 = 19,000.00
        self.assertEqual(report.total_manpower_cost, Decimal('9000.00'))
        self.assertEqual(report.total_machinery_cost, Decimal('8500.00'))
        self.assertEqual(report.total_employee_cost, Decimal('1500.00'))
        self.assertEqual(report.total_site_cost, Decimal('19000.00'))
        self.assertEqual(report.total_manpower_count, 12)

    def test_approval_workflow_permissions(self):
        """Test approval and return workflow."""
        report = SiteReport.objects.create(
            site=self.site,
            report_date=date(2026, 11, 9),
            status=SiteReport.ReportStatus.SUBMITTED,
            reported_by_name="Test Engineer",
            reported_by_designation="Site Engineer",
            work_done_today="Workflow test"
        )

        # Management approves report
        ReportService.approve_report(report, self.manager_user)
        self.assertEqual(report.status, SiteReport.ReportStatus.APPROVED)
        self.assertEqual(report.approved_by, self.manager_user)

        # Return report for correction
        ReportService.return_report(report, self.manager_user, "Incomplete concrete cube test results.")
        self.assertEqual(report.status, SiteReport.ReportStatus.RETURNED)
        self.assertEqual(report.rejection_remarks, "Incomplete concrete cube test results.")

    def test_excel_export_generation(self):
        """Verify openpyxl workbook creation for single and bulk exports."""
        report = SiteReport.objects.create(
            site=self.site,
            report_date=date(2026, 11, 10),
            status=SiteReport.ReportStatus.APPROVED,
            reported_by_name="Test Engineer",
            reported_by_designation="Site Engineer",
            work_done_today="Export test"
        )
        ManpowerEntry.objects.create(
            site_report=report,
            category=ManpowerCategory.LABOUR,
            type=ManpowerType.CONTRACTOR,
            worker_count=5,
            rate_per_head=Decimal('600.00')
        )
        report.recalculate_totals()

        # Single export
        single_stream = export_single_report_to_excel(report)
        self.assertIsNotNone(single_stream)
        self.assertTrue(single_stream.getbuffer().nbytes > 1000)

        # Bulk export
        bulk_stream = export_bulk_reports_to_excel(SiteReport.objects.filter(pk=report.pk))
        self.assertIsNotNone(bulk_stream)
        self.assertTrue(bulk_stream.getbuffer().nbytes > 1000)


class DailySiteReportViewAccessTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username='admin', password='password123')
        UserProfile.objects.create(user=self.admin, role=UserRole.ADMIN)

        self.engineer = User.objects.create_user(username='engineer', password='password123')
        UserProfile.objects.create(user=self.engineer, role=UserRole.SITE_ENGINEER)

        self.site = Site.objects.create(
            name="Test Site Alpha",
            code="SITE-A",
            location="Bandra Kurla Complex",
            status="ACTIVE"
        )

    def test_unauthenticated_user_redirected_to_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_authenticated_dashboard_access(self):
        self.client.login(username='engineer', password='password123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Construction Site Operations & Cost Dashboard")

    def test_site_engineer_cannot_access_user_master(self):
        self.client.login(username='engineer', password='password123')
        response = self.client.get(reverse('user_list'))
        # Should redirect with permission warning
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_admin_can_access_user_master(self):
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Users & Role Permissions")


class SameDayReportUpdateTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='engineer', password='password123')
        self.profile = UserProfile.objects.create(user=self.user, role=UserRole.SITE_ENGINEER)
        self.site = Site.objects.create(
            name="1391 Meerut",
            code="1391",
            location="Meerut Bypass Site",
            status="ACTIVE"
        )
        self.today = date(2026, 10, 30)

    def test_same_day_report_seamless_update(self):
        """Entering data for the same site and date updates the existing report without error."""
        report1 = ReportService.save_report(
            user=self.user,
            report_data={
                'site': self.site.id,
                'report_date': self.today,
                'reported_by_name': 'Amit Verma',
                'reported_by_designation': 'Site Engineer',
                'work_done_today': 'Morning shift excavation',
            },
            manpower_rows=[{
                'category': ManpowerCategory.LABOUR,
                'type': ManpowerType.CONTRACTOR,
                'worker_count': 5,
                'rate_per_head': Decimal('600.00'),
            }],
            machinery_rows=[],
            employee_rows=[],
            submit_action='save_draft'
        )
        self.assertEqual(report1.total_site_cost, Decimal('3000.00'))

        # Later on the same day, user adds evening shift data
        report2 = ReportService.save_report(
            user=self.user,
            report_data={
                'site': self.site.id,
                'report_date': self.today,
                'reported_by_name': 'Amit Verma',
                'reported_by_designation': 'Site Engineer',
                'work_done_today': 'Morning shift excavation + Evening concreting',
            },
            manpower_rows=[
                {
                    'category': ManpowerCategory.LABOUR,
                    'type': ManpowerType.CONTRACTOR,
                    'worker_count': 5,
                    'rate_per_head': Decimal('600.00'),
                },
                {
                    'category': ManpowerCategory.MASON,
                    'type': ManpowerType.PERMANENT,
                    'worker_count': 3,
                    'rate_per_head': Decimal('850.00'),
                }
            ],
            machinery_rows=[],
            employee_rows=[],
            submit_action='save_draft'
        )

        # Both should point to the same updated report
        self.assertEqual(report1.id, report2.id)
        self.assertEqual(report2.total_site_cost, Decimal('5550.00'))
        self.assertIn("Evening concreting", report2.work_done_today)


class SiteDetailWorkHistoryTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='engineer', password='password123')
        UserProfile.objects.create(user=self.user, role=UserRole.SITE_ENGINEER)
        self.client.login(username='engineer', password='password123')

        self.site = Site.objects.create(
            name="1391 Meerut",
            code="1391",
            location="Meerut Project Site",
            status="ACTIVE"
        )

    def test_site_detail_view_work_history(self):
        """Verify that opening a site displays its work timeline and month-wise spend."""
        report = ReportService.save_report(
            user=self.user,
            report_data={
                'site': self.site.id,
                'report_date': date(2026, 10, 30),
                'reported_by_name': 'Amit Verma',
                'reported_by_designation': 'Site Engineer',
                'work_done_today': 'Pier 12 drilling and chemical rebar anchoring',
            },
            manpower_rows=[{
                'category': ManpowerCategory.LABOUR,
                'type': ManpowerType.CONTRACTOR,
                'worker_count': 6,
                'rate_per_head': Decimal('600.00'),
            }],
            machinery_rows=[],
            employee_rows=[],
            submit_action='save_draft'
        )

        response = self.client.get(reverse('site_detail', args=[self.site.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1391 Meerut")
        self.assertContains(response, "Pier 12 drilling and chemical rebar anchoring")
        self.assertContains(response, "Month-Wise Spend Summary")

    def test_report_tools_entry_saved(self):
        report = ReportService.save_report(
            user=self.user,
            report_data={
                'site': self.site.id,
                'report_date': date(2026, 10, 30),
                'reported_by_name': 'Amit Verma',
                'reported_by_designation': 'Site Engineer',
                'work_done_today': 'Pier cutting and drilling',
            },
            manpower_rows=[],
            machinery_rows=[],
            employee_rows=[],
            tool_rows=[
                {
                    'tool_name': 'Bosch 14-Inch Cut-Off Saw',
                    'quantity': 2,
                    'used_by': 'Jahid',
                    'remarks': 'Rebar cutting',
                }
            ],
            submit_action='save_draft'
        )
        self.assertEqual(report.tool_entries.count(), 1)
        tool = report.tool_entries.first()
        self.assertEqual(tool.tool_name, 'Bosch 14-Inch Cut-Off Saw')
        self.assertEqual(tool.quantity, 2)
        self.assertEqual(tool.used_by, 'Jahid')

