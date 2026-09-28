import unittest
from utils.validation import (
    is_afaq_email,
    check_password_strength,
    get_domain_role,
    validate_email_role_match
)

class TestSecurity(unittest.TestCase):
    def test_afaq_email(self):
        self.assertTrue(is_afaq_email("student@afaq.trainee.edu"))
        self.assertTrue(is_afaq_email("john.doe-99@afaq.instructor.edu"))
        self.assertTrue(is_afaq_email("admin1@afaq.admin.edu"))
        
        # Invalid domains
        self.assertFalse(is_afaq_email("student@gmail.com"))
        self.assertFalse(is_afaq_email("student@afaq.trainee.com"))
        
        # Invalid usernames
        self.assertFalse(is_afaq_email("!student@afaq.trainee.edu"))
        self.assertFalse(is_afaq_email("@afaq.trainee.edu"))

    def test_domain_role(self):
        self.assertEqual(get_domain_role("a@afaq.trainee.edu"), "trainee")
        self.assertEqual(get_domain_role("a@afaq.instructor.edu"), "instructor")
        self.assertEqual(get_domain_role("a@afaq.admin.edu"), "admin")
        self.assertIsNone(get_domain_role("a@other.edu"))

    def test_email_role_match(self):
        self.assertTrue(validate_email_role_match("a@afaq.trainee.edu", "trainee"))
        self.assertFalse(validate_email_role_match("a@afaq.instructor.edu", "trainee"))

    def test_password_strength(self):
        # Good password
        ok, msg = check_password_strength("StrongPass123!")
        self.assertTrue(ok, msg)

        # Too short
        ok, msg = check_password_strength("Short1!")
        self.assertFalse(ok)
        self.assertIn("at least 12 characters", msg)

        # No uppercase
        ok, msg = check_password_strength("weakpass123!")
        self.assertFalse(ok)
        self.assertIn("uppercase", msg)

        # No lowercase
        ok, msg = check_password_strength("WEAKPASS123!")
        self.assertFalse(ok)
        self.assertIn("lowercase", msg)

        # No digit
        ok, msg = check_password_strength("StrongPassword!")
        self.assertFalse(ok)
        self.assertIn("number", msg)

        # No special char
        ok, msg = check_password_strength("StrongPass12345")
        self.assertFalse(ok)
        self.assertIn("special character", msg)

        # Common password
        ok, msg = check_password_strength("Abc12345678!")
        self.assertFalse(ok)
        self.assertIn("too common", msg)

if __name__ == '__main__':
    unittest.main()
