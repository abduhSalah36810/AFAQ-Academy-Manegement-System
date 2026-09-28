
import getpass

from database import create_tables, get_connection

from services.auth_service import AuthService
from services.authorization import has_permission
from services.session import Session

from services.Admin_service import AdminService
from services.trainee_service import TraineeService
from services.course_service import CourseService
from services.enrollment_service import EnrollmentService
from services.Attendence_service import AttendanceService
from services.grade_service import GradeService


# ==========================================================
# GENERAL UI HELPERS
# ==========================================================

def print_header(title):

    print("\n" + "=" * 50)
    print(title)
    print("=" * 50)


def choose_item(items, title):

    if not items:
        print(f"\nNo {title.lower()} found.")
        return None

    print_header(title)

    for index, item in enumerate(items, start=1):

        print(f"{index}. {item[1]}")

    while True:

        try:

            choice = int(
                input("\nChoose an option: ")
            )

            if 1 <= choice <= len(items):

                return items[choice - 1]

            print("Invalid choice.")

        except ValueError:

            print("Please enter a number.")


# ==========================================================
# ADMIN FUNCTIONS
# ==========================================================

def create_user_admin(admin_service, role):

    role_name = role.capitalize()

    print_header(
        f"CREATE {role_name.upper()}"
    )

    name = input("Name: ")

    email = input("Email: ")

    password = getpass.getpass(
        "Password: "
    )

    try:

        admin_service.create_user(
            name,
            email,
            password,
            role
        )

        print(
            f"{role_name} created successfully."
        )

    except ValueError as error:

        print(f"Error: {error}")


def show_instructors(admin_service):

    instructors = (
        admin_service
        .get_instructors()
    )

    print_header("INSTRUCTORS")

    if not instructors:

        print("No instructors found.")
        return

    for instructor in instructors:

        print(
            f"Name: {instructor[1]} | "
            f"Email: {instructor[2]}"
        )


def assign_instructor(
    admin_service,
    course_service
):

    instructors = (
        admin_service
        .get_instructors()
    )

    instructor = choose_item(
        instructors,
        "SELECT INSTRUCTOR"
    )

    if instructor is None:
        return

    courses = course_service.get_all()

    # get_all returns:
    # id, course name, instructor name

    if not courses:

        print("No courses found.")
        return

    print_header("SELECT COURSE")

    for index, course in enumerate(
        courses,
        start=1
    ):

        instructor_name = (
            course[2]
            if course[2]
            else "Not assigned"
        )

        print(
            f"{index}. "
            f"{course[1]} "
            f"(Instructor: {instructor_name})"
        )

    while True:

        try:

            choice = int(
                input("\nChoose course: ")
            )

            if 1 <= choice <= len(courses):

                course = courses[
                    choice - 1
                ]

                break

            print("Invalid choice.")

        except ValueError:

            print("Please enter a number.")

    try:

        admin_service.assign_instructor(
            instructor[0],
            course[0]
        )

        print(
            f"\n{instructor[1]} "
            f"assigned to "
            f"{course[1]}."
        )

    except ValueError as error:

        print(f"Error: {error}")


def enroll_trainee(
    admin_service,
    course_service,
    enrollment_service
):

    trainees = (
        admin_service
        .get_trainees()
    )

    trainee = choose_item(
        trainees,
        "SELECT TRAINEE"
    )

    if trainee is None:
        return

    courses = course_service.get_all()

    if not courses:

        print("No courses found.")
        return

    print_header("SELECT COURSE")

    for index, course in enumerate(
        courses,
        start=1
    ):

        instructor_name = (
            course[2]
            if course[2]
            else "Not assigned"
        )

        print(
            f"{index}. "
            f"{course[1]} "
            f"(Instructor: {instructor_name})"
        )

    while True:

        try:

            choice = int(
                input("\nChoose course: ")
            )

            if 1 <= choice <= len(courses):

                course = courses[
                    choice - 1
                ]

                break

            print("Invalid choice.")

        except ValueError:

            print("Please enter a number.")

    try:

        enrollment_service.enroll(
            trainee[0],
            course[0]
        )

        print(
            f"\n{trainee[1]} "
            f"enrolled in "
            f"{course[1]}."
        )

    except ValueError as error:

        print(f"Error: {error}")


# ==========================================================
# INSTRUCTOR FUNCTIONS
# ==========================================================

def instructor_choose_course(
    course_service,
    instructor_id
):

    courses = (
        course_service
        .get_instructor_courses(
            instructor_id
        )
    )

    return choose_item(
        courses,
        "MY COURSES"
    )


