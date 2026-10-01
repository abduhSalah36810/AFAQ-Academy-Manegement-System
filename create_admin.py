import getpass

from database import create_tables, get_connection
from utils.security import hash_password
from utils.validation import (
    normalize_email,
    is_valid_email,
    is_valid_password,
    check_password_strength,
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
    confirm_password = getpass.getpass(
        "Confirm password: "
    )

    if password != confirm_password:
        print("\nError: Passwords do not match.")
        connection.close()
        return

    if not validate_name(name):
        print("\nError: Name must contain at least 2 characters.")
        connection.close()
        return

    if not is_valid_email(email):
        print("\nError: Invalid email format.")
        connection.close()
        return

    ok, msg = check_password_strength(password)
    if not ok:
        print(f"\nError: Invalid password - {msg}")
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

        print(f"\nAdmin account '{email}' created successfully.")

    except Exception as e:
        connection.rollback()
        print(f"\nCould not create admin. Database error: {e}")

    finally:
        connection.close()


if __name__ == "__main__":
    create_admin()

