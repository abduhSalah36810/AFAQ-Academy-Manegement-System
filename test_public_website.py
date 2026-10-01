import os
import sys
import unittest
import asyncio
from starlette.requests import Request

# Ensure test DB is used
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["SQLITE_DB_PATH"] = "test_public_website.db"

if os.path.exists("test_public_website.db"):
    os.remove("test_public_website.db")

from database import create_tables, get_connection
create_tables()

import web_app
from services.Admin_service import AdminService
from services.course_service import CourseService
from services.batch_service import BatchService
from services.chapter_service import ChapterService
from services.public_service import PublicService
from services.auth_service import AuthService


def make_request(path="/", method="GET", session=None, form_data=None):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "session": session if session is not None else {},
    }
    return Request(scope)


class TestPublicWebsite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = get_connection()

        # Seed users
        cls.conn.cursor().execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (1, 'Admin User', 'admin@afaq.admin.edu', 'hash123', 'admin', 1)")
        cls.conn.cursor().execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active) VALUES (2, 'Instructor Jane', 'jane@afaq.instructor.edu', 'hash123', 'instructor', 1)")
        cls.conn.cursor().execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active, show_on_public_profile, public_bio, graduation_status) VALUES (3, 'Trainee Omar', 'omar@afaq.trainee.edu', 'hash123', 'trainee', 1, 1, 'Top graduated engineer', 'Graduate')")
        cls.conn.cursor().execute("INSERT OR REPLACE INTO users (id, name, email, password_hash, role, active, show_on_public_profile) VALUES (4, 'Private Trainee', 'private@afaq.trainee.edu', 'hash123', 'trainee', 1, 0)")
        cls.conn.commit()

        # Seed Course & Batches
        course_svc = CourseService(cls.conn)
        cls.course_id = course_svc.create(
            name="Full-Stack Web Development",
            description="Comprehensive bootcamp covering Next.js, Python, and Databases.",
            instructor_id=2
        )
        cls.conn.cursor().execute("""
            UPDATE courses
            SET is_public = 1, price = 250.0, show_price_publicly = 1,
                category = 'Software Engineering', level = 'Intermediate',
                prerequisites = 'Basic JavaScript knowledge'
            WHERE id = ?
        """, (cls.course_id,))
        cls.conn.commit()

        # Add chapters
        ch_svc = ChapterService(cls.conn)
        ch_svc.create(cls.course_id, "Frontend Mastery", "Modern React & Next.js", 1)
        ch_svc.create(cls.course_id, "Backend & APIs", "FastAPI and Database Architecture", 2)

        # Add Batches
        batch_svc = BatchService(cls.conn)
        cls.batch_open_id = batch_svc.create(
            course_id=cls.course_id,
            name="FSW-01 (Fall Cohort)",
            start_date="2026-11-01",
            end_date="2027-02-01",
            capacity=15,
            instructor_id=2,
            notes="Evening sessions via hybrid campus."
        )
        cls.conn.cursor().execute("UPDATE batches SET is_public = 1, status = 'upcoming' WHERE id = ?", (cls.batch_open_id,))

        cls.batch_completed_id = batch_svc.create(
            course_id=cls.course_id,
            name="FSW-00 (Pilot Cohort)",
            start_date="2026-05-01",
            end_date="2026-08-01",
            capacity=10,
            instructor_id=2
        )
        cls.conn.cursor().execute("UPDATE batches SET is_public = 1, status = 'completed' WHERE id = ?", (cls.batch_completed_id,))
        cls.conn.commit()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        if os.path.exists("test_public_website.db"):
            os.remove("test_public_website.db")

    def test_01_public_homepage_renders_without_auth(self):
        """Requirement #1 & #2: Public homepage must be accessible without login."""
        req = make_request("/")
        response = asyncio.run(web_app.public_home(req))
        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn("AFAQ Academy", body)
        self.assertIn("Explore Available Courses", body)
        self.assertIn("Full-Stack Web Development", body)
        self.assertIn("Log In", body)
        self.assertIn("Join AFAQ", body)

    def test_02_privacy_protection_graduates(self):
        """Requirement #7 & #18: Only public students appear; private student data is never leaked."""
        pub_svc = PublicService(self.conn)
        graduates = pub_svc.get_public_graduates()
        names = [g["name"] for g in graduates]
        self.assertIn("Trainee Omar", names)
        self.assertNotIn("Private Trainee", names)

        # Check no sensitive keys
        for g in graduates:
            self.assertNotIn("email", g)
            self.assertNotIn("phone", g)
            self.assertNotIn("password", g)
            self.assertNotIn("password_hash", g)

        req = make_request("/")
        response = asyncio.run(web_app.public_home(req))
        body = response.body.decode("utf-8")
        self.assertIn("Trainee Omar", body)
        self.assertNotIn("Private Trainee", body)
        self.assertNotIn("omar@afaq.trainee.edu", body)

    def test_03_public_course_details_and_batch_capacity(self):
        """Requirement #5 & #26: Public course details page with chapters and batches."""
        req = make_request(f"/courses/{self.course_id}")
        response = asyncio.run(web_app.public_course_details(req, self.course_id))
        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn("Full-Stack Web Development", body)
        self.assertIn("Frontend Mastery", body)
        self.assertIn("Backend", body)
        self.assertIn("FSW-01 (Fall Cohort)", body)
        self.assertIn("Login to Request", body)
        self.assertIn(f"/login?next=/courses/{self.course_id}", body)

    def test_04_contact_form_submission_and_validation(self):
        """Requirement #14: Contact form submission with server-side validation."""
        req = make_request("/contact", method="POST")

        # Submission with valid data
        response = asyncio.run(web_app.submit_contact(
            request=req,
            name="Sarah Connor",
            email="sarah@example.com",
            phone="+201234567890",
            subject="Enrollment Inquiry",
            message="When is the next cohort starting for the web development track?"
        ))
        self.assertEqual(response.status_code, 302)

        # Verify message stored in DB
        pub_svc = PublicService(self.conn)
        messages = pub_svc.get_contact_messages()
        self.assertTrue(any(m["name"] == "Sarah Connor" and m["subject"] == "Enrollment Inquiry" for m in messages))

    def test_05_admin_website_settings_management(self):
        """Requirement #19: Admin can manage content and website settings."""
        pub_svc = PublicService(self.conn)
        pub_svc.update_org_settings(
            hero_headline="Empowering Future Tech Leaders",
            about_text="AFAQ Academy is an elite coding academy."
        )
        org = pub_svc.get_org_settings()
        self.assertEqual(org["hero_headline"], "Empowering Future Tech Leaders")

        # Homepage reflects dynamic change
        req = make_request("/")
        response = asyncio.run(web_app.public_home(req))
        body = response.body.decode("utf-8")
        self.assertIn("Empowering Future Tech Leaders", body)

    def test_06_auth_redirect_with_next(self):
        """Requirement #26 & #27: Next parameter preserves user journey to the selected course."""
        req = make_request("/login")
        response = asyncio.run(web_app.login_page(req, next=f"/courses/{self.course_id}"))
        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn(f'value="/courses/{self.course_id}"', body)

    def test_07_trainee_public_visibility_toggle(self):
        """Requirement #7 & #19: Admin can toggle public graduate showcase visibility."""
        admin_svc = AdminService(self.conn)
        # Trainee 4 is initially private
        trainees = admin_svc.get_trainees()
        t4 = next(t for t in trainees if t[0] == 4)
        self.assertEqual(t4[4], 0) # not public

        # Toggle to public
        admin_svc.update_trainee_public_visibility(4, show_on_public=1, public_bio="Top developer", graduation_status="Alumni")
        trainees_after = admin_svc.get_trainees()
        t4_after = next(t for t in trainees_after if t[0] == 4)
        self.assertEqual(t4_after[4], 1)


if __name__ == "__main__":
    unittest.main()
