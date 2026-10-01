"""
submission_service.py
Manages task submissions by trainees.
Workflow: submitted → under_review → approved / rejected / needs_revision
"""


class SubmissionService:

    VALID_STATUSES = {"submitted", "under_review", "approved", "rejected", "needs_revision"}

    def __init__(self, connection):
        self.connection = connection

    def submit(self, task_id, trainee_id, batch_id=None,
               submission_url=None, submission_text=None):
        """
        Trainee submits a task (URL or text).
        If already submitted, updates the submission and resets status to 'submitted'.
        """
        if not submission_url and not submission_text:
            raise ValueError("Submission must include a URL or text.")

        cursor = self.connection.cursor()

        # Verify task exists
        cursor.execute("SELECT id, max_score FROM course_tasks WHERE id = ?", (task_id,))
        task = cursor.fetchone()
        if not task:
            raise ValueError("Task not found.")

        # Verify trainee
        cursor.execute("SELECT id FROM users WHERE id = ? AND role = 'trainee'", (trainee_id,))
        if not cursor.fetchone():
            raise ValueError("Trainee not found.")

        # If batch provided, verify enrollment
        if batch_id:
            cursor.execute(
                "SELECT 1 FROM batch_enrollments WHERE batch_id = ? AND trainee_id = ? AND status = 'active'",
                (batch_id, trainee_id)
            )
            if not cursor.fetchone():
                raise ValueError("Trainee is not enrolled in this batch.")

        # Check for existing submission (upsert)
        cursor.execute(
            "SELECT id FROM task_submissions WHERE task_id = ? AND trainee_id = ?",
            (task_id, trainee_id)
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE task_submissions SET
                    submission_url = ?, submission_text = ?,
                    submitted_at = datetime('now'),
                    status = 'submitted', score = NULL,
                    feedback = NULL, reviewed_by = NULL, reviewed_at = NULL
                WHERE task_id = ? AND trainee_id = ?
                """,
                (submission_url, submission_text, task_id, trainee_id)
            )
        else:
            cursor.execute(
                """
                INSERT INTO task_submissions
                    (task_id, trainee_id, batch_id, submission_url, submission_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, trainee_id, batch_id, submission_url, submission_text)
            )

        self.connection.commit()

    def review(self, submission_id, status, score=None, feedback=None, reviewed_by=None):
        """
        Instructor/admin reviews a submission.
        status must be one of: approved, rejected, needs_revision, under_review
        score must be within [0, task.max_score] if provided.
        """
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {self.VALID_STATUSES}")

        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT ts.id, ct.max_score FROM task_submissions ts
            JOIN course_tasks ct ON ts.task_id = ct.id
            WHERE ts.id = ?
            """,
            (submission_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Submission not found.")

        max_score = row[1]
        if score is not None and (score < 0 or score > max_score):
            raise ValueError(f"Score must be between 0 and {max_score}.")

        cursor.execute(
            """
            UPDATE task_submissions SET
                status = ?, score = ?, feedback = ?,
                reviewed_by = ?, reviewed_at = datetime('now')
            WHERE id = ?
            """,
            (status, score, feedback, reviewed_by, submission_id)
        )
        self.connection.commit()

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_by_id(self, submission_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT ts.id, ts.task_id, ct.title AS task_title,
                   ts.trainee_id, u.name AS trainee_name,
                   ts.batch_id, ts.submission_url, ts.submission_text,
                   ts.submitted_at, ts.status, ts.score, ts.feedback,
                   ts.reviewed_by, ts.reviewed_at, ct.max_score
            FROM task_submissions ts
            JOIN course_tasks ct ON ts.task_id = ct.id
            JOIN users u ON ts.trainee_id = u.id
            WHERE ts.id = ?
            """,
            (submission_id,)
        )
        return cursor.fetchone()

    def get_by_task(self, task_id, status=None):
        cursor = self.connection.cursor()
        query = """
            SELECT ts.id, ts.task_id, ct.title AS task_title,
                   ts.trainee_id, u.name AS trainee_name, u.email AS trainee_email,
                   ts.submitted_at, ts.status, ts.score, ts.feedback, ct.max_score
            FROM task_submissions ts
            JOIN course_tasks ct ON ts.task_id = ct.id
            JOIN users u ON ts.trainee_id = u.id
            WHERE ts.task_id = ?
        """
        params = [task_id]
        if status:
            query += " AND ts.status = ?"
            params.append(status)
        query += " ORDER BY ts.submitted_at DESC"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_by_trainee(self, trainee_id, course_id=None):
        cursor = self.connection.cursor()
        query = """
            SELECT ts.id, ts.task_id, ct.title AS task_title,
                   ct.course_id, c.name AS course_name,
                   ts.submitted_at, ts.status, ts.score, ct.max_score,
                   ts.feedback, ts.submission_url, ts.submission_text
            FROM task_submissions ts
            JOIN course_tasks ct ON ts.task_id = ct.id
            JOIN courses c ON ct.course_id = c.id
            WHERE ts.trainee_id = ?
        """
        params = [trainee_id]
        if course_id:
            query += " AND ct.course_id = ?"
            params.append(course_id)
        query += " ORDER BY ts.submitted_at DESC"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_by_batch(self, batch_id, status=None):
        cursor = self.connection.cursor()
        query = """
            SELECT ts.id, ts.task_id, ct.title AS task_title,
                   ts.trainee_id, u.name AS trainee_name, u.email AS trainee_email,
                   ts.submitted_at, ts.status, ts.score, ts.feedback, ct.max_score,
                   ts.submission_url, ts.submission_text
            FROM task_submissions ts
            JOIN course_tasks ct ON ts.task_id = ct.id
            JOIN users u ON ts.trainee_id = u.id
            WHERE ts.batch_id = ?
        """
        params = [batch_id]
        if status:
            query += " AND ts.status = ?"
            params.append(status)
        query += " ORDER BY ts.submitted_at DESC"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_pending_review(self, course_id=None, batch_id=None):
        """Get all submissions needing review."""
        cursor = self.connection.cursor()
        query = """
            SELECT ts.id, ts.task_id, ct.title AS task_title,
                   ts.trainee_id, u.name AS trainee_name,
                   ts.submitted_at, ts.status, ct.max_score
            FROM task_submissions ts
            JOIN course_tasks ct ON ts.task_id = ct.id
            JOIN users u ON ts.trainee_id = u.id
            WHERE ts.status IN ('submitted', 'under_review')
        """
        params = []
        if course_id:
            query += " AND ct.course_id = ?"
            params.append(course_id)
        if batch_id:
            query += " AND ts.batch_id = ?"
            params.append(batch_id)
        query += " ORDER BY ts.submitted_at ASC"
        cursor.execute(query, params)
        return cursor.fetchall()
