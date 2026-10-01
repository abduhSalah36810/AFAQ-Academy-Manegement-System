"""
bonus_service.py
Manages student bonuses awarded by instructors/admins.
Bonuses are additive points on top of the calculated grade.
"""


class BonusService:

    def __init__(self, connection):
        self.connection = connection

    def award(self, trainee_id, amount, reason, awarded_by=None,
              batch_id=None, course_id=None):
        reason = reason.strip() if reason else ""
        if not reason:
            raise ValueError("Bonus reason cannot be empty.")
        if amount <= 0:
            raise ValueError("Bonus amount must be greater than 0.")

        cursor = self.connection.cursor()

        cursor.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'trainee'", (trainee_id,)
        )
        if not cursor.fetchone():
            raise ValueError("Trainee not found.")

        cursor.execute(
            """
            INSERT INTO student_bonuses
                (trainee_id, batch_id, course_id, amount, reason, awarded_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (trainee_id, batch_id, course_id, amount, reason, awarded_by)
        )
        self.connection.commit()
        return cursor.lastrowid

    def delete(self, bonus_id):
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM student_bonuses WHERE id = ?", (bonus_id,))
        if cursor.rowcount == 0:
            raise ValueError("Bonus not found.")
        self.connection.commit()

    def get_trainee_bonuses(self, trainee_id, batch_id=None, course_id=None):
        cursor = self.connection.cursor()
        query = """
            SELECT sb.id, sb.amount, sb.reason, sb.awarded_at,
                   b.name AS batch_name, c.name AS course_name,
                   u.name AS awarded_by_name
            FROM student_bonuses sb
            LEFT JOIN batches b ON sb.batch_id = b.id
            LEFT JOIN courses c ON sb.course_id = c.id
            LEFT JOIN users u ON sb.awarded_by = u.id
            WHERE sb.trainee_id = ?
        """
        params = [trainee_id]
        if batch_id:
            query += " AND sb.batch_id = ?"
            params.append(batch_id)
        if course_id:
            query += " AND sb.course_id = ?"
            params.append(course_id)
        query += " ORDER BY sb.awarded_at DESC"
        cursor.execute(query, params)
        return cursor.fetchall()

    def get_total_bonus(self, trainee_id, batch_id=None) -> float:
        """Get the total bonus points for a trainee, optionally scoped to a batch."""
        cursor = self.connection.cursor()
        if batch_id:
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM student_bonuses WHERE trainee_id = ? AND batch_id = ?",
                (trainee_id, batch_id)
            )
        else:
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM student_bonuses WHERE trainee_id = ?",
                (trainee_id,)
            )
        return cursor.fetchone()[0]

    def get_batch_bonuses(self, batch_id):
        """Get all bonuses for all trainees in a batch."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT sb.id, sb.trainee_id, u.name AS trainee_name,
                   sb.amount, sb.reason, sb.awarded_at,
                   ub.name AS awarded_by_name
            FROM student_bonuses sb
            JOIN users u ON sb.trainee_id = u.id
            LEFT JOIN users ub ON sb.awarded_by = ub.id
            WHERE sb.batch_id = ?
            ORDER BY sb.awarded_at DESC
            """,
            (batch_id,)
        )
        return cursor.fetchall()

    def get_batch_bonus_totals(self, batch_id):
        """Return {trainee_id: total_bonus} for all trainees in a batch."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT trainee_id, COALESCE(SUM(amount), 0) AS total
            FROM student_bonuses
            WHERE batch_id = ?
            GROUP BY trainee_id
            """,
            (batch_id,)
        )
        return {row[0]: row[1] for row in cursor.fetchall()}
