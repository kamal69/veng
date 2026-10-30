from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from reports.models import (
    UserProfile, UserRole, Site, Employee, SiteReport,
    ManpowerEntry, MachineryEntry, EmployeeSiteVisit, ReportAuditLog, ReportToolEntry,
    ManpowerCategory, ManpowerType, MachineryOwnership, MachineryBillingBasis, VisitType
)


class Command(BaseCommand):
    help = "Seeds initial roles, users, sites, employees, and realistic construction site reports"

    def handle(self, *args, **options):
        self.stdout.write("Initializing system demo data...")

        # 1. Create Users & Profiles
        users_data = [
            ('admin', 'admin@vikaseng.com', 'admin123', 'Rajesh', 'Sharma', UserRole.ADMIN, 'Chief Operations Officer', '+91 98200 11223', True),
            ('engineer', 'engineer@vikaseng.com', 'engineer123', 'Amit', 'Verma', UserRole.SITE_ENGINEER, 'Senior Site Engineer', '+91 98200 44556', False),
            ('manager', 'manager@vikaseng.com', 'manager123', 'Pooja', 'Mehta', UserRole.MANAGEMENT, 'General Manager - Projects', '+91 98200 77889', False),
        ]

        created_users = {}
        for username, email, pwd, first, last, role, desig, phone, is_staff in users_data:
            user, created = User.objects.get_or_create(username=username, defaults={'email': email, 'first_name': first, 'last_name': last})
            user.set_password(pwd)
            user.is_staff = is_staff
            user.is_superuser = (role == UserRole.ADMIN)
            user.save()

            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.designation = desig
            profile.phone = phone
            profile.save()
            created_users[username] = user
            self.stdout.write(f"  User '{username}' ({role}) ready. Password: {pwd}")

        # 2. Create Construction Sites (Real sites from Expense Workbook)
        sites_data = [
            ("Tepla Project", "SITE-TEPLA", "Tepla Site Office & Work Strata", "Vikas Engineering", "ACTIVE"),
            ("Rock Rose Sector 20 Chandigarh", "SITE-ROCKROSE", "Sector 20, Chandigarh", "Vikas Engineering", "ACTIVE"),
            ("VRK Banquet", "SITE-VRK", "VRK Palace & Banquet Complex", "Vikas Engineering", "ACTIVE"),
            ("Mohinder, Lalru", "SITE-LALRU", "Lalru Industrial Corridor", "Mohinder Pavers", "ACTIVE"),
            ("Guru Teg Bahadur, Anandpur Sahib", "SITE-GTB-AS", "Anandpur Sahib Project", "Vikas Engineering", "ACTIVE"),
            ("Birumal Jairam, Amloh", "SITE-BIRUMAL", "Amloh Strata Project", "Birumal Jairam", "ACTIVE"),
            ("Vikas Engg (Head Office)", "SITE-HQ", "Head Office Operations", "Vikas Engineering", "ACTIVE"),
            ("VIBRA", "SITE-VIBRA", "Vibra Project Site", "Vikas Engineering", "ACTIVE"),
            ("ALPAS", "SITE-ALPAS", "Alpas Location", "Vikas Engineering", "ACTIVE"),
        ]

        created_sites = []
        for name, code, loc, client, status in sites_data:
            site = Site.objects.filter(code=code).first() or Site.objects.filter(name=name).first()
            if site:
                site.name = name
                site.code = code
                site.location = loc
                site.client_name = client
                site.status = status
                site.save()
            else:
                site = Site.objects.create(name=name, code=code, location=loc, client_name=client, status=status)
            created_sites.append(site)

        # Assign sites to engineer
        created_users['engineer'].profile.assigned_sites.set(created_sites[:3])

        # 3. Create Company Employees (with daily & hourly rates)
        employees_data = [
            ("EMP-001", "Vikram Patel", "Project Manager", "Projects", "+91 98111 22334", Decimal('4500.00'), Decimal('600.00')),
            ("EMP-002", "Suresh Kulkarni", "Senior Quality Engineer", "Quality Control", "+91 98222 33445", Decimal('3200.00'), Decimal('420.00')),
            ("EMP-003", "Deepak Rao", "Chief Safety Officer", "EHS & Safety", "+91 98333 44556", Decimal('2800.00'), Decimal('370.00')),
            ("EMP-004", "Rohan Nair", "Site Surveyor", "Engineering", "+91 98444 55667", Decimal('2200.00'), Decimal('300.00')),
            ("EMP-005", "Anita Deshmukh", "Structural Consultant", "Design & Planning", "+91 98555 66778", Decimal('5000.00'), Decimal('750.00')),
            ("EMP-006", "Karan Malhotra", "Electrical Supervisor", "MEP", "+91 98666 77889", Decimal('2400.00'), Decimal('320.00')),
        ]

        created_employees = []
        for emp_id, name, desig, dept, phone, d_rate, h_rate in employees_data:
            emp, _ = Employee.objects.get_or_create(
                employee_id=emp_id,
                defaults={
                    'name': name, 'designation': desig, 'department': dept,
                    'phone': phone, 'daily_rate': d_rate, 'hourly_rate': h_rate, 'is_active': True
                }
            )
            created_employees.append(emp)

        # 4. Generate Realistic Historical Reports (Past 5 days + Today)
        today = timezone.localdate()
        engineer_user = created_users['engineer']
        admin_user = created_users['admin']

        # Clear existing sample reports to avoid duplicate validation on re-seed
        SiteReport.objects.all().delete()

        report_blueprints = [
            # Day 0 (Today): Active draft / submitted reports
            {
                'days_ago': 0,
                'site': created_sites[0],
                'status': SiteReport.ReportStatus.SUBMITTED,
                'site_status': SiteReport.SiteStatus.IN_PROGRESS,
                'work': "Erection of precast concrete pier caps on Pier 112. Reinforcement steel binding for pier 114 base. Total 42 MT steel tied.",
                'remarks': "Concrete batching plant dispatch delayed by 45 mins due to traffic at highway.",
                'manpower': [
                    (ManpowerCategory.LABOUR, ManpowerType.CONTRACTOR, 24, Decimal('650.00'), "Pier cap rigging & lifting support"),
                    (ManpowerCategory.MASON, ManpowerType.CHOWK, 8, Decimal('950.00'), "Base levelling and pedestal mortar grouting"),
                    (ManpowerCategory.OTHER_CONTRACTOR, ManpowerType.CONTRACTOR, 6, Decimal('850.00'), "Bar benders for steel reinforcement cage"),
                ],
                'machinery': [
                    ("75T Telescopic Mobile Crane", MachineryOwnership.RENTAL, Decimal('1.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('18000.00'), "For pier cap hoisting"),
                    ("Hydraulic Transit Mixer (6 cum)", MachineryOwnership.RENTAL, Decimal('2.00'), MachineryBillingBasis.HOUR, Decimal('6.00'), Decimal('1200.00'), "Ready mix delivery"),
                    ("DG Power Generator 125 KVA", MachineryOwnership.COMPANY_OWNED, Decimal('1.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('0.00'), "Site power supply"),
                ],
                'visits': [
                    (created_employees[1], VisitType.FULL_DAY, Decimal('0.00'), "Pre-pour reinforcement checklist inspection"),
                    (created_employees[2], VisitType.HALF_DAY, Decimal('0.00'), "Height safety harness and rigging audit"),
                ],
                'tools': [
                    ("Electric Rebar Cutter & Bending Machine", Decimal('2.00'), "Reinforcement Crew", "Cutting 25mm TMT bars"),
                    ("Total Station Survey Equipment", Decimal('1.00'), "Surveyor Team", "Alignment & pier axis verification"),
                    ("Heavy Duty Air Compressor", Decimal('1.00'), "Cleaning Gang", "Dust clearance before pour"),
                ]
            },
            {
                'days_ago': 0,
                'site': created_sites[1],
                'status': SiteReport.ReportStatus.DRAFT,
                'site_status': SiteReport.SiteStatus.IN_PROGRESS,
                'work': "Shuttering work on approach span pier 4. Excavation for abutment wall foundation in rock strata.",
                'remarks': "High water table requires dewatering submersible pumps running continuously.",
                'manpower': [
                    (ManpowerCategory.LABOUR, ManpowerType.PERMANENT, 14, Decimal('700.00'), "Excavation and muck clearing"),
                    (ManpowerCategory.MASON, ManpowerType.CONTRACTOR, 6, Decimal('900.00'), "Foundation formwork setup"),
                ],
                'machinery': [
                    ("JCB 3DX Super Excavator", MachineryOwnership.RENTAL, Decimal('1.00'), MachineryBillingBasis.HOUR, Decimal('8.00'), Decimal('1450.00'), "Rock breaker and excavation"),
                    ("Submersible Dewatering Pump 10 HP", MachineryOwnership.RENTAL, Decimal('2.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('1800.00'), "Water evacuation"),
                ],
                'visits': [
                    (created_employees[3], VisitType.FULL_DAY, Decimal('0.00'), "Abutment level check with Total Station"),
                ],
                'tools': [
                    ("Rotary Hammer Drill", Decimal('3.00'), "Mason Team", "Anchor bolt dowel fixing"),
                    ("Submersible Pump Hose Sets", Decimal('4.00'), "Excavation Crew", "Trench dewatering"),
                ]
            },
            # Yesterday (Approved)
            {
                'days_ago': 1,
                'site': created_sites[0],
                'status': SiteReport.ReportStatus.APPROVED,
                'site_status': SiteReport.SiteStatus.IN_PROGRESS,
                'work': "Concrete pouring of pier 110 column M50 grade (total 68 cum). Continuous vibrating and curing pond setup on pier 108.",
                'remarks': "All 7-day and 28-day cube samples successfully taken by QC engineer.",
                'manpower': [
                    (ManpowerCategory.LABOUR, ManpowerType.CONTRACTOR, 28, Decimal('650.00'), "Concreting shift and chute handling"),
                    (ManpowerCategory.MASON, ManpowerType.CHOWK, 10, Decimal('950.00'), "Surface screeding and column head finish"),
                    (ManpowerCategory.OTHER_CONTRACTOR, ManpowerType.CONTRACTOR, 4, Decimal('800.00'), "Formwork carpenters"),
                ],
                'machinery': [
                    ("Boom Concrete Placer 36m", MachineryOwnership.RENTAL, Decimal('1.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('22000.00'), "High lift concrete pump"),
                    ("Needle Concrete Vibrator (Electric)", MachineryOwnership.COMPANY_OWNED, Decimal('4.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('0.00'), "Company assets"),
                ],
                'visits': [
                    (created_employees[0], VisitType.HALF_DAY, Decimal('0.00'), "Site inspection with client executives"),
                    (created_employees[1], VisitType.FULL_DAY, Decimal('0.00'), "Slump tests and pour monitoring"),
                ],
                'tools': [
                    ("High Frequency Needle Vibrators (60mm)", Decimal('4.00'), "Concreting Team", "Pier column pour compaction"),
                    ("Laser Distance Meter & Auto Level", Decimal('2.00'), "QC Team", "Level mark verification"),
                ]
            },
            # 2 days ago (Approved)
            {
                'days_ago': 2,
                'site': created_sites[2],
                'status': SiteReport.ReportStatus.APPROVED,
                'site_status': SiteReport.SiteStatus.IN_PROGRESS,
                'work': "6th floor post-tensioned slab cable laying and duct profiling. Internal masonry walls 4th floor.",
                'remarks': "PT strand tensioning scheduled for Friday morning.",
                'manpower': [
                    (ManpowerCategory.LABOUR, ManpowerType.CONTRACTOR, 32, Decimal('650.00'), "Material shifting and duct placement"),
                    (ManpowerCategory.MASON, ManpowerType.CONTRACTOR, 12, Decimal('920.00'), "AAC block masonry with polymer adhesive"),
                    (ManpowerCategory.PAINTER, ManpowerType.CONTRACTOR, 5, Decimal('850.00'), "Primer coat in basement 2 parking"),
                ],
                'machinery': [
                    ("Tower Crane 6T (Potain)", MachineryOwnership.RENTAL, Decimal('1.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('16000.00'), "Vertical material lifting"),
                    ("Passenger & Material Hoist", MachineryOwnership.RENTAL, Decimal('1.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('6500.00'), "Floor movement"),
                ],
                'visits': [
                    (created_employees[4], VisitType.HALF_DAY, Decimal('0.00'), "Structural inspection of tendon curvature"),
                    (created_employees[2], VisitType.HALF_DAY, Decimal('0.00'), "Edge protection & debris netting audit"),
                ],
                'tools': [
                    ("PT Multi-Strand Hydraulic Stressing Jack", Decimal('1.00'), "PT Specialist", "Pre-stressing preparation"),
                    ("High Pressure Grout Pump Machine", Decimal('1.00'), "Grouting Operator", "Duct pressure test"),
                ]
            },
            # 3 days ago (Approved)
            {
                'days_ago': 3,
                'site': created_sites[3],
                'status': SiteReport.ReportStatus.APPROVED,
                'site_status': SiteReport.SiteStatus.IN_PROGRESS,
                'work': "Dense Bituminous Macadam (DBM) paving on left carriageway KM 88+200 to 89+100 (total 900 lane meters).",
                'remarks': "Hot mix asphalt delivered at 155°C maintained as per MoRTH standards.",
                'manpower': [
                    (ManpowerCategory.LABOUR, ManpowerType.CONTRACTOR, 20, Decimal('650.00'), "Tack coat spraying and joint finishing"),
                    (ManpowerCategory.MASON, ManpowerType.CHOWK, 4, Decimal('950.00'), "Kerbstone fixing and edge drain channels"),
                ],
                'machinery': [
                    ("Sensor Paver Vogele Super 1800", MachineryOwnership.RENTAL, Decimal('1.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('35000.00'), "Asphalt paving"),
                    ("Tandem Vibratory Roller 10T", MachineryOwnership.RENTAL, Decimal('2.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('7500.00'), "Breakdown & intermediate rolling"),
                    ("Pneumatic Tyre Roller (PTR)", MachineryOwnership.RENTAL, Decimal('1.00'), MachineryBillingBasis.DAY, Decimal('1.00'), Decimal('8000.00'), "Finish rolling"),
                ],
                'visits': [
                    (created_employees[0], VisitType.FULL_DAY, Decimal('0.00'), "NHAI independent engineer site inspection"),
                ],
                'tools': [
                    ("Bitumen Sprayer Lance Guns", Decimal('2.00'), "Road Gang", "Emulsion tack coat spraying"),
                    ("Core Cutting Machine 150mm", Decimal('1.00'), "Quality Lab Tech", "Pavement thickness check"),
                ]
            },
        ]

        for bp in report_blueprints:
            r_date = today - timedelta(days=bp['days_ago'])
            report = SiteReport.objects.create(
                site=bp['site'],
                report_date=r_date,
                status=bp['status'],
                site_status=bp['site_status'],
                reported_by_name=engineer_user.get_full_name(),
                reported_by_designation="Senior Site Engineer",
                reported_by_user=engineer_user,
                company_employees_on_site="Amit Verma (Site Eng), Safety Supervisor",
                work_done_today=bp['work'],
                remarks=bp['remarks'],
                submitted_at=timezone.now() if bp['status'] in (SiteReport.ReportStatus.SUBMITTED, SiteReport.ReportStatus.APPROVED) else None,
                submitted_by=engineer_user if bp['status'] in (SiteReport.ReportStatus.SUBMITTED, SiteReport.ReportStatus.APPROVED) else None,
                approved_at=timezone.now() if bp['status'] == SiteReport.ReportStatus.APPROVED else None,
                approved_by=admin_user if bp['status'] == SiteReport.ReportStatus.APPROVED else None,
            )

            # Manpower
            for cat, m_type, count, rate, rem in bp['manpower']:
                ManpowerEntry.objects.create(
                    site_report=report,
                    category=cat,
                    type=m_type,
                    worker_count=count,
                    rate_per_head=rate,
                    remarks=rem
                )

            # Machinery
            for m_name, own, qty, basis, usage, rate, rem in bp['machinery']:
                MachineryEntry.objects.create(
                    site_report=report,
                    machine_name=m_name,
                    ownership=own,
                    quantity=qty,
                    billing_basis=basis,
                    usage_value=usage,
                    rate=rate,
                    remarks=rem
                )

            # Employee visits
            for emp, v_type, hours, rem in bp['visits']:
                EmployeeSiteVisit.objects.create(
                    site_report=report,
                    employee=emp,
                    designation_snapshot=emp.designation,
                    visit_type=v_type,
                    hours_spent=hours,
                    remarks=rem
                )

            # Tools & Equipment
            for t_name, qty, used_by, rem in bp.get('tools', []):
                ReportToolEntry.objects.create(
                    site_report=report,
                    tool_name=t_name,
                    quantity=qty,
                    used_by=used_by,
                    remarks=rem
                )

            report.recalculate_totals(save=True)

            ReportAuditLog.objects.create(
                site_report=report,
                action='INITIALIZED',
                performed_by=engineer_user,
                notes=f"Report created with total cost of ₹{report.total_site_cost:,.2f}"
            )

            self.stdout.write(f"  Created report for {report.site.name} on {report.report_date}: INR {report.total_site_cost:,.2f}")

        self.stdout.write(self.style.SUCCESS("Demo construction site data successfully populated!"))
