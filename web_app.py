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
import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import io
from fastapi import FastAPI, Request, Form, Response, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
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
# New LMS services
from services.batch_service import BatchService
from services.chapter_service import ChapterService
from services.session_service import SessionService
from services.batch_enrollment_service import BatchEnrollmentService
from services.enrollment_request_service import EnrollmentRequestService
from services.batch_attendance_service import BatchAttendanceService
from services.task_service import TaskService
from services.submission_service import SubmissionService
from services.grading_service import GradingService
from services.bonus_service import BonusService
from services import excel_service
from services.public_service import PublicService
from utils.session_config import get_session_secret

# ── App setup ───────────────────────────────────────────────────────────────
SECRET_KEY = get_session_secret()

try:
    create_tables()
except Exception as e:
    print(f"Warning: create_tables skipped on boot: {e}")

app = FastAPI(title="AFAQ Academy")


@app.get("/api/health")
async def health_check():
    info = {
        "status": "ok",
        "vercel": bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")),
    }
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM courses")
        count = cursor.fetchone()[0]
        info["database"] = "connected"
        info["courses_count"] = count
        conn.close()
    except Exception as e:
        info["database"] = "error"
        info["db_error"] = str(e)
    return info


@app.get("/api/debug-templates")
async def debug_templates():
    import os
    t_dir = ROOT / "web" / "templates"
    files = []
    if t_dir.exists():
        for r, _, fs in os.walk(t_dir):
            for f in fs:
                files.append(os.path.relpath(os.path.join(r, f), t_dir).replace("\\", "/"))
    return {"exists": t_dir.exists(), "files": sorted(files)}

# Session middleware (signed cookie; the key is required from the environment)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, session_cookie="afaq_session")

# Static files & templates
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "web" / "templates")


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_db(request: Request = None):
    """Return a DB connection (request-scoped within async context, closed by caller)."""
    if request and hasattr(request, "state") and hasattr(request.state, "db"):
        if request.state.db is not None:
            return request.state.db
    return get_connection(request_scoped=True)


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
    return templates.TemplateResponse(request=request, name=template, context=ctx)


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


def require_roles(request: Request, *roles: str) -> dict | None:
    """Return user if logged in and has any of the specified roles."""
    user = get_session_user(request)
    if user and user.get("role") in roles:
        return user
    return None


def today_str() -> str:
    return date.today().isoformat()


# ── Public Organization Website ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def public_home(request: Request):
    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        org = pub_svc.get_org_settings()
        stats = pub_svc.get_public_stats()
        featured_courses = pub_svc.get_featured_courses()
        upcoming_batches = pub_svc.get_upcoming_batches()
        completed_batches = pub_svc.get_completed_batches()
        graduates = pub_svc.get_public_graduates()
        gallery = pub_svc.get_public_gallery()
        testimonials = pub_svc.get_public_testimonials()
        return render(
            request,
            "public/index.html",
            page_title=f"{org.get('org_name', 'AFAQ Academy')} — Excellence in Technology & Management",
            active_page="home",
            org=org,
            org_settings=org,
            stats=stats,
            featured_courses=featured_courses,
            upcoming_batches=upcoming_batches,
            completed_batches=completed_batches,
            graduates=graduates,
            gallery=gallery,
            testimonials=testimonials,
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Error in public_home: {tb}")
        return HTMLResponse(f"<html><body><h2>Error in public_home:</h2><pre>{tb}</pre></body></html>", status_code=500)
    finally:
        conn.close()


@app.get("/courses/{course_id}", response_class=HTMLResponse)
async def public_course_details(request: Request, course_id: int):
    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        org = pub_svc.get_org_settings()
        course = pub_svc.get_course_details(course_id)
        if not course:
            flash(request, "Course not found or not currently publicly available.", "error")
            return RedirectResponse("/#courses", status_code=302)
        return render(
            request,
            "public/course_details.html",
            page_title=f"{course['name']} — Course Details | {org.get('org_name', 'AFAQ Academy')}",
            active_page="courses",
            org=org,
            org_settings=org,
            course=course,
        )
    finally:
        conn.close()


@app.post("/contact", response_class=HTMLResponse)
async def submit_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form(...),
    message: str = Form(...),
    phone: str = Form(default=""),
):
    name = name.strip()
    email = email.strip()
    subject = subject.strip()
    message = message.strip()
    phone = phone.strip()

    if not name or not email or not subject or not message:
        flash(request, "Please fill in all required fields (Name, Email, Subject, Message).", "error")
        return RedirectResponse("/#contact", status_code=302)

    if "@" not in email or "." not in email:
        flash(request, "Please enter a valid email address.", "error")
        return RedirectResponse("/#contact", status_code=302)

    if len(name) > 100 or len(subject) > 200 or len(message) > 5000:
        flash(request, "One of the submitted fields exceeds maximum length limit.", "error")
        return RedirectResponse("/#contact", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        pub_svc.submit_contact_message(
            name=name,
            email=email,
            subject=subject,
            message=message,
            phone=phone
        )
        flash(request, "Thank you! Your message has been sent to our team. We will get back to you shortly.", "success")
        return RedirectResponse("/#contact", status_code=302)
    except Exception as e:
        flash(request, f"Unable to submit message: {e}", "error")
        return RedirectResponse("/#contact", status_code=302)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

_AUTH_UI_MESSAGES = {
    "Name must contain at least 2 characters.": "يجب ألا يقل الاسم عن حرفين.",
    "Please use your institutional AFAQ email address (e.g. username@afaq.trainee.edu).":
        "استخدم بريدك المؤسسي التابع لأكاديمية آفاق، مثل username@afaq.trainee.edu.",
    "Public signup is available for trainees only. Use your @afaq.trainee.edu address.":
        "التسجيل العام متاح للمتدربين فقط. استخدم بريدًا ينتهي بـ @afaq.trainee.edu.",
    "Password must be at least 12 characters.": "يجب ألا تقل كلمة المرور عن 12 حرفًا.",
    "Password must contain at least one uppercase letter.": "يجب أن تحتوي كلمة المرور على حرف إنجليزي كبير واحد على الأقل.",
    "Password must contain at least one lowercase letter.": "يجب أن تحتوي كلمة المرور على حرف إنجليزي صغير واحد على الأقل.",
    "Password must contain at least one number.": "يجب أن تحتوي كلمة المرور على رقم واحد على الأقل.",
    "Password must contain at least one special character (!@#$%^&* etc.).":
        "يجب أن تحتوي كلمة المرور على رمز خاص واحد على الأقل.",
    "This password is too common. Please choose a stronger password.":
        "كلمة المرور شائعة جدًا. اختر كلمة مرور أقوى.",
    "Email already exists or signup failed.": "هذا البريد مسجل بالفعل أو تعذر إنشاء الحساب.",
    "Invalid email or password.": "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
    "Your account has been deactivated. Please contact an administrator.":
        "تم إيقاف حسابك. يُرجى التواصل مع إدارة الأكاديمية.",
    "Account created successfully.": "تم إنشاء الحساب بنجاح.",
    "User not found.": "لم يتم العثور على المستخدم.",
    "Current password is incorrect.": "كلمة المرور الحالية غير صحيحة.",
    "New password must be different from your current password.":
        "يجب أن تختلف كلمة المرور الجديدة عن الحالية.",
    "Password updated successfully.": "تم تحديث كلمة المرور بنجاح.",
}


def _auth_ui_message(message):
    return _AUTH_UI_MESSAGES.get(message, message)

def _redirect_after_auth(user: dict, next_url: str | None = None) -> RedirectResponse:
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return RedirectResponse(next_url, status_code=302)
    role = user.get("role")
    if role == "admin":
        return RedirectResponse("/admin/dashboard", status_code=302)
    if role == "instructor":
        return RedirectResponse("/instructor/dashboard", status_code=302)
    return RedirectResponse("/trainee/dashboard", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str | None = None):
    user = get_session_user(request)
    if user:
        return _redirect_after_auth(user, next)
    return render(request, "auth/login.html", page_title="تسجيل الدخول", next=next or "")


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(default=""),
):
    conn = get_db()
    try:
        auth = AuthService(conn)
        user, message = auth.login(email, password)
        if user:
            request.session["user"] = user
            return _redirect_after_auth(user, next)
        return render(request, "auth/login.html", page_title="تسجيل الدخول",
                      error=_auth_ui_message(message), email=email, next=next)
    finally:
        conn.close()


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, next: str | None = None):
    user = get_session_user(request)
    if user:
        return _redirect_after_auth(user, next)
    return render(request, "auth/signup.html", page_title="إنشاء حساب", next=next or "")


