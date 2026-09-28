
class GradeService:

    def __init__(self, connection):
        self.connection = connection

    def add_grade(
        self,
        trainee_id,
        course_id,
        score
    ):

        if score < 0 or score > 100:
            raise ValueError(
                "Score must be between 0 and 100."
            )

        cursor = self.connection.cursor()

        # Check enrollment
        cursor.execute(
            """
            SELECT 1
            FROM enrollments
            WHERE trainee_id = ?
            AND course_id = ?
            """,
            (
                trainee_id,
                course_id
            )
        )

        enrollment = cursor.fetchone()

        if enrollment is None:
            raise ValueError(
                "Trainee is not enrolled in this course."
            )

        cursor.execute(
            """
            INSERT INTO grades
                (
                    trainee_id,
                    course_id,
                    score
                )
            VALUES
                (?, ?, ?)

            ON CONFLICT (trainee_id, course_id)

            DO UPDATE SET
                score = excluded.score
            """,
            (
                trainee_id,
                course_id,
                score
            )
        )

        self.connection.commit()

    def get_trainee_grades(self, trainee_id):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                courses.name,
                grades.score
            FROM grades

            JOIN courses
                ON grades.course_id = courses.id

            WHERE grades.trainee_id = ?

            ORDER BY courses.name
            """,
            (trainee_id,)
        )

        return cursor.fetchall()

