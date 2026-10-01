"""
excel_service.py
Excel import/export for:
  - Enrollment (import trainee list to enroll in a batch)
  - Grades (export grades, import component scores)
  - Attendance (export attendance records)

Uses the openpyxl library (added to requirements.txt).
"""

import io
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


def _check_openpyxl():
    if not OPENPYXL_AVAILABLE:
        raise ImportError("openpyxl is required. Run: pip install openpyxl")


def _style_header(cell, bold=True, bg_color="1A3A5C"):
    """Apply header styling to a cell."""
    cell.font = Font(bold=bold, color="FFFFFF", size=11)
    cell.fill = PatternFill(start_color=bg_color, end_color=bg_color, fill_type="solid")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _style_row(row_cells, even=True):
    bg = "EBF2FA" if even else "FFFFFF"
    for cell in row_cells:
        cell.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
        cell.alignment = Alignment(vertical="center", wrap_text=True)


# ── ENROLLMENT TEMPLATE ───────────────────────────────────────────────────────

def generate_enrollment_template(batch_name: str) -> bytes:
    """
    Generate an Excel template for admins to fill in trainee emails for bulk enrollment.
    Returns bytes of the .xlsx file.
    """
    _check_openpyxl()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Enrollment"

    ws["A1"] = f"Batch: {batch_name}"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws["A2"].font = Font(italic=True, color="666666", size=10)

    headers = ["#", "Trainee Email", "Trainee Name (optional)", "Notes"]
    ws.append([])
    ws.append(headers)
    header_row = ws.max_row
    for col, _ in enumerate(headers, 1):
        _style_header(ws.cell(header_row, col))

    # Add sample row
    ws.append([1, "trainee@example.com", "Optional: Full Name", ""])

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 35
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 25
    ws.row_dimensions[header_row].height = 25

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_enrollment_import(file_bytes: bytes) -> list[dict]:
    """
    Parse an enrollment import file.
    Expects columns: #, Email, Name (optional), Notes (optional)
    Returns list of {"email": str, "name": str|None, "notes": str|None}
    """
    _check_openpyxl()
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active

    results = []
    header_row_idx = None

    for row in ws.iter_rows():
        vals = [str(cell.value).strip() if cell.value is not None else "" for cell in row]
        # Locate header row
        if header_row_idx is None:
            lowered = [v.lower() for v in vals]
            if any("email" in v for v in lowered):
                header_row_idx = row[0].row
                # Find email column index
                email_col = next(i for i, v in enumerate(lowered) if "email" in v)
                name_col = next((i for i, v in enumerate(lowered) if "name" in v), None)
                notes_col = next((i for i, v in enumerate(lowered) if "note" in v), None)
            continue

        if header_row_idx and row[0].row > header_row_idx:
            email = vals[email_col] if email_col < len(vals) else ""
            if not email or "@" not in email:
                continue
            results.append({
                "email": email.lower(),
                "name": vals[name_col] if name_col and name_col < len(vals) else None,
                "notes": vals[notes_col] if notes_col and notes_col < len(vals) else None,
            })

    return results


# ── GRADES EXPORT ─────────────────────────────────────────────────────────────

def export_grades(batch_name: str, components: list, trainee_grades: list) -> bytes:
    """
    Export a grades spreadsheet.
    components: [(id, name, weight), ...]
    trainee_grades: [(trainee_id, name, email, component_scores_dict, final_grade, bonus), ...]
    """
    _check_openpyxl()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Grades"

    ws["A1"] = f"Batch: {batch_name} — Grade Report"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws["A2"].font = Font(italic=True, color="666666", size=10)

    ws.append([])

    headers = ["#", "Name", "Email"]
    for comp in components:
        headers.append(f"{comp[1]} ({comp[2]}%)")
    headers += ["Final Grade", "Bonus", "Total"]

    ws.append(headers)
    header_row = ws.max_row
    for col in range(1, len(headers) + 1):
        _style_header(ws.cell(header_row, col))

    for i, row_data in enumerate(trainee_grades, 1):
        tid, name, email, scores, final, bonus = row_data
        row = [i, name, email]
        for comp in components:
            row.append(scores.get(comp[0], ""))
        row.append(f"{final:.1f}" if final is not None else "N/A")
        row.append(bonus or 0)
        total = (final or 0) + (bonus or 0)
        row.append(f"{min(total, 100):.1f}")
        ws.append(row)
        _style_row(ws[ws.max_row], even=(i % 2 == 0))

    # Column widths
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 35
    for col_idx in range(4, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── ATTENDANCE EXPORT ─────────────────────────────────────────────────────────

def export_attendance(batch_name: str, attendance_data: list) -> bytes:
    """
    Export attendance records.
    attendance_data: [(trainee_name, date, status, session_title|None), ...]
    """
    _check_openpyxl()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance"

    ws["A1"] = f"Batch: {batch_name} — Attendance Report"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws["A2"].font = Font(italic=True, color="666666", size=10)

    ws.append([])

    headers = ["#", "Trainee Name", "Date", "Status", "Session"]
    ws.append(headers)
    header_row = ws.max_row
    for col in range(1, len(headers) + 1):
        _style_header(ws.cell(header_row, col))

    status_colors = {
        "present": "C6EFCE",
        "absent": "FFC7CE",
        "late": "FFEB9C",
        "excused": "D9E1F2",
    }

    for i, (name, date, status, session) in enumerate(attendance_data, 1):
        ws.append([i, name, date, status.capitalize(), session or ""])
        color = status_colors.get(status, "FFFFFF")
        for col in range(1, 6):
            ws.cell(ws.max_row, col).fill = PatternFill(
                start_color=color, end_color=color, fill_type="solid"
            )

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 15
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 25

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