@app.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(default=""),
):
    conn = get_db()
    try:
        auth = AuthService(conn)
        success, message = auth.signup(name, email, password)
        if success:
            user, _ = auth.login(email, password)
            if user:
                request.session["user"] = user
                flash(request, "مرحبًا بك في أكاديمية آفاق! تم إنشاء حسابك بنجاح.", "success")
                return _redirect_after_auth(user, next)
            return render(request, "auth/login.html", page_title="تسجيل الدخول",
                          success=_auth_ui_message(message), next=next)
        return render(request, "auth/signup.html", page_title="إنشاء حساب",
                      error=_auth_ui_message(message), name=name, email=email, next=next)
    finally:
        conn.close()


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    flash(request, "تم تسجيل خروجك بنجاح.", "info")
    return RedirectResponse("/", status_code=302)


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

        user_counts      = admin_svc.get_user_counts_by_role()
        courses_count    = course_svc.count()
        enrollment_count = enroll_svc.count()
        recent_courses   = course_svc.get_recent(limit=6)

        stats = {
            "trainees":    user_counts.get("trainee", 0),
            "instructors": user_counts.get("instructor", 0),
            "courses":     courses_count,
            "enrollments": enrollment_count,
        }

        return render(request, "admin/dashboard.html",
                      page_title="Dashboard",
                      active_page="dashboard",
                      stats=stats,
                      recent_courses=recent_courses)
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
                      page_title="لوحة المتدرب",
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
                      page_title="دوراتي",
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
                      page_title="سجلات الحضور",
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
                      page_title="درجاتي",
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
                      page_title="المواد التعليمية",
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
                  page_title="الملف الشخصي",
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
            flash(request, _auth_ui_message(msg), "success")
        else:
            flash(request, _auth_ui_message(msg), "error")
        return RedirectResponse("/profile", status_code=302)
    finally:
        conn.close()





