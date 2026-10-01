import os
import shutil
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


BASE_DIR = Path(__file__).resolve().parent
DATABASE_NAME = "afaq.db"


def get_db_path() -> str:
    # On Vercel / serverless environments without Turso, fallback to /tmp.
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        tmp_db = Path("/tmp") / DATABASE_NAME
        base_db = BASE_DIR / DATABASE_NAME
        if not tmp_db.exists():
            if base_db.exists():
                shutil.copy2(base_db, tmp_db)
        return str(tmp_db)

    return str(BASE_DIR / DATABASE_NAME)


def get_connection():
    # If Turso Cloud database is configured in .env / environment, use it
    turso_url = os.environ.get("TURSO_DATABASE_URL")
    turso_token = os.environ.get("TURSO_AUTH_TOKEN")

    if turso_url and turso_token:
        # Strip all whitespace, newlines, and surrounding quotes that can cause InvalidHeaderValue
        turso_url = turso_url.strip().strip("'\"").strip()
        turso_token = turso_token.strip().strip("'\"").strip()

        import libsql
        connection = libsql.connect(turso_url, auth_token=turso_token)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
        return connection

    connection = sqlite3.connect(get_db_path())

    # Enable foreign key enforcement in SQLite.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def create_tables():
    connection = get_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
                CHECK (role IN ('trainee', 'instructor', 'admin')),
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            instructor_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            description TEXT,

            FOREIGN KEY (instructor_id)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ── Safe Migrations for Existing Databases ──────────────────────
    cursor = connection.cursor()

    # users.active
    user_cols = [c[1] for c in cursor.execute("PRAGMA table_info(users)").fetchall()]
    if "active" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")

    # courses.active & courses.description
    course_cols = [c[1] for c in cursor.execute("PRAGMA table_info(courses)").fetchall()]
    if "active" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "description" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN description TEXT")

    connection.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            trainee_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,

            PRIMARY KEY (trainee_id, course_id),

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trainee_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('present', 'absent')),

            UNIQUE (trainee_id, course_id, date),

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trainee_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            score REAL NOT NULL
                CHECK (score >= 0 AND score <= 100),

            UNIQUE (trainee_id, course_id),

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE
        )
    """)

    # Indexes for frequently searched columns.
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email
        ON users(email)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_enrollments_trainee
        ON enrollments(trainee_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_enrollments_course
        ON enrollments(course_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_trainee
        ON attendance(trainee_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_grades_trainee
        ON grades(trainee_id)
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS course_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT,
            material_type TEXT NOT NULL DEFAULT 'link'
                CHECK (material_type IN ('link', 'video', 'document', 'github', 'drive', 'other')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),

            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER,
            actor_name TEXT NOT NULL,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            entity_id INTEGER,
            detail TEXT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp
        ON audit_log(timestamp)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_materials_course
        ON course_materials(course_id)
    """)

    connection.commit()
    connection.close()


if __name__ == "__main__":
    create_tables()
    print("Database initialized successfully.")