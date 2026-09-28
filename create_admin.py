import getpass

from database import create_tables, get_connection
from utils.security import hash_password
from utils.validation import (
    normalize_email,
    is_valid_email,
    is_valid_password,
    validate_name
)


def create_admin():
    create_tables()

    connection = get_connection()

    print("=" * 40)
    print("CREATE ADMIN ACCOUNT")
    print("=" * 40)

    name = input("Admin name: ").strip()
    email = normalize_email(
        input("Admin email: ")
    )
    password = getpass.getpass(
        "Admin password: "
    )

    if not validate_name(name):
        print("Name must contain at least 2 characters.")
        connection.close()
        return

    if not is_valid_email(email):
        print("Invalid email.")
        connection.close()
        return

    if not is_valid_password(password):
        print("Password must be at least 8 characters.")
        connection.close()
        return

    password_hash = hash_password(password)

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO users
                (name, email, password_hash, role)
            VALUES
                (?, ?, ?, ?)
            """,
            (
                name,
                email,
                password_hash,
                "admin"
            )
        )

        connection.commit()

        print("\nAdmin account created successfully.")

    except Exception:
        connection.rollback()
        print("\nCould not create admin.")
        print("The email may already exist.")

    finally:
        connection.close()


if __name__ == "__main__":
    create_admin()

