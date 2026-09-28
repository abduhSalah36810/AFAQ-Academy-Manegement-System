class TraineeService:

    def __init__(self, connection):
        self.connection = connection # انهي داتا بيز 

    def create(self, trainee):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO users (name, email, role)
            VALUES (?, ?, ?)
            """,
            (trainee.name, trainee.email, "trainee")
        )

        self.connection.commit()

    def get_all(self):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT id, name, email
            FROM users
            WHERE role = 'trainee'
            """
        )

        return cursor.fetchall()