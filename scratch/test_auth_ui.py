import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="afaq-auth-ui-")
os.environ["TURSO_DATABASE_URL"] = ""
os.environ["TURSO_AUTH_TOKEN"] = ""
os.environ["SQLITE_DB_PATH"] = str(Path(TEST_DIRECTORY.name) / "auth-ui.db")
os.environ.setdefault("AFAQ_SECRET_KEY", "auth-ui-test-key")
sys.path.insert(0, str(ROOT))

from database import create_tables, get_connection
import web_app


def make_request(path="/", session=None):
    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "session": session if session is not None else {},
    })


class AuthenticationPresentationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        create_tables()

    @staticmethod
    def _body(response):
        return response.body.decode("utf-8")

    async def test_login_and_signup_share_arabic_auth_layout(self):
        login = await web_app.login_page(make_request("/login"), next="/courses/7")
        signup = await web_app.signup_page(make_request("/signup"), next="/courses/7")
        login_html, signup_html = self._body(login), self._body(signup)

        for body in (login_html, signup_html):
            self.assertIn('class="auth-page" dir="rtl"', body)
            self.assertIn('href="/static/css/auth.css"', body)
            self.assertIn("أكاديمية آفاق", body)
            self.assertIn("auth-card", body)
            self.assertNotIn("auth-visual", body)
            self.assertNotIn("100%", body)
            self.assertNotIn("Welcome Back", body)
            self.assertIn('name="next" value="/courses/7"', body)

        self.assertIn("مرحبًا بعودتك", login_html)
        self.assertIn("سجّل الدخول للوصول إلى حسابك ومتابعة رحلتك التعليمية.", login_html)
        self.assertIn('action="/login"', login_html)
        self.assertIn('placeholder="أدخل بريدك الإلكتروني"', login_html)
        self.assertIn('placeholder="أدخل كلمة المرور"', login_html)
        self.assertIn('href="/signup?next=/courses/7"', login_html)

        self.assertIn("إنشاء حساب متدرب", signup_html)
        self.assertIn("أنشئ حسابك للانضمام إلى الدورات ومتابعة رحلتك التعليمية.", signup_html)
        self.assertIn('action="/signup"', signup_html)
        self.assertIn('name="name"', signup_html)
        self.assertEqual(len(re.findall(r'<input[^>]+name="(?:name|email|password)"', signup_html)), 3)
        self.assertIn('href="/login?next=/courses/7"', signup_html)
        self.assertIn('data-show-password="password"', login_html)
        self.assertIn('data-show-password="password"', signup_html)

    async def test_login_error_is_rendered_in_shared_arabic_feedback(self):
        response = await web_app.login_submit(
            make_request("/login"), email="unknown@afaq.trainee.edu",
            password="incorrect", next="/courses/7",
        )
        body = self._body(response)
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="auth-message auth-message--error"', body)
        self.assertIn('role="alert"', body)
        self.assertIn("البريد الإلكتروني أو كلمة المرور غير صحيحة.", body)
        self.assertIn('name="next" value="/courses/7"', body)

    async def test_signup_validation_and_success_preserve_existing_flow(self):
        invalid = await web_app.signup_submit(
            make_request("/signup"), name="متدرب تجريبي",
            email="learner@example.com", password="StrongAfaqPass1!", next="/courses/7",
        )
        invalid_html = self._body(invalid)
        self.assertEqual(invalid.status_code, 200)
        self.assertIn('class="auth-message auth-message--error"', invalid_html)
        self.assertIn("استخدم بريدك المؤسسي التابع لأكاديمية آفاق", invalid_html)
        self.assertIn('name="next" value="/courses/7"', invalid_html)

        session = {}
        success = await web_app.signup_submit(
            make_request("/signup", session=session), name="متدرب تجريبي",
            email="auth-ui-test@afaq.trainee.edu", password="StrongAfaqPass1!",
            next="/courses/7",
        )
        self.assertEqual(success.status_code, 302)
        self.assertEqual(success.headers["location"], "/courses/7")
        self.assertEqual(session["user"]["role"], "trainee")

        login_session = {}
        login = await web_app.login_submit(
            make_request("/login", session=login_session),
            email="auth-ui-test@afaq.trainee.edu", password="StrongAfaqPass1!",
            next="/courses/7",
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.headers["location"], "/courses/7")
        self.assertEqual(login_session["user"]["role"], "trainee")


if __name__ == "__main__":
    unittest.main()
