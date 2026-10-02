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


# ── OFFICIAL BATCH REPORT ────────────────────────────────────────────────────

_ACADEMY_NAVY = "1A3A5C"
_ACADEMY_BLUE = "DCE6F1"
_ACADEMY_PALE = "F4F7FA"
_ACADEMY_BORDER = "C8D2DC"
_ATTENDANCE_LABELS = {
    "present": "حاضر",
    "absent": "غائب",
    "late": "متأخر",
    "excused": "مستأذن",
}
_ATTENDANCE_FILLS = {
    "present": "E2F0D9",
    "absent": "FCE4D6",
    "late": "FFF2CC",
    "excused": "DDEBF7",
}


def build_batch_grade_rows(components, trainees, score_rows, bonus_totals):
    """Build export rows from one batch score dataset without per-trainee queries."""
    scores_by_trainee = {}
    for trainee_id, _name, component_id, _component_name, _weight, score in score_rows:
        if score is not None:
            scores_by_trainee.setdefault(trainee_id, {})[component_id] = score

    total_weight = sum(float(component[3] or 0) for component in components)
    grade_rows = []
    for trainee in trainees:
        trainee_id = trainee[0]
        scores = scores_by_trainee.get(trainee_id, {})
        if not components or total_weight == 0:
            final_grade = None
        else:
            final_grade = round(sum(
                (float(scores[component[0]]) / 100.0) * float(component[3])
                for component in components
                if component[0] in scores
            ), 2)
        bonus = bonus_totals.get(trainee_id, 0) or 0
        grade_rows.append((
            trainee_id, trainee[1], trainee[2], scores, final_grade, bonus
        ))
    return grade_rows


def _set_document_layout(ws, last_column, last_row, freeze_panes="C9", title_rows="1:8"):
    ws.sheet_view.rightToLeft = True
    ws.freeze_panes = freeze_panes
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.45
    ws.page_margins.bottom = 0.45
    ws.page_margins.header = 0.2
    ws.page_margins.footer = 0.2
    ws.print_title_rows = title_rows
    ws.print_area = f"A1:{get_column_letter(last_column)}{last_row}"


def _style_document_title(ws, last_column, academy_name, report_title):
    end = get_column_letter(last_column)
    ws.merge_cells(f"A1:{end}1")
    ws.merge_cells(f"A2:{end}2")
    ws["A1"] = academy_name or ""
    ws["A2"] = report_title
    for cell_ref, size, color in (("A1", 15, "FFFFFF"), ("A2", 12, "FFFFFF")):
        cell = ws[cell_ref]
        cell.font = Font(name="Arial", size=size, bold=True, color=color)
        cell.fill = PatternFill("solid", fgColor=_ACADEMY_NAVY)
        cell.alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 25


def _add_document_metadata(ws, batch_info, session_count):
    fields = [
        ("اسم الأكاديمية", batch_info.get("academy_name")),
        ("الدورة التدريبية", batch_info.get("course_name")),
        ("الدفعة", batch_info.get("batch_name")),
        ("المحاضر", batch_info.get("instructor_name")),
        ("تاريخ البداية", batch_info.get("start_date")),
        ("عدد الجلسات", session_count),
    ]
    fields = [(label, value) for label, value in fields if value is not None and value != ""]
    for index, (label, value) in enumerate(fields):
        row = 4 + index // 2
        start_col = 1 if index % 2 == 0 else 3
        value_col = start_col + 1
        label_cell = ws.cell(row, start_col, label)
        value_cell = ws.cell(row, value_col, value)
        for cell in (label_cell, value_cell):
            cell.border = Border(
                left=Side(style="thin", color=_ACADEMY_BORDER),
                right=Side(style="thin", color=_ACADEMY_BORDER),
                top=Side(style="thin", color=_ACADEMY_BORDER),
                bottom=Side(style="thin", color=_ACADEMY_BORDER),
            )
        label_cell.font = Font(name="Arial", size=10, bold=True, color=_ACADEMY_NAVY)
        label_cell.fill = PatternFill("solid", fgColor=_ACADEMY_BLUE)
        label_cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
        value_cell.font = Font(name="Arial", size=10, color="263746")
        value_cell.fill = PatternFill("solid", fgColor="FFFFFF")
        value_cell.alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)
        ws.row_dimensions[row].height = 34


