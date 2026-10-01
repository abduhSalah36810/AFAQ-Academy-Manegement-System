ROLE_PERMISSIONS = {
    "trainee": {
        # Existing
        "view_courses",
        "view_attendance",
        "view_grades",
        # New
        "browse_courses",
        "view_batches",
        "request_enrollment",
        "view_own_requests",
        "submit_task",
        "view_own_submissions",
        "view_own_bonuses",
        "view_own_progress",
    },

    "instructor": {
        # Existing
        "view_courses",
        "view_trainees",
        "record_attendance",
        "add_grades",
        # New
        "view_batches",
        "manage_own_batch_sessions",
        "record_batch_attendance",
        "review_submissions",
        "add_component_scores",
        "award_bonus",
        "view_batch_grades",
        "manage_materials",
    },

    "admin": {
        # Existing
        "view_courses",
        "view_trainees",
        "view_instructors",
        "create_user",
        "create_course",
        "enroll_trainee",
        "assign_instructor",
        "record_attendance",
        "add_grades",
        "view_attendance",
        "view_grades",
        # New
        "manage_batches",
        "manage_chapters",
        "manage_sessions",
        "manage_tasks",
        "review_submissions",
        "review_enrollment_requests",
        "bulk_enroll",
        "manage_grading_components",
        "add_component_scores",
        "award_bonus",
        "view_batch_grades",
        "view_audit_log",
        "manage_materials",
        "browse_courses",
        "view_batches",
        "view_own_progress",
        "manage_own_batch_sessions",
        "record_batch_attendance",
    }
}


def has_permission(user, permission):
    if user is None:
        return False

    role = user.get("role") if isinstance(user, dict) else user["role"]
    permissions = ROLE_PERMISSIONS.get(role, set())
    return permission in permissions


def require_permission(user, permission):
    """Raise PermissionError if user doesn't have the given permission."""
    if not has_permission(user, permission):
        raise PermissionError(f"Permission denied: '{permission}' required.")