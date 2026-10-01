import os
import shutil
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


DEFAULT_TURSO_URL = "libsql://afaq-abduh38.aws-eu-west-1.turso.io"
DEFAULT_TURSO_TOKEN = (
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9."
    "eyJhIjoicnciLCJpYXQiOjE3OTA4ODM2MzEsImlkIjoiMDFhMGY4ZmItMTIwMS03ZjNjLWEzMGQtMjU5OTcxYTU3YWI5Iiwia2lkIjoiWFVZelBGdWRyaHY4RXFoZEZJemw1c3lXOWVRUHZqTkVTVXBBWVlxNXF4VSIsInJpZCI6IjlmNDhlYzcyLWJhNTAtNDBlZS1iYWYyLWIyODg2Mjc1MDA0OSJ9."
    "vHzJVfk84RCI39Ab8dl2htIAm3i6u3qJA7EQXsOK6__dOYnRZPVf_h8amqTjDJU8lmORqfN34INSJmK0zaF3AQ"
)

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
    # If explicitly running tests with local test SQLite
    if os.environ.get("SQLITE_DB_PATH"):
        connection = sqlite3.connect(os.environ["SQLITE_DB_PATH"])
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    # If Turso Cloud database is configured in .env / environment or default fallback, use it
    turso_url = os.environ.get("TURSO_DATABASE_URL") or DEFAULT_TURSO_URL
    turso_token = os.environ.get("TURSO_AUTH_TOKEN") or DEFAULT_TURSO_TOKEN

    if turso_url and turso_token:
        # Strip all whitespace, newlines, and surrounding quotes that can cause InvalidHeaderValue
        turso_url = turso_url.strip().strip("'\"").strip()
        turso_token = turso_token.strip().strip("'\"").strip()

        try:
            import libsql
            connection = libsql.connect(turso_url, auth_token=turso_token)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
            except Exception:
                pass
            return connection
        except Exception as e:
            print(f"Warning: Turso connection failed, falling back to local SQLite: {e}")

    connection = sqlite3.connect(get_db_path())
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


# ── Helper to get column names for a table ────────────────────────────────────
def _col_names(cursor, table: str) -> list[str]:
    cursor.execute(f"PRAGMA table_info({table})")
    return [r[1] for r in cursor.fetchall()]