def _style_table_header(ws, row, last_column):
    border = Border(bottom=Side(style="medium", color=_ACADEMY_NAVY))
    for column in range(1, last_column + 1):
        cell = ws.cell(row, column)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=_ACADEMY_NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[row].height = 58


def _style_data_row(ws, row, last_column, alternate=False):
    fill = _ACADEMY_PALE if alternate else "FFFFFF"
    border = Border(bottom=Side(style="thin", color=_ACADEMY_BORDER))
    for column in range(1, last_column + 1):
        cell = ws.cell(row, column)
        cell.font = Font(name="Arial", size=10, color="263746")
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = border
    ws.row_dimensions[row].height = 24


def _attendance_cells(sessions, attendance_records, trainees):
    session_index = {session[0]: index for index, session in enumerate(sessions)}
    sessions_by_date = {}
    for index, session in enumerate(sessions):
        session_date = session[4]
        if session_date:
            sessions_by_date.setdefault(session_date, []).append(index)

    trainee_ids = {trainee[0] for trainee in trainees}
    values = {}
    counts = {trainee_id: {status: 0 for status in _ATTENDANCE_LABELS} for trainee_id in trainee_ids}
    totals = {trainee_id: 0 for trainee_id in trainee_ids}
    warnings = []

    for trainee_id, trainee_name, attendance_date, status, session_id in attendance_records:
        if trainee_id not in trainee_ids:
            continue
        totals[trainee_id] += 1
        if status in counts[trainee_id]:
            counts[trainee_id][status] += 1

        target_index = session_index.get(session_id) if session_id is not None else None
        if target_index is None and session_id is None:
            date_matches = sessions_by_date.get(attendance_date, [])
            if len(date_matches) == 1:
                target_index = date_matches[0]
            elif len(date_matches) > 1:
                for index in date_matches:
                    values[(trainee_id, index)] = "غير محدد"
                warnings.append(
                    f"{trainee_name} — {attendance_date}: يتعذر إسناد سجل الحضور إلى جلسة واحدة من جلسات هذا اليوم."
                )
                continue

        if target_index is None:
            warnings.append(
                f"{trainee_name} — {attendance_date}: سجل الحضور غير مرتبط بجلسة معروفة في هذه الدفعة."
            )
            continue

        label = _ATTENDANCE_LABELS.get(status, "قيمة غير معروفة")
        values[(trainee_id, target_index)] = label
        if status not in _ATTENDANCE_LABELS:
            warnings.append(f"{trainee_name} — {attendance_date}: حالة حضور غير معروفة ({status}).")

    return values, counts, totals, warnings, sessions_by_date


