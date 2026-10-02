"""
grading_service.py
Configurable grading components per batch.
Each component has a weight (percentage of total grade).
Supports auto-calculating the final weighted grade from component scores.
"""


class GradingService:

    def __init__(self, connection):
        self.connection = connection

    # ── Grading Component CRUD ────────────────────────────────────────────────

    def create_component(self, batch_id, name, weight, description=None, order_index=None):
        name = name.strip() if name else ""
        if not name:
            raise ValueError("Component name cannot be empty.")
        if weight <= 0 or weight > 100:
            raise ValueError("Weight must be between 0 and 100.")

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM batches WHERE id = ?", (batch_id,))
        if not cursor.fetchone():
            raise ValueError("Batch not found.")

        # Check total weights don't exceed 100
        cursor.execute(
            "SELECT COALESCE(SUM(weight), 0) FROM grading_components WHERE batch_id = ?",
            (batch_id,)
        )
        current_total = cursor.fetchone()[0]
        if current_total + weight > 100:
            raise ValueError(
                f"Total component weights cannot exceed 100%. "
                f"Current total: {current_total}%. Adding {weight}% would exceed limit."
            )

        if order_index is None:
            cursor.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM grading_components WHERE batch_id = ?",
                (batch_id,)
            )
            order_index = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO grading_components (batch_id, name, weight, description, order_index)
            VALUES (?, ?, ?, ?, ?)
            """,
            (batch_id, name, weight, description, order_index)
        )
        self.connection.commit()
        return cursor.lastrowid

    def update_component(self, component_id, name, weight, description=None):
        name = name.strip() if name else ""
        if not name:
            raise ValueError("Component name cannot be empty.")
        if weight <= 0 or weight > 100:
            raise ValueError("Weight must be between 0 and 100.")

        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT batch_id FROM grading_components WHERE id = ?", (component_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Grading component not found.")

        batch_id = row[0]
        cursor.execute(
            "SELECT COALESCE(SUM(weight), 0) FROM grading_components WHERE batch_id = ? AND id != ?",
            (batch_id, component_id)
        )
        other_total = cursor.fetchone()[0]
        if other_total + weight > 100:
            raise ValueError(
                f"Total component weights cannot exceed 100%. "
                f"Other components total: {other_total}%."
            )

        cursor.execute(
            "UPDATE grading_components SET name = ?, weight = ?, description = ? WHERE id = ?",
            (name, weight, description, component_id)
        )
        self.connection.commit()

    def delete_component(self, component_id):
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM grading_components WHERE id = ?", (component_id,))
        if cursor.rowcount == 0:
            raise ValueError("Grading component not found.")
        self.connection.commit()

    def get_components(self, batch_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, batch_id, name, weight, description, order_index, created_at
            FROM grading_components
            WHERE batch_id = ?
            ORDER BY order_index ASC, id ASC
            """,
            (batch_id,)
        )
        return cursor.fetchall()

    def get_total_weight(self, batch_id) -> float:
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(weight), 0) FROM grading_components WHERE batch_id = ?",
            (batch_id,)
        )
        return cursor.fetchone()[0]

    # ── Component Scores ──────────────────────────────────────────────────────

    def set_score(self, component_id, trainee_id, score, notes=None, recorded_by=None):
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT id FROM grading_components WHERE id = ?", (component_id,)
        )
        if not cursor.fetchone():
            raise ValueError("Grading component not found.")

        if score < 0 or score > 100:
            raise ValueError("Score must be between 0 and 100.")

        cursor.execute(
            """
            INSERT INTO component_scores (component_id, trainee_id, score, notes, recorded_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (component_id, trainee_id)
            DO UPDATE SET
                score = excluded.score, notes = excluded.notes,
                recorded_by = excluded.recorded_by,
                recorded_at = datetime('now')
            """,
            (component_id, trainee_id, score, notes, recorded_by)
        )
        self.connection.commit()

    def get_scores_for_trainee(self, batch_id, trainee_id):
        """
        Return all component scores for a trainee in a batch.
        Returns list of (component_id, component_name, weight, score|None)
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT gc.id, gc.name, gc.weight, cs.score, cs.notes
            FROM grading_components gc
            LEFT JOIN component_scores cs
                ON gc.id = cs.component_id AND cs.trainee_id = ?
            WHERE gc.batch_id = ?
            ORDER BY gc.order_index ASC
            """,
            (trainee_id, batch_id)
        )
        return cursor.fetchall()

    def calculate_final_grade(self, batch_id, trainee_id) -> float | None:
        """
        Calculate the weighted final grade for a trainee.
        Returns None if no scores exist.
        Scores are normalized: (score/100) * weight, summed across all components.
        """
        scores = self.get_scores_for_trainee(batch_id, trainee_id)
        if not scores:
            return None

        total_weight = sum(s[2] for s in scores)
        if total_weight == 0:
            return None

        weighted_sum = sum(
            (s[3] / 100.0) * s[2]
            for s in scores
            if s[3] is not None
        )
        # Scale to 0-100
        return round(weighted_sum, 2)

    def get_batch_grades_summary(self, batch_id):
        """
        Return a summary of final grades for all trainees in a batch.
        (trainee_id, name, email, final_grade | None)
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT DISTINCT be.trainee_id, u.name, u.email
            FROM batch_enrollments be
            JOIN users u ON be.trainee_id = u.id
            WHERE be.batch_id = ? AND be.status = 'active'
            ORDER BY u.name
            """,
            (batch_id,)
        )
        trainees = cursor.fetchall()

        score_rows = self.get_all_scores_for_batch(batch_id)
        scores_by_trainee = {}
        for tid, _trainee_name, _component_id, _component_name, weight, score in score_rows:
            scores_by_trainee.setdefault(tid, []).append((weight, score))

        result = []
        for tid, name, email in trainees:
            scores = scores_by_trainee.get(tid, [])
            if not scores or sum(row[0] for row in scores) == 0:
                grade = None
            else:
                weighted_sum = sum(
                    (score / 100.0) * weight
                    for weight, score in scores
                    if score is not None
                )
                grade = round(weighted_sum, 2)
            result.append((tid, name, email, grade))
        return result

    def get_all_scores_for_batch(self, batch_id):
        """
        Get all scores for all trainees in a batch.
        Returns list of (trainee_id, trainee_name, component_id, component_name, weight, score)
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT be.trainee_id, u.name AS trainee_name,
                   gc.id AS component_id, gc.name AS component_name, gc.weight,
                   cs.score
            FROM batch_enrollments be
            JOIN users u ON be.trainee_id = u.id
            CROSS JOIN grading_components gc
            LEFT JOIN component_scores cs
                ON cs.component_id = gc.id AND cs.trainee_id = be.trainee_id
            WHERE be.batch_id = ? AND be.status = 'active' AND gc.batch_id = ?
            ORDER BY u.name, gc.order_index
            """,
            (batch_id, batch_id)
        )
        return cursor.fetchall()