def instructor_record_attendance(
    course_service,
    enrollment_service,
    attendance_service,
    instructor_id
):

    course = instructor_choose_course(
        course_service,
        instructor_id
    )

    if course is None:
        return

    trainees = (
        enrollment_service
        .get_course_trainees(
            course[0]
        )
    )

    trainee = choose_item(
        trainees,
        "SELECT TRAINEE"
    )

    if trainee is None:
        return

    date = input(
        "\nDate (YYYY-MM-DD): "
    )

    status = input(
        "Status (present/absent): "
    ).strip().lower()

    try:

        attendance_service.record(
            trainee[0],
            course[0],
            date,
            status
        )

        print(
            "\nAttendance recorded successfully."
        )

    except ValueError as error:

        print(f"Error: {error}")


def instructor_add_grade(
    course_service,
    enrollment_service,
    grade_service,
    instructor_id
):

    course = instructor_choose_course(
        course_service,
        instructor_id
    )

    if course is None:
        return

    trainees = (
        enrollment_service
        .get_course_trainees(
            course[0]
        )
    )

    trainee = choose_item(
        trainees,
        "SELECT TRAINEE"
    )

    if trainee is None:
        return

    try:

        score = float(
            input("\nScore: ")
        )

        grade_service.add_grade(
            trainee[0],
            course[0],
            score
        )

        print(
            "\nGrade saved successfully."
        )

    except ValueError as error:

        print(f"Error: {error}")


# ==========================================================
# MAIN
# ==========================================================

