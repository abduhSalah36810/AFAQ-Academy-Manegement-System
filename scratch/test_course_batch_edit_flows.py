import json
import os
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="afaq-edit-flow-")
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["SQLITE_DB_PATH"] = str(Path(TEST_DIRECTORY.name) / "edit-flow.db")
os.environ.setdefault("AFAQ_SECRET_KEY", "focused-test-key")
sys.path.insert(0, str(ROOT))

from database import create_tables, get_connection
from services.batch_service import BatchService
from services.course_service import CourseService
import web_app
from starlette.requests import Request


class EditButtonDataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.courses = []
        self.batches = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "data-edit-course" in values:
            self.courses.append(json.loads(values["data-edit-course"]))
        if "data-edit-batch" in values:
            self.batches.append(json.loads(values["data-edit-batch"]))


def make_request(path, method="GET"):
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [],
        "session": {"user": {"id": 1, "role": "admin", "name": "مدير"}},
    })


class CourseBatchEditFlowTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        create_tables()
        cls.connection = get_connection()
        cursor = cls.connection.cursor()
        cursor.execute(
            "INSERT INTO users (id, name, email, password_hash, role, active) "
            "VALUES (1, 'مدير', 'admin@afaq.admin.edu', 'hash', 'admin', 1)"
        )
        cursor.execute(
            "INSERT INTO users (id, name, email, password_hash, role, active) "
            "VALUES (2, 'محاضر علي', 'instructor@afaq.instructor.edu', 'hash', 'instructor', 1)"
        )
        cls.connection.commit()

        cls.course_name = 'Children\'s "Programming"'
        cls.course_description = 'وصف الدورة: \'اقتباس\' و"اقتباس"\nسطر ثانٍ'
        cls.course_id = CourseService(cls.connection).create(
            cls.course_name, instructor_id=2, description=cls.course_description
        )
        cls.assigned_batch_name = 'دفعة Children\'s "AI"'
        cls.assigned_batch_id = BatchService(cls.connection).create(
            cls.course_id, cls.assigned_batch_name, instructor_id=2,
            capacity=20, start_date="2026-10-01"
        )
        cls.unassigned_batch_id = BatchService(cls.connection).create(
            cls.course_id, "دفعة بلا محاضر", instructor_id=None
        )

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()
        TEST_DIRECTORY.cleanup()

    async def test_course_details_button_reuses_course_edit_page_and_modal(self):
        batch_response = await web_app.admin_course_batches(
            make_request(f"/admin/courses/{self.course_id}/batches"), self.course_id
        )
        batch_html = batch_response.body.decode("utf-8")
        self.assertIn(
            f'/admin/courses?edit_course_id={self.course_id}', batch_html
        )

        response = await web_app.admin_courses(
            make_request(f"/admin/courses?edit_course_id={self.course_id}"),
            edit_course_id=self.course_id,
        )
        html = response.body.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("openCourseEdit(", html)
        self.assertIn(f"openCourseEdit([{self.course_id},", html)

    async def test_course_edit_payload_handles_arabic_quotes_and_multiline_text(self):
        response = await web_app.admin_courses(
            make_request("/admin/courses"), edit_course_id=None
        )
        parser = EditButtonDataParser()
        parser.feed(response.body.decode("utf-8"))
        course = next(row for row in parser.courses if row[0] == self.course_id)
        self.assertEqual(course[1], self.course_name)
        self.assertEqual(course[4], self.course_description)
        self.assertEqual(course[5], 2)

    async def test_batch_edit_payload_preserves_instructor_id_and_names(self):
        response = await web_app.admin_course_batches(
            make_request(f"/admin/courses/{self.course_id}/batches"), self.course_id
        )
        html = response.body.decode("utf-8")
        parser = EditButtonDataParser()
        parser.feed(html)
        assigned = next(row for row in parser.batches if row[0] == self.assigned_batch_id)
        unassigned = next(row for row in parser.batches if row[0] == self.unassigned_batch_id)

        self.assertEqual(assigned[2], self.assigned_batch_name)
        self.assertEqual(assigned[3], 2)
        self.assertEqual(unassigned[3], None)
        self.assertIn(".value = instructorId || ''", html)

    async def test_saving_batch_edit_with_selected_existing_instructor_keeps_assignment(self):
        request = make_request(
            f"/admin/batches/{self.assigned_batch_id}/edit", method="POST"
        )
        response = await web_app.admin_edit_batch(
            request,
            batch_id=self.assigned_batch_id,
            name=self.assigned_batch_name,
            instructor_id="2",
            capacity=20,
            start_date="2026-10-01",
            end_date="",
            registration_cutoff_sessions=0,
            status="upcoming",
        )
        self.assertEqual(response.status_code, 302)
        connection = get_connection()
        try:
            batch = BatchService(connection).get_by_id(self.assigned_batch_id)
            self.assertEqual(batch[3], 2)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
