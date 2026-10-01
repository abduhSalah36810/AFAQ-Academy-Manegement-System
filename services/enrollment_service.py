import sqlite3


class EnrollmentService:

    def __init__(self, connection):
        self.connection = connection

    def enroll(self, trainee_id, course_id):
        cursor = self.connection.cursor()

        # Check trainee exists and is active
        cursor.execute(
            """
            SELECT id, active
            FROM users
            WHERE id = ?
            AND role = 'trainee'
            """,
            (trainee_id,)
        )
        trainee = cursor.fetchone()

        if trainee is None:
            raise ValueError("Trainee does not exist.")
        if trainee[1] == 0:
            raise ValueError("Cannot enroll a deactivated student.")

        # Check course exists and is active
        cursor.execute(
            """
            SELECT id, active
            FROM courses
            WHERE id = ?
            """,
            (course_id,)
        )
        course = cursor.fetchone()

        if course is None:
            raise ValueError("Course does not exist.")
        if course[1] == 0:
            raise ValueError("Cannot enroll in an archived course.")

        try:
            cursor.execute(
                """
                INSERT INTO enrollments
                    (trainee_id, course_id)
                VALUES
                    (?, ?)
                """,
                (
                    trainee_id,
                    course_id
                )
            )
            self.connection.commit()

        except sqlite3.IntegrityError:
            self.connection.rollback()
            raise ValueError("Student is already enrolled in this course.")

    def unenroll(self, trainee_id, course_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            DELETE FROM enrollments
            WHERE trainee_id = ? AND course_id = ?
            """,
            (trainee_id, course_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("Enrollment record not found.")
        self.connection.commit()

    def get_all_enrollments(self):
        """Return all enrollments with student and course IDs and names."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                u.id,
                u.name,
                u.email,
                c.id,
                c.name,
                c.active
            FROM enrollments e
            JOIN users u ON e.trainee_id = u.id
            JOIN courses c ON e.course_id = c.id
            ORDER BY u.name, c.name
            """
        )
        return cursor.fetchall()

    def count(self) -> int:
        """Return total count of enrollments."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM enrollments")
        return cursor.fetchone()[0]

    def get_trainee_courses(self, trainee_id):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                courses.id,
                courses.name
            FROM courses
            JOIN enrollments
                ON courses.id = enrollments.course_id
            WHERE enrollments.trainee_id = ?
            ORDER BY courses.name
            """,
            (trainee_id,)
        )

        return cursor.fetchall()

    def get_course_trainees(self, course_id):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                users.id,
                users.name,
                users.email
            FROM users
            JOIN enrollments
                ON users.id = enrollments.trainee_id
            WHERE enrollments.course_id = ?
            AND users.role = 'trainee'
            ORDER BY users.name
            """,
            (course_id,)
        )

        return cursor.fetchall()
