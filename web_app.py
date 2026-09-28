"""
AFAQ Academy — Web Application
================================
FastAPI web layer that wraps the existing services entirely.
All business logic, validation, and DB access remain in the
original services — this file is purely the HTTP/session/UI layer.

Architecture:
  Browser → FastAPI routes → Existing Services → SQLite DB

Session: itsdangerous signed cookies (server-side via Starlette middleware).
Auth: Uses existing AuthService; session stores the user dict.
Authorization: Uses existing has_permission() for all protected routes.
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# ── Make existing services importable ──────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from database import create_tables, get_connection
from services.auth_service import AuthService
from services.authorization import has_permission
from services.Admin_service import AdminService
from services.course_service import CourseService
from services.enrollment_service import EnrollmentService
from services.Attendence_service import AttendanceService
from services.grade_service import GradeService
from services.material_service import CourseMaterialService
from services.audit_service import AuditService

# ── App setup ───────────────────────────────────────────────────────────────
create_tables()

app = FastAPI(title="AFAQ Academy")

# Session middleware (signed cookie; keep the secret in env for production)
SECRET_KEY = os.environ.get("AFAQ_SECRET_KEY", "afaq-academy-secret-key-change-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="afaq_session")

# Static files & templates
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "web" / "templates")


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_db():
    """Return a fresh DB connection (closed by caller)."""
    return get_connection()


def get_session_user(request: Request):
    """Return the current logged-in user dict, or None."""
    return request.session.get("user")


def render(request: Request, template: str, **ctx):
    """Render a Jinja2 template with common context injected."""
    user = get_session_user(request)
    ctx.setdefault("user", user)
    ctx.setdefault("active_page", "")
    ctx.setdefault("page_title", "")
    # Pop flash from session if present
    ctx.setdefault("flash_message", request.session.pop("flash_message", None))
    ctx.setdefault("flash_type", request.session.pop("flash_type", "success"))
    return templates.TemplateResponse(template, {"request": request, **ctx})


def flash(request: Request, message: str, type_: str = "success"):
    """Store a flash message in the session."""
    request.session["flash_message"] = message
    request.session["flash_type"] = type_


def require_login(request: Request) -> dict | None:
    """Return user if logged in, else None (caller redirects)."""
    return get_session_user(request)


def require_role(request: Request, role: str) -> dict | None:
    """Return user if logged in and has the required role."""
    user = get_session_user(request)
    if user and user.get("role") == role:
        return user
    return None


def today_str() -> str:
    return date.today().isoformat()


# ── Root redirect ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    role = user["role"]
    if role == "admin":
        return RedirectResponse("/admin/dashboard", status_code=302)
    if role == "instructor":
        return RedirectResponse("/instructor/dashboard", status_code=302)
    return RedirectResponse("/trainee/dashboard", status_code=302)


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_session_user(request):
        return RedirectResponse("/", status_code=302)
    return render(request, "auth/login.html", page_title="Login")


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    conn = get_db()
    try:
        auth = AuthService(conn)
        user, message = auth.login(email, password)
        if user:
            request.session["user"] = user
            return RedirectResponse("/", status_code=302)
        return render(request, "auth/login.html", page_title="Login",
                      error=message, email=email)
    finally:
        conn.close()


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if get_session_user(request):
        return RedirectResponse("/", status_code=302)
    return render(request, "auth/signup.html", page_title="Sign Up")


@app.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    conn = get_db()
    try:
        auth = AuthService(conn)
        success, message = auth.signup(name, email, password)
        if success:
            return render(request, "auth/signup.html", page_title="Sign Up",
                          success=message)
        return render(request, "auth/signup.html", page_title="Sign Up",
                      error=message, name=name, email=email)
    finally:
        conn.close()


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)
        enroll_svc = EnrollmentService(conn)

        trainees    = admin_svc.get_trainees()
        instructors = admin_svc.get_instructors()
        courses     = course_svc.get_all()

        # Count total enrollments
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM enrollments")
        enrollment_count = cursor.fetchone()[0]

        stats = {
            "trainees":    len(trainees),
            "instructors": len(instructors),
            "courses":     len(courses),
            "enrollments": enrollment_count,
        }

        return render(request, "admin/dashboard.html",
                      page_title="Dashboard",
                      active_page="dashboard",
                      stats=stats,
                      recent_courses=courses[:6])
    finally:
        conn.close()


# ── TRAINEES ──────────────────────────────────────────────────────────────────

@app.get("/admin/trainees", response_class=HTMLResponse)
async def admin_trainees(request: Request):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc = AdminService(conn)
        trainees  = admin_svc.get_trainees()
        return render(request, "admin/trainees.html",
                      page_title="Students",
                      active_page="trainees",
                      trainees=trainees)
    finally:
        conn.close()


@app.post("/admin/trainees/create", response_class=HTMLResponse)
async def admin_create_trainee(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc = AdminService(conn)
        try:
            admin_svc.create_user(name, email, password, "trainee")
            flash(request, f"Student '{name}' created successfully.", "success")
            return RedirectResponse("/admin/trainees", status_code=302)
        except ValueError as e:
            trainees = admin_svc.get_trainees()
            return render(request, "admin/trainees.html",
                          page_title="Students",
                          active_page="trainees",
                          trainees=trainees,
                          form_error=str(e),
                          show_modal=True)
    finally:
        conn.close()


@app.post("/admin/trainees/{trainee_id}/edit", response_class=HTMLResponse)
async def admin_edit_trainee(
    request: Request,
    trainee_id: int,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc = AdminService(conn)
        try:
            admin_svc.update_user(
                trainee_id,
                name=name,
                email=email,
                password=password if password and password.strip() else None
            )
            flash(request, f"Student '{name}' updated successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse("/admin/trainees", status_code=302)
    finally:
        conn.close()


# ── INSTRUCTORS ───────────────────────────────────────────────────────────────

@app.get("/admin/instructors", response_class=HTMLResponse)
async def admin_instructors(request: Request):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc   = AdminService(conn)
        instructors = admin_svc.get_instructors()
        return render(request, "admin/instructors.html",
                      page_title="Instructors",
                      active_page="instructors",
                      instructors=instructors)
    finally:
        conn.close()


@app.post("/admin/instructors/create", response_class=HTMLResponse)
async def admin_create_instructor(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc = AdminService(conn)
        try:
            admin_svc.create_user(name, email, password, "instructor")
            flash(request, f"Instructor '{name}' created successfully.", "success")
            return RedirectResponse("/admin/instructors", status_code=302)
        except ValueError as e:
            instructors = admin_svc.get_instructors()
            return render(request, "admin/instructors.html",
                          page_title="Instructors",
                          active_page="instructors",
                          instructors=instructors,
                          form_error=str(e),
                          show_modal=True)
    finally:
        conn.close()


@app.post("/admin/instructors/{instructor_id}/edit", response_class=HTMLResponse)
async def admin_edit_instructor(
    request: Request,
    instructor_id: int,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc = AdminService(conn)
        try:
            admin_svc.update_user(
                instructor_id,
                name=name,
                email=email,
                password=password if password and password.strip() else None
            )
            flash(request, f"Instructor '{name}' updated successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse("/admin/instructors", status_code=302)
    finally:
        conn.close()


# ── USER STATUS TOGGLE (Shared) ───────────────────────────────────────────────

@app.post("/admin/users/{user_id}/toggle-status", response_class=HTMLResponse)
async def admin_toggle_user_status(
    request: Request,
    user_id: int,
    return_to: str = Form("/admin/trainees"),
):
    current_user = require_role(request, "admin")
    if not current_user:
        return RedirectResponse("/login", status_code=302)

    if current_user.get("id") == user_id:
        flash(request, "You cannot deactivate your own account.", "error")
        return RedirectResponse(return_to, status_code=302)

    conn = get_db()
    try:
        admin_svc = AdminService(conn)
        target = admin_svc.get_user_by_id(user_id)
        if not target:
            flash(request, "User not found.", "error")
            return RedirectResponse(return_to, status_code=302)

        is_active = target[4]
        name = target[1]

        if is_active == 1:
            admin_svc.deactivate_user(user_id)
            flash(request, f"User '{name}' has been deactivated.", "warning")
        else:
            admin_svc.reactivate_user(user_id)
            flash(request, f"User '{name}' has been reactivated.", "success")

        return RedirectResponse(return_to, status_code=302)
    finally:
        conn.close()


# ── COURSES ───────────────────────────────────────────────────────────────────

@app.get("/admin/courses", response_class=HTMLResponse)
async def admin_courses(request: Request):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)
        return render(request, "admin/courses.html",
                      page_title="Courses",
                      active_page="courses",
                      courses=course_svc.get_all(),
                      instructors=admin_svc.get_active_instructors())
    finally:
        conn.close()


@app.post("/admin/courses/create", response_class=HTMLResponse)
async def admin_create_course(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    instructor_id: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        admin_svc  = AdminService(conn)
        ins_id = int(instructor_id) if instructor_id and instructor_id.strip() else None
        try:
            course_svc.create(name.strip(), instructor_id=ins_id, description=description)
            flash(request, f"Course '{name}' created successfully.", "success")
            return RedirectResponse("/admin/courses", status_code=302)
        except Exception as e:
            return render(request, "admin/courses.html",
                          page_title="Courses",
                          active_page="courses",
                          courses=course_svc.get_all(),
                          instructors=admin_svc.get_active_instructors(),
                          form_error=str(e),
                          form_action="create",
                          show_modal="create")
    finally:
        conn.close()


@app.post("/admin/courses/{course_id}/edit", response_class=HTMLResponse)
async def admin_edit_course(
    request: Request,
    course_id: int,
    name: str = Form(...),
    description: str = Form(""),
    instructor_id: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        ins_id = int(instructor_id) if instructor_id and instructor_id.strip() else None
        try:
            course_svc.update(course_id, name.strip(), description=description, instructor_id=ins_id)
            flash(request, f"Course '{name}' updated successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse("/admin/courses", status_code=302)
    finally:
        conn.close()


@app.post("/admin/courses/{course_id}/toggle-status", response_class=HTMLResponse)
async def admin_toggle_course_status(request: Request, course_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        course = course_svc.get_by_id(course_id)
        if not course:
            flash(request, "Course not found.", "error")
            return RedirectResponse("/admin/courses", status_code=302)

        is_active = course[3]
        name = course[1]
        if is_active == 1:
            course_svc.archive_course(course_id)
            flash(request, f"Course '{name}' has been archived.", "warning")
        else:
            course_svc.reactivate_course(course_id)
            flash(request, f"Course '{name}' has been reactivated.", "success")

        return RedirectResponse("/admin/courses", status_code=302)
    finally:
        conn.close()


@app.post("/admin/courses/assign", response_class=HTMLResponse)
async def admin_assign_instructor(
    request: Request,
    instructor_id: int = Form(...),
    course_id: int = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)
        try:
            admin_svc.assign_instructor(instructor_id, course_id)
            flash(request, "Instructor assigned successfully.", "success")
            return RedirectResponse("/admin/courses", status_code=302)
        except ValueError as e:
            return render(request, "admin/courses.html",
                          page_title="Courses",
                          active_page="courses",
                          courses=course_svc.get_all(),
                          instructors=admin_svc.get_active_instructors(),
                          form_error=str(e),
                          form_action="assign",
                          show_modal="assign")
    finally:
        conn.close()


# ── ENROLLMENT ────────────────────────────────────────────────────────────────

@app.get("/admin/enrollment", response_class=HTMLResponse)
async def admin_enrollment(request: Request):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)
        enroll_svc = EnrollmentService(conn)

        return render(request, "admin/enrollment.html",
                      page_title="Enrollment",
                      active_page="enrollment",
                      trainees=admin_svc.get_active_trainees(),
                      courses=course_svc.get_active_courses(),
                      enrollments=enroll_svc.get_all_enrollments())
    finally:
        conn.close()


@app.post("/admin/enrollment/enroll", response_class=HTMLResponse)
async def admin_enroll_trainee(
    request: Request,
    trainee_id: int = Form(...),
    course_id: int = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = EnrollmentService(conn)
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)
        try:
            enroll_svc.enroll(trainee_id, course_id)
            flash(request, "Student enrolled successfully.", "success")
            return RedirectResponse("/admin/enrollment", status_code=302)
        except ValueError as e:
            return render(request, "admin/enrollment.html",
                          page_title="Enrollment",
                          active_page="enrollment",
                          trainees=admin_svc.get_active_trainees(),
                          courses=course_svc.get_active_courses(),
                          enrollments=enroll_svc.get_all_enrollments(),
                          form_error=str(e))
    finally:
        conn.close()


@app.post("/admin/enrollment/unenroll", response_class=HTMLResponse)
async def admin_unenroll_trainee(
    request: Request,
    trainee_id: int = Form(...),
    course_id: int = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = EnrollmentService(conn)
        try:
            enroll_svc.unenroll(trainee_id, course_id)
            flash(request, "Student unenrolled successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse("/admin/enrollment", status_code=302)
    finally:
        conn.close()


# ── ATTENDANCE (admin) ────────────────────────────────────────────────────────

@app.get("/admin/attendance", response_class=HTMLResponse)
async def admin_attendance(request: Request):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)

        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.name, c.name, a.date, a.status
            FROM attendance a
            JOIN users u ON a.trainee_id = u.id
            JOIN courses c ON a.course_id = c.id
            ORDER BY a.date DESC
            LIMIT 50
        """)
        recent_attendance = cursor.fetchall()

        return render(request, "admin/attendance.html",
                      page_title="Attendance",
                      active_page="attendance",
                      trainees=admin_svc.get_active_trainees(),
                      courses=course_svc.get_active_courses(),
                      recent_attendance=recent_attendance,
                      today=today_str())
    finally:
        conn.close()


