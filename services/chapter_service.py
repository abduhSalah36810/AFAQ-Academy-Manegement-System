"""
chapter_service.py
Manages chapters (ordered sections) within a course.
"""


class ChapterService:

    def __init__(self, connection):
        self.connection = connection

    def create(self, course_id, title, description=None, order_index=None):
        title = title.strip() if title else ""
        if not title:
            raise ValueError("Chapter title cannot be empty.")

        cursor = self.connection.cursor()

        cursor.execute("SELECT id FROM courses WHERE id = ?", (course_id,))
        if not cursor.fetchone():
            raise ValueError("Course not found.")

        if order_index is None:
            cursor.execute(
                "SELECT COALESCE(MAX(order_index), -1) + 1 FROM chapters WHERE course_id = ?",
                (course_id,)
            )
            order_index = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO chapters (course_id, title, description, order_index)
            VALUES (?, ?, ?, ?)
            """,
            (course_id, title, description, order_index)
        )
        self.connection.commit()
        return cursor.lastrowid

    def update(self, chapter_id, title, description=None, order_index=None):
        title = title.strip() if title else ""
        if not title:
            raise ValueError("Chapter title cannot be empty.")

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM chapters WHERE id = ?", (chapter_id,))
        if not cursor.fetchone():
            raise ValueError("Chapter not found.")

        cursor.execute(
            """
            UPDATE chapters
            SET title = ?, description = ?,
                order_index = COALESCE(?, order_index)
            WHERE id = ?
            """,
            (title, description, order_index, chapter_id)
        )
        self.connection.commit()

    def delete(self, chapter_id):
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
        if cursor.rowcount == 0:
            raise ValueError("Chapter not found.")
        self.connection.commit()

    def get_by_id(self, chapter_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, course_id, title, description, order_index, created_at
            FROM chapters WHERE id = ?
            """,
            (chapter_id,)
        )
        return cursor.fetchone()

    def get_by_course(self, course_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, course_id, title, description, order_index, created_at
            FROM chapters
            WHERE course_id = ?
            ORDER BY order_index ASC, id ASC
            """,
            (course_id,)
        )
        return cursor.fetchall()

    def reorder(self, chapter_id, new_index):
        """Move a chapter to a new order_index position."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT course_id FROM chapters WHERE id = ?", (chapter_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Chapter not found.")
        cursor.execute(
            "UPDATE chapters SET order_index = ? WHERE id = ?",
            (new_index, chapter_id)
        )
        self.connection.commit()
