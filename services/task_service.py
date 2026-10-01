"""
task_service.py
Manages course tasks (assignments, quizzes, projects) attached to chapters.
"""


class TaskService:

    VALID_TYPES = {"assignment", "quiz", "project", "reading", "other"}

    def __init__(self, connection):
        self.connection = connection

    def create(self, course_id, title, description=None, task_type="assignment",
               chapter_id=None, due_date=None, max_score=100.0,
               is_required=True, order_index=None):
        title = title.strip() if title else ""
        if not title:
            raise ValueError("Task title cannot be empty.")
        if task_type not in self.VALID_TYPES:
            task_type = "assignment"
        if max_score <= 0:
            raise ValueError("Max score must be greater than 0.")

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM courses WHERE id = ?", (course_id,))
        if not cursor.fetchone():
            raise ValueError("Course not found.")

        if chapter_id:
            cursor.execute("SELECT course_id FROM chapters WHERE id = ?", (chapter_id,))
            ch = cursor.fetchone()
            if not ch:
                raise ValueError("Chapter not found.")
            if ch[0] != course_id:
                raise ValueError("Chapter does not belong to this course.")

        if order_index is None:
            cursor.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM course_tasks WHERE course_id = ?",
                (course_id,)
            )
            order_index = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO course_tasks
                (course_id, chapter_id, title, description, task_type,
                 due_date, max_score, is_required, order_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (course_id, chapter_id, title, description, task_type,
             due_date, max_score, 1 if is_required else 0, order_index)
        )
        self.connection.commit()
        return cursor.lastrowid

    def update(self, task_id, title, description=None, task_type="assignment",
               chapter_id=None, due_date=None, max_score=100.0,
               is_required=True, order_index=None):
        title = title.strip() if title else ""
        if not title:
            raise ValueError("Task title cannot be empty.")
        if task_type not in self.VALID_TYPES:
            task_type = "assignment"

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM course_tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            raise ValueError("Task not found.")

        cursor.execute(
            """
            UPDATE course_tasks SET
                title = ?, description = ?, task_type = ?,
                chapter_id = ?, due_date = ?, max_score = ?,
                is_required = ?,
                order_index = COALESCE(?, order_index)
            WHERE id = ?
            """,
            (title, description, task_type, chapter_id, due_date, max_score,
             1 if is_required else 0, order_index, task_id)
        )
        self.connection.commit()

    def delete(self, task_id):
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM course_tasks WHERE id = ?", (task_id,))
        if cursor.rowcount == 0:
            raise ValueError("Task not found.")
        self.connection.commit()

    def get_by_id(self, task_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT ct.id, ct.course_id, ct.chapter_id, ch.title AS chapter_title,
                   ct.title, ct.description, ct.task_type,
                   ct.due_date, ct.max_score, ct.is_required, ct.order_index, ct.created_at
            FROM course_tasks ct
            LEFT JOIN chapters ch ON ct.chapter_id = ch.id
            WHERE ct.id = ?
            """,
            (task_id,)
        )
        return cursor.fetchone()

    def get_by_course(self, course_id, chapter_id=None):
        cursor = self.connection.cursor()
        query = """
            SELECT ct.id, ct.course_id, ct.chapter_id, ch.title AS chapter_title,
                   ct.title, ct.description, ct.task_type,
                   ct.due_date, ct.max_score, ct.is_required, ct.order_index, ct.created_at
            FROM course_tasks ct
            LEFT JOIN chapters ch ON ct.chapter_id = ch.id
            WHERE ct.course_id = ?
        """
        params = [course_id]
        if chapter_id:
            query += " AND ct.chapter_id = ?"
            params.append(chapter_id)
        query += " ORDER BY ct.order_index ASC, ct.id ASC"
        cursor.execute(query, params)
        return cursor.fetchall()
