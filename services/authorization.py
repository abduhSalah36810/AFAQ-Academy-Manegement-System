ROLE_PERMISSIONS = {
    "trainee": {
        "view_courses",
        "view_attendance",
        "view_grades"
    },

    "instructor": {
        "view_courses",
        "view_trainees",
        "record_attendance",
        "add_grades"
    },

     "admin": {
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
        "view_grades"
    }
}


def has_permission(user, permission):
    if user is None:
        return False

    role = user["role"]

    permissions = ROLE_PERMISSIONS.get(role, set())

    return permission in permissions