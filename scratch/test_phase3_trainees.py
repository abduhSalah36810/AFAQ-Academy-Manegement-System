import os
import sys

os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["SQLITE_DB_PATH"] = "test_phase3.db"

if os.path.exists("test_phase3.db"):
    try:
        os.remove("test_phase3.db")
    except Exception:
        pass

sys.path.insert(0, os.path.abspath("."))

from database import create_tables, get_connection
create_tables()

import asyncio
from starlette.requests import Request
import web_app

def make_request(path="/", method="GET", session=None):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "session": session if session is not None else {},
    }
    return Request(scope)

async def test_trainees_page():
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (1, 'Admin', 'admin@afaq.edu', 'hash', 'admin', 1)")
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active, show_on_public_profile, public_bio) VALUES (10, 'خالد علي', 'khaled@example.com', 'hash', 'trainee', 1, 1, 'مهندس برمجيات')")
    c.execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active, show_on_public_profile) VALUES (11, 'سارة حسن', 'sara@example.com', 'hash', 'trainee', 0, 0)")
    conn.commit()

    req = make_request("/admin/trainees", session={"user": {"id": 1, "role": "admin", "name": "Admin", "email": "admin@afaq.edu"}})
    resp = await web_app.admin_trainees(req)
    html = resp.body.decode("utf-8")

    assert 'المتدربون' in html
    assert 'خالد علي' in html
    assert 'sara@example.com' in html
    assert 'نشط' in html
    assert 'معطل' in html
    assert 'col-actions' in html
    assert 'ltr-cell' in html
    assert 'إضافة متدرب' in html
    assert 'تعديل بيانات المتدرب' in html
    print("[OK] Admin Trainees page rendered successfully with Arabic RTL standardization!")

if __name__ == "__main__":
    asyncio.run(test_trainees_page())
