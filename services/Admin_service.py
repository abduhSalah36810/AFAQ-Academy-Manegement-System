import sqlite3

from utils.security import hash_password
from utils.validation import (
    normalize_email,
    is_afaq_email,
    check_password_strength,
    validate_name,
    get_domain_role,
    validate_email_role_match,
)


class AdminService:

    def __init__(self, connection):
        self.connection = connection

    # --------------------------------------------------
    # USER MANAGEMENT
    # --------------------------------------------------

    def create_user(self, name, email, password, role):
        name = name.strip()
        email = normalize_email(email)

        allowed_roles = {"trainee", "instructor", "admin"}
        if role not in allowed_roles:
            raise ValueError("Invalid role.")

        if not validate_name(name):
            raise ValueError("Name must contain at least 2 characters.")

        if not is_afaq_email(email):
            raise ValueError(
                f"Email must be an AFAQ institutional address "
                f"(e.g. username@afaq.{role}.edu)."
            )

        if not validate_email_role_match(email, role):
            from utils.validation import ROLE_DOMAIN_MAP
            expected_domain = ROLE_DOMAIN_MAP.get(role, "afaq.<role>.edu")
            raise ValueError(
                f"Email domain does not match the selected role. "
                f"A {role} account requires @{expected_domain}."
            )

        ok, msg = check_password_strength(password)
        if not ok:
            raise ValueError(msg)

        password_hash = hash_password(password)

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                INSERT INTO users
                    (name, email, password_hash, role)
                VALUES
                    (?, ?, ?, ?)
                """,
                (name, email, password_hash, role)
            )
            self.connection.commit()

        except sqlite3.IntegrityError:
            self.connection.rollback()
            raise ValueError("This email already exists.")

    def get_user_by_id(self, user_id):
        """Return full user row (id, name, email, role, active) or None."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT id, name, email, role, active FROM users WHERE id = ?",
            (user_id,)
        )
        return cursor.fetchone()

    def update_user(self, user_id, name=None, email=None, password=None, role=None):
        """
        Update editable user fields.
        Role changes are admin-only — the route enforces this.
        If email is changed, it must still be an AFAQ institutional address
        matching the (new or current) role.
        """
        current = self.get_user_by_id(user_id)
        if current is None:
            raise ValueError("User not found.")

        cur_id, cur_name, cur_email, cur_role, cur_active = current

        final_role = role if role is not None else cur_role

        if name is not None:
            name = name.strip()
            if not validate_name(name):
                raise ValueError("Name must contain at least 2 characters.")
        else:
            name = cur_name

        if email is not None:
            email = normalize_email(email)
            if not is_afaq_email(email):
                raise ValueError("Email must be an AFAQ institutional address.")
            if not validate_email_role_match(email, final_role):
                from utils.validation import ROLE_DOMAIN_MAP
                expected = ROLE_DOMAIN_MAP.get(final_role, "")
                raise ValueError(
                    f"Email domain does not match role '{final_role}'. "
                    f"Expected @{expected}."
                )
        else:
            email = cur_email

        if final_role not in {"trainee", "instructor", "admin"}:
            raise ValueError("Invalid role.")

        cursor = self.connection.cursor()

        if password and password.strip():
            ok, msg = check_password_strength(password)
            if not ok:
                raise ValueError(msg)
            new_hash = hash_password(password)
        else:
            cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            new_hash = row[0] if row else None

        try:
            cursor.execute(
                """
                UPDATE users
                SET name = ?, email = ?, password_hash = ?, role = ?
                WHERE id = ?
                """,
                (name, email, new_hash, final_role, user_id)
            )
            self.connection.commit()
        except sqlite3.IntegrityError:
            self.connection.rollback()
            raise ValueError("This email is already in use by another account.")

    def deactivate_user(self, user_id):
        """Set active=0. User cannot log in or appear in new selections."""
        cursor = self.connection.cursor()
        cursor.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))
        self.connection.commit()

    def reactivate_user(self, user_id):
        """Set active=1. Restores login and availability."""
        cursor = self.connection.cursor()
        cursor.execute("UPDATE users SET active = 1 WHERE id = ?", (user_id,))
        self.connection.commit()

    # --------------------------------------------------
    # INSTRUCTORS
    # --------------------------------------------------

    def get_instructors(self):
        """Return all instructors (active and inactive) for display."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, name, email, active
            FROM users
            WHERE role = 'instructor'
            ORDER BY name
            """
        )
        return cursor.fetchall()

    def get_active_instructors(self):
        """Return only active instructors — for dropdowns / new assignments."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, name, email, active
            FROM users
            WHERE role = 'instructor'
            AND active = 1
            ORDER BY name
            """
        )
        return cursor.fetchall()

    # --------------------------------------------------
    # TRAINEES
    # --------------------------------------------------

    def get_trainees(self):
        """Return all trainees (active and inactive) for display."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, name, email, active,
                   COALESCE(show_on_public_profile, 0),
                   COALESCE(public_bio, ''),
                   COALESCE(graduation_status, 'graduate')
            FROM users
            WHERE role = 'trainee'
            ORDER BY name
            """
        )
        return cursor.fetchall()

    def update_trainee_public_visibility(self, trainee_id: int, show_on_public: int, public_bio: str = None, graduation_status: str = None):
        """Update public showcase visibility and profile bio for a student."""
        cursor = self.connection.cursor()
        updates = ["show_on_public_profile = ?"]
        params = [show_on_public]
        if public_bio is not None:
            updates.append("public_bio = ?")
            params.append(public_bio.strip())
        if graduation_status is not None:
            updates.append("graduation_status = ?")
            params.append(graduation_status.strip())
        params.append(trainee_id)
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ? AND role = 'trainee'", params)
        self.connection.commit()

    def get_active_trainees(self):
        """Return only active trainees — for enrollment dropdowns."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, name, email, active
            FROM users
            WHERE role = 'trainee'
            AND active = 1
            ORDER BY name
            """
        )
        return cursor.fetchall()

    # --------------------------------------------------
    # ASSIGN INSTRUCTOR TO COURSE
    # --------------------------------------------------

    def assign_instructor(self, instructor_id, course_id):
        cursor = self.connection.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'instructor' AND active = 1",
            (instructor_id,)
        )
        if cursor.fetchone() is None:
            raise ValueError("Instructor does not exist or is inactive.")

        cursor.execute(
            "SELECT id FROM courses WHERE id = ? AND active = 1",
            (course_id,)
        )
        if cursor.fetchone() is None:
            raise ValueError("Course does not exist or is archived.")

        cursor.execute(
            "UPDATE courses SET instructor_id = ? WHERE id = ?",
            (instructor_id, course_id)
        )
        self.connection.commit()
