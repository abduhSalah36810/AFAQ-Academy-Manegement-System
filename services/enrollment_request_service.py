"""
enrollment_request_service.py
Manages enrollment requests submitted by trainees to join a batch.
Workflow: trainee submits → admin/instructor approves or rejects → if approved, auto-enroll.
"""

from services.batch_service import BatchService
from services.batch_enrollment_service import BatchEnrollmentService


class EnrollmentRequestService:

    VALID_STATUSES = {"pending", "approved", "rejected"}

    def __init__(self, connection):
        self.connection = connection

    def submit_request(self, batch_id, trainee_id, trainee_note=None):
        """
        Trainee submits a request to join a batch.
        Raises ValueError if:
          - Batch is cancelled/completed
          - Already enrolled in this batch
          - Already has a pending request
        Does NOT enforce capacity at request time (capacity is checked at approval).
        """
        cursor = self.connection.cursor()

        # Check batch exists and is open
        cursor.execute(
            "SELECT id, status FROM batches WHERE id = ?", (batch_id,)
        )
        batch = cursor.fetchone()
        if not batch:
            raise ValueError("Batch not found.")
        if batch[1] in ("cancelled", "completed"):
            raise ValueError("This batch is no longer accepting applications.")

        # Check trainee exists and is active
        cursor.execute(
            "SELECT id, active FROM users WHERE id = ? AND role = 'trainee'", (trainee_id,)
        )
        trainee = cursor.fetchone()
        if not trainee:
            raise ValueError("Trainee not found.")
        if trainee[1] == 0:
            raise ValueError("Deactivated trainees cannot submit enrollment requests.")

        # Already enrolled?
        cursor.execute(
            "SELECT status FROM batch_enrollments WHERE batch_id = ? AND trainee_id = ? AND status = 'active'",
            (batch_id, trainee_id)
        )
        if cursor.fetchone():
            raise ValueError("You are already enrolled in this batch.")

        # Already has a pending/approved request?
        cursor.execute(
            "SELECT status FROM enrollment_requests WHERE batch_id = ? AND trainee_id = ?",
            (batch_id, trainee_id)
        )
        existing = cursor.fetchone()
        if existing:
            if existing[0] == "pending":
                raise ValueError("You already have a pending request for this batch.")
            if existing[0] == "approved":
                raise ValueError("Your request for this batch was already approved.")
            # If rejected, allow re-submission: update the existing record
            cursor.execute(
                """
                UPDATE enrollment_requests
                SET status = 'pending', trainee_note = ?, admin_note = NULL,
                    reviewed_by = NULL, reviewed_at = NULL,
                    requested_at = datetime('now')
                WHERE batch_id = ? AND trainee_id = ?
                """,
                (trainee_note, batch_id, trainee_id)
            )
            self.connection.commit()
            return

        cursor.execute(
            """
            INSERT INTO enrollment_requests (batch_id, trainee_id, trainee_note)
            VALUES (?, ?, ?)
            """,
            (batch_id, trainee_id, trainee_note)
        )
        self.connection.commit()

    def approve(self, request_id, reviewed_by=None, admin_note=None):
        """
        Approve a pending request and auto-enroll the trainee.
        Returns (batch_id, trainee_id) on success.
        """
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT batch_id, trainee_id, status FROM enrollment_requests WHERE id = ?",
            (request_id,)
        )
        req = cursor.fetchone()
        if not req:
            raise ValueError("Enrollment request not found.")
        if req[2] != "pending":
            raise ValueError(f"Request is already {req[2]}.")

        batch_id, trainee_id = req[0], req[1]

        # Validate capacity/cutoff before approving
        batch_svc = BatchService(self.connection)
        batch_svc.check_can_enroll(batch_id)

        # Auto-enroll
        enroll_svc = BatchEnrollmentService(self.connection)
        enroll_svc.enroll(batch_id, trainee_id, enrolled_by=reviewed_by)

        # Mark request as approved
        cursor.execute(
            """
            UPDATE enrollment_requests
            SET status = 'approved', reviewed_by = ?, admin_note = ?,
                reviewed_at = datetime('now')
            WHERE id = ?
            """,
            (reviewed_by, admin_note, request_id)
        )
        self.connection.commit()
        return batch_id, trainee_id

    def reject(self, request_id, reviewed_by=None, admin_note=None):
        """Reject a pending enrollment request."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT status FROM enrollment_requests WHERE id = ?", (request_id,)
        )
        req = cursor.fetchone()
        if not req:
            raise ValueError("Enrollment request not found.")
        if req[0] != "pending":
            raise ValueError(f"Request is already {req[0]}.")

        cursor.execute(
            """
            UPDATE enrollment_requests
            SET status = 'rejected', reviewed_by = ?, admin_note = ?,
                reviewed_at = datetime('now')
            WHERE id = ?
            """,
            (reviewed_by, admin_note, request_id)
        )
        self.connection.commit()

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_pending(self, batch_id=None):
        """Get all pending requests, optionally filtered by batch."""
        cursor = self.connection.cursor()
        query = """
            SELECT er.id, er.batch_id, b.name AS batch_name,
                   c.name AS course_name,
                   er.trainee_id, u.name AS trainee_name, u.email AS trainee_email,
                   er.status, er.trainee_note, er.requested_at
            FROM enrollment_requests er
            JOIN batches b ON er.batch_id = b.id
            JOIN courses c ON b.course_id = c.id
            JOIN users u ON er.trainee_id = u.id
            WHERE er.status = 'pending'
        """
        params = []
        if batch_id:
            query += " AND er.batch_id = ?"
            params.append(batch_id)
        query += " ORDER BY er.requested_at ASC"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_all(self, batch_id=None, trainee_id=None, status=None):
        cursor = self.connection.cursor()
        query = """
            SELECT er.id, er.batch_id, b.name AS batch_name,
                   c.name AS course_name,
                   er.trainee_id, u.name AS trainee_name, u.email AS trainee_email,
                   er.status, er.trainee_note, er.admin_note, er.requested_at, er.reviewed_at
            FROM enrollment_requests er
            JOIN batches b ON er.batch_id = b.id
            JOIN courses c ON b.course_id = c.id
            JOIN users u ON er.trainee_id = u.id
            WHERE 1=1
        """
        params = []
        if batch_id:
            query += " AND er.batch_id = ?"
            params.append(batch_id)
        if trainee_id:
            query += " AND er.trainee_id = ?"
            params.append(trainee_id)
        if status:
            query += " AND er.status = ?"
            params.append(status)
        query += " ORDER BY er.requested_at DESC"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_trainee_requests(self, trainee_id):
        return self.get_all(trainee_id=trainee_id)

    def get_pending_count(self) -> int:
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM enrollment_requests WHERE status = 'pending'")
        return cursor.fetchone()[0]
