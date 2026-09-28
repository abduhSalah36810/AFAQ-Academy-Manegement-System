class Session:

    def __init__(self):
        self.user = None

    def login(self, user):
        self.user = user

    def logout(self):
        self.user = None

    def is_authenticated(self):
        return self.user is not None

    def get_user(self):
        return self.user