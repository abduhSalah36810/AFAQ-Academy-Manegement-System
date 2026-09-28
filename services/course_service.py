class CourseService:

    def __init__(self, connection):
        self.connection = connection

    def create(self, name, instructor_id=None, description=None):
        name = name.strip()
        if not name:
            raise ValueError("Course name cannot be empty.")

        cursor = self.connection.cursor()

        if instructor_id:
            cursor.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'instructor' AND active = 1",
                (instructor_id,)
            )
            if cursor.fetchone() is None:
                raise ValueError("Selected instructor does not exist or is inactive.")

        cursor.execute(
            """
            INSERT INTO courses
                (name, instructor_id, active, description)
            VALUES
                (?, ?, 1, ?)
            """,
            (
                name,
                instructor_id,
                description.strip() if description else None
            )
        )

        self.connection.commit()
        return cursor.lastrowid

    def get_all(self, include_archived=True):
        cursor = self.connection.cursor()

        query = """
            SELECT
                courses.id,
                courses.name,
                users.name,
                courses.active,
                courses.description,
                courses.instructor_id
            FROM courses
            LEFT JOIN users
                ON courses.instructor_id = users.id
        """
        if not include_archived:
            query += " WHERE courses.active = 1"

        query += " ORDER BY courses.id"

        cursor.execute(query)
        return cursor.fetchall()

    def get_active_courses(self):
        return self.get_all(include_archived=False)

    def get_by_id(self, course_id):
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT
                courses.id,
                courses.name,
                users.name,
                courses.active,
                courses.description,
                courses.instructor_id
            FROM courses
            LEFT JOIN users
                ON courses.instructor_id = users.id
            WHERE courses.id = ?
            """,
            (course_id,)
        )
        return cursor.fetchone()

    def update(self, course_id, name, description=None, instructor_id=None):
        name = name.strip()
        if not name:
            raise ValueError("Course name cannot be empty.")

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM courses WHERE id = ?", (course_id,))
        if cursor.fetchone() is None:
            raise ValueError("Course not found.")

        if instructor_id:
            cursor.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'instructor' AND active = 1",
                (instructor_id,)
            )
            if cursor.fetchone() is None:
                raise ValueError("Selected instructor does not exist or is inactive.")

        cursor.execute(
            """
            UPDATE courses
            SET name = ?, description = ?, instructor_id = ?
            WHERE id = ?
            """,
            (
                name,
                description.strip() if description else None,
                instructor_id,
                course_id
            )
        )
        self.connection.commit()

    def archive_course(self, course_id):
        cursor = self.connection.cursor()
        cursor.execute("UPDATE courses SET active = 0 WHERE id = ?", (course_id,))
        self.connection.commit()

    def reactivate_course(self, course_id):
        cursor = self.connection.cursor()
        cursor.execute("UPDATE courses SET active = 1 WHERE id = ?", (course_id,))
        self.connection.commit()

    def get_instructor_courses(self, instructor_id):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT id, name
            FROM courses
            WHERE instructor_id = ?
            AND active = 1
            ORDER BY name
            """,
            (instructor_id,)
        )

        return cursor.fetchall()