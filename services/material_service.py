class CourseMaterialService:

    VALID_TYPES = {"link", "video", "document", "github", "drive", "other"}

    def __init__(self, connection):
        self.connection = connection

    def add_material(self, course_id, title, url, description=None, material_type="link"):
        """Add a URL-based material to a course."""
        title = title.strip() if title else ""
        url = url.strip() if url else ""

        if not title:
            raise ValueError("Material title cannot be empty.")
        if not url:
            raise ValueError("URL cannot be empty.")
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        if material_type not in self.VALID_TYPES:
            material_type = "link"

        cursor = self.connection.cursor()
        # Verify course exists
        cursor.execute("SELECT id FROM courses WHERE id = ?", (course_id,))
        if cursor.fetchone() is None:
            raise ValueError("Course not found.")

        cursor.execute(
            """
            INSERT INTO course_materials
                (course_id, title, url, description, material_type)
            VALUES
                (?, ?, ?, ?, ?)
            """,
            (course_id, title, url, description.strip() if description else None, material_type)
        )
        self.connection.commit()
        return cursor.lastrowid

    def get_course_materials(self, course_id):
        """Return all materials for a course, ordered by id."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, title, url, description, material_type, created_at
            FROM course_materials
            WHERE course_id = ?
            ORDER BY id
            """,
            (course_id,)
        )
        return cursor.fetchall()

    def delete_material(self, material_id, course_id):
        """
        Delete a material.  course_id is passed to prevent cross-course deletion.
        """
        cursor = self.connection.cursor()
        cursor.execute(
            "DELETE FROM course_materials WHERE id = ? AND course_id = ?",
            (material_id, course_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("Material not found or does not belong to this course.")
        self.connection.commit()

    def update_material(self, material_id, course_id, title, url,
                        description=None, material_type="link"):
        """Update a material record."""
        title = title.strip() if title else ""
        url = url.strip() if url else ""

        if not title:
            raise ValueError("Material title cannot be empty.")
        if not url:
            raise ValueError("URL cannot be empty.")
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        if material_type not in self.VALID_TYPES:
            material_type = "link"

        cursor = self.connection.cursor()
        cursor.execute(
            """
            UPDATE course_materials
            SET title = ?, url = ?, description = ?, material_type = ?
            WHERE id = ? AND course_id = ?
            """,
            (title, url, description.strip() if description else None,
             material_type, material_id, course_id)
        )
        if cursor.rowcount == 0:
            raise ValueError("Material not found or does not belong to this course.")
        self.connection.commit()