@app.post("/admin/attendance/record", response_class=HTMLResponse)
async def admin_record_attendance(
    request: Request,
    trainee_id: int = Form(...),
    course_id: int = Form(...),
    date: str = Form(...),
    status: str = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        att_svc    = AttendanceService(conn)
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)

        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.name, c.name, a.date, a.status
            FROM attendance a
            JOIN users u ON a.trainee_id = u.id
            JOIN courses c ON a.course_id = c.id
            ORDER BY a.date DESC LIMIT 50
        """)
        recent_attendance = cursor.fetchall()

        try:
            att_svc.record(trainee_id, course_id, date, status)
            flash(request, "Attendance recorded successfully.", "success")
            return RedirectResponse("/admin/attendance", status_code=302)
        except ValueError as e:
            return render(request, "admin/attendance.html",
                          page_title="Attendance",
                          active_page="attendance",
                          trainees=admin_svc.get_active_trainees(),
                          courses=course_svc.get_active_courses(),
                          recent_attendance=recent_attendance,
                          today=today_str(),
                          form_error=str(e))
    finally:
        conn.close()


# ── GRADES (admin) ────────────────────────────────────────────────────────────

@app.get("/admin/grades", response_class=HTMLResponse)
async def admin_grades(request: Request):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)

        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.name, c.name, g.score
            FROM grades g
            JOIN users u ON g.trainee_id = u.id
            JOIN courses c ON g.course_id = c.id
            ORDER BY u.name, c.name
        """)
        grades = cursor.fetchall()

        return render(request, "admin/grades.html",
                      page_title="Grades",
                      active_page="grades",
                      trainees=admin_svc.get_active_trainees(),
                      courses=course_svc.get_active_courses(),
                      grades=grades)
    finally:
        conn.close()