def create_tables():
    connection = get_connection()
    cursor = connection.cursor()

    # ══════════════════════════════════════════════════════════════════════════
    # EXISTING TABLES (kept exactly as-is for backward compatibility)
    # ══════════════════════════════════════════════════════════════════════════

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
                CHECK (status IN ('present', 'absent', 'late', 'excused')),

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

    # ── Safe Migrations for Existing Tables ───────────────────────────────────

    # users: add new columns
    user_cols = _col_names(cursor, "users")
    if "active" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "profile_image_url" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN profile_image_url TEXT")
    if "show_on_public_profile" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN show_on_public_profile INTEGER NOT NULL DEFAULT 0")
    if "public_bio" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN public_bio TEXT")
    if "graduation_status" not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN graduation_status TEXT")

    # courses: add new columns
    course_cols = _col_names(cursor, "courses")
    if "active" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "description" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN description TEXT")
    if "image_url" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN image_url TEXT")
    if "total_sessions" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN total_sessions INTEGER NOT NULL DEFAULT 0")
    if "status" not in course_cols:
        # 'active' field already exists; status mirrors it for richer semantics
        cursor.execute("ALTER TABLE courses ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    if "created_at" not in course_cols:
        # Turso/libsql does not support function expressions as defaults in ALTER TABLE.
        # Use an empty string default; new rows created via INSERT will use datetime('now')
        # from the CREATE TABLE IF NOT EXISTS statement above.
        try:
            cursor.execute("ALTER TABLE courses ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # Column may already exist with a different definition
    if "category" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN category TEXT")
    if "level" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN level TEXT DEFAULT 'beginner'")
    if "language" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN language TEXT DEFAULT 'Arabic'")
    if "price" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN price REAL NOT NULL DEFAULT 0.0")
    if "is_public" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1")
    if "show_price_publicly" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN show_price_publicly INTEGER NOT NULL DEFAULT 0")
    if "prerequisites" not in course_cols:
        cursor.execute("ALTER TABLE courses ADD COLUMN prerequisites TEXT")

    # ══════════════════════════════════════════════════════════════════════════
    # NEW TABLES
    # ══════════════════════════════════════════════════════════════════════════

    # ── Chapters (belong to a course) ─────────────────────────────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),

            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE
        )
    """)

    # ── Batches (cohort of a course, has instructor + capacity) ───────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            instructor_id INTEGER,
            capacity INTEGER NOT NULL DEFAULT 0,
            start_date TEXT,
            end_date TEXT,
            registration_open_date TEXT,
            registration_close_date TEXT,
            registration_cutoff_sessions INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'upcoming'
                CHECK (status IN ('upcoming', 'active', 'completed', 'cancelled')),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),

            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE,

            FOREIGN KEY (instructor_id)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ── Batch Sessions (individual class sessions in a batch) ─────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS batch_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            session_number INTEGER NOT NULL,
            date TEXT,
            start_time TEXT,
            end_time TEXT,
            status TEXT NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned', 'completed', 'cancelled')),
            notes TEXT,
            recording_url TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),

            FOREIGN KEY (batch_id)
                REFERENCES batches(id)
                ON DELETE CASCADE
        )
    """)

    # ── Batch Enrollments (trainee enrolled in a specific batch) ──────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS batch_enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            trainee_id INTEGER NOT NULL,
            enrolled_at TEXT NOT NULL DEFAULT (datetime('now')),
            enrolled_by INTEGER,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'dropped', 'completed')),

            UNIQUE (batch_id, trainee_id),

            FOREIGN KEY (batch_id)
                REFERENCES batches(id)
                ON DELETE CASCADE,

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (enrolled_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ── Enrollment Requests (trainee requests to join a batch) ────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS enrollment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            trainee_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected')),
            trainee_note TEXT,
            admin_note TEXT,
            reviewed_by INTEGER,
            requested_at TEXT NOT NULL DEFAULT (datetime('now')),
            reviewed_at TEXT,

            UNIQUE (batch_id, trainee_id),

            FOREIGN KEY (batch_id)
                REFERENCES batches(id)
                ON DELETE CASCADE,

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (reviewed_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ── Batch Attendance (session-level, replaces course-level for new system) ─
    connection.execute("""
        CREATE TABLE IF NOT EXISTS batch_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            session_id INTEGER,
            trainee_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'absent'
                CHECK (status IN ('present', 'absent', 'late', 'excused')),
            notes TEXT,
            recorded_by INTEGER,
            recorded_at TEXT NOT NULL DEFAULT (datetime('now')),

            UNIQUE (batch_id, trainee_id, date),

            FOREIGN KEY (batch_id)
                REFERENCES batches(id)
                ON DELETE CASCADE,

            FOREIGN KEY (session_id)
                REFERENCES batch_sessions(id)
                ON DELETE SET NULL,

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (recorded_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ── Course Tasks (assignments per chapter) ────────────────────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS course_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            chapter_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            task_type TEXT NOT NULL DEFAULT 'assignment'
                CHECK (task_type IN ('assignment', 'quiz', 'project', 'reading', 'other')),
            due_date TEXT,
            max_score REAL NOT NULL DEFAULT 100,
            is_required INTEGER NOT NULL DEFAULT 1,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),

            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE,

            FOREIGN KEY (chapter_id)
                REFERENCES chapters(id)
                ON DELETE SET NULL
        )
    """)

    # ── Task Submissions (trainee submits a task) ─────────────────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS task_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            trainee_id INTEGER NOT NULL,
            batch_id INTEGER,
            submission_url TEXT,
            submission_text TEXT,
            submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
            status TEXT NOT NULL DEFAULT 'submitted'
                CHECK (status IN ('submitted', 'under_review', 'approved', 'rejected', 'needs_revision')),
            score REAL,
            feedback TEXT,
            reviewed_by INTEGER,
            reviewed_at TEXT,

            UNIQUE (task_id, trainee_id),

            FOREIGN KEY (task_id)
                REFERENCES course_tasks(id)
                ON DELETE CASCADE,

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (batch_id)
                REFERENCES batches(id)
                ON DELETE SET NULL,

            FOREIGN KEY (reviewed_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ── Grading Components (configurable grade breakdown per batch) ────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS grading_components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            weight REAL NOT NULL
                CHECK (weight > 0 AND weight <= 100),
            description TEXT,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),

            FOREIGN KEY (batch_id)
                REFERENCES batches(id)
                ON DELETE CASCADE
        )
    """)

    # ── Component Scores (per trainee per grading component) ──────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS component_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            component_id INTEGER NOT NULL,
            trainee_id INTEGER NOT NULL,
            score REAL NOT NULL
                CHECK (score >= 0 AND score <= 100),
            notes TEXT,
            recorded_by INTEGER,
            recorded_at TEXT NOT NULL DEFAULT (datetime('now')),

            UNIQUE (component_id, trainee_id),

            FOREIGN KEY (component_id)
                REFERENCES grading_components(id)
                ON DELETE CASCADE,

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (recorded_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ── Student Bonuses ───────────────────────────────────────────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS student_bonuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trainee_id INTEGER NOT NULL,
            batch_id INTEGER,
            course_id INTEGER,
            amount REAL NOT NULL
                CHECK (amount > 0),
            reason TEXT NOT NULL,
            awarded_by INTEGER,
            awarded_at TEXT NOT NULL DEFAULT (datetime('now')),

            FOREIGN KEY (trainee_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (batch_id)
                REFERENCES batches(id)
                ON DELETE SET NULL,

            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE SET NULL,

            FOREIGN KEY (awarded_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ── Batches: Safe Migrations ──────────────────────────────────────────────
    batch_cols = _col_names(cursor, "batches")
    if "is_public" not in batch_cols:
        cursor.execute("ALTER TABLE batches ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1")
    if "price" not in batch_cols:
        cursor.execute("ALTER TABLE batches ADD COLUMN price REAL")

    # ── Organization Settings (dynamic content for public homepage) ───────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS organization_settings (
            id INTEGER PRIMARY KEY,
            org_name TEXT NOT NULL DEFAULT 'AFAQ Academy',
            tagline TEXT DEFAULT 'Empowering the Next Generation of Tech Leaders',
            about_text TEXT DEFAULT 'AFAQ Academy provides intensive, cohort-based practical tech education designed to bridge the gap between academic theory and real-world software engineering.',
            approach_text TEXT DEFAULT 'Our learning experience is structured around hands-on tasks, chapter-based mastery, direct mentor evaluation, and live collaborative sessions.',
            email TEXT DEFAULT 'contact@afaq-academy.com',
            phone TEXT DEFAULT '+20 100 000 0000',
            whatsapp TEXT DEFAULT '+20 100 000 0000',
            address TEXT DEFAULT 'Cairo, Egypt',
            working_hours TEXT DEFAULT 'Sunday - Thursday: 9:00 AM - 6:00 PM',
            facebook_url TEXT DEFAULT '',
            instagram_url TEXT DEFAULT '',
            linkedin_url TEXT DEFAULT '',
            youtube_url TEXT DEFAULT '',
            hero_headline TEXT DEFAULT 'Transform Your Tech Career with Structured, Mentor-Led Programs',
            hero_subheadline TEXT DEFAULT 'Join elite cohorts, build real projects, and master in-demand technologies with direct guidance from experienced industry instructors.'
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM organization_settings")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO organization_settings (id, org_name, tagline, email, phone, address)
            VALUES (1, 'AFAQ Academy', 'Empowering the Next Generation of Tech Leaders', 'contact@afaq-academy.com', '+20 100 000 0000', 'Cairo, Egypt')
        """)

    # ── Gallery Items (Graduation, Events, Workshops, Activities) ─────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS gallery_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            image_url TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Graduation'
                CHECK (category IN ('Graduation', 'Courses', 'Events', 'Workshops', 'Activities')),
            caption TEXT,
            display_order INTEGER NOT NULL DEFAULT 0,
            is_visible INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── Testimonials / Student Stories ────────────────────────────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS testimonials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            role_or_course TEXT,
            avatar_url TEXT,
            content TEXT NOT NULL,
            rating INTEGER NOT NULL DEFAULT 5,
            display_order INTEGER NOT NULL DEFAULT 0,
            is_approved INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # ── Contact Messages ──────────────────────────────────────────────────────
    connection.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unread'
                CHECK (status IN ('unread', 'read', 'handled', 'archived')),
            handled_by INTEGER,
            handled_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),

            FOREIGN KEY (handled_by)
                REFERENCES users(id)
                ON DELETE SET NULL
        )
    """)

    # ══════════════════════════════════════════════════════════════════════════
    # INDEXES
    # ══════════════════════════════════════════════════════════════════════════

    # Existing indexes (kept)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_trainee ON enrollments(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_attendance_trainee ON attendance(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_grades_trainee ON grades(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_materials_course ON course_materials(course_id)")

    # New indexes
    connection.execute("CREATE INDEX IF NOT EXISTS idx_batches_course ON batches(course_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_batches_instructor ON batches(instructor_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_batch_sessions_batch ON batch_sessions(batch_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_batch_enroll_batch ON batch_enrollments(batch_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_batch_enroll_trainee ON batch_enrollments(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_enroll_req_batch ON enrollment_requests(batch_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_enroll_req_trainee ON enrollment_requests(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_batch_att_batch ON batch_attendance(batch_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_batch_att_trainee ON batch_attendance(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_chapters_course ON chapters(course_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_course ON course_tasks(course_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_chapter ON course_tasks(chapter_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_submissions_task ON task_submissions(task_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_submissions_trainee ON task_submissions(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_grading_comp_batch ON grading_components(batch_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_comp_scores_component ON component_scores(component_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_comp_scores_trainee ON component_scores(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_bonuses_trainee ON student_bonuses(trainee_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_gallery_visible ON gallery_items(is_visible, display_order)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_testimonials_approved ON testimonials(is_approved, display_order)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_contact_status ON contact_messages(status, created_at)")

    connection.commit()
    connection.close()


if __name__ == "__main__":
    create_tables()
    print("Database initialized successfully.")