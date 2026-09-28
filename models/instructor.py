from .user import User


class Instructor(User):

    def view_trainees(self):
        print(f"{self.name}'s trainees")