@app.post("/admin/grades/add", response_class=HTMLResponse)
async def admin_add_grade(
    request: Request,
    trainee_id: int = Form(...),
    course_id: int = Form(...),
    score: float = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        grade_svc  = GradeService(conn)
        admin_svc  = AdminService(conn)
        course_svc = CourseService(conn)

        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.name, c.name, g.score FROM grades g
            JOIN users u ON g.trainee_id = u.id
            JOIN courses c ON g.course_id = c.id
            ORDER BY u.name, c.name
        """)
        grades = cursor.fetchall()

        try:
            grade_svc.add_grade(trainee_id, course_id, score)
            flash(request, "Grade saved successfully.", "success")
            return RedirectResponse("/admin/grades", status_code=302)
        except ValueError as e:
            return render(request, "admin/grades.html",
                          page_title="Grades",
                          active_page="grades",
                          trainees=admin_svc.get_active_trainees(),
                          courses=course_svc.get_active_courses(),
                          grades=grades,
                          form_error=str(e))
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# INSTRUCTOR
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/instructor/dashboard", response_class=HTMLResponse)
async def instructor_dashboard(request: Request):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        enroll_svc = EnrollmentService(conn)

        courses = course_svc.get_instructor_courses(user["id"])

        # Count distinct students across all instructor courses
        total_students = set()
        for course in courses:
            trainees = enroll_svc.get_course_trainees(course[0])
            for t in trainees:
                total_students.add(t[0])

        return render(request, "instructor/dashboard.html",
                      page_title="Dashboard",
                      active_page="dashboard",
                      courses=courses,
                      total_students=len(total_students))
    finally:
        conn.close()


@app.get("/instructor/courses", response_class=HTMLResponse)
async def instructor_courses(request: Request):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        courses    = course_svc.get_instructor_courses(user["id"])
        return render(request, "instructor/courses.html",
                      page_title="My Courses",
                      active_page="courses",
                      courses=courses)
    finally:
        conn.close()


@app.get("/instructor/students", response_class=HTMLResponse)
async def instructor_students(request: Request, course_id: int = None):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        enroll_svc = EnrollmentService(conn)

        courses = course_svc.get_instructor_courses(user["id"])
        selected_course = None
        trainees = []

        if course_id:
            # Verify this course belongs to the instructor
            for c in courses:
                if c[0] == course_id:
                    selected_course = c
                    break
            if selected_course:
                trainees = enroll_svc.get_course_trainees(course_id)

        return render(request, "instructor/students.html",
                      page_title="My Students",
                      active_page="students",
                      courses=courses,
                      selected_course=selected_course,
                      trainees=trainees)
    finally:
        conn.close()


@app.get("/instructor/attendance", response_class=HTMLResponse)
async def instructor_attendance(request: Request, course_id: int = None):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        enroll_svc = EnrollmentService(conn)
        att_svc    = AttendanceService(conn)

        courses = course_svc.get_instructor_courses(user["id"])
        selected_course = None
        trainees = []
        recent_attendance = []

        if course_id:
            for c in courses:
                if c[0] == course_id:
                    selected_course = c
                    break
            if selected_course:
                trainees = enroll_svc.get_course_trainees(course_id)
                recent_attendance = att_svc.get_course_attendance(course_id)

        return render(request, "instructor/attendance.html",
                      page_title="Attendance",
                      active_page="attendance",
                      courses=courses,
                      selected_course=selected_course,
                      trainees=trainees,
                      recent_attendance=recent_attendance,
                      today=today_str())
    finally:
        conn.close()


@app.post("/instructor/attendance/record", response_class=HTMLResponse)
async def instructor_record_attendance(request: Request):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    course_id = int(form.get("course_id", 0))
    date_val  = form.get("date", today_str())

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        enroll_svc = EnrollmentService(conn)
        att_svc    = AttendanceService(conn)

        # Verify ownership
        courses = course_svc.get_instructor_courses(user["id"])
        selected_course = next((c for c in courses if c[0] == course_id), None)
        if not selected_course:
            flash(request, "Course not found or not assigned to you.", "error")
            return RedirectResponse("/instructor/attendance", status_code=302)

        trainees = enroll_svc.get_course_trainees(course_id)
        errors = []

        for t in trainees:
            trainee_id = t[0]
            status_key = f"status_{trainee_id}"
            status = form.get(status_key, "present")
            try:
                att_svc.record(trainee_id, course_id, date_val, status)
            except ValueError as e:
                errors.append(f"{t[1]}: {e}")

        if errors:
            # Partial success — show which ones failed
            recent_attendance = att_svc.get_course_attendance(course_id)
            return render(request, "instructor/attendance.html",
                          page_title="Attendance",
                          active_page="attendance",
                          courses=courses,
                          selected_course=selected_course,
                          trainees=trainees,
                          recent_attendance=recent_attendance,
                          today=today_str(),
                          form_error="Some records failed: " + "; ".join(errors))
        else:
            flash(request, f"Attendance for {date_val} saved successfully.", "success")
            return RedirectResponse(f"/instructor/attendance?course_id={course_id}", status_code=302)
    finally:
        conn.close()


@app.get("/instructor/grades", response_class=HTMLResponse)
async def instructor_grades(request: Request, course_id: int = None):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        enroll_svc = EnrollmentService(conn)
        grade_svc  = GradeService(conn)

        courses = course_svc.get_instructor_courses(user["id"])
        selected_course = None
        trainees = []
        existing_grades = {}

        if course_id:
            for c in courses:
                if c[0] == course_id:
                    selected_course = c
                    break
            if selected_course:
                trainees = enroll_svc.get_course_trainees(course_id)
                # Fetch existing grades for this course
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT trainee_id, score FROM grades
                    WHERE course_id = ?
                """, (course_id,))
                for row in cursor.fetchall():
                    existing_grades[row[0]] = row[1]

        return render(request, "instructor/grades.html",
                      page_title="Grades",
                      active_page="grades",
                      courses=courses,
                      selected_course=selected_course,
                      trainees=trainees,
                      existing_grades=existing_grades)
    finally:
        conn.close()


