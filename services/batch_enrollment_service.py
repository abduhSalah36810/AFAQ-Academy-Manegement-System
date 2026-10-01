"""
batch_enrollment_service.py
Manages the enrollment of trainees into specific batches.
Enforces:
  - Capacity limits
  - Registration cutoff (based on completed sessions)
  - Active trainee only
  - No duplicate enrollments
  - Uses BatchService for business rule validation
"""

from services.batch_service import BatchService


class BatchEnrollmentService:

    def __init__(self, connection):
        self.connection = connection
        self._batch_svc = BatchService(connection)

    # ── Enrollment ────────────────────────────────────────────────────────────

    def enroll(self, batch_id, trainee_id, enrolled_by=None, price=None, amount_paid=0.0, payment_status=None, payment_notes=None):
        """
        Enroll a trainee in a batch.
        Raises ValueError if any business rule is violated.
        """
        cursor = self.connection.cursor()

        # Validate trainee
        cursor.execute(
            "SELECT id, active FROM users WHERE id = ? AND role = 'trainee'",
            (trainee_id,)
        )
        trainee = cursor.fetchone()
        if not trainee:
            raise ValueError("Trainee not found.")
        if trainee[1] == 0:
            raise ValueError("Cannot enroll a deactivated trainee.")

        # Check business rules (capacity, cutoff, status)
        self._batch_svc.check_can_enroll(batch_id)

        # Default price from batch or course if not provided
        if price is None:
            cursor.execute(
                """
                SELECT COALESCE(b.price, c.price, 0.0)
                FROM batches b
                JOIN courses c ON b.course_id = c.id
                WHERE b.id = ?
                """,
                (batch_id,)
            )
            p_row = cursor.fetchone()
            price = p_row[0] if p_row and p_row[0] is not None else 0.0

        price = float(price or 0.0)
        amount_paid = float(amount_paid or 0.0)

        if not payment_status:
            if amount_paid >= price and price > 0:
                payment_status = "paid"
            elif amount_paid > 0:
                payment_status = "partially_paid"
            else:
                payment_status = "unpaid"

        # Check not already enrolled
        cursor.execute(
            "SELECT status FROM batch_enrollments WHERE batch_id = ? AND trainee_id = ?",
            (batch_id, trainee_id)
        )
        existing = cursor.fetchone()
        if existing:
            if existing[0] == "active":
                raise ValueError("Trainee is already enrolled in this batch.")
            # Re-activate a dropped enrollment
            cursor.execute(
                """
                UPDATE batch_enrollments
                SET status = 'active', enrolled_by = ?, price = ?, amount_paid = ?, payment_status = ?, payment_notes = ?
                WHERE batch_id = ? AND trainee_id = ?
                """,
                (enrolled_by, price, amount_paid, payment_status, payment_notes, batch_id, trainee_id)
            )
            self.connection.commit()
            return

        cursor.execute(
            """
            INSERT INTO batch_enrollments
                (batch_id, trainee_id, enrolled_by, price, amount_paid, payment_status, payment_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (batch_id, trainee_id, enrolled_by, price, amount_paid, payment_status, payment_notes)
        )
        self.connection.commit()

    def update_payment(self, enrollment_id, price=None, amount_paid=None, payment_status=None, payment_notes=None):
        """Update payment record for a batch enrollment."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT id, price, amount_paid, payment_status, payment_notes FROM batch_enrollments WHERE id = ?",
            (enrollment_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Enrollment record not found.")

        curr_price = row[1] if row[1] is not None else 0.0
        curr_paid = row[2] if row[2] is not None else 0.0
        curr_status = row[3] or "unpaid"
        curr_notes = row[4] or ""

        new_price = float(price) if price is not None else curr_price
        new_paid = float(amount_paid) if amount_paid is not None else curr_paid
        new_notes = payment_notes if payment_notes is not None else curr_notes

        if payment_status:
            new_status = payment_status
        else:
            if new_paid >= new_price and new_price > 0:
                new_status = "paid"
            elif new_paid > 0:
                new_status = "partially_paid"
            else:
                new_status = "unpaid"

        cursor.execute(
            """
            UPDATE batch_enrollments
            SET price = ?, amount_paid = ?, payment_status = ?, payment_notes = ?
            WHERE id = ?
            """,
            (new_price, new_paid, new_status, new_notes, enrollment_id)
        )
        self.connection.commit()
        return {
            "id": enrollment_id,
            "price": new_price,
            "amount_paid": new_paid,
            "payment_status": new_status,
            "payment_notes": new_notes,
        }

    def unenroll(self, batch_id, trainee_id):
        """Mark enrollment as dropped (soft delete)."""
        cursor = self.connection.cursor()
        cursor.execute(
            "UPDATE batch_enrollments SET status = 'dropped' WHERE batch_id = ? AND trainee_id = ? AND status = 'active'",
            (batch_id, trainee_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("Active enrollment not found.")
        self.connection.commit()

    def complete_enrollment(self, batch_id, trainee_id):
        """Mark enrollment as completed (batch finished)."""
        cursor = self.connection.cursor()
        cursor.execute(
            "UPDATE batch_enrollments SET status = 'completed' WHERE batch_id = ? AND trainee_id = ?",
            (batch_id, trainee_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("Enrollment not found.")
        self.connection.commit()

    # ── Bulk Enroll (admin import) ─────────────────────────────────────────────

    def bulk_enroll(self, batch_id, trainee_ids: list, enrolled_by=None):
        """
        Enroll multiple trainees, collecting per-trainee errors instead of stopping.
        Returns (successes: list[int], errors: list[str])
        """
        successes = []
        errors = []
        for tid in trainee_ids:
            try:
                self.enroll(batch_id, tid, enrolled_by=enrolled_by)
                successes.append(tid)
            except ValueError as e:
                errors.append(f"Trainee {tid}: {e}")
        return successes, errors

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_batch_trainees(self, batch_id, status="active"):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT u.id, u.name, u.email, u.profile_image_url,
                   be.status, be.enrolled_at,
                   be.id, be.price, be.amount_paid, be.payment_status, be.payment_notes
            FROM batch_enrollments be
            JOIN users u ON be.trainee_id = u.id
            WHERE be.batch_id = ?
            AND be.status = ?
            ORDER BY u.name
            """,
            (batch_id, status)
        )
        return cursor.fetchall()

    def get_all_batch_trainees(self, batch_id):
        """Return all trainees regardless of enrollment status."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT u.id, u.name, u.email, u.profile_image_url,
                   be.status, be.enrolled_at,
                   be.id, be.price, be.amount_paid, be.payment_status, be.payment_notes
            FROM batch_enrollments be
            JOIN users u ON be.trainee_id = u.id
            WHERE be.batch_id = ?
            ORDER BY be.enrolled_at DESC
            """,
            (batch_id,)
        )
        return cursor.fetchall()

    def get_trainee_batches(self, trainee_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT b.id, b.name, b.course_id, c.name AS course_name,
                   b.start_date, b.end_date, b.status AS batch_status,
                   be.status AS enrollment_status, be.enrolled_at,
                   be.id, be.price, be.amount_paid, be.payment_status, be.payment_notes
            FROM batch_enrollments be
            JOIN batches b ON be.batch_id = b.id
            JOIN courses c ON b.course_id = c.id
            WHERE be.trainee_id = ?
            ORDER BY be.enrolled_at DESC
            """,
            (trainee_id,)
        )
        return cursor.fetchall()

    def is_enrolled(self, batch_id, trainee_id) -> bool:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT 1 FROM batch_enrollments WHERE batch_id = ? AND trainee_id = ? AND status = 'active'",
            (batch_id, trainee_id)
        )
        return cursor.fetchone() is not None

    def get_enrolled_count(self, batch_id) -> int:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM batch_enrollments WHERE batch_id = ? AND status = 'active'",
            (batch_id,)
        )
        return cursor.fetchone()[0]

    def get_enrollment(self, batch_id, trainee_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, batch_id, trainee_id, status, enrolled_at,
                   price, amount_paid, payment_status, payment_notes
            FROM batch_enrollments
            WHERE batch_id = ? AND trainee_id = ?
            """,
            (batch_id, trainee_id)
        )
        return cursor.fetchone()
