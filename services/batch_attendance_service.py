"""
batch_attendance_service.py
Manages session-level attendance for batches.
Separate from the legacy course-level attendance table (which is preserved).
"""


class BatchAttendanceService:

    VALID_STATUSES = {"present", "absent", "late", "excused"}

    def __init__(self, connection):
        self.connection = connection

    def record(self, batch_id, trainee_id, date, status,
               session_id=None, notes=None, recorded_by=None, commit=True):
        """Insert or update attendance (UPSERT by batch+trainee+date)."""
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Status must be one of: {self.VALID_STATUSES}")

        cursor = self.connection.cursor()

        # Verify trainee is enrolled in this batch
        cursor.execute(
            "SELECT 1 FROM batch_enrollments WHERE batch_id = ? AND trainee_id = ? AND status = 'active'",
            (batch_id, trainee_id)
        )
        if not cursor.fetchone():
            raise ValueError("Trainee is not actively enrolled in this batch.")

        cursor.execute(
            """
            INSERT INTO batch_attendance
                (batch_id, session_id, trainee_id, date, status, notes, recorded_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (batch_id, trainee_id, date)
            DO UPDATE SET
                status = excluded.status,
                notes = excluded.notes,
                recorded_by = excluded.recorded_by,
                session_id = COALESCE(excluded.session_id, session_id),
                recorded_at = datetime('now')
            """,
            (batch_id, session_id, trainee_id, date, status, notes, recorded_by)
        )
        if commit:
            self.connection.commit()

    def record_bulk(self, batch_id, date, records: list[dict],
                    session_id=None, recorded_by=None):
        """
        Bulk record attendance for a session using batch operations and a single transaction.
        records = [{"trainee_id": int, "status": str, "notes": str|None}, ...]
        Returns (saved: int, errors: list[str])
        """
        if not records:
            return 0, []

        cursor = self.connection.cursor()

        # 1. Fetch all actively enrolled trainees for this batch in a single query
        cursor.execute(
            "SELECT trainee_id FROM batch_enrollments WHERE batch_id = ? AND status = 'active'",
            (batch_id,)
        )
        active_trainee_ids = {row[0] for row in cursor.fetchall()}

        saved = 0
        errors = []
        valid_rows = []

        for rec in records:
            tid = rec.get("trainee_id")
            status = rec.get("status", "absent")
            notes = rec.get("notes")

            if status not in self.VALID_STATUSES:
                errors.append(f"Trainee {tid}: Status must be one of: {self.VALID_STATUSES}")
                continue

            if tid not in active_trainee_ids:
                errors.append(f"Trainee {tid}: Trainee is not actively enrolled in this batch.")
                continue

            valid_rows.append((batch_id, session_id, tid, date, status, notes, recorded_by))

        if valid_rows:
            try:
                cursor.executemany(
                    """
                    INSERT INTO batch_attendance
                        (batch_id, session_id, trainee_id, date, status, notes, recorded_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (batch_id, trainee_id, date)
                    DO UPDATE SET
                        status = excluded.status,
                        notes = excluded.notes,
                        recorded_by = excluded.recorded_by,
                        session_id = COALESCE(excluded.session_id, session_id),
                        recorded_at = datetime('now')
                    """,
                    valid_rows
                )
                self.connection.commit()
                saved = len(valid_rows)
            except Exception as e:
                self.connection.rollback()
                errors.append(f"Database error during batch attendance save: {e}")

        return saved, errors

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_batch_attendance(self, batch_id, date=None):
        cursor = self.connection.cursor()
        query = """
            SELECT u.id, u.name, ba.date, ba.status, ba.notes,
                   bs.title AS session_title
            FROM batch_attendance ba
            JOIN users u ON ba.trainee_id = u.id
            LEFT JOIN batch_sessions bs ON ba.session_id = bs.id
            WHERE ba.batch_id = ?
        """
        params = [batch_id]
        if date:
            query += " AND ba.date = ?"
            params.append(date)
        query += " ORDER BY ba.date DESC, u.name"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_trainee_attendance(self, batch_id, trainee_id):
        """Get all attendance records for a trainee in a batch."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT ba.date, ba.status, ba.notes, bs.title AS session_title
            FROM batch_attendance ba
            LEFT JOIN batch_sessions bs ON ba.session_id = bs.id
            WHERE ba.batch_id = ? AND ba.trainee_id = ?
            ORDER BY ba.date DESC
            """,
            (batch_id, trainee_id)
        )
        return cursor.fetchall()

    def get_session_attendance(self, batch_id, date):
        """Return {trainee_id: status} for a specific date."""
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT trainee_id, status FROM batch_attendance WHERE batch_id = ? AND date = ?",
            (batch_id, date)
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def get_attendance_summary(self, batch_id):
        """
        Return attendance summary per trainee:
        (trainee_id, name, total, present, absent, late, excused, rate)
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                u.id, u.name,
                COUNT(ba.id) AS total,
                SUM(CASE WHEN ba.status = 'present' THEN 1 ELSE 0 END) AS present,
                SUM(CASE WHEN ba.status = 'absent'  THEN 1 ELSE 0 END) AS absent,
                SUM(CASE WHEN ba.status = 'late'    THEN 1 ELSE 0 END) AS late,
                SUM(CASE WHEN ba.status = 'excused' THEN 1 ELSE 0 END) AS excused
            FROM batch_enrollments be
            JOIN users u ON be.trainee_id = u.id
            LEFT JOIN batch_attendance ba
                ON ba.batch_id = be.batch_id AND ba.trainee_id = be.trainee_id
            WHERE be.batch_id = ? AND be.status = 'active'
            GROUP BY u.id, u.name
            ORDER BY u.name
            """,
            (batch_id,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            total = r[2] or 0
            present = r[3] or 0
            rate = round((present / total * 100), 1) if total > 0 else 0
            result.append((*r, rate))
        return result
