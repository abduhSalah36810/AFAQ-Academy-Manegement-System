import os
import sys

# Isolate to local SQLite DB
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["SQLITE_DB_PATH"] = "test_phase2.db"

if os.path.exists("test_phase2.db"):
    try:
        os.remove("test_phase2.db")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath("."))

from database import create_tables, get_connection
create_tables()

import asyncio
from starlette.requests import Request
import web_app
from services.course_service import CourseService

def make_request(path="/", method="GET", session=None):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "session": session if session is not None else {},
    }
    return Request(scope)

async def run_tests():
    print("--- Testing Phase 2 Foundation Rendering ---")
    conn = get_connection()
    c = conn.cursor()

    # Seed test users
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (1, 'Admin User', 'admin@afaq.admin.edu', 'hash123', 'admin', 1)")
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (2, 'Instructor Jane', 'jane@afaq.instructor.edu', 'hash123', 'instructor', 1)")
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (3, 'Trainee Omar', 'omar@afaq.trainee.edu', 'hash123', 'trainee', 1)")
    conn.commit()

    course_svc = CourseService(conn)
    course_svc.create("Full-Stack Web Development", instructor_id=2, description="Bootcamp description")

    # 1. Login Page
    req = make_request("/login")
    resp = await web_app.login_page(req)
    html = resp.body.decode("utf-8")
    assert 'dir="rtl"' in html, "RTL attribute missing in login page"
    assert 'lang="ar"' in html, "lang=ar attribute missing in login page"
    assert 'Cairo' in html, "Cairo font link missing in login page"
    assert 'main.css' in html, "main.css link missing in login page"
    assert 'main.js' in html, "main.js link missing in login page"
    print("[OK] 1. Login page: dir='rtl', lang='ar', Cairo font, main.css, main.js verified")

    # 2. Public Home Page
    req = make_request("/")
    resp = await web_app.public_home(req)
    html = resp.body.decode("utf-8")
    assert 'dir="rtl"' in html, "RTL attribute missing in public page"
    assert 'lang="ar"' in html, "lang=ar attribute missing in public page"
    print("[OK] 2. Public home page: dir='rtl', lang='ar' verified")

    # 3. Admin Dashboard
    admin_session = {
        "user": {
            "id": 1,
            "role": "admin",
            "name": "مدير النظام",
            "email": "admin@afaq.admin.edu"
        }
    }
    req = make_request("/admin/dashboard", session=admin_session)
    resp = await web_app.admin_dashboard(req)
    html = resp.body.decode("utf-8")
    assert 'dir="rtl"' in html, "RTL attribute missing in admin dashboard"
    assert 'lang="ar"' in html, "lang=ar attribute missing in admin dashboard"
    assert 'Cairo' in html, "Cairo font missing in admin dashboard"
    assert 'لوحة التحكم' in html, "Arabic 'لوحة التحكم' missing in sidebar"
    assert 'الإدارة الأكاديمية' in html, "Arabic 'الإدارة الأكاديمية' missing in sidebar"
    assert 'المتدربون' in html, "Arabic 'المتدربون' missing in sidebar"
    assert 'المحاضرون' in html, "Arabic 'المحاضرون' missing in sidebar"
    assert 'الدورات التدريبية' in html, "Arabic 'الدورات التدريبية' missing in sidebar"
    assert 'التسجيل والقبول' in html, "Arabic 'التسجيل والقبول' missing in sidebar"
    assert 'سجلات الحضور' in html, "Arabic 'سجلات الحضور' missing in sidebar"
    assert 'كشوف الدرجات' in html, "Arabic 'كشوف الدرجات' missing in sidebar"
    assert 'تسجيل الخروج' in html, "Arabic 'تسجيل الخروج' missing"
    assert 'مدير النظام' in html, "Arabic role badge missing"
    print("[OK] 3. Admin dashboard: full Arabic sidebar navigation & header confirmed")

    # 4. Instructor Dashboard
    inst_session = {
        "user": {
            "id": 2,
            "role": "instructor",
            "name": "محاضر تجريبي",
            "email": "jane@afaq.instructor.edu"
        }
    }
    req = make_request("/instructor/dashboard", session=inst_session)
    resp = await web_app.instructor_dashboard(req)
    html = resp.body.decode("utf-8")
    assert 'dir="rtl"' in html
    assert 'مساحة العمل' in html, "Arabic 'مساحة العمل' missing for instructor"
    assert 'دفعاتي التدريبية' in html, "Arabic 'دفعاتي التدريبية' missing"
    assert 'دوراتي' in html, "Arabic 'دوراتي' missing"
    assert 'طلابي' in html, "Arabic 'طلابي' missing"
    assert 'رصد الحضور' in html, "Arabic 'رصد الحضور' missing"
    assert 'رصد الدرجات' in html, "Arabic 'رصد الدرجات' missing"
    assert 'المحاضر' in html, "Arabic instructor role badge missing"
    print("[OK] 4. Instructor dashboard: Arabic workspace navigation confirmed")

    # 5. Trainee Dashboard
    trainee_session = {
        "user": {
            "id": 3,
            "role": "trainee",
            "name": "متدرب تجريبي",
            "email": "omar@afaq.trainee.edu"
        }
    }
    req = make_request("/trainee/dashboard", session=trainee_session)
    resp = await web_app.trainee_dashboard(req)
    html = resp.body.decode("utf-8")
    assert 'dir="rtl"' in html
    assert 'مساحتي التعليمية' in html, "Arabic 'مساحتي التعليمية' missing for trainee"
    assert 'لوحة المتابعة' in html, "Arabic 'لوحة المتابعة' missing"
    assert 'استعراض الدورات' in html, "Arabic 'استعراض الدورات' missing"
    assert 'دفعاتي' in html, "Arabic 'دفعاتي' missing"
    assert 'سجلي في الحضور' in html, "Arabic 'سجلي في الحضور' missing"
    assert 'درجاتي وتقييماتي' in html, "Arabic 'درجاتي وتقييماتي' missing"
    assert 'المتدرب' in html, "Arabic trainee role badge missing"
    print("[OK] 5. Trainee dashboard: Arabic learning space navigation confirmed")

    # 6. Verify CSS & JS assets
    css_content = open("web/static/css/main.css", "r", encoding="utf-8").read()
    assert "Cairo" in css_content, "Cairo font declaration missing in main.css"
    assert "direction: rtl" in css_content, "direction: rtl missing in main.css"
    assert "right: 0" in css_content, "Sidebar right-alignment missing in main.css"
    assert "margin-right: var(--sidebar-width)" in css_content, "Main wrapper margin-right missing in main.css"
    assert "background-position: left" in css_content, "Form-select left chevron missing in main.css"
    assert ".table-wrapper" in css_content, "Table foundation missing in main.css"
    assert ".badge-" in css_content, "Badge system missing in main.css"
    print("[OK] 6. main.css design system tokens & RTL layout verified")

    js_content = open("web/static/js/main.js", "r", encoding="utf-8").read()
    assert "هل أنت متأكد" in js_content, "Arabic confirmation fallback missing in main.js"
    print("[OK] 7. main.js Arabic confirmation fallback verified")

    print("\n=======================================================")
    print("SUCCESS: ALL PHASE 2 VERIFICATIONS PASSED (7/7)!")
    print("=======================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
