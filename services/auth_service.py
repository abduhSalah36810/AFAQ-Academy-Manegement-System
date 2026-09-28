from utils.security import hash_password, verify_password
from utils.validation import (
    normalize_email,
    is_valid_email,
    is_afaq_email,
    check_password_strength,
    validate_name,
    get_domain_role,
    validate_email_role_match,
)


class AuthService:

    def __init__(self, connection):
        self.connection = connection

    def signup(self, name, email, password):
        """
        Public signup — creates trainee only.
        Email must be an AFAQ trainee institutional address.
        """
        name = name.strip()
        email = normalize_email(email)

        if not validate_name(name):
            return False, "Name must contain at least 2 characters."

        if not is_afaq_email(email):
            return False, (
                "Please use your institutional AFAQ email address "
                "(e.g. username@afaq.trainee.edu)."
            )

        domain_role = get_domain_role(email)
        if domain_role != "trainee":
            return False, (
                "Public signup is available for trainees only. "
                "Use your @afaq.trainee.edu address."
            )

        ok, msg = check_password_strength(password)
        if not ok:
            return False, msg

        password_hash = hash_password(password)

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                INSERT INTO users
                    (name, email, password_hash, role)
                VALUES
                    (?, ?, ?, 'trainee')
                """,
                (name, email, password_hash)
            )
            self.connection.commit()
            return True, "Account created successfully."

        except Exception:
            self.connection.rollback()
            return False, "Email already exists or signup failed."

    def login(self, email, password):
        email = normalize_email(email)

        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, name, email, password_hash, role, active
            FROM users
            WHERE email = ?
            """,
            (email,)
        )

        user = cursor.fetchone()

        if user is None:
            return None, "Invalid email or password."

        user_id, name, user_email, stored_hash, role, active = user

        if not verify_password(password, stored_hash):
            return None, "Invalid email or password."

        if active == 0:
            return None, "Your account has been deactivated. Please contact an administrator."

        return {
            "id": user_id,
            "name": name,
            "email": user_email,
            "role": role,
            "active": active
        }, "Login successful."

    def change_password(self, user_id, current_password, new_password):
        """
        Authenticated password change.
        Verifies the current password before updating.
        Returns (ok: bool, message: str).
        """
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return False, "User not found."

        stored_hash = row[0]
        if not verify_password(current_password, stored_hash):
            return False, "Current password is incorrect."

        ok, msg = check_password_strength(new_password)
        if not ok:
            return False, msg

        if current_password == new_password:
            return False, "New password must be different from your current password."

        new_hash = hash_password(new_password)
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user_id)
        )
        self.connection.commit()
        return True, "Password updated successfully."