@app.post("/instructor/grades/save", response_class=HTMLResponse)
async def instructor_save_grades(request: Request):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    course_id = int(form.get("course_id", 0))

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        enroll_svc = EnrollmentService(conn)
        grade_svc  = GradeService(conn)

        courses = course_svc.get_instructor_courses(user["id"])
        selected_course = next((c for c in courses if c[0] == course_id), None)
        if not selected_course:
            flash(request, "Course not found.", "error")
            return RedirectResponse("/instructor/grades", status_code=302)

        trainees = enroll_svc.get_course_trainees(course_id)
        errors = []
        saved = 0

        for t in trainees:
            trainee_id = t[0]
            score_key  = f"score_{trainee_id}"
            score_val  = form.get(score_key, "").strip()
            if not score_val:
                continue  # Skip blank entries
            try:
                score = float(score_val)
                grade_svc.add_grade(trainee_id, course_id, score)
                saved += 1
            except (ValueError, TypeError) as e:
                errors.append(f"{t[1]}: {e}")

        if errors:
            cursor = conn.cursor()
            cursor.execute("SELECT trainee_id, score FROM grades WHERE course_id = ?", (course_id,))
            existing_grades = {row[0]: row[1] for row in cursor.fetchall()}
            return render(request, "instructor/grades.html",
                          page_title="Grades",
                          active_page="grades",
                          courses=courses,
                          selected_course=selected_course,
                          trainees=trainees,
                          existing_grades=existing_grades,
                          form_error="Some grades failed: " + "; ".join(errors))
        else:
            flash(request, f"{saved} grade(s) saved successfully.", "success")
            return RedirectResponse(f"/instructor/grades?course_id={course_id}", status_code=302)
    finally:
        conn.close()


