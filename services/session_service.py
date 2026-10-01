"""
session_service.py
Manages individual class sessions (meetings) within a batch.
Sessions have a session_number, date, and status (planned/completed/cancelled).
"""


class SessionService:

    VALID_STATUSES = {"planned", "completed", "cancelled"}

    def __init__(self, connection):
        self.connection = connection

    def create(self, batch_id, title, session_number=None, date=None,
               start_time=None, end_time=None, notes=None, recording_url=None):
        title = title.strip() if title else ""
        if not title:
            raise ValueError("Session title cannot be empty.")

        cursor = self.connection.cursor()

        cursor.execute("SELECT id FROM batches WHERE id = ?", (batch_id,))
        if not cursor.fetchone():
            raise ValueError("Batch not found.")

        if session_number is None:
            cursor.execute(
                "SELECT COALESCE(MAX(session_number), 0) + 1 FROM batch_sessions WHERE batch_id = ?",
                (batch_id,)
            )
            session_number = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO batch_sessions
                (batch_id, title, session_number, date, start_time, end_time, notes, recording_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (batch_id, title, session_number, date, start_time, end_time, notes, recording_url)
        )
        self.connection.commit()
        return cursor.lastrowid

    def update(self, session_id, title, date=None, start_time=None,
               end_time=None, notes=None, recording_url=None, status=None):
        title = title.strip() if title else ""
        if not title:
            raise ValueError("Session title cannot be empty.")
        if status and status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {self.VALID_STATUSES}")

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM batch_sessions WHERE id = ?", (session_id,))
        if not cursor.fetchone():
            raise ValueError("Session not found.")

        cursor.execute(
            """
            UPDATE batch_sessions SET
                title = ?, date = ?, start_time = ?, end_time = ?,
                notes = ?, recording_url = ?,
                status = COALESCE(?, status)
            WHERE id = ?
            """,
            (title, date, start_time, end_time, notes, recording_url, status, session_id)
        )
        self.connection.commit()

    def set_status(self, session_id, status):
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {self.VALID_STATUSES}")
        cursor = self.connection.cursor()
        cursor.execute(
            "UPDATE batch_sessions SET status = ? WHERE id = ?", (status, session_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("Session not found.")
        self.connection.commit()

    def delete(self, session_id):
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM batch_sessions WHERE id = ?", (session_id,))
        if cursor.rowcount == 0:
            raise ValueError("Session not found.")
        self.connection.commit()

    def get_by_id(self, session_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, batch_id, title, session_number, date, start_time,
                   end_time, status, notes, recording_url, created_at
            FROM batch_sessions WHERE id = ?
            """,
            (session_id,)
        )
        return cursor.fetchone()

    def get_by_batch(self, batch_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, batch_id, title, session_number, date, start_time,
                   end_time, status, notes, recording_url, created_at
            FROM batch_sessions
            WHERE batch_id = ?
            ORDER BY session_number ASC
            """,
            (batch_id,)
        )
        return cursor.fetchall()

    def get_completed_count(self, batch_id) -> int:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM batch_sessions WHERE batch_id = ? AND status = 'completed'",
            (batch_id,)
        )
        return cursor.fetchone()[0]
