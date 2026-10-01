"""
batch_service.py
Manages batches (cohorts) of a course.
Business rules enforced here:
  - Capacity check: batch_enrollments count < capacity (0 = unlimited)
  - Registration cutoff: new enrollments blocked after `registration_cutoff_sessions`
    completed batch sessions have passed.
  - Only active trainees may be enrolled.
  - One active enrollment per trainee per batch.
"""


class BatchService:

    def __init__(self, connection):
        self.connection = connection

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(self, course_id, name, instructor_id=None, capacity=0,
               start_date=None, end_date=None,
               registration_open_date=None, registration_close_date=None,
               registration_cutoff_sessions=0, notes=None):
        name = name.strip() if name else ""
        if not name:
            raise ValueError("Batch name cannot be empty.")

        cursor = self.connection.cursor()

        # Verify course exists and is active
        cursor.execute("SELECT id, active FROM courses WHERE id = ?", (course_id,))
        course = cursor.fetchone()
        if not course:
            raise ValueError("Course not found.")
        if course[1] == 0:
            raise ValueError("Cannot create a batch for an archived course.")

        # Verify instructor if given
        if instructor_id:
            cursor.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'instructor' AND active = 1",
                (instructor_id,)
            )
            if not cursor.fetchone():
                raise ValueError("Instructor not found or inactive.")

        if capacity < 0:
            raise ValueError("Capacity cannot be negative (use 0 for unlimited).")

        cursor.execute(
            """
            INSERT INTO batches
                (course_id, name, instructor_id, capacity, start_date, end_date,
                 registration_open_date, registration_close_date,
                 registration_cutoff_sessions, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (course_id, name, instructor_id, capacity, start_date, end_date,
             registration_open_date, registration_close_date,
             registration_cutoff_sessions, notes)
        )
        self.connection.commit()
        return cursor.lastrowid

    def update(self, batch_id, name, instructor_id=None, capacity=0,
               start_date=None, end_date=None,
               registration_open_date=None, registration_close_date=None,
               registration_cutoff_sessions=0, status=None, notes=None):
        name = name.strip() if name else ""
        if not name:
            raise ValueError("Batch name cannot be empty.")

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM batches WHERE id = ?", (batch_id,))
        if not cursor.fetchone():
            raise ValueError("Batch not found.")

        if instructor_id:
            cursor.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'instructor' AND active = 1",
                (instructor_id,)
            )
            if not cursor.fetchone():
                raise ValueError("Instructor not found or inactive.")

        valid_statuses = {"upcoming", "active", "completed", "cancelled"}
        if status and status not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")

        cursor.execute(
            """
            UPDATE batches SET
                name = ?, instructor_id = ?, capacity = ?,
                start_date = ?, end_date = ?,
                registration_open_date = ?, registration_close_date = ?,
                registration_cutoff_sessions = ?,
                status = COALESCE(?, status), notes = ?
            WHERE id = ?
            """,
            (name, instructor_id, capacity, start_date, end_date,
             registration_open_date, registration_close_date,
             registration_cutoff_sessions, status, notes, batch_id)
        )
        self.connection.commit()

    def set_status(self, batch_id, status):
        valid = {"upcoming", "active", "completed", "cancelled"}
        if status not in valid:
            raise ValueError(f"Invalid status. Must be one of: {valid}")
        cursor = self.connection.cursor()
        cursor.execute("UPDATE batches SET status = ? WHERE id = ?", (status, batch_id))
        if cursor.rowcount == 0:
            raise ValueError("Batch not found.")
        self.connection.commit()

    def delete(self, batch_id):
        """Delete a batch. CASCADE will remove sessions, enrollments, attendance."""
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        if cursor.rowcount == 0:
            raise ValueError("Batch not found.")
        self.connection.commit()

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_by_id(self, batch_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT b.id, b.course_id, b.name, b.instructor_id, u.name AS instructor_name,
                   b.capacity, b.start_date, b.end_date,
                   b.registration_open_date, b.registration_close_date,
                   b.registration_cutoff_sessions, b.status, b.notes, b.created_at,
                   c.name AS course_name
            FROM batches b
            LEFT JOIN users u ON b.instructor_id = u.id
            LEFT JOIN courses c ON b.course_id = c.id
            WHERE b.id = ?
            """,
            (batch_id,)
        )
        return cursor.fetchone()

    def get_by_course(self, course_id, include_cancelled=True):
        cursor = self.connection.cursor()
        query = """
            SELECT b.id, b.course_id, b.name, b.instructor_id, u.name AS instructor_name,
                   b.capacity, b.start_date, b.end_date, b.status, b.created_at,
                   c.name AS course_name,
                   (SELECT COUNT(*) FROM batch_enrollments be
                    WHERE be.batch_id = b.id AND be.status = 'active') AS enrolled_count
            FROM batches b
            LEFT JOIN users u ON b.instructor_id = u.id
            LEFT JOIN courses c ON b.course_id = c.id
            WHERE b.course_id = ?
        """
        params = [course_id]
        if not include_cancelled:
            query += " AND b.status != 'cancelled'"
        query += " ORDER BY b.created_at DESC"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_instructor_batches(self, instructor_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT b.id, b.course_id, b.name, b.instructor_id,
                   b.capacity, b.start_date, b.end_date, b.status, b.created_at,
                   c.name AS course_name,
                   (SELECT COUNT(*) FROM batch_enrollments be
                    WHERE be.batch_id = b.id AND be.status = 'active') AS enrolled_count
            FROM batches b
            LEFT JOIN courses c ON b.course_id = c.id
            WHERE b.instructor_id = ?
            AND b.status NOT IN ('cancelled', 'completed')
            ORDER BY b.start_date DESC
            """,
            (instructor_id,)
        )
        return cursor.fetchall()

    def get_all(self, include_cancelled=True):
        cursor = self.connection.cursor()
        query = """
            SELECT b.id, b.course_id, b.name, b.instructor_id, u.name AS instructor_name,
                   b.capacity, b.start_date, b.end_date, b.status, b.created_at,
                   c.name AS course_name,
                   (SELECT COUNT(*) FROM batch_enrollments be
                    WHERE be.batch_id = b.id AND be.status = 'active') AS enrolled_count
            FROM batches b
            LEFT JOIN users u ON b.instructor_id = u.id
            LEFT JOIN courses c ON b.course_id = c.id
        """
        if not include_cancelled:
            query += " WHERE b.status != 'cancelled'"
        query += " ORDER BY b.created_at DESC"
        cursor.execute(query)
        return cursor.fetchall()

    # ── Capacity / Cutoff Helpers ─────────────────────────────────────────────

    def get_enrolled_count(self, batch_id) -> int:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM batch_enrollments WHERE batch_id = ? AND status = 'active'",
            (batch_id,)
        )
        return cursor.fetchone()[0]

    def get_completed_sessions_count(self, batch_id) -> int:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM batch_sessions WHERE batch_id = ? AND status = 'completed'",
            (batch_id,)
        )
        return cursor.fetchone()[0]

    def check_can_enroll(self, batch_id):
        """
        Raises ValueError if enrollment is not allowed.
        Returns True if OK.
        """
        batch = self.get_by_id(batch_id)
        if not batch:
            raise ValueError("Batch not found.")

        # batch cols: id[0], course_id[1], name[2], instructor_id[3], instructor_name[4],
        #             capacity[5], start_date[6], end_date[7], reg_open[8], reg_close[9],
        #             cutoff_sessions[10], status[11], ...
        status = batch[11]
        if status == "cancelled":
            raise ValueError("This batch has been cancelled.")
        if status == "completed":
            raise ValueError("This batch has already completed.")

        capacity = batch[5]
        if capacity > 0:
            enrolled = self.get_enrolled_count(batch_id)
            if enrolled >= capacity:
                raise ValueError(
                    f"Batch is full ({enrolled}/{capacity} enrolled)."
                )

        cutoff = batch[10]
        if cutoff > 0:
            completed = self.get_completed_sessions_count(batch_id)
            if completed >= cutoff:
                raise ValueError(
                    f"Registration is closed: {completed} sessions have already been completed "
                    f"(cutoff is {cutoff} sessions)."
                )

        return True
