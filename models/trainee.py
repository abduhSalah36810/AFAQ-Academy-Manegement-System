from .user import User


class Trainee(User):

    def view_courses(self):
        print(f"{self.name}'s courses")