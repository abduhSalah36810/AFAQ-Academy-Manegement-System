import os
import sys

os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["SQLITE_DB_PATH"] = "test_phase3_admin.db"

if os.path.exists("test_phase3_admin.db"):
    try:
        os.remove("test_phase3_admin.db")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath("."))

from database import create_tables, get_connection
create_tables()

import asyncio
from starlette.requests import Request
import web_app
from services.course_service import CourseService
from services.batch_service import BatchService

def make_request(path="/", method="GET", session=None):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "session": session if session is not None else {},
    }
    return Request(scope)

async def test_admin_pages():
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (1, 'Admin', 'admin@afaq.edu', 'hash', 'admin', 1)")
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (2, 'Instructor Jane', 'jane@afaq.edu', 'hash', 'instructor', 1)")
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (3, 'Trainee Omar', 'omar@afaq.edu', 'hash', 'trainee', 1)")
    conn.commit()

    course_svc = CourseService(conn)
    course_id = course_svc.create("Full-Stack Web Dev", instructor_id=2, description="Course description")

    batch_svc = BatchService(conn)
    batch_id = batch_svc.create(course_id, "Batch 101", instructor_id=2)

    session = {"user": {"id": 1, "role": "admin", "name": "Admin", "email": "admin@afaq.edu"}}

    # 1. Dashboard
    resp = await web_app.admin_dashboard(make_request("/admin/dashboard", session=session))
    assert 'لوحة التحكم' in resp.body.decode("utf-8")
    print("[OK] Admin Dashboard verified")

    # 2. Trainees
    resp = await web_app.admin_trainees(make_request("/admin/trainees", session=session))
    assert 'المتدربون' in resp.body.decode("utf-8")
    print("[OK] Admin Trainees verified")

    # 3. Instructors
    resp = await web_app.admin_instructors(make_request("/admin/instructors", session=session))
    assert 'المحاضرون' in resp.body.decode("utf-8")
    print("[OK] Admin Instructors verified")

    # 4. Courses
    resp = await web_app.admin_courses(make_request("/admin/courses", session=session))
    assert 'الدورات التدريبية' in resp.body.decode("utf-8")
    print("[OK] Admin Courses verified")

    # 5. Batches
    resp = await web_app.admin_course_batches(make_request(f"/admin/courses/{course_id}/batches", session=session), course_id=course_id)
    assert 'الدفعات' in resp.body.decode("utf-8")
    print("[OK] Admin Batches verified")

    # 6. Batch Detail
    resp = await web_app.admin_batch_detail(make_request(f"/admin/batches/{batch_id}", session=session), batch_id=batch_id)
    assert 'الدفعة' in resp.body.decode("utf-8")
    print("[OK] Admin Batch Detail verified")

    # 7. Enrollment
    resp = await web_app.admin_enrollment(make_request("/admin/enrollment", session=session))
    assert 'التسجيل والقبول' in resp.body.decode("utf-8")
    print("[OK] Admin Enrollment verified")

    # 8. Attendance
    resp = await web_app.admin_attendance(make_request("/admin/attendance", session=session))
    assert 'سجلات الحضور' in resp.body.decode("utf-8")
    print("[OK] Admin Attendance verified")

    # 9. Grades
    resp = await web_app.admin_grades(make_request("/admin/grades", session=session))
    assert 'كشوف الدرجات' in resp.body.decode("utf-8")
    print("[OK] Admin Grades verified")

    # 10. Website Settings
    resp = await web_app.admin_website_settings(make_request("/admin/website/settings", session=session))
    assert 'إعدادات الموقع والمحتوى العام' in resp.body.decode("utf-8")
    print("[OK] Admin Website Settings verified")

    print("\nALL ADMIN TEMPLATES VERIFIED SUCCESSFULLY (10/10)!")

if __name__ == "__main__":
    asyncio.run(test_admin_pages())