@app.get("/instructor/materials", response_class=HTMLResponse)
async def instructor_materials(request: Request, course_id: int = None):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not course_id:
        return RedirectResponse("/instructor/courses", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        mat_svc    = CourseMaterialService(conn)

        courses = course_svc.get_instructor_courses(user["id"])
        selected_course = next((c for c in courses if c[0] == course_id), None)
        
        if not selected_course:
            flash(request, "Course not found or not assigned to you.", "error")
            return RedirectResponse("/instructor/courses", status_code=302)

        materials = mat_svc.get_course_materials(course_id)

        return render(request, "instructor/materials.html",
                      page_title="Materials",
                      active_page="courses",
                      courses=courses,
                      selected_course=selected_course,
                      materials=materials)
    finally:
        conn.close()


@app.post("/instructor/materials/add", response_class=HTMLResponse)
async def instructor_add_material(
    request: Request,
    course_id: int = Form(...),
    title: str = Form(...),
    url: str = Form(...),
    material_type: str = Form("link"),
    description: str = Form(""),
):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        mat_svc    = CourseMaterialService(conn)
        audit      = AuditService(conn)

        courses = course_svc.get_instructor_courses(user["id"])
        if not any(c[0] == course_id for c in courses):
            flash(request, "Not authorized to modify this course.", "error")
            return RedirectResponse("/instructor/courses", status_code=302)

        try:
            mat_id = mat_svc.add_material(course_id, title, url, description, material_type)
            audit.log(user, "added_material", "course_materials", mat_id, f"Added '{title}' to course {course_id}")
            flash(request, "Material added successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
            
        return RedirectResponse(f"/instructor/materials?course_id={course_id}", status_code=302)
    finally:
        conn.close()


@app.post("/instructor/materials/delete", response_class=HTMLResponse)
async def instructor_delete_material(
    request: Request,
    course_id: int = Form(...),
    material_id: int = Form(...)
):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        mat_svc    = CourseMaterialService(conn)
        audit      = AuditService(conn)

        courses = course_svc.get_instructor_courses(user["id"])
        if not any(c[0] == course_id for c in courses):
            flash(request, "Not authorized to modify this course.", "error")
            return RedirectResponse("/instructor/courses", status_code=302)

        try:
            mat_svc.delete_material(material_id, course_id)
            audit.log(user, "deleted_material", "course_materials", material_id, f"Deleted material {material_id} from course {course_id}")
            flash(request, "Material deleted successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
            
        return RedirectResponse(f"/instructor/materials?course_id={course_id}", status_code=302)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# TRAINEE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/trainee/dashboard", response_class=HTMLResponse)
async def trainee_dashboard(request: Request):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = EnrollmentService(conn)
        att_svc    = AttendanceService(conn)
        grade_svc  = GradeService(conn)

        courses    = enroll_svc.get_trainee_courses(user["id"])
        attendance = att_svc.get_trainee_attendance(user["id"])
        grades     = grade_svc.get_trainee_grades(user["id"])

        present_count = sum(1 for a in attendance if a[2] == "present")
        avg_score     = (sum(g[1] for g in grades) / len(grades)) if grades else None

        return render(request, "trainee/dashboard.html",
                      page_title="Dashboard",
                      active_page="dashboard",
                      courses=courses,
                      attendance=attendance,
                      grades=grades,
                      present_count=present_count,
                      avg_score=avg_score)
    finally:
        conn.close()


@app.get("/trainee/courses", response_class=HTMLResponse)
async def trainee_courses(request: Request):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = EnrollmentService(conn)
        courses    = enroll_svc.get_trainee_courses(user["id"])
        return render(request, "trainee/courses.html",
                      page_title="My Courses",
                      active_page="courses",
                      courses=courses)
    finally:
        conn.close()


@app.get("/trainee/attendance", response_class=HTMLResponse)
async def trainee_attendance(request: Request):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        att_svc    = AttendanceService(conn)
        attendance = att_svc.get_trainee_attendance(user["id"])

        total         = len(attendance)
        present_count = sum(1 for a in attendance if a[2] == "present")
        absent_count  = total - present_count
        attendance_rate = round((present_count / total * 100)) if total else 0

        return render(request, "trainee/attendance.html",
                      page_title="My Attendance",
                      active_page="attendance",
                      attendance=attendance,
                      present_count=present_count,
                      absent_count=absent_count,
                      attendance_rate=attendance_rate)
    finally:
        conn.close()


@app.get("/trainee/grades", response_class=HTMLResponse)
async def trainee_grades(request: Request):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        grade_svc = GradeService(conn)
        grades    = grade_svc.get_trainee_grades(user["id"])
        avg_score = (sum(g[1] for g in grades) / len(grades)) if grades else None

        return render(request, "trainee/grades.html",
                      page_title="My Grades",
                      active_page="grades",
                      grades=grades,
                      avg_score=avg_score)
    finally:
        conn.close()


@app.get("/trainee/materials", response_class=HTMLResponse)
async def trainee_materials(request: Request, course_id: int = None):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not course_id:
        return RedirectResponse("/trainee/courses", status_code=302)

    conn = get_db()
    try:
        enroll_svc = EnrollmentService(conn)
        mat_svc    = CourseMaterialService(conn)

        courses = enroll_svc.get_trainee_courses(user["id"])
        selected_course = next((c for c in courses if c[0] == course_id), None)
        
        if not selected_course:
            flash(request, "Course not found or you are not enrolled.", "error")
            return RedirectResponse("/trainee/courses", status_code=302)

        materials = mat_svc.get_course_materials(course_id)

        return render(request, "trainee/materials.html",
                      page_title="Materials",
                      active_page="courses",
                      selected_course=selected_course,
                      materials=materials)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# PROFILE & SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/profile", response_class=HTMLResponse)
async def view_profile(request: Request):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    return render(request, "auth/profile.html",
                  page_title="My Profile",
                  active_page="profile")


@app.post("/profile/password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
):
    user = require_login(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        auth_svc = AuthService(conn)
        audit = AuditService(conn)
        ok, msg = auth_svc.change_password(user["id"], current_password, new_password)
        if ok:
            audit.log(user, "changed_password", "user", user["id"], "User changed their password")
            flash(request, msg, "success")
        else:
            flash(request, msg, "error")
        return RedirectResponse("/profile", status_code=302)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