def build_official_batch_workbook(batch_info, sessions, trainees, attendance_records,
                                  components, score_rows, bonus_totals) -> bytes:
    """Create the official Arabic two-sheet batch workbook from current app data."""
    _check_openpyxl()
    workbook = openpyxl.Workbook()
    attendance_ws = workbook.active
    attendance_ws.title = "الحضور"
    grades_ws = workbook.create_sheet("الدرجات")
    academy_name = batch_info.get("academy_name", "")

    # Attendance matrix and record-based summary.
    attendance_values, attendance_counts, attendance_totals, warnings, sessions_by_date = _attendance_cells(
        sessions, attendance_records, trainees
    )
    attendance_last_column = max(2 + len(sessions) + 5, 4)
    _style_document_title(attendance_ws, attendance_last_column, academy_name, "كشف الحضور الرسمي")
    _add_document_metadata(attendance_ws, batch_info, len(sessions))
    attendance_ws.merge_cells(start_row=7, start_column=1, end_row=7, end_column=attendance_last_column)
    attendance_ws.cell(
        7, 1,
        "نسبة الحضور محسوبة من سجلات الحضور المسجلة، وليست من عدد الجلسات المخططة أو المكتملة."
    )
    attendance_ws.cell(7, 1).font = Font(name="Arial", size=9, italic=True, color="596B7A")
    attendance_ws.cell(7, 1).alignment = Alignment(horizontal="right", wrap_text=True)

    attendance_header_row = 8
    attendance_headers = ["رقم", "اسم المتدرب"]
    for session in sessions:
        session_number, session_title, session_date, session_status = session[3], session[2], session[4], session[7]
        header_lines = [f"الجلسة {session_number}" if session_number is not None else "الجلسة"]
        if session_date:
            header_lines.append(str(session_date))
        if session_title:
            header_lines.append(str(session_title))
        if session_status == "cancelled":
            header_lines.append("ملغاة")
        attendance_headers.append("\n".join(header_lines))
    attendance_headers.extend([
        "حاضر", "غائب", "متأخر", "مستأذن", "نسبة الحضور\n(من السجلات)",
    ])
    for column, value in enumerate(attendance_headers, 1):
        attendance_ws.cell(attendance_header_row, column, value)
    _style_table_header(attendance_ws, attendance_header_row, attendance_last_column)

    for index, trainee in enumerate(trainees, 1):
        row_number = attendance_header_row + index
        trainee_id = trainee[0]
        attendance_ws.cell(row_number, 1, index)
        attendance_ws.cell(row_number, 2, trainee[1])
        for session_index, _session in enumerate(sessions):
            attendance_ws.cell(
                row_number, 3 + session_index,
                attendance_values.get((trainee_id, session_index))
            )
        summary_start = 3 + len(sessions)
        counts = attendance_counts[trainee_id]
        for offset, status in enumerate(("present", "absent", "late", "excused")):
            attendance_ws.cell(row_number, summary_start + offset, counts[status])
        total = attendance_totals[trainee_id]
        rate = round(counts["present"] / total * 100, 1) if total else 0
        rate_cell = attendance_ws.cell(row_number, summary_start + 4, rate)
        rate_cell.number_format = '0.0"%"'
        _style_data_row(attendance_ws, row_number, attendance_last_column, alternate=index % 2 == 0)
        for session_index in range(len(sessions)):
            cell = attendance_ws.cell(row_number, 3 + session_index)
            if cell.value in _ATTENDANCE_LABELS.values():
                status = next(key for key, label in _ATTENDANCE_LABELS.items() if label == cell.value)
                cell.fill = PatternFill("solid", fgColor=_ATTENDANCE_FILLS[status])
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            elif cell.value == "غير محدد":
                cell.fill = PatternFill("solid", fgColor="FFF2CC")
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for column in (1, *range(3, attendance_last_column + 1)):
            attendance_ws.cell(row_number, column).alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )

    attendance_last_row = attendance_header_row + len(trainees)
    note_row = attendance_last_row + 2
    attendance_ws.cell(note_row, 1, "مفتاح الحالات")
    attendance_ws.cell(note_row, 1).font = Font(name="Arial", bold=True, color=_ACADEMY_NAVY)
    legend = ["حاضر: حاضر", "غائب: غائب", "متأخر: متأخر", "مستأذن: مستأذن", "الخانة الفارغة: لا يوجد سجل مرتبط بالجلسة"]
    if warnings:
        legend.append("غير محدد: يوجد سجل في يوم متعدد الجلسات ولا يمكن تحديد الجلسة بأمان")
    for offset, value in enumerate(legend, 1):
        attendance_ws.cell(note_row + offset, 1, value)
        attendance_ws.cell(note_row + offset, 1).font = Font(name="Arial", size=9, color="596B7A")
    current_note_row = note_row + len(legend) + 1
    if any(len(indices) > 1 for indices in sessions_by_date.values()):
        attendance_ws.cell(
            current_note_row, 1,
            "تنبيه: يوجد أكثر من جلسة في تاريخ واحد؛ قاعدة البيانات تحفظ سجل حضور واحدًا فقط لكل متدرب في اليوم."
        )
        attendance_ws.cell(current_note_row, 1).font = Font(name="Arial", size=9, bold=True, color="9A6700")
        current_note_row += 1
    for warning in warnings:
        attendance_ws.cell(current_note_row, 1, warning)
        attendance_ws.cell(current_note_row, 1).font = Font(name="Arial", size=9, color="9A6700")
        current_note_row += 1
    if not trainees:
        attendance_ws.merge_cells(
            start_row=attendance_header_row + 1, start_column=1,
            end_row=attendance_header_row + 1, end_column=attendance_last_column,
        )
        empty_cell = attendance_ws.cell(attendance_header_row + 1, 1, "لا يوجد متدربون نشطون في هذه الدفعة.")
        empty_cell.font = Font(name="Arial", size=10, italic=True, color="596B7A")
        empty_cell.alignment = Alignment(horizontal="right", vertical="center")
    attendance_ws.column_dimensions["A"].width = 9
    attendance_ws.column_dimensions["B"].width = 28
    for column in range(3, 3 + len(sessions)):
        attendance_ws.column_dimensions[get_column_letter(column)].width = 20
    for column in range(3 + len(sessions), attendance_last_column + 1):
        attendance_ws.column_dimensions[get_column_letter(column)].width = 16
    _set_document_layout(attendance_ws, attendance_last_column, max(current_note_row - 1, note_row + 1))

    # Grades from the existing weighted-component and bonus model.
    grade_rows = build_batch_grade_rows(components, trainees, score_rows, bonus_totals)
    grade_last_column = max(3 + len(components) + 3, 4)
    _style_document_title(grades_ws, grade_last_column, academy_name, "كشف الدرجات الرسمي")
    _add_document_metadata(grades_ws, batch_info, len(sessions))
    grades_headers = ["رقم", "اسم المتدرب", "البريد الإلكتروني"]
    for component in components:
        grades_headers.append(f"{component[2]}\nالوزن: {component[3]}%")
    grades_headers.extend(["الدرجة النهائية", "المكافأة", "الإجمالي\n(بحد أقصى 100)"])
    grade_header_row = 8
    for column, value in enumerate(grades_headers, 1):
        grades_ws.cell(grade_header_row, column, value)
    _style_table_header(grades_ws, grade_header_row, grade_last_column)

    for index, grade_row in enumerate(grade_rows, 1):
        _trainee_id, name, email, scores, final_grade, bonus = grade_row
        row_number = grade_header_row + index
        grades_ws.cell(row_number, 1, index)
        grades_ws.cell(row_number, 2, name)
        grades_ws.cell(row_number, 3, email)
        for component_index, component in enumerate(components, 4):
            score = scores.get(component[0])
            cell = grades_ws.cell(row_number, component_index, score)
            if score is not None:
                cell.number_format = "0.0"
        final_column = 4 + len(components)
        bonus_column = final_column + 1
        total_column = final_column + 2
        final_cell = grades_ws.cell(row_number, final_column, final_grade if final_grade is not None else "—")
        bonus_cell = grades_ws.cell(row_number, bonus_column, bonus)
        total = min((final_grade or 0) + (bonus or 0), 100)
        total_cell = grades_ws.cell(row_number, total_column, total)
        for cell in (final_cell, bonus_cell, total_cell):
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0.0"
        _style_data_row(grades_ws, row_number, grade_last_column, alternate=index % 2 == 0)
        for column in (1, *range(4, grade_last_column + 1)):
            grades_ws.cell(row_number, column).alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )
        grades_ws.cell(row_number, 3).alignment = Alignment(
            horizontal="left", vertical="center", wrap_text=True
        )

    grades_last_row = grade_header_row + len(grade_rows)
    if not grade_rows:
        grades_ws.merge_cells(
            start_row=grade_header_row + 1, start_column=1,
            end_row=grade_header_row + 1, end_column=grade_last_column,
        )
        empty_cell = grades_ws.cell(grade_header_row + 1, 1, "لا يوجد متدربون نشطون في هذه الدفعة.")
        empty_cell.font = Font(name="Arial", size=10, italic=True, color="596B7A")
        empty_cell.alignment = Alignment(horizontal="right", vertical="center")
        grades_last_row += 1
    grades_ws.column_dimensions["A"].width = 9
    grades_ws.column_dimensions["B"].width = 28
    grades_ws.column_dimensions["C"].width = 32
    for column in range(4, grade_last_column + 1):
        grades_ws.column_dimensions[get_column_letter(column)].width = 18
    _set_document_layout(grades_ws, grade_last_column, grades_last_row)

    workbook.properties.creator = academy_name or ""
    workbook.properties.title = f"{batch_info.get('batch_name', '')} — تقرير الدفعة"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
