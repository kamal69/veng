import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


HEADER_FILL = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

SECTION_FILL = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
SECTION_FONT = Font(name="Calibri", size=11, bold=True, color="0F172A")

SUBTOTAL_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
SUBTOTAL_FONT = Font(name="Calibri", size=11, bold=True, color="92400E")

TOTAL_FILL = PatternFill(start_color="10B981", end_color="10B981", fill_type="solid")
TOTAL_FONT = Font(name="Calibri", size=12, bold=True, color="FFFFFF")

THIN_BORDER = Border(
    left=Side(style='thin', color='CBD5E1'),
    right=Side(style='thin', color='CBD5E1'),
    top=Side(style='thin', color='CBD5E1'),
    bottom=Side(style='thin', color='CBD5E1')
)


def export_single_report_to_excel(report):
    """
    Generate a formatted Excel workbook for a single Daily Site Report.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = f"Report-{report.report_date}"

    # Title block
    ws.merge_cells("A1:G1")
    title_cell = ws["A1"]
    title_cell.value = "VIKAS ENGINEERING & INFRASTRUCTURE"
    title_cell.font = Font(name="Calibri", size=16, bold=True, color="1E3A8A")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("A2:G2")
    sub_title = ws["A2"]
    sub_title.value = f"DAILY SITE REPORT & COST SUMMARY - {report.site.name.upper()}"
    sub_title.font = Font(name="Calibri", size=12, bold=True, color="475569")
    sub_title.alignment = Alignment(horizontal="center", vertical="center")

    # Metadata Grid
    meta = [
        ("Date", report.report_date.strftime("%d-%b-%Y"), "Site Code", report.site.code),
        ("Site Name", report.site.name, "Site Status", report.get_site_status_display()),
        ("Reported By", f"{report.reported_by_name} ({report.reported_by_designation})", "Report Status", report.get_status_display()),
        ("Company Staff", report.company_employees_on_site or "N/A", "Approved By", report.approved_by.get_full_name() if report.approved_by else "Pending Approval"),
    ]

    row_idx = 4
    for label1, val1, label2, val2 in meta:
        ws.cell(row=row_idx, column=1, value=label1).font = Font(bold=True)
        ws.cell(row=row_idx, column=2, value=val1)
        ws.cell(row=row_idx, column=4, value=label2).font = Font(bold=True)
        ws.cell(row=row_idx, column=5, value=val2)
        row_idx += 1

    row_idx += 1

    # 1. Manpower Section
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=6)
    sec_cell = ws.cell(row=row_idx, column=1, value="1. MANPOWER BREAKDOWN")
    sec_cell.font = SECTION_FONT
    sec_cell.fill = SECTION_FILL
    row_idx += 1

    mp_headers = ["Category", "Type", "Worker Count", "Rate per Head (INR)", "Total Cost (INR)", "Remarks"]
    for col_idx, header in enumerate(mp_headers, 1):
        c = ws.cell(row=row_idx, column=col_idx, value=header)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.border = THIN_BORDER
        c.alignment = Alignment(horizontal="center")
    row_idx += 1

    mp_start_row = row_idx
    manpower_list = list(report.manpower_entries.all())
    if manpower_list:
        for item in manpower_list:
            ws.cell(row=row_idx, column=1, value=item.category).border = THIN_BORDER
            ws.cell(row=row_idx, column=2, value=item.type).border = THIN_BORDER
            c_cnt = ws.cell(row=row_idx, column=3, value=item.worker_count)
            c_cnt.border = THIN_BORDER
            c_cnt.alignment = Alignment(horizontal="right")
            c_rate = ws.cell(row=row_idx, column=4, value=float(item.rate_per_head))
            c_rate.border = THIN_BORDER
            c_rate.number_format = '₹ #,##0.00'
            c_cost = ws.cell(row=row_idx, column=5, value=float(item.total_cost))
            c_cost.border = THIN_BORDER
            c_cost.number_format = '₹ #,##0.00'
            ws.cell(row=row_idx, column=6, value=item.remarks).border = THIN_BORDER
            row_idx += 1
    else:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=6)
        c = ws.cell(row=row_idx, column=1, value="No manpower entries recorded.")
        c.alignment = Alignment(horizontal="center")
        row_idx += 1

    # Manpower Subtotal
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=4)
    c_sub = ws.cell(row=row_idx, column=1, value=f"Manpower Subtotal ({report.total_manpower_count} Workers):")
    c_sub.font = SUBTOTAL_FONT
    c_sub.fill = SUBTOTAL_FILL
    c_sub.alignment = Alignment(horizontal="right")
    c_val = ws.cell(row=row_idx, column=5, value=float(report.total_manpower_cost))
    c_val.font = SUBTOTAL_FONT
    c_val.fill = SUBTOTAL_FILL
    c_val.number_format = '₹ #,##0.00'
    ws.cell(row=row_idx, column=6).fill = SUBTOTAL_FILL
    row_idx += 2

    # 2. Machinery Section
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=7)
    sec_cell = ws.cell(row=row_idx, column=1, value="2. MACHINERY & EQUIPMENT ON SITE")
    sec_cell.font = SECTION_FONT
    sec_cell.fill = SECTION_FILL
    row_idx += 1

    mac_headers = ["Machine Name", "Ownership", "Quantity", "Billing Basis", "Usage", "Rate (INR)", "Rental Total (INR)"]
    for col_idx, header in enumerate(mac_headers, 1):
        c = ws.cell(row=row_idx, column=col_idx, value=header)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.border = THIN_BORDER
        c.alignment = Alignment(horizontal="center")
    row_idx += 1

    machinery_list = list(report.machinery_entries.all())
    if machinery_list:
        for item in machinery_list:
            ws.cell(row=row_idx, column=1, value=item.machine_name).border = THIN_BORDER
            ws.cell(row=row_idx, column=2, value=item.get_ownership_display()).border = THIN_BORDER
            ws.cell(row=row_idx, column=3, value=float(item.quantity)).border = THIN_BORDER
            ws.cell(row=row_idx, column=4, value=item.get_billing_basis_display()).border = THIN_BORDER
            ws.cell(row=row_idx, column=5, value=float(item.usage_value)).border = THIN_BORDER
            c_rate = ws.cell(row=row_idx, column=6, value=float(item.rate))
            c_rate.border = THIN_BORDER
            c_rate.number_format = '₹ #,##0.00'
            c_cost = ws.cell(row=row_idx, column=7, value=float(item.rental_cost))
            c_cost.border = THIN_BORDER
            c_cost.number_format = '₹ #,##0.00'
            row_idx += 1
    else:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=7)
        c = ws.cell(row=row_idx, column=1, value="No machinery entries recorded.")
        c.alignment = Alignment(horizontal="center")
        row_idx += 1

    # Machinery Subtotal
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=6)
    c_sub = ws.cell(row=row_idx, column=1, value="Rental Machinery Subtotal:")
    c_sub.font = SUBTOTAL_FONT
    c_sub.fill = SUBTOTAL_FILL
    c_sub.alignment = Alignment(horizontal="right")
    c_val = ws.cell(row=row_idx, column=7, value=float(report.total_machinery_cost))
    c_val.font = SUBTOTAL_FONT
    c_val.fill = SUBTOTAL_FILL
    c_val.number_format = '₹ #,##0.00'
    row_idx += 2

    # 3. Employee Visits Section (Only if visits exist)
    visit_list = list(report.employee_visits.all())
    if visit_list:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=6)
        sec_cell = ws.cell(row=row_idx, column=1, value="3. COMPANY EMPLOYEE SITE VISITS")
        sec_cell.font = SECTION_FONT
        sec_cell.fill = SECTION_FILL
        row_idx += 1

        emp_headers = ["Employee Name", "Designation", "Visit Type", "Hours", "Applied Rate (INR)", "Allocated Cost (INR)"]
        for col_idx, header in enumerate(emp_headers, 1):
            c = ws.cell(row=row_idx, column=col_idx, value=header)
            c.font = HEADER_FONT
            c.fill = HEADER_FILL
            c.border = THIN_BORDER
            c.alignment = Alignment(horizontal="center")
        row_idx += 1

        for item in visit_list:
            ws.cell(row=row_idx, column=1, value=item.employee.name).border = THIN_BORDER
            ws.cell(row=row_idx, column=2, value=item.designation_snapshot).border = THIN_BORDER
            ws.cell(row=row_idx, column=3, value=item.get_visit_type_display()).border = THIN_BORDER
            ws.cell(row=row_idx, column=4, value=float(item.hours_spent)).border = THIN_BORDER
            c_rate = ws.cell(row=row_idx, column=5, value=float(item.applied_rate))
            c_rate.border = THIN_BORDER
            c_rate.number_format = '₹ #,##0.00'
            c_cost = ws.cell(row=row_idx, column=6, value=float(item.allocated_cost))
            c_cost.border = THIN_BORDER
            c_cost.number_format = '₹ #,##0.00'
            row_idx += 1

        # Employee Subtotal
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=5)
        c_sub = ws.cell(row=row_idx, column=1, value="Employee Site Visit Cost Subtotal:")
        c_sub.font = SUBTOTAL_FONT
        c_sub.fill = SUBTOTAL_FILL
        c_sub.alignment = Alignment(horizontal="right")
        c_val = ws.cell(row=row_idx, column=6, value=float(report.total_employee_cost))
        c_val.font = SUBTOTAL_FONT
        c_val.fill = SUBTOTAL_FILL
        c_val.number_format = '₹ #,##0.00'
        row_idx += 2

    # Grand Cost Summary Table
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=4)
    sec_num = "4" if visit_list else "3"
    sec_cell = ws.cell(row=row_idx, column=1, value=f"{sec_num}. SITE COST SUMMARY (TODAY)")
    sec_cell.font = SECTION_FONT
    sec_cell.fill = SECTION_FILL
    row_idx += 1

    cost_summary_items = [
        ("Total Manpower Cost", float(report.total_manpower_cost)),
        ("Total Rental Machinery Cost", float(report.total_machinery_cost)),
        ("Total Company Employee Cost", float(report.total_employee_cost)),
    ]

    for label, val in cost_summary_items:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=3)
        c_lbl = ws.cell(row=row_idx, column=1, value=label)
        c_lbl.font = Font(bold=True)
        c_lbl.border = THIN_BORDER
        c_val = ws.cell(row=row_idx, column=4, value=val)
        c_val.font = Font(bold=True)
        c_val.number_format = '₹ #,##0.00'
        c_val.border = THIN_BORDER
        row_idx += 1

    # Total Grand Row
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=3)
    c_lbl = ws.cell(row=row_idx, column=1, value="TOTAL SITE COST TODAY")
    c_lbl.font = TOTAL_FONT
    c_lbl.fill = TOTAL_FILL
    c_val = ws.cell(row=row_idx, column=4, value=float(report.total_site_cost))
    c_val.font = TOTAL_FONT
    c_val.fill = TOTAL_FILL
    c_val.number_format = '₹ #,##0.00'
    row_idx += 2

    # Work Details Block
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=6)
    wd_sec_num = "5" if visit_list else "4"
    c_wd = ws.cell(row=row_idx, column=1, value=f"{wd_sec_num}. WORK DETAILS & SITE PROGRESS")
    c_wd.font = SECTION_FONT
    c_wd.fill = SECTION_FILL
    row_idx += 1

    ws.cell(row=row_idx, column=1, value="Today Work:").font = Font(bold=True)
    ws.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx+1, end_column=6)
    ws.cell(row=row_idx, column=2, value=report.work_done_today).alignment = Alignment(wrap_text=True)
    row_idx += 2

    if report.remarks:
        ws.cell(row=row_idx, column=1, value="Remarks:").font = Font(bold=True)
        ws.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx+1, end_column=6)
        ws.cell(row=row_idx, column=2, value=report.remarks).alignment = Alignment(wrap_text=True)
        row_idx += 2

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            if cell.value:
                # ignore merged header lines for width calculation
                if cell.row in [1, 2]:
                    continue
                val_str = str(cell.value)
                if len(val_str) > max_len and len(val_str) < 50:
                    max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def export_bulk_reports_to_excel(reports_qs, title="Site Reports Summary"):
    """
    Generate a multi-sheet Excel workbook covering all filtered reports.
    """
    wb = Workbook()

    # Sheet 1: Master Summary
    ws_sum = wb.active
    ws_sum.title = "Reports Summary"

    ws_sum.merge_cells("A1:H1")
    t = ws_sum["A1"]
    t.value = "VIKAS ENGINEERING - DAILY SITE REPORTS CONSOLIDATED SUMMARY"
    t.font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    t.alignment = Alignment(horizontal="center")

    headers = [
        "Report ID", "Date", "Site Name", "Site Status", "Reported By",
        "Total Workers", "Manpower Cost", "Machinery Cost", "Employee Cost",
        "Total Site Cost", "Status"
    ]
    for col_idx, h in enumerate(headers, 1):
        c = ws_sum.cell(row=3, column=col_idx, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.border = THIN_BORDER
        c.alignment = Alignment(horizontal="center")

    r_idx = 4
    total_workers_all = 0
    total_mp_all = 0.0
    total_mac_all = 0.0
    total_emp_all = 0.0
    total_cost_all = 0.0

    for rep in reports_qs:
        ws_sum.cell(row=r_idx, column=1, value=f"REP-{rep.id:04d}").border = THIN_BORDER
        ws_sum.cell(row=r_idx, column=2, value=rep.report_date.strftime("%d-%b-%Y")).border = THIN_BORDER
        ws_sum.cell(row=r_idx, column=3, value=rep.site.name).border = THIN_BORDER
        ws_sum.cell(row=r_idx, column=4, value=rep.get_site_status_display()).border = THIN_BORDER
        ws_sum.cell(row=r_idx, column=5, value=rep.reported_by_name).border = THIN_BORDER

        c_w = ws_sum.cell(row=r_idx, column=6, value=rep.total_manpower_count)
        c_w.border = THIN_BORDER
        c_w.alignment = Alignment(horizontal="right")

        c_m = ws_sum.cell(row=r_idx, column=7, value=float(rep.total_manpower_cost))
        c_m.border = THIN_BORDER
        c_m.number_format = '₹ #,##0.00'

        c_mac = ws_sum.cell(row=r_idx, column=8, value=float(rep.total_machinery_cost))
        c_mac.border = THIN_BORDER
        c_mac.number_format = '₹ #,##0.00'

        c_e = ws_sum.cell(row=r_idx, column=9, value=float(rep.total_employee_cost))
        c_e.border = THIN_BORDER
        c_e.number_format = '₹ #,##0.00'

        c_tot = ws_sum.cell(row=r_idx, column=10, value=float(rep.total_site_cost))
        c_tot.border = THIN_BORDER
        c_tot.number_format = '₹ #,##0.00'

        ws_sum.cell(row=r_idx, column=11, value=rep.get_status_display()).border = THIN_BORDER

        total_workers_all += rep.total_manpower_count
        total_mp_all += float(rep.total_manpower_cost)
        total_mac_all += float(rep.total_machinery_cost)
        total_emp_all += float(rep.total_employee_cost)
        total_cost_all += float(rep.total_site_cost)

        r_idx += 1

    # Grand Totals Row
    ws_sum.merge_cells(start_row=r_idx, start_column=1, end_row=r_idx, end_column=5)
    c_tot_lbl = ws_sum.cell(row=r_idx, column=1, value="CONSOLIDATED TOTALS:")
    c_tot_lbl.font = TOTAL_FONT
    c_tot_lbl.fill = TOTAL_FILL
    c_tot_lbl.alignment = Alignment(horizontal="right")

    c_tw = ws_sum.cell(row=r_idx, column=6, value=total_workers_all)
    c_tw.font = TOTAL_FONT
    c_tw.fill = TOTAL_FILL

    c_tmp = ws_sum.cell(row=r_idx, column=7, value=total_mp_all)
    c_tmp.font = TOTAL_FONT
    c_tmp.fill = TOTAL_FILL
    c_tmp.number_format = '₹ #,##0.00'

    c_tmac = ws_sum.cell(row=r_idx, column=8, value=total_mac_all)
    c_tmac.font = TOTAL_FONT
    c_tmac.fill = TOTAL_FILL
    c_tmac.number_format = '₹ #,##0.00'

    c_temp = ws_sum.cell(row=r_idx, column=9, value=total_emp_all)
    c_temp.font = TOTAL_FONT
    c_temp.fill = TOTAL_FILL
    c_temp.number_format = '₹ #,##0.00'

    c_ttot = ws_sum.cell(row=r_idx, column=10, value=total_cost_all)
    c_ttot.font = TOTAL_FONT
    c_ttot.fill = TOTAL_FILL
    c_ttot.number_format = '₹ #,##0.00'

    ws_sum.cell(row=r_idx, column=11).fill = TOTAL_FILL

    # Auto column widths
    for col in ws_sum.columns:
        col_letter = get_column_letter(col[0].column)
        max_l = max(len(str(c.value or '')) for c in col if c.row > 1)
        ws_sum.column_dimensions[col_letter].width = max(max_l + 3, 14)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