# ══════════════════════════════════════════════════════════════════════════════
# BATCH MANAGEMENT (Admin)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/courses/{course_id}/batches", response_class=HTMLResponse)
async def admin_course_batches(request: Request, course_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        batch_svc = BatchService(conn)
        admin_svc = AdminService(conn)

        course = course_svc.get_by_id(course_id)
        if not course:
            flash(request, "Course not found.", "error")
            return RedirectResponse("/admin/courses", status_code=302)

        batches = batch_svc.get_by_course(course_id)
        instructors = admin_svc.get_active_instructors()
        return render(request, "admin/batches.html",
                      page_title=f"Batches — {course[1]}",
                      active_page="courses",
                      course=course,
                      batches=batches,
                      instructors=instructors)
    finally:
        conn.close()


@app.post("/admin/courses/{course_id}/batches/create", response_class=HTMLResponse)
async def admin_create_batch(
    request: Request,
    course_id: int,
    name: str = Form(...),
    instructor_id: str = Form(""),
    capacity: int = Form(0),
    start_date: str = Form(""),
    end_date: str = Form(""),
    registration_cutoff_sessions: int = Form(0),
    notes: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        ins_id = int(instructor_id) if instructor_id and instructor_id.strip() else None
        try:
            batch_svc.create(
                course_id, name.strip(),
                instructor_id=ins_id,
                capacity=capacity,
                start_date=start_date or None,
                end_date=end_date or None,
                registration_cutoff_sessions=registration_cutoff_sessions,
                notes=notes or None,
            )
            flash(request, f"Batch '{name}' created successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/courses/{course_id}/batches", status_code=302)
    finally:
        conn.close()


@app.get("/admin/batches/{batch_id}", response_class=HTMLResponse)
async def admin_batch_detail(request: Request, batch_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        session_svc = SessionService(conn)
        enroll_svc = BatchEnrollmentService(conn)
        req_svc = EnrollmentRequestService(conn)
        grading_svc = GradingService(conn)
        admin_svc = AdminService(conn)

        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            flash(request, "Batch not found.", "error")
            return RedirectResponse("/admin/courses", status_code=302)

        sessions = session_svc.get_by_batch(batch_id)
        trainees = enroll_svc.get_batch_trainees(batch_id)
        enrolled_count = len(trainees)
        pending_requests_count = len(req_svc.get_pending(batch_id=batch_id))
        components = grading_svc.get_components(batch_id)
        total_weight = grading_svc.get_total_weight(batch_id)
        all_trainees = admin_svc.get_active_trainees()

        return render(request, "admin/batch_detail.html",
                      page_title=f"Batch — {batch[2]}",
                      active_page="courses",
                      batch=batch,
                      sessions=sessions,
                      trainees=trainees,
                      enrolled_count=enrolled_count,
                      pending_requests_count=pending_requests_count,
                      components=components,
                      total_weight=total_weight,
                      all_trainees=all_trainees)
    finally:
        conn.close()


@app.post("/admin/batches/{batch_id}/edit", response_class=HTMLResponse)
async def admin_edit_batch(
    request: Request,
    batch_id: int,
    name: str = Form(...),
    instructor_id: str = Form(""),
    capacity: int = Form(0),
    start_date: str = Form(""),
    end_date: str = Form(""),
    registration_cutoff_sessions: int = Form(0),
    status: str = Form("upcoming"),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        ins_id = int(instructor_id) if instructor_id and instructor_id.strip() else None
        try:
            batch_svc.update(
                batch_id, name.strip(),
                instructor_id=ins_id,
                capacity=capacity,
                start_date=start_date or None,
                end_date=end_date or None,
                registration_cutoff_sessions=registration_cutoff_sessions,
                status=status,
            )
            flash(request, "Batch updated successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")

        # Find course_id to redirect back
        batch = batch_svc.get_by_id(batch_id)
        course_id = batch[1] if batch else 0
        return RedirectResponse(f"/admin/courses/{course_id}/batches", status_code=302)
    finally:
        conn.close()


@app.post("/admin/batches/{batch_id}/enroll", response_class=HTMLResponse)
async def admin_batch_enroll(
    request: Request,
    batch_id: int,
    trainee_id: int = Form(...),
    price: str = Form(""),
    amount_paid: str = Form("0.0"),
    payment_status: str = Form(""),
    payment_notes: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = BatchEnrollmentService(conn)
        price_val = float(price) if price and price.strip() else None
        paid_val = float(amount_paid) if amount_paid and amount_paid.strip() else 0.0
        status_val = payment_status.strip() if payment_status and payment_status.strip() else None
        notes_val = payment_notes.strip() if payment_notes and payment_notes.strip() else None
        try:
            enroll_svc.enroll(batch_id, trainee_id, enrolled_by=user["id"],
                              price=price_val, amount_paid=paid_val,
                              payment_status=status_val, payment_notes=notes_val)
            flash(request, "Student enrolled successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


@app.post("/admin/enrollments/{enrollment_id}/payment", response_class=HTMLResponse)
async def admin_update_enrollment_payment(
    request: Request,
    enrollment_id: int,
    batch_id: int = Form(...),
    price: str = Form(""),
    amount_paid: str = Form("0.0"),
    payment_status: str = Form(""),
    payment_notes: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = BatchEnrollmentService(conn)
        price_val = float(price) if price and price.strip() else None
        paid_val = float(amount_paid) if amount_paid and amount_paid.strip() else 0.0
        status_val = payment_status.strip() if payment_status and payment_status.strip() else None
        notes_val = payment_notes.strip() if payment_notes else ""
        try:
            enroll_svc.update_payment(
                enrollment_id,
                price=price_val,
                amount_paid=paid_val,
                payment_status=status_val,
                payment_notes=notes_val,
            )
            flash(request, "Payment details recorded successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


@app.post("/admin/batches/{batch_id}/unenroll", response_class=HTMLResponse)
async def admin_batch_unenroll(
    request: Request,
    batch_id: int,
    trainee_id: int = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = BatchEnrollmentService(conn)
        try:
            enroll_svc.unenroll(batch_id, trainee_id)
            flash(request, "Student removed from batch.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


# ── SESSIONS ──────────────────────────────────────────────────────────────────

@app.post("/admin/batches/{batch_id}/sessions/create", response_class=HTMLResponse)
async def admin_create_session(
    request: Request,
    batch_id: int,
    title: str = Form(...),
    date: str = Form(""),
    session_number: str = Form(""),
    notes: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        session_svc = SessionService(conn)
        num = int(session_number) if session_number.strip() else None
        try:
            session_svc.create(batch_id, title.strip(),
                               session_number=num,
                               date=date or None,
                               notes=notes or None)
            flash(request, f"Session '{title}' created.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


@app.post("/admin/sessions/{session_id}/status", response_class=HTMLResponse)
async def admin_set_session_status(
    request: Request,
    session_id: int,
    status: str = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        session_svc = SessionService(conn)
        try:
            sess = session_svc.get_by_id(session_id)
            session_svc.set_status(session_id, status)
        except ValueError as e:
            flash(request, str(e), "error")
        # redirect back to batch
        if sess:
            return RedirectResponse(f"/admin/batches/{sess[1]}", status_code=302)
        return RedirectResponse("/admin/courses", status_code=302)
    finally:
        conn.close()


# ── ENROLLMENT REQUESTS ───────────────────────────────────────────────────────

@app.get("/admin/batches/{batch_id}/requests", response_class=HTMLResponse)
async def admin_enrollment_requests(request: Request, batch_id: int, status: str = None):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        req_svc = EnrollmentRequestService(conn)
        batch_svc = BatchService(conn)

        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            flash(request, "Batch not found.", "error")
            return RedirectResponse("/admin/courses", status_code=302)

        requests = req_svc.get_all(batch_id=batch_id, status=status)
        pending_count = len(req_svc.get_pending(batch_id=batch_id))

        return render(request, "admin/enrollment_requests.html",
                      page_title="Enrollment Requests",
                      active_page="enrollment",
                      batch=batch,
                      requests=requests,
                      pending_count=pending_count,
                      current_status=status)
    finally:
        conn.close()


@app.post("/admin/enrollment-requests/{request_id}/approve", response_class=HTMLResponse)
async def admin_approve_request(request: Request, request_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        req_svc = EnrollmentRequestService(conn)
        # Get batch_id for redirect
        cursor = conn.cursor()
        cursor.execute("SELECT batch_id FROM enrollment_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        batch_id = row[0] if row else 0

        try:
            req_svc.approve(request_id, reviewed_by=user["id"])
            flash(request, "Request approved and student enrolled.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}/requests", status_code=302)
    finally:
        conn.close()


@app.post("/admin/enrollment-requests/{request_id}/reject", response_class=HTMLResponse)
async def admin_reject_request(request: Request, request_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        req_svc = EnrollmentRequestService(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT batch_id FROM enrollment_requests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        batch_id = row[0] if row else 0

        try:
            req_svc.reject(request_id, reviewed_by=user["id"])
            flash(request, "Request rejected.", "warning")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}/requests", status_code=302)
    finally:
        conn.close()


# ── CHAPTERS ──────────────────────────────────────────────────────────────────

@app.get("/admin/courses/{course_id}/chapters", response_class=HTMLResponse)
async def admin_course_chapters(request: Request, course_id: int):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        chapter_svc = ChapterService(conn)
        task_svc = TaskService(conn)

        course = course_svc.get_by_id(course_id)
        if not course:
            flash(request, "Course not found.", "error")
            return RedirectResponse("/admin/courses" if user["role"] == "admin" else "/instructor/batches", status_code=302)

        chapters = chapter_svc.get_by_course(course_id)
        all_tasks = task_svc.get_by_course(course_id)

        # Group tasks by chapter_id
        tasks_by_chapter = {}
        for t in all_tasks:
            ch_id = t[2]  # chapter_id column
            tasks_by_chapter.setdefault(ch_id, []).append(t)

        return render(request, "admin/chapters.html",
                      page_title=f"Chapters — {course[1]}",
                      active_page="courses",
                      course=course,
                      chapters=chapters,
                      tasks_by_chapter=tasks_by_chapter)
    finally:
        conn.close()


@app.post("/admin/courses/{course_id}/chapters/create", response_class=HTMLResponse)
async def admin_create_chapter(
    request: Request,
    course_id: int,
    title: str = Form(...),
    description: str = Form(""),
):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        chapter_svc = ChapterService(conn)
        try:
            chapter_svc.create(course_id, title.strip(), description or None)
            flash(request, f"Chapter '{title}' added.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/courses/{course_id}/chapters", status_code=302)
    finally:
        conn.close()


@app.post("/admin/chapters/{chapter_id}/edit", response_class=HTMLResponse)
async def admin_edit_chapter(
    request: Request,
    chapter_id: int,
    title: str = Form(...),
    description: str = Form(""),
    order_index: str = Form(""),
):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        chapter_svc = ChapterService(conn)
        ch = chapter_svc.get_by_id(chapter_id)
        if not ch:
            flash(request, "Chapter not found.", "error")
            return RedirectResponse("/admin/courses" if user["role"] == "admin" else "/instructor/batches", status_code=302)
        course_id = ch[1]
        idx = int(order_index) if order_index.strip() else None
        try:
            chapter_svc.update(chapter_id, title.strip(), description or None, order_index=idx)
            flash(request, "Chapter updated.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/courses/{course_id}/chapters", status_code=302)
    finally:
        conn.close()


@app.post("/admin/chapters/{chapter_id}/delete", response_class=HTMLResponse)
async def admin_delete_chapter(request: Request, chapter_id: int):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        chapter_svc = ChapterService(conn)
        ch = chapter_svc.get_by_id(chapter_id)
        course_id = ch[1] if ch else 0
        try:
            chapter_svc.delete(chapter_id)
            flash(request, "Chapter deleted.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/courses/{course_id}/chapters", status_code=302)
    finally:
        conn.close()


# ── TASKS ─────────────────────────────────────────────────────────────────────

@app.post("/admin/courses/{course_id}/tasks/create", response_class=HTMLResponse)
async def admin_create_task(
    request: Request,
    course_id: int,
    title: str = Form(...),
    task_type: str = Form("assignment"),
    chapter_id: str = Form(""),
    due_date: str = Form(""),
    max_score: float = Form(100.0),
    description: str = Form(""),
    is_required: str = Form(""),
):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        task_svc = TaskService(conn)
        ch_id = int(chapter_id) if chapter_id.strip() else None
        required = is_required == "1"
        try:
            task_svc.create(course_id, title.strip(), description or None,
                            task_type=task_type, chapter_id=ch_id,
                            due_date=due_date or None, max_score=max_score,
                            is_required=required)
            flash(request, f"Task '{title}' added.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/courses/{course_id}/chapters", status_code=302)
    finally:
        conn.close()


@app.post("/admin/tasks/{task_id}/delete", response_class=HTMLResponse)
async def admin_delete_task(request: Request, task_id: int):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        task_svc = TaskService(conn)
        task = task_svc.get_by_id(task_id)
        course_id = task[1] if task else 0
        try:
            task_svc.delete(task_id)
            flash(request, "Task deleted.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/courses/{course_id}/chapters", status_code=302)
    finally:
        conn.close()


# ── BATCH ATTENDANCE ──────────────────────────────────────────────────────────

@app.get("/admin/batches/{batch_id}/attendance", response_class=HTMLResponse)
async def admin_batch_attendance(request: Request, batch_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        session_svc = SessionService(conn)
        enroll_svc = BatchEnrollmentService(conn)
        att_svc = BatchAttendanceService(conn)

        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            flash(request, "Batch not found.", "error")
            return RedirectResponse("/admin/courses", status_code=302)

        sessions = session_svc.get_by_batch(batch_id)
        trainees = enroll_svc.get_batch_trainees(batch_id)
        summary = att_svc.get_attendance_summary(batch_id)

        return render(request, "admin/batch_attendance.html",
                      page_title="Batch Attendance",
                      active_page="attendance",
                      batch=batch,
                      sessions=sessions,
                      trainees=trainees,
                      summary=summary,
                      today=today_str())
    finally:
        conn.close()


@app.post("/admin/batches/{batch_id}/attendance/record", response_class=HTMLResponse)
async def admin_batch_record_attendance(request: Request, batch_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    date_val = form.get("date", today_str())
    session_id_raw = form.get("session_id", "")
    session_id = int(session_id_raw) if session_id_raw.strip() else None

    conn = get_db()
    try:
        att_svc = BatchAttendanceService(conn)
        enroll_svc = BatchEnrollmentService(conn)

        trainees = enroll_svc.get_batch_trainees(batch_id)
        records = []
        for t in trainees:
            tid = t[0]
            status = form.get(f"status_{tid}", "absent")
            notes = form.get(f"notes_{tid}", "")
            records.append({"trainee_id": tid, "status": status, "notes": notes or None})

        saved, errors = att_svc.record_bulk(batch_id, date_val, records,
                                            session_id=session_id, recorded_by=user["id"])

        if errors:
            flash(request, f"{saved} recorded. Errors: {'; '.join(errors)}", "warning")
        else:
            flash(request, f"Attendance for {date_val} saved ({saved} records).", "success")
        return RedirectResponse(f"/admin/batches/{batch_id}/attendance", status_code=302)
    finally:
        conn.close()


# ── GRADING COMPONENTS ────────────────────────────────────────────────────────

@app.post("/admin/batches/{batch_id}/grading-components/create", response_class=HTMLResponse)
async def admin_create_grading_component(
    request: Request,
    batch_id: int,
    name: str = Form(...),
    weight: float = Form(...),
    description: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        grading_svc = GradingService(conn)
        try:
            grading_svc.create_component(batch_id, name.strip(), weight, description or None)
            flash(request, f"Component '{name}' added.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


@app.post("/admin/grading-components/{component_id}/delete", response_class=HTMLResponse)
async def admin_delete_grading_component(request: Request, component_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        grading_svc = GradingService(conn)
        # Find batch_id for redirect
        cursor = conn.cursor()
        cursor.execute("SELECT batch_id FROM grading_components WHERE id = ?", (component_id,))
        row = cursor.fetchone()
        batch_id = row[0] if row else 0
        try:
            grading_svc.delete_component(component_id)
            flash(request, "Component deleted.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


# ── BATCH GRADES ──────────────────────────────────────────────────────────────

@app.get("/admin/batches/{batch_id}/grades", response_class=HTMLResponse)
async def admin_batch_grades(request: Request, batch_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        grading_svc = GradingService(conn)
        bonus_svc = BonusService(conn)
        enroll_svc = BatchEnrollmentService(conn)

        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            flash(request, "Batch not found.", "error")
            return RedirectResponse("/admin/courses", status_code=302)

        components = grading_svc.get_components(batch_id)
        total_weight = grading_svc.get_total_weight(batch_id)
        trainees = enroll_svc.get_batch_trainees(batch_id)
        bonus_totals = bonus_svc.get_batch_bonus_totals(batch_id)
        score_rows = grading_svc.get_all_scores_for_batch(batch_id)
        grades_summary = excel_service.build_batch_grade_rows(
            components, trainees, score_rows, bonus_totals
        )

        return render(request, "admin/batch_grades.html",
                      page_title=f"Grades — {batch[2]}",
                      active_page="grades",
                      batch=batch,
                      components=components,
                      total_weight=total_weight,
                      trainees=trainees,
                      grades_summary=grades_summary)
    finally:
        conn.close()


@app.post("/admin/batches/{batch_id}/grades/save", response_class=HTMLResponse)
async def admin_save_batch_grades(request: Request, batch_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    conn = get_db()
    try:
        grading_svc = GradingService(conn)
        bonus_svc = BonusService(conn)
        enroll_svc = BatchEnrollmentService(conn)

        trainees = enroll_svc.get_batch_trainees(batch_id)
        components = grading_svc.get_components(batch_id)
        saved = 0
        errors = []

        for t in trainees:
            tid = t[0]
            for comp in components:
                cid = comp[0]
                key = f"score_{tid}_{cid}"
                val = form.get(key, "").strip()
                if not val:
                    continue
                try:
                    score = float(val)
                    grading_svc.set_score(cid, tid, score, recorded_by=user["id"])
                    saved += 1
                except (ValueError, TypeError) as e:
                    errors.append(f"Trainee {t[1]}, {comp[2]}: {e}")

            # Handle bonus
            bonus_key = f"bonus_{tid}"
            bonus_val = form.get(bonus_key, "").strip()
            if bonus_val:
                try:
                    bonus_amount = float(bonus_val)
                    if bonus_amount > 0:
                        # Check if bonus already exists for this batch/trainee — just add if new
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT COALESCE(SUM(amount),0) FROM student_bonuses WHERE trainee_id=? AND batch_id=?",
                            (tid, batch_id)
                        )
                        existing_bonus = cursor.fetchone()[0]
                        if abs(bonus_amount - existing_bonus) > 0.001:
                            # Replace with single bonus entry
                            cursor.execute(
                                "DELETE FROM student_bonuses WHERE trainee_id=? AND batch_id=?",
                                (tid, batch_id)
                            )
                            conn.commit()
                            if bonus_amount > 0:
                                bonus_svc.award(tid, bonus_amount, "Grade bonus",
                                               awarded_by=user["id"], batch_id=batch_id)
                except (ValueError, TypeError):
                    pass

        if errors:
            flash(request, f"{saved} saved. Errors: {'; '.join(errors[:3])}", "warning")
        else:
            flash(request, f"{saved} grade(s) saved successfully.", "success")
        return RedirectResponse(f"/admin/batches/{batch_id}/grades", status_code=302)
    finally:
        conn.close()


# ── EXCEL IMPORT / EXPORT ─────────────────────────────────────────────────────

def _export_content_disposition(prefix: str, batch_name: str, batch_id: int) -> str:
    """Build an ASCII-safe attachment header with an RFC 5987 UTF-8 filename."""
    batch_label = str(batch_name or "").strip()
    batch_label = "".join(
        "_" if char in "/\\" or ord(char) < 32 or ord(char) == 127 else char
        for char in batch_label
    )
    batch_label = re.sub(r"\s+", "_", batch_label).strip("._")

    ascii_label = re.sub(r"[^A-Za-z0-9._-]+", "_", batch_label).strip("._-")
    if not ascii_label:
        ascii_label = f"batch_{batch_id}"

    fallback = f"{prefix}_{ascii_label}.xlsx"
    unicode_name = f"{prefix}_{batch_label or f'batch_{batch_id}'}.xlsx"
    encoded_name = quote(unicode_name, safe="")
    return f'attachment; filename="{fallback}"; filename*=UTF-8\'\'{encoded_name}'

def _get_batch_grade_export_rows(connection, batch_id):
    """Load batch grade data in bounded queries, not once per trainee."""
    grading_svc = GradingService(connection)
    enroll_svc = BatchEnrollmentService(connection)
    bonus_svc = BonusService(connection)
    components = grading_svc.get_components(batch_id)
    trainees = enroll_svc.get_batch_trainees(batch_id)
    score_rows = grading_svc.get_all_scores_for_batch(batch_id)
    bonus_totals = bonus_svc.get_batch_bonus_totals(batch_id)
    grade_rows = excel_service.build_batch_grade_rows(
        components, trainees, score_rows, bonus_totals
    )
    return components, trainees, grade_rows


@app.get("/admin/batches/{batch_id}/export-report")
@app.get("/instructor/batches/{batch_id}/export-report")
async def export_official_batch_report(request: Request, batch_id: int):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            return RedirectResponse("/admin/courses" if user["role"] == "admin" else "/instructor/batches", status_code=302)

        if user["role"] == "instructor" and batch[3] != user["id"]:
            flash(request, "Not authorized to export this batch.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        session_svc = SessionService(conn)
        attendance_svc = BatchAttendanceService(conn)
        enroll_svc = BatchEnrollmentService(conn)
        grading_svc = GradingService(conn)
        bonus_svc = BonusService(conn)

        sessions = session_svc.get_by_batch(batch_id)
        trainees = enroll_svc.get_batch_trainees(batch_id)
        attendance_records = attendance_svc.get_batch_attendance_export_data(batch_id)
        components = grading_svc.get_components(batch_id)
        score_rows = grading_svc.get_all_scores_for_batch(batch_id)
        bonus_totals = bonus_svc.get_batch_bonus_totals(batch_id)
        org_name = PublicService(conn).get_org_settings().get("org_name", "")
        batch_info = {
            "academy_name": org_name,
            "course_name": batch[14],
            "batch_name": batch[2],
            "instructor_name": batch[4],
            "start_date": batch[6],
        }

        try:
            file_bytes = excel_service.build_official_batch_workbook(
                batch_info, sessions, trainees, attendance_records,
                components, score_rows, bonus_totals,
            )
            filename = f"batch_{batch_id}_report.xlsx"
            return StreamingResponse(
                io.BytesIO(file_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
            )
        except ImportError:
            flash(request, "openpyxl not installed on server.", "error")
            return RedirectResponse(f"/admin/batches/{batch_id}" if user["role"] == "admin" else "/instructor/batches", status_code=302)
    finally:
        conn.close()

@app.get("/admin/batches/{batch_id}/import")
@app.get("/admin/batches/{batch_id}/import-template")
async def admin_batch_import_page(request: Request, batch_id: int):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            flash(request, "Batch not found.", "error")
            return RedirectResponse("/admin/courses" if user["role"] == "admin" else "/instructor/batches", status_code=302)

        # Generate and return the template for download
        try:
            template_bytes = excel_service.generate_enrollment_template(batch[2])
            filename = f"enrollment_template_{batch[2].replace(' ', '_')}.xlsx"
            return StreamingResponse(
                io.BytesIO(template_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
            )
        except ImportError:
            flash(request, "openpyxl not installed on server.", "error")
            return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


@app.post("/admin/batches/{batch_id}/import", response_class=HTMLResponse)
async def admin_batch_import_upload(
    request: Request,
    batch_id: int,
    file: UploadFile = File(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        file_bytes = await file.read()
        try:
            records = excel_service.parse_enrollment_import(file_bytes)
        except Exception as e:
            flash(request, f"Could not parse file: {e}", "error")
            return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)

        admin_svc = AdminService(conn)
        enroll_svc = BatchEnrollmentService(conn)

        trainee_ids = []
        lookup_errors = []
        for rec in records:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ? AND role = 'trainee'", (rec["email"],))
            row = cursor.fetchone()
            if row:
                trainee_ids.append(row[0])
            else:
                lookup_errors.append(f"Not found: {rec['email']}")

        successes, enroll_errors = enroll_svc.bulk_enroll(batch_id, trainee_ids, enrolled_by=user["id"])
        all_errors = lookup_errors + enroll_errors

        if all_errors:
            flash(request, f"{len(successes)} enrolled. {len(all_errors)} errors: {'; '.join(all_errors[:3])}", "warning")
        else:
            flash(request, f"{len(successes)} student(s) enrolled from Excel.", "success")
        return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


@app.get("/admin/batches/{batch_id}/export-attendance")
@app.get("/instructor/batches/{batch_id}/export-attendance")
async def admin_export_attendance(request: Request, batch_id: int):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        att_svc = BatchAttendanceService(conn)

        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            return RedirectResponse("/admin/courses" if user["role"] == "admin" else "/instructor/batches", status_code=302)

        if user["role"] == "instructor" and batch[3] != user["id"]:
            flash(request, "Not authorized to export attendance for this batch.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        attendance_data = att_svc.get_batch_attendance(batch_id)
        # attendance_data: (uid, uname, date, status, notes, session_title)
        formatted = [(r[1], r[2], r[3], r[5]) for r in attendance_data]

        try:
            file_bytes = excel_service.export_attendance(batch[2], formatted)
            return StreamingResponse(
                io.BytesIO(file_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": _export_content_disposition("attendance", batch[2], batch_id)}
            )
        except ImportError:
            flash(request, "openpyxl not installed on server.", "error")
            return RedirectResponse(f"/admin/batches/{batch_id}", status_code=302)
    finally:
        conn.close()


@app.get("/admin/batches/{batch_id}/export-grades")
@app.get("/instructor/batches/{batch_id}/export-grades")
async def admin_export_grades(request: Request, batch_id: int):
    user = require_roles(request, "admin", "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            return RedirectResponse("/admin/courses" if user["role"] == "admin" else "/instructor/batches", status_code=302)

        if user["role"] == "instructor" and batch[3] != user["id"]:
            flash(request, "Not authorized to export grades for this batch.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        components, _trainees, trainee_grades = _get_batch_grade_export_rows(conn, batch_id)

        try:
            file_bytes = excel_service.export_grades(batch[2], components, trainee_grades)
            return StreamingResponse(
                io.BytesIO(file_bytes),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": _export_content_disposition("grades", batch[2], batch_id)}
            )
        except ImportError:
            flash(request, "openpyxl not installed.", "error")
            return RedirectResponse(f"/admin/batches/{batch_id}/grades", status_code=302)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT — BATCH BROWSING & ENROLLMENT REQUESTS
# ══════════════════════════════════════════════════════════════════════════════

_TRAINEE_UI_MESSAGES = {
    "Batch not found.": "لم نعثر على هذه الدفعة.",
    "This batch is no longer accepting applications.": "لم تعد هذه الدفعة تستقبل طلبات الانضمام.",
    "Trainee not found.": "لم نعثر على حساب المتدرب.",
    "Deactivated trainees cannot submit enrollment requests.": "لا يمكن للحسابات الموقوفة إرسال طلبات الانضمام.",
    "You are already enrolled in this batch.": "أنت مسجل بالفعل في هذه الدفعة.",
    "You already have a pending request for this batch.": "لديك طلب قيد المراجعة لهذه الدفعة بالفعل.",
    "Your request for this batch was already approved.": "تمت الموافقة على طلبك لهذه الدفعة مسبقًا.",
    "You are not enrolled in this batch.": "أنت غير مسجل في هذه الدفعة.",
    "Submission must include a URL or text.": "أضف رابط الحل أو اكتب نصه قبل الإرسال.",
    "Task not found.": "لم نعثر على هذه المهمة.",
    "Trainee is not enrolled in this batch.": "أنت غير مسجل في هذه الدفعة.",
}


def _trainee_ui_message(message):
    return _TRAINEE_UI_MESSAGES.get(message, message)

@app.get("/trainee/batches", response_class=HTMLResponse)
async def trainee_batches(request: Request):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = BatchEnrollmentService(conn)
        req_svc = EnrollmentRequestService(conn)

        my_batches = enroll_svc.get_trainee_batches(user["id"])
        my_requests = req_svc.get_trainee_requests(user["id"])

        return render(request, "trainee/batches.html",
                      page_title="دفعاتي التدريبية",
                      active_page="batches",
                      my_batches=my_batches,
                      my_requests=my_requests)
    finally:
        conn.close()


@app.get("/trainee/browse", response_class=HTMLResponse)
async def trainee_browse_courses(request: Request):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        course_svc = CourseService(conn)
        batch_svc = BatchService(conn)

        courses = course_svc.get_active_courses()
        # For each course, get its open batches
        courses_with_batches = []
        for c in courses:
            batches = batch_svc.get_by_course(c[0], include_cancelled=False)
            open_batches = [b for b in batches if b[8] in ("upcoming", "active")]
            courses_with_batches.append((c, open_batches))

        return render(request, "trainee/browse.html",
                      page_title="استعراض الدورات",
                      active_page="browse",
                      courses_with_batches=courses_with_batches)
    finally:
        conn.close()


@app.post("/trainee/batches/{batch_id}/request", response_class=HTMLResponse)
async def trainee_request_enrollment(
    request: Request,
    batch_id: int,
    trainee_note: str = Form(""),
    return_to: str = Form(""),
):
    user = require_role(request, "trainee")
    if not user:
        redirect_target = return_to if (return_to and return_to.startswith("/")) else f"/trainee/browse"
        return RedirectResponse(f"/login?next={redirect_target}", status_code=302)

    conn = get_db()
    try:
        req_svc = EnrollmentRequestService(conn)
        try:
            req_svc.submit_request(batch_id, user["id"], trainee_note or None)
            flash(request, "تم إرسال طلب الانضمام. سنُعلمك بعد مراجعته من قِبل إدارة القبول.", "success")
        except ValueError as e:
            flash(request, _trainee_ui_message(str(e)), "error")

        if return_to and return_to.startswith("/") and not return_to.startswith("//"):
            return RedirectResponse(return_to, status_code=302)
        return RedirectResponse("/trainee/browse", status_code=302)
    finally:
        conn.close()


@app.get("/trainee/batches/{batch_id}/progress", response_class=HTMLResponse)
async def trainee_batch_progress(request: Request, batch_id: int):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        enroll_svc = BatchEnrollmentService(conn)
        batch_svc = BatchService(conn)
        att_svc = BatchAttendanceService(conn)
        grading_svc = GradingService(conn)
        bonus_svc = BonusService(conn)
        submission_svc = SubmissionService(conn)

        if not enroll_svc.is_enrolled(batch_id, user["id"]):
            flash(request, "أنت غير مسجل في هذه الدفعة.", "error")
            return RedirectResponse("/trainee/batches", status_code=302)

        batch = batch_svc.get_by_id(batch_id)
        attendance = att_svc.get_trainee_attendance(batch_id, user["id"])
        scores = grading_svc.get_scores_for_trainee(batch_id, user["id"])
        final_grade = grading_svc.calculate_final_grade(batch_id, user["id"])
        bonuses = bonus_svc.get_trainee_bonuses(user["id"], batch_id=batch_id)
        total_bonus = bonus_svc.get_total_bonus(user["id"], batch_id=batch_id)
        submissions = submission_svc.get_by_trainee(user["id"])

        task_svc = TaskService(conn)
        tasks = task_svc.get_by_course(batch[1])
        task_submissions_map = {s[1]: s for s in submissions}

        # Attendance stats
        total_att = len(attendance)
        present_count = sum(1 for a in attendance if a[1] == "present")
        att_rate = round(present_count / total_att * 100, 1) if total_att else 0
        enrollment = enroll_svc.get_enrollment(batch_id, user["id"])

        return render(request, "trainee/batch_progress.html",
                      page_title=f"متابعة الدفعة — {batch[2]}",
                      active_page="batches",
                      batch=batch,
                      attendance=attendance,
                      scores=scores,
                      final_grade=final_grade,
                      bonuses=bonuses,
                      total_bonus=total_bonus,
                      tasks=tasks,
                      submissions=submissions,
                      task_submissions_map=task_submissions_map,
                      total_att=total_att,
                      present_count=present_count,
                      att_rate=att_rate,
                      enrollment=enrollment)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# INSTRUCTOR — BATCH MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/instructor/batches", response_class=HTMLResponse)
async def instructor_batches(request: Request):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        batches = batch_svc.get_instructor_batches(user["id"])
        return render(request, "instructor/batches.html",
                      page_title="My Batches",
                      active_page="batches",
                      batches=batches)
    finally:
        conn.close()


@app.get("/instructor/batches/{batch_id}/attendance", response_class=HTMLResponse)
async def instructor_batch_attendance(request: Request, batch_id: int):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        session_svc = SessionService(conn)
        enroll_svc = BatchEnrollmentService(conn)
        att_svc = BatchAttendanceService(conn)

        batch = batch_svc.get_by_id(batch_id)
        if not batch or batch[3] != user["id"]:
            flash(request, "Batch not found or not assigned to you.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        sessions = session_svc.get_by_batch(batch_id)
        trainees = enroll_svc.get_batch_trainees(batch_id)
        summary = att_svc.get_attendance_summary(batch_id)

        return render(request, "admin/batch_attendance.html",
                      page_title="Batch Attendance",
                      active_page="attendance",
                      batch=batch,
                      sessions=sessions,
                      trainees=trainees,
                      summary=summary,
                      today=today_str())
    finally:
        conn.close()


@app.post("/instructor/batches/{batch_id}/attendance/record", response_class=HTMLResponse)
async def instructor_batch_record_attendance(request: Request, batch_id: int):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    date_val = form.get("date", today_str())
    session_id_raw = form.get("session_id", "")
    session_id = int(session_id_raw) if session_id_raw.strip() else None

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        batch = batch_svc.get_by_id(batch_id)
        if not batch or batch[3] != user["id"]:
            flash(request, "Not authorized.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        att_svc = BatchAttendanceService(conn)
        enroll_svc = BatchEnrollmentService(conn)
        trainees = enroll_svc.get_batch_trainees(batch_id)
        records = []
        for t in trainees:
            tid = t[0]
            status = form.get(f"status_{tid}", "absent")
            notes = form.get(f"notes_{tid}", "")
            records.append({"trainee_id": tid, "status": status, "notes": notes or None})

        saved, errors = att_svc.record_bulk(batch_id, date_val, records,
                                            session_id=session_id, recorded_by=user["id"])
        if errors:
            flash(request, f"{saved} recorded. Errors: {'; '.join(errors)}", "warning")
        else:
            flash(request, f"Attendance for {date_val} saved.", "success")
        return RedirectResponse(f"/instructor/batches/{batch_id}/attendance", status_code=302)
    finally:
        conn.close()


@app.get("/instructor/batches/{batch_id}/grades", response_class=HTMLResponse)
async def instructor_batch_grades(request: Request, batch_id: int):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        grading_svc = GradingService(conn)
        bonus_svc = BonusService(conn)
        enroll_svc = BatchEnrollmentService(conn)

        batch = batch_svc.get_by_id(batch_id)
        if not batch or batch[3] != user["id"]:
            flash(request, "Not authorized.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        components = grading_svc.get_components(batch_id)
        total_weight = grading_svc.get_total_weight(batch_id)
        trainees = enroll_svc.get_batch_trainees(batch_id)
        bonus_totals = bonus_svc.get_batch_bonus_totals(batch_id)
        score_rows = grading_svc.get_all_scores_for_batch(batch_id)
        grades_summary = excel_service.build_batch_grade_rows(
            components, trainees, score_rows, bonus_totals
        )

        return render(request, "admin/batch_grades.html",
                      page_title=f"Grades — {batch[2]}",
                      active_page="grades",
                      batch=batch,
                      components=components,
                      total_weight=total_weight,
                      trainees=trainees,
                      grades_summary=grades_summary)
    finally:
        conn.close()


@app.post("/instructor/batches/{batch_id}/grades/save", response_class=HTMLResponse)
async def instructor_save_batch_grades(request: Request, batch_id: int):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()
    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        batch = batch_svc.get_by_id(batch_id)
        if not batch or batch[3] != user["id"]:
            flash(request, "Not authorized.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        grading_svc = GradingService(conn)
        enroll_svc = BatchEnrollmentService(conn)
        trainees = enroll_svc.get_batch_trainees(batch_id)
        components = grading_svc.get_components(batch_id)
        saved = 0

        for t in trainees:
            tid = t[0]
            for comp in components:
                cid = comp[0]
                val = form.get(f"score_{tid}_{cid}", "").strip()
                if not val:
                    continue
                try:
                    grading_svc.set_score(cid, tid, float(val), recorded_by=user["id"])
                    saved += 1
                except (ValueError, TypeError):
                    pass

        flash(request, f"{saved} grade(s) saved.", "success")
        return RedirectResponse(f"/instructor/batches/{batch_id}/grades", status_code=302)
    finally:
        conn.close()



# ══════════════════════════════════════════════════════════════════════════════
# STUDENT TASK SUBMISSION
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/trainee/tasks/{task_id}/submit", response_class=HTMLResponse)
async def trainee_submit_task(
    request: Request,
    task_id: int,
    batch_id: int = Form(...),
    submission_url: str = Form(""),
    submission_text: str = Form(""),
):
    user = require_role(request, "trainee")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        sub_svc = SubmissionService(conn)
        url = submission_url.strip() if submission_url else None
        text = submission_text.strip() if submission_text else None
        try:
            sub_svc.submit(task_id, user["id"], batch_id=batch_id,
                           submission_url=url, submission_text=text)
            flash(request, "تم إرسال حل المهمة بنجاح.", "success")
        except ValueError as e:
            flash(request, _trainee_ui_message(str(e)), "error")
        return RedirectResponse(f"/trainee/batches/{batch_id}/progress", status_code=302)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# INSTRUCTOR & ADMIN — TASK SUBMISSION REVIEWS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/instructor/batches/{batch_id}/submissions", response_class=HTMLResponse)
async def instructor_batch_submissions(request: Request, batch_id: int):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        batch = batch_svc.get_by_id(batch_id)
        if not batch or batch[3] != user["id"]:
            flash(request, "Not authorized.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        sub_svc = SubmissionService(conn)
        submissions = sub_svc.get_by_batch(batch_id)
        return render(request, "instructor/batch_submissions.html",
                      page_title=f"Submissions — {batch[2]}",
                      active_page="batches",
                      batch=batch,
                      submissions=submissions)
    finally:
        conn.close()


@app.post("/instructor/submissions/{submission_id}/review", response_class=HTMLResponse)
async def instructor_review_submission(
    request: Request,
    submission_id: int,
    status: str = Form(...),
    score: str = Form(""),
    feedback: str = Form(""),
):
    user = require_role(request, "instructor")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        sub_svc = SubmissionService(conn)
        sub = sub_svc.get_by_id(submission_id)
        if not sub:
            flash(request, "Submission not found.", "error")
            return RedirectResponse("/instructor/batches", status_code=302)

        batch_id = sub[5]
        score_val = float(score) if score and score.strip() else None
        feedback_val = feedback.strip() if feedback else None
        try:
            sub_svc.review(submission_id, status=status, score=score_val,
                           feedback=feedback_val, reviewed_by=user["id"])
            flash(request, "Submission review saved successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/instructor/batches/{batch_id}/submissions", status_code=302)
    finally:
        conn.close()


@app.get("/admin/batches/{batch_id}/submissions", response_class=HTMLResponse)
async def admin_batch_submissions(request: Request, batch_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        batch_svc = BatchService(conn)
        batch = batch_svc.get_by_id(batch_id)
        if not batch:
            flash(request, "Batch not found.", "error")
            return RedirectResponse("/admin/courses", status_code=302)

        sub_svc = SubmissionService(conn)
        submissions = sub_svc.get_by_batch(batch_id)
        return render(request, "instructor/batch_submissions.html",
                      page_title=f"Submissions — {batch[2]}",
                      active_page="courses",
                      batch=batch,
                      submissions=submissions)
    finally:
        conn.close()


@app.post("/admin/submissions/{submission_id}/review", response_class=HTMLResponse)
async def admin_review_submission(
    request: Request,
    submission_id: int,
    status: str = Form(...),
    score: str = Form(""),
    feedback: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        sub_svc = SubmissionService(conn)
        sub = sub_svc.get_by_id(submission_id)
        if not sub:
            flash(request, "Submission not found.", "error")
            return RedirectResponse("/admin/courses", status_code=302)

        batch_id = sub[5]
        score_val = float(score) if score and score.strip() else None
        feedback_val = feedback.strip() if feedback else None
        try:
            sub_svc.review(submission_id, status=status, score=score_val,
                           feedback=feedback_val, reviewed_by=user["id"])
            flash(request, "Submission review saved successfully.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}/submissions", status_code=302)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# BONUS MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/admin/batches/{batch_id}/bonuses/add", response_class=HTMLResponse)
async def admin_add_batch_bonus(
    request: Request,
    batch_id: int,
    trainee_id: int = Form(...),
    amount: float = Form(...),
    reason: str = Form(...),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        bonus_svc = BonusService(conn)
        try:
            bonus_svc.award(trainee_id, amount, reason.strip(), awarded_by=user["id"], batch_id=batch_id)
            flash(request, f"+{amount} bonus points awarded.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(f"/admin/batches/{batch_id}/grades", status_code=302)
    finally:
        conn.close()


@app.post("/admin/bonuses/{bonus_id}/delete", response_class=HTMLResponse)
async def admin_delete_bonus(request: Request, bonus_id: int, redirect_to: str = Form("/admin/courses")):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        bonus_svc = BonusService(conn)
        try:
            bonus_svc.delete(bonus_id)
            flash(request, "Bonus removed.", "success")
        except ValueError as e:
            flash(request, str(e), "error")
        return RedirectResponse(redirect_to, status_code=302)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — PUBLIC WEBSITE & CONTENT MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/website/settings", response_class=HTMLResponse)
async def admin_website_settings(request: Request, tab: str = "org"):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        org = pub_svc.get_org_settings()
        gallery_items = pub_svc.get_all_gallery_items()
        testimonials = pub_svc.get_all_testimonials()
        contact_messages = pub_svc.get_contact_messages()
        return render(
            request,
            "admin/website_settings.html",
            page_title="Website & Content Management",
            active_page="website_settings",
            org_settings=org,
            org=org,
            gallery_items=gallery_items,
            testimonials=testimonials,
            contact_messages=contact_messages,
            active_tab=tab,
        )
    finally:
        conn.close()


@app.post("/admin/website/settings", response_class=HTMLResponse)
async def admin_update_website_settings(
    request: Request,
    org_name: str = Form(...),
    tagline: str = Form(""),
    hero_headline: str = Form(...),
    hero_subheadline: str = Form(""),
    about_text: str = Form(""),
    approach_text: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    whatsapp: str = Form(""),
    working_hours: str = Form(""),
    address: str = Form(""),
    facebook_url: str = Form(""),
    linkedin_url: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        pub_svc.update_org_settings(
            org_name=org_name.strip(),
            tagline=tagline.strip(),
            hero_headline=hero_headline.strip(),
            hero_subheadline=hero_subheadline.strip(),
            about_text=about_text.strip(),
            approach_text=approach_text.strip(),
            email=email.strip(),
            phone=phone.strip(),
            whatsapp=whatsapp.strip(),
            working_hours=working_hours.strip(),
            address=address.strip(),
            facebook_url=facebook_url.strip(),
            linkedin_url=linkedin_url.strip(),
        )
        flash(request, "Organization settings updated successfully!", "success")
        return RedirectResponse("/admin/website/settings?tab=org", status_code=302)
    except Exception as e:
        flash(request, f"Failed to update settings: {e}", "error")
        return RedirectResponse("/admin/website/settings?tab=org", status_code=302)
    finally:
        conn.close()


@app.post("/admin/website/gallery/add", response_class=HTMLResponse)
async def admin_add_gallery_item(
    request: Request,
    title: str = Form(...),
    image_url: str = Form(...),
    category: str = Form("Graduation"),
    caption: str = Form(""),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        pub_svc.add_gallery_item(
            title=title.strip(),
            image_url=image_url.strip(),
            category=category.strip(),
            caption=caption.strip(),
            display_order=0,
            is_visible=True
        )
        flash(request, "Gallery photo added successfully!", "success")
        return RedirectResponse("/admin/website/settings?tab=gallery", status_code=302)
    except Exception as e:
        flash(request, f"Error adding gallery item: {e}", "error")
        return RedirectResponse("/admin/website/settings?tab=gallery", status_code=302)
    finally:
        conn.close()


@app.post("/admin/website/gallery/{item_id}/delete", response_class=HTMLResponse)
async def admin_delete_gallery_item(request: Request, item_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        pub_svc.delete_gallery_item(item_id)
        flash(request, "Gallery photo removed.", "success")
        return RedirectResponse("/admin/website/settings?tab=gallery", status_code=302)
    finally:
        conn.close()


@app.post("/admin/website/testimonials/add", response_class=HTMLResponse)
async def admin_add_testimonial(
    request: Request,
    student_name: str = Form(...),
    content: str = Form(...),
    role_or_course: str = Form(""),
    rating: int = Form(5),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        pub_svc.add_testimonial(
            student_name=student_name.strip(),
            content=content.strip(),
            role_or_course=role_or_course.strip(),
            rating=rating,
            is_approved=True,
        )
        flash(request, "Testimonial published successfully!", "success")
        return RedirectResponse("/admin/website/settings?tab=testimonials", status_code=302)
    except Exception as e:
        flash(request, f"Error publishing testimonial: {e}", "error")
        return RedirectResponse("/admin/website/settings?tab=testimonials", status_code=302)
    finally:
        conn.close()


@app.post("/admin/website/testimonials/{test_id}/delete", response_class=HTMLResponse)
async def admin_delete_testimonial(request: Request, test_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        pub_svc.delete_testimonial(test_id)
        flash(request, "Testimonial deleted.", "success")
        return RedirectResponse("/admin/website/settings?tab=testimonials", status_code=302)
    finally:
        conn.close()


@app.post("/admin/website/messages/{msg_id}/status", response_class=HTMLResponse)
async def admin_update_message_status(request: Request, msg_id: int, status: str = Form(...)):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        pub_svc.update_contact_message_status(msg_id, status, handled_by=user["id"])
        flash(request, f"Message status updated to {status}.", "success")
        return RedirectResponse("/admin/website/settings?tab=messages", status_code=302)
    finally:
        conn.close()


@app.post("/admin/website/messages/{msg_id}/delete", response_class=HTMLResponse)
async def admin_delete_message(request: Request, msg_id: int):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        pub_svc = PublicService(conn)
        pub_svc.delete_contact_message(msg_id)
        flash(request, "Message deleted.", "success")
        return RedirectResponse("/admin/website/settings?tab=messages", status_code=302)
    finally:
        conn.close()


@app.post("/admin/trainees/{trainee_id}/toggle-public-profile", response_class=HTMLResponse)
async def admin_toggle_trainee_public(
    request: Request,
    trainee_id: int,
    current_val: int = Form(0),
):
    user = require_role(request, "admin")
    if not user:
        return RedirectResponse("/login", status_code=302)

    conn = get_db()
    try:
        admin_svc = AdminService(conn)
        new_val = 0 if current_val == 1 else 1
        admin_svc.update_trainee_public_visibility(trainee_id, show_on_public=new_val)
        status_text = "now visible on" if new_val == 1 else "hidden from"
        flash(request, f"Student is {status_text} the public showcase.", "success")
        return RedirectResponse("/admin/trainees", status_code=302)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_app:app", host="127.0.0.1", port=8000, reload=True)
