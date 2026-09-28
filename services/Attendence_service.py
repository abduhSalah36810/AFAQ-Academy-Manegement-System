import sqlite3


class AttendanceService:

    def __init__(self, connection):
        self.connection = connection

    def record(self, trainee_id, course_id, date, status):
        """
        Insert or update an attendance record.
        If a record already exists for (trainee, course, date), it is updated.
        This allows correcting mistakes without deleting records.
        """
        if status not in ("present", "absent"):
            raise ValueError("Status must be 'present' or 'absent'.")

        cursor = self.connection.cursor()

        # Check that trainee is enrolled in the course
        cursor.execute(
            """
            SELECT 1 FROM enrollments
            WHERE trainee_id = ? AND course_id = ?
            """,
            (trainee_id, course_id)
        )
        if cursor.fetchone() is None:
            raise ValueError("Trainee is not enrolled in this course.")

        # UPSERT: insert if new, update if duplicate (trainee+course+date)
        cursor.execute(
            """
            INSERT INTO attendance
                (trainee_id, course_id, date, status)
            VALUES
                (?, ?, ?, ?)
            ON CONFLICT (trainee_id, course_id, date)
            DO UPDATE SET status = excluded.status
            """,
            (trainee_id, course_id, date, status)
        )
        self.connection.commit()

    def get_trainee_attendance(self, trainee_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                courses.name,
                attendance.date,
                attendance.status
            FROM attendance
            JOIN courses ON attendance.course_id = courses.id
            WHERE attendance.trainee_id = ?
            ORDER BY attendance.date DESC
            """,
            (trainee_id,)
        )
        return cursor.fetchall()

    def get_course_attendance(self, course_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                users.name,
                attendance.date,
                attendance.status
            FROM attendance
            JOIN users ON attendance.trainee_id = users.id
            WHERE attendance.course_id = ?
            ORDER BY attendance.date DESC
            """,
            (course_id,)
        )
        return cursor.fetchall()

    def get_attendance_for_date(self, course_id, date):
        """Return {trainee_id: status} for a specific course+date."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT trainee_id, status
            FROM attendance
            WHERE course_id = ? AND date = ?
            """,
            (course_id, date)
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_student_course_attendance(self, trainee_id, course_id):
        """Return all attendance records for a specific student in a course."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT date, status
            FROM attendance
            WHERE trainee_id = ? AND course_id = ?
            ORDER BY date DESC
            """,
            (trainee_id, course_id)
        )
        return cursor.fetchall()