def main():

    create_tables()

    connection = get_connection()

    auth_service = AuthService(connection)

    admin_service = AdminService(connection)

    trainee_service = TraineeService(connection)

    course_service = CourseService(connection)

    enrollment_service = (
        EnrollmentService(connection)
    )

    attendance_service = (
        AttendanceService(connection)
    )

    grade_service = (
        GradeService(connection)
    )

    session = Session()

    while True:

        # ==================================================
        # NOT LOGGED IN
        # ==================================================

        if not session.is_authenticated():

            print_header("DAFAQ ACADEMY")

            print("1. Sign Up")
            print("2. Login")
            print("3. Exit")

            choice = input(
                "\nChoose an option: "
            )

            # -----------------------------
            # SIGN UP
            # -----------------------------

            if choice == "1":

                name = input("Name: ")

                email = input("Email: ")

                password = getpass.getpass(
                    "Password: "
                )

                success, message = (
                    auth_service.signup(
                        name,
                        email,
                        password
                    )
                )

                print(message)

            # -----------------------------
            # LOGIN
            # -----------------------------

            elif choice == "2":

                email = input("Email: ")

                password = getpass.getpass(
                    "Password: "
                )

                user, message = (
                    auth_service.login(
                        email,
                        password
                    )
                )

                print(message)

                if user:

                    session.login(user)

            # -----------------------------
            # EXIT
            # -----------------------------

            elif choice == "3":

                break

            else:

                print("Invalid option.")

            continue

        # ==================================================
        # LOGGED-IN USER
        # ==================================================

        user = session.get_user()

        role = user["role"]

        print_header(
            f"Welcome {user['name']} "
            f"({role})"
        )

        # ==================================================
        # ADMIN
        # ==================================================

        if role == "admin":

            print("1. View Courses")
            print("2. View Trainees")
            print("3. View Instructors")
            print("4. Create Trainee")
            print("5. Create Instructor")
            print("6. Create Admin")
            print("7. Create Course")
            print("8. Enroll Trainee")
            print("9. Assign Instructor to Course")
            print("10. Logout")

            choice = input(
                "\nChoose an option: "
            )

            if choice == "1":

                courses = (
                    course_service
                    .get_all()
                )

                print_header("COURSES")

                for course in courses:

                    instructor = (
                        course[2]
                        if course[2]
                        else "Not assigned"
                    )

                    print(
                        f"Course: {course[1]} | "
                        f"Instructor: {instructor}"
                    )

            elif choice == "2":

                trainees = (
                    admin_service
                    .get_trainees()
                )

                print_header("TRAINEES")

                for trainee in trainees:

                    print(
                        f"Name: {trainee[1]} | "
                        f"Email: {trainee[2]}"
                    )

            elif choice == "3":

                show_instructors(
                    admin_service
                )

            elif choice == "4":

                create_user_admin(
                    admin_service,
                    "trainee"
                )

            elif choice == "5":

                create_user_admin(
                    admin_service,
                    "instructor"
                )

            elif choice == "6":

                create_user_admin(
                    admin_service,
                    "admin"
                )

            elif choice == "7":

                name = input(
                    "Course name: "
                ).strip()

                try:

                    course_service.create(
                        name
                    )

                    print(
                        "Course created successfully."
                    )

                except Exception as error:

                    print(
                        f"Error: {error}"
                    )

            elif choice == "8":

                enroll_trainee(
                    admin_service,
                    course_service,
                    enrollment_service
                )

            elif choice == "9":

                assign_instructor(
                    admin_service,
                    course_service
                )

            elif choice == "10":

                session.logout()

                print(
                    "Logged out successfully."
                )

            else:

                print("Invalid option.")

        # ==================================================
        # INSTRUCTOR
        # ==================================================

        elif role == "instructor":

            print("1. View Courses")
            print("2. View My Trainees")
            print("3. Record Attendance")
            print("4. Add Grade")
            print("5. Logout")

            choice = input(
                "\nChoose an option: "
            )

            # -----------------------------
            # VIEW COURSES
            # -----------------------------

            if choice == "1":

                courses = (
                    course_service
                    .get_instructor_courses(
                        user["id"]
                    )
                )

                print_header("MY COURSES")

                if not courses:

                    print(
                        "No courses assigned."
                    )

                for course in courses:

                    print(
                        f"Course: {course[1]}"
                    )

            # -----------------------------
            # VIEW TRAINEES
            # -----------------------------

            elif choice == "2":

                course = (
                    instructor_choose_course(
                        course_service,
                        user["id"]
                    )
                )

                if course:

                    trainees = (
                        enrollment_service
                        .get_course_trainees(
                            course[0]
                        )
                    )

                    print_header(
                        f"TRAINEES - {course[1]}"
                    )

                    if not trainees:

                        print(
                            "No trainees enrolled."
                        )

                    for trainee in trainees:

                        print(
                            f"Name: {trainee[1]} | "
                            f"Email: {trainee[2]}"
                        )

            # -----------------------------
            # ATTENDANCE
            # -----------------------------

            elif choice == "3":

                instructor_record_attendance(
                    course_service,
                    enrollment_service,
                    attendance_service,
                    user["id"]
                )

            # -----------------------------
            # GRADES
            # -----------------------------

            elif choice == "4":

                instructor_add_grade(
                    course_service,
                    enrollment_service,
                    grade_service,
                    user["id"]
                )

            # -----------------------------
            # LOGOUT
            # -----------------------------

            elif choice == "5":

                session.logout()

                print(
                    "Logged out successfully."
                )

            else:

                print("Invalid option.")

        # ==================================================
        # TRAINEE
        # ==================================================

        elif role == "trainee":

            print("1. View Courses")
            print("2. View My Courses")
            print("3. View My Attendance")
            print("4. View My Grades")
            print("5. Logout")

            choice = input(
                "\nChoose an option: "
            )

            # -----------------------------
            # VIEW ALL COURSES
            # -----------------------------

            if choice == "1":

                courses = (
                    course_service
                    .get_all()
                )

                print_header("COURSES")

                for course in courses:

                    instructor = (
                        course[2]
                        if course[2]
                        else "Not assigned"
                    )

                    print(
                        f"Course: {course[1]} | "
                        f"Instructor: {instructor}"
                    )

            # -----------------------------
            # MY COURSES
            # -----------------------------

            elif choice == "2":

                courses = (
                    enrollment_service
                    .get_trainee_courses(
                        user["id"]
                    )
                )

                print_header("MY COURSES")

                if not courses:

                    print(
                        "You are not enrolled "
                        "in any course."
                    )

                for course in courses:

                    print(
                        f"Course: {course[1]}"
                    )

            # -----------------------------
            # ATTENDANCE
            # -----------------------------

            elif choice == "3":

                attendance = (
                    attendance_service
                    .get_trainee_attendance(
                        user["id"]
                    )
                )

                print_header(
                    "MY ATTENDANCE"
                )

                if not attendance:

                    print(
                        "No attendance records."
                    )

                for row in attendance:

                    print(
                        f"Course: {row[0]} | "
                        f"Date: {row[1]} | "
                        f"Status: {row[2]}"
                    )

            # -----------------------------
            # GRADES
            # -----------------------------

            elif choice == "4":

                grades = (
                    grade_service
                    .get_trainee_grades(
                        user["id"]
                    )
                )

                print_header("MY GRADES")

                if not grades:

                    print(
                        "No grades available."
                    )

                for row in grades:

                    print(
                        f"Course: {row[0]} | "
                        f"Score: {row[1]}"
                    )

            # -----------------------------
            # LOGOUT
            # -----------------------------

            elif choice == "5":

                session.logout()

                print(
                    "Logged out successfully."
                )

            else:

                print("Invalid option.")

    connection.close()

    print("Goodbye!")


if __name__ == "__main__":
    main()
