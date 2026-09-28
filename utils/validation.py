import re

# ── AFAQ institutional email domains ────────────────────────────────────────
# Each role maps to exactly one allowed domain.
ROLE_DOMAIN_MAP = {
    "trainee":    "afaq.trainee.edu",
    "instructor": "afaq.instructor.edu",
    "admin":      "afaq.admin.edu",
}
# All valid AFAQ domains (for generic validation before role is known)
AFAQ_DOMAINS = set(ROLE_DOMAIN_MAP.values())

# Username rules: letters, digits, dots, hyphens; 2-64 chars
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,63}$")

# Common/weak passwords to explicitly reject
_COMMON_PASSWORDS = {
    "password", "password1", "password12", "password123",
    "Password1!", "123456789012", "qwerty123456",
    "admin12345678", "letmein123!", "afaqacademy1!",
    "passw0rd!", "Welcome1!", "Abc12345678!",
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    """Generic structural check — any valid email."""
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return re.match(pattern, email) is not None


def is_afaq_email(email: str) -> bool:
    """Check that email belongs to one of the AFAQ institutional domains."""
    email = normalize_email(email)
    parts = email.split("@")
    if len(parts) != 2:
        return False
    username, domain = parts
    if domain not in AFAQ_DOMAINS:
        return False
    if not _USERNAME_RE.match(username):
        return False
    return True


def get_domain_role(email: str):
    """Return the expected role for an AFAQ email, or None if not valid."""
    email = normalize_email(email)
    parts = email.split("@")
    if len(parts) != 2:
        return None
    _, domain = parts
    for role, d in ROLE_DOMAIN_MAP.items():
        if d == domain:
            return role
    return None


def validate_email_role_match(email: str, role: str) -> bool:
    """Confirm that the email domain is consistent with the given role."""
    expected_role = get_domain_role(email)
    return expected_role == role


def is_valid_password(password: str) -> bool:
    """Legacy minimal check — still used as baseline.  True if >= 12 chars."""
    return len(password) >= 12


def check_password_strength(password: str) -> tuple[bool, str]:
    """
    Full policy check.
    Returns (ok: bool, message: str).
    Policy:
      - 12+ characters
      - At least one uppercase letter
      - At least one lowercase letter
      - At least one digit
      - At least one special character
      - Not a common/weak password
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return False, "Password must contain at least one special character (!@#$%^&* etc.)."
    if password.lower() in _COMMON_PASSWORDS or password in _COMMON_PASSWORDS:
        return False, "This password is too common. Please choose a stronger password."
    return True, "Password is strong."


def validate_name(name: str) -> bool:
    return len(name.strip()) >= 2


def get_password_strength_score(password: str) -> dict:
    """
    Returns a dict for the frontend strength meter:
      { score: 0-4, label: str, color: str }
    """
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r"[A-Z]", password) and re.search(r"[a-z]", password):
        score += 1
    if re.search(r"\d", password):
        score += 0.5
    if re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        score += 0.5

    score = min(4, int(score))

    labels = ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"]
    colors = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#10b981"]

    return {
        "score": score,
        "label": labels[score],
        "color": colors[score],
        "percent": score * 25
    }