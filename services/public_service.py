"""
public_service.py
=================
Handles data queries and mutations for the public-facing organization homepage,
public course details, alumni showcase, gallery, testimonials, and contact inquiries.

Privacy Guarantees:
- Public queries strictly return sanitized DTOs.
- Internal student IDs, emails, phone numbers, payment records, private grades,
  and attendance details are NEVER exposed publicly.
- Only graduates with `show_on_public_profile = 1` appear on the public alumni page.
"""

from datetime import date
import re
from urllib.parse import unquote, urlsplit


class PublicService:

    def __init__(self, connection):
        self.connection = connection

    # ══════════════════════════════════════════════════════════════════════════
    # ORGANIZATION SETTINGS
    # ══════════════════════════════════════════════════════════════════════════

    def get_org_settings(self) -> dict:
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT org_name, tagline, about_text, approach_text,
                   email, phone, whatsapp, address, working_hours,
                   facebook_url, instagram_url, linkedin_url, youtube_url,
                   hero_headline, hero_subheadline
            FROM organization_settings
            WHERE id = 1
        """)
        row = cursor.fetchone()
        if not row:
            return {
                "org_name": "AFAQ Academy",
                "tagline": "Empowering the Next Generation of Tech Leaders",
                "about_text": "AFAQ Academy provides intensive, cohort-based practical tech education designed to bridge the gap between academic theory and real-world software engineering.",
                "approach_text": "Our learning experience is structured around hands-on tasks, chapter-based mastery, direct mentor evaluation, and live collaborative sessions.",
                "email": "contact@afaq-academy.com",
                "phone": "+20 100 000 0000",
                "whatsapp": "+20 100 000 0000",
                "address": "Cairo, Egypt",
                "working_hours": "Sunday - Thursday: 9:00 AM - 6:00 PM",
                "facebook_url": "",
                "instagram_url": "",
                "linkedin_url": "",
                "youtube_url": "",
                "hero_headline": "Transform Your Tech Career with Structured, Mentor-Led Programs",
                "hero_subheadline": "Join elite cohorts, build real projects, and master in-demand technologies with direct guidance from experienced industry instructors.",
            }

        return {
            "org_name": row[0] or "AFAQ Academy",
            "tagline": row[1] or "",
            "about_text": row[2] or "",
            "approach_text": row[3] or "",
            "email": row[4] or "",
            "phone": row[5] or "",
            "whatsapp": row[6] or "",
            "address": row[7] or "",
            "working_hours": row[8] or "",
            "facebook_url": row[9] or "",
            "instagram_url": row[10] or "",
            "linkedin_url": row[11] or "",
            "youtube_url": row[12] or "",
            "hero_headline": row[13] or "",
            "hero_subheadline": row[14] or "",
        }

    def get_public_org_settings(self) -> dict:
        """Return configured organization content after suppressing seeded placeholders."""
        settings = self.get_org_settings()
        defaults = {
            "email": "contact@afaq-academy.com",
            "phone": "+20 100 000 0000",
            "whatsapp": "+20 100 000 0000",
            "address": "Cairo, Egypt",
            "working_hours": "Sunday - Thursday: 9:00 AM - 6:00 PM",
        }
        for field, default in defaults.items():
            if (settings.get(field) or "").strip().casefold() == default.casefold():
                settings[field] = ""

        email = settings.get("email", "").strip()
        settings["email"] = email if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) else ""
        settings["email_href"] = f"mailto:{settings['email']}" if settings["email"] else ""

        for field in ("phone", "whatsapp"):
            value = settings.get(field, "").strip()
            digits = re.sub(r"\D", "", value)
            if (not value or not re.fullmatch(r"[+()0-9 .-]+", value)
                    or len(digits) < 7 or len(digits) > 15):
                settings[field] = ""
                settings[f"{field}_href"] = ""
            elif field == "whatsapp":
                settings[f"{field}_href"] = f"https://wa.me/{digits}" if value.startswith(("+", "00")) else ""
                if not settings[f"{field}_href"]:
                    settings[field] = ""
            else:
                settings[f"{field}_href"] = f"tel:{value}"

        social_links = []
        for field, label in (("facebook_url", "فيسبوك"), ("instagram_url", "إنستغرام"),
                             ("linkedin_url", "لينكدإن"), ("youtube_url", "يوتيوب")):
            value = settings.get(field, "").strip()
            try:
                parsed = urlsplit(value)
                valid = parsed.scheme in ("https", "http") and bool(parsed.hostname)
            except ValueError:
                valid = False
            settings[field] = value if valid else ""
            if valid:
                social_links.append({"label": label, "url": value})
        settings["social_links"] = social_links

        # Avoid presenting seeded English marketing copy as approved Arabic content.
        for field in ("tagline", "about_text", "approach_text", "hero_headline", "hero_subheadline"):
            value = settings.get(field, "").strip()
            if value and not any("\u0600" <= char <= "\u06ff" for char in value):
                settings[field] = ""
        settings["tagline"] = settings["tagline"] or "تعلم منظّم وممارسة عملية في التقنية"
        settings["hero_headline"] = settings["hero_headline"] or "خطوتك القادمة في عالم التقنية تبدأ من هنا"
        settings["hero_subheadline"] = settings["hero_subheadline"] or "مسارات تعليمية تجمع بين المحتوى المنظم والمهام التطبيقية والجلسات التدريبية."
        settings["about_text"] = settings["about_text"] or "في أكاديمية آفاق، نرتب التعلم في فصول متتابعة ونربط المفاهيم بمهام تطبيقية تساعد المتدرب على التقدم خطوة بخطوة."
        settings["approach_text"] = settings["approach_text"] or "يتقدم المتدرب عبر محتوى منظم ومهام عملية وجلسات تدريبية، مع متابعة التقييمات ضمن المنصة."
        settings["org_name"] = settings.get("org_name") or "أكاديمية آفاق"
        return settings

    @staticmethod
    def _public_image_url(value: str | None) -> str:
        value = (value or "").strip()
        decoded_path = unquote(value.split("?", 1)[0])
        if (value.startswith("/static/") and ".." not in decoded_path
                and "\\" not in decoded_path):
            return value
        try:
            parsed = urlsplit(value)
            if parsed.scheme in ("https", "http") and parsed.hostname:
                return value
        except ValueError:
            pass
        return ""

    def update_org_settings(self, **kwargs):
        allowed = {
            "org_name", "tagline", "about_text", "approach_text",
            "email", "phone", "whatsapp", "address", "working_hours",
            "facebook_url", "instagram_url", "linkedin_url", "youtube_url",
            "hero_headline", "hero_subheadline"
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return

        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        params = list(fields.values())

        cursor = self.connection.cursor()
        cursor.execute("SELECT id FROM organization_settings WHERE id = 1")
        if cursor.fetchone():
            cursor.execute(f"UPDATE organization_settings SET {set_clause} WHERE id = 1", params)
        else:
            cols = ", ".join(["id"] + list(fields.keys()))
            placeholders = ", ".join(["?"] * (len(fields) + 1))
            cursor.execute(f"INSERT INTO organization_settings ({cols}) VALUES ({placeholders})", [1] + params)
        self.connection.commit()

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC STATISTICS (Real, calculated from DB)
    # ══════════════════════════════════════════════════════════════════════════

    def get_public_stats(self) -> dict:
        cursor = self.connection.cursor()

        # Total active courses
        cursor.execute("SELECT COUNT(*) FROM courses WHERE active = 1 AND is_public = 1")
        active_courses = cursor.fetchone()[0]

        # Total batches (completed + active + upcoming)
        cursor.execute("SELECT COUNT(*) FROM batches WHERE status != 'cancelled'")
        total_batches = cursor.fetchone()[0]

        # Total completed batches
        cursor.execute("SELECT COUNT(*) FROM batches WHERE status = 'completed'")
        completed_batches = cursor.fetchone()[0]

        # Total active instructors
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'instructor' AND active = 1")
        instructors_count = cursor.fetchone()[0]

        # Total students enrolled across cohorts
        cursor.execute("SELECT COUNT(DISTINCT trainee_id) FROM batch_enrollments")
        total_students = cursor.fetchone()[0]

        # Total verified graduates
        cursor.execute("""
            SELECT COUNT(DISTINCT trainee_id)
            FROM batch_enrollments
            WHERE status = 'completed'
        """)
        graduates_count = cursor.fetchone()[0]

        return {
            "active_courses": active_courses,
            "total_batches": total_batches,
            "completed_batches": completed_batches,
            "instructors_count": instructors_count,
            "total_students": total_students,
            "graduates_count": graduates_count,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # PUBLIC COURSES & DETAILS
    # ══════════════════════════════════════════════════════════════════════════

    def get_featured_courses(self) -> list[dict]:
        """
        Return public active courses with chapter counts and open batches.
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.image_url,
                   c.category, c.level, c.language, c.total_sessions,
                   c.price, c.show_price_publicly,
                   u.name AS instructor_name,
                   (SELECT COUNT(*) FROM chapters ch WHERE ch.course_id = c.id) AS chapter_count,
                   (SELECT COUNT(*) FROM batches b
                    WHERE b.course_id = c.id
                    AND b.status IN ('upcoming', 'active')
                    AND b.is_public = 1
                    AND ((b.status = 'upcoming' AND (b.start_date IS NULL OR b.start_date = '' OR date(b.start_date) >= date('now')))
                      OR (b.status = 'active' AND (b.start_date IS NULL OR b.start_date = '' OR date(b.start_date) <= date('now'))
                                              AND (b.end_date IS NULL OR b.end_date = '' OR date(b.end_date) >= date('now'))))) AS open_batches_count
            FROM courses c
            LEFT JOIN users u ON c.instructor_id = u.id
            WHERE c.active = 1 AND c.is_public = 1
            ORDER BY c.id ASC
        """)
        rows = cursor.fetchall()
        courses = []
        for r in rows:
            courses.append({
                "id": r[0],
                "name": r[1],
                "description": r[2] or "",
                "image_url": self._public_image_url(r[3]),
                "category": r[4] or "",
                "level": r[5] or "",
                "language": r[6] or "",
                "total_sessions": r[7] or 0,
                "price": r[8] if r[9] == 1 else None,
                "instructor_name": r[10] or "",
                "chapter_count": r[11] or 0,
                "open_batches_count": r[12] or 0,
            })
        return courses

    def get_course_details(self, course_id: int) -> dict | None:
        """
        Public course details including syllabus chapters and open batches.
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT c.id, c.name, c.description, c.image_url,
                   c.category, c.level, c.language, c.total_sessions,
                   c.price, c.show_price_publicly, c.prerequisites,
                   u.name AS instructor_name
            FROM courses c
            LEFT JOIN users u ON c.instructor_id = u.id
            WHERE c.id = ? AND c.active = 1 AND c.is_public = 1
        """, (course_id,))
        c = cursor.fetchone()
        if not c:
            return None

        # Fetch chapters & task counts
        cursor.execute("""
            SELECT ch.id, ch.title, ch.description, ch.order_index,
                   (SELECT COUNT(*) FROM course_tasks ct WHERE ct.chapter_id = ch.id) AS task_count
            FROM chapters ch
            WHERE ch.course_id = ?
            ORDER BY ch.order_index ASC, ch.id ASC
        """, (course_id,))
        chapters = [{
            "id": row[0],
            "title": row[1],
            "description": row[2] or "",
            "order_index": row[3],
            "task_count": row[4],
        } for row in cursor.fetchall()]

        # Fetch open / upcoming batches
        cursor.execute("""
            SELECT b.id, b.name, b.capacity, b.start_date, b.end_date,
                   b.status, b.registration_cutoff_sessions, b.notes,
                   u.name AS instructor_name,
                   (SELECT COUNT(*) FROM batch_enrollments be
                    WHERE be.batch_id = b.id AND be.status = 'active') AS enrolled_count,
                   (SELECT COUNT(*) FROM batch_sessions bs
                    WHERE bs.batch_id = b.id AND bs.status = 'completed') AS completed_sessions
            FROM batches b
            LEFT JOIN users u ON b.instructor_id = u.id
            WHERE b.course_id = ?
            AND b.status IN ('upcoming', 'active')
            AND b.is_public = 1
            AND ((b.status = 'upcoming' AND (b.start_date IS NULL OR b.start_date = '' OR date(b.start_date) >= date('now')))
              OR (b.status = 'active' AND (b.start_date IS NULL OR b.start_date = '' OR date(b.start_date) <= date('now'))
                                      AND (b.end_date IS NULL OR b.end_date = '' OR date(b.end_date) >= date('now'))))
            ORDER BY b.start_date ASC
        """, (course_id,))
        batches = []
        for b in cursor.fetchall():
            capacity = b[2]
            enrolled = b[9]
            cutoff = b[6]
            completed_s = b[10]

            is_open = True
            close_reason = None
            if capacity > 0 and enrolled >= capacity:
                is_open = False
                close_reason = "اكتمل العدد المتاح"
            elif cutoff > 0 and completed_s >= cutoff:
                is_open = False
                close_reason = "أُغلق التسجيل لبدء الجلسات"

            batches.append({
                "id": b[0],
                "name": b[1],
                "start_date": b[3] or "لم يُحدد بعد",
                "end_date": b[4] or "",
                "status": b[5],
                "instructor_name": b[8] or c[11] or "",
                "is_open": is_open,
                "close_reason": close_reason,
            })

        return {
            "id": c[0],
            "name": c[1],
            "description": c[2] or "",
            "image_url": self._public_image_url(c[3]),
            "category": c[4] or "",
            "level": c[5] or "",
            "language": c[6] or "",
            "total_sessions": c[7] or 0,
            "price": c[8] if c[9] == 1 else None,
            "prerequisites": c[10] or "",
            "instructor_name": c[11] or "",
            "chapters": chapters,
            "batches": batches,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # UPCOMING BATCHES
    # ══════════════════════════════════════════════════════════════════════════

    def get_upcoming_batches(self, limit: int = 6) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT b.id, b.name, b.course_id, c.name AS course_name,
                   c.image_url AS course_image_url,
                   b.capacity, b.start_date, b.end_date, b.status,
                   b.registration_cutoff_sessions,
                   u.name AS instructor_name,
                   (SELECT COUNT(*) FROM batch_enrollments be
                    WHERE be.batch_id = b.id AND be.status = 'active') AS enrolled_count,
                   (SELECT COUNT(*) FROM batch_sessions bs
                    WHERE bs.batch_id = b.id AND bs.status = 'completed') AS completed_sessions
            FROM batches b
            JOIN courses c ON b.course_id = c.id
            LEFT JOIN users u ON b.instructor_id = u.id
            WHERE b.status IN ('upcoming', 'active')
            AND b.is_public = 1
            AND c.active = 1 AND c.is_public = 1
            AND ((b.status = 'upcoming' AND (b.start_date IS NULL OR b.start_date = '' OR date(b.start_date) >= date('now')))
              OR (b.status = 'active' AND (b.start_date IS NULL OR b.start_date = '' OR date(b.start_date) <= date('now'))
                                      AND (b.end_date IS NULL OR b.end_date = '' OR date(b.end_date) >= date('now'))))
            ORDER BY b.start_date ASC
            LIMIT ?
        """, (limit,))
        batches = []
        for b in cursor.fetchall():
            capacity = b[5]
            enrolled = b[11]
            cutoff = b[9]
            completed_s = b[12]

            is_open = True
            if capacity > 0 and enrolled >= capacity:
                is_open = False
            elif cutoff > 0 and completed_s >= cutoff:
                is_open = False

            batches.append({
                "id": b[0],
                "name": b[1],
                "course_id": b[2],
                "course_name": b[3],
                "course_image_url": self._public_image_url(b[4]),
                "start_date": b[6] or "لم يُحدد بعد",
                "end_date": b[7] or "",
                "status": b[8],
                "instructor_name": b[10] or "",
                "is_open": is_open,
                "display_status": "جارية" if b[8] == "active" else ("التسجيل مفتوح" if is_open else "التسجيل مغلق"),
            })
        return batches

    # ══════════════════════════════════════════════════════════════════════════
    # COMPLETED COURSES & BATCHES
    # ══════════════════════════════════════════════════════════════════════════

    def get_completed_batches(self, limit: int = 6) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT b.id, b.name, b.course_id, c.name AS course_name,
                   c.image_url AS course_image_url,
                   b.start_date, b.end_date,
                   u.name AS instructor_name
            FROM batches b
            JOIN courses c ON b.course_id = c.id
            LEFT JOIN users u ON b.instructor_id = u.id
            WHERE (b.status = 'completed' OR (b.end_date IS NOT NULL AND b.end_date != '' AND b.end_date < date('now')))
            AND b.status != 'cancelled'
            AND b.is_public = 1
            AND c.active = 1 AND c.is_public = 1
            ORDER BY b.end_date DESC
            LIMIT ?
        """, (limit,))
        completed = []
        for r in cursor.fetchall():
            completed.append({
                "id": r[0],
                "batch_name": r[1],
                "course_id": r[2],
                "course_name": r[3],
                "course_image_url": self._public_image_url(r[4]),
                "start_date": r[5] or "",
                "end_date": r[6] or "مكتملة",
                "instructor_name": r[7] or "",
            })
        return completed

    # ══════════════════════════════════════════════════════════════════════════
    # GRADUATES / ALUMNI (Strictly Privacy-Safe)
    # ══════════════════════════════════════════════════════════════════════════

    def get_public_graduates(self, limit: int = 8) -> list[dict]:
        """
        Return public graduate profiles.
        ONLY returns users who have show_on_public_profile = 1.
        NEVER returns private emails, phones, or grades.
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT u.name, u.profile_image_url, u.public_bio, u.graduation_status,
                   (SELECT c.name FROM batch_enrollments be
                    JOIN batches b ON b.id = be.batch_id JOIN courses c ON c.id = b.course_id
                    WHERE be.trainee_id = u.id AND LOWER(be.status) = 'completed'
                      AND (b.status = 'completed' OR (b.end_date IS NOT NULL AND b.end_date != '' AND date(b.end_date) < date('now')))
                      AND b.is_public = 1 AND b.status != 'cancelled' AND c.active = 1 AND c.is_public = 1
                    ORDER BY COALESCE(b.end_date, '') DESC LIMIT 1) AS course_name,
                   (SELECT b.name FROM batch_enrollments be
                    JOIN batches b ON b.id = be.batch_id JOIN courses c ON c.id = b.course_id
                    WHERE be.trainee_id = u.id AND LOWER(be.status) = 'completed'
                      AND (b.status = 'completed' OR (b.end_date IS NOT NULL AND b.end_date != '' AND date(b.end_date) < date('now')))
                      AND b.is_public = 1 AND b.status != 'cancelled' AND c.active = 1 AND c.is_public = 1
                    ORDER BY COALESCE(b.end_date, '') DESC LIMIT 1) AS batch_name
            FROM users u
            WHERE u.role = 'trainee' AND u.active = 1 AND u.show_on_public_profile = 1
              AND LOWER(COALESCE(u.graduation_status, '')) IN ('graduate', 'graduated', 'alumni', 'completed')
              AND EXISTS (SELECT 1 FROM batch_enrollments be
                    JOIN batches b ON b.id = be.batch_id JOIN courses c ON c.id = b.course_id
                    WHERE be.trainee_id = u.id AND LOWER(be.status) = 'completed'
                      AND (b.status = 'completed' OR (b.end_date IS NOT NULL AND b.end_date != '' AND date(b.end_date) < date('now')))
                      AND b.is_public = 1 AND b.status != 'cancelled' AND c.active = 1 AND c.is_public = 1)
            ORDER BY u.id DESC LIMIT ?
        """, (limit,))
        graduates = []
        for r in cursor.fetchall():
            graduates.append({
                "name": r[0],
                "profile_image_url": self._public_image_url(r[1]),
                "bio": r[2] or "",
                "status": r[3] or "",
                "course_name": r[4] or "",
                "batch_name": r[5] or "",
            })
        return graduates

    # ══════════════════════════════════════════════════════════════════════════
    # GALLERY
    # ══════════════════════════════════════════════════════════════════════════

    def get_public_gallery(self, category: str | None = None, limit: int = 12) -> list[dict]:
        cursor = self.connection.cursor()
        query = """
            SELECT id, title, image_url, category, caption, display_order
            FROM gallery_items
            WHERE is_visible = 1
        """
        params = []
        if category and category.lower() != "all":
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY display_order ASC, id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        items = []
        for r in cursor.fetchall():
            image_url = self._public_image_url(r[2])
            if not image_url:
                continue
            items.append({
                "id": r[0],
                "title": r[1],
                "image_url": image_url,
                "category": {"Graduation": "التخرج", "Courses": "الدورات", "Events": "الفعاليات",
                             "Workshops": "ورش العمل", "Activities": "الأنشطة"}.get(r[3], ""),
                "caption": r[4] or "",
                "display_order": r[5],
            })
        return items

    def add_gallery_item(self, title: str, image_url: str, category: str = "Graduation",
                         caption: str = "", display_order: int = 0, is_visible: bool = True) -> int:
        title = title.strip()
        image_url = image_url.strip()
        if not title:
            raise ValueError("Gallery item title cannot be empty.")
        if not image_url:
            raise ValueError("Gallery image URL cannot be empty.")

        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO gallery_items (title, image_url, category, caption, display_order, is_visible)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, image_url, category, caption.strip() or None, display_order, 1 if is_visible else 0))
        self.connection.commit()
        return cursor.lastrowid

    def delete_gallery_item(self, item_id: int):
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM gallery_items WHERE id = ?", (item_id,))
        self.connection.commit()

    def get_all_gallery_items(self) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT id, title, image_url, category, caption, display_order, is_visible, created_at
            FROM gallery_items
            ORDER BY display_order ASC, id DESC
        """)
        return [{
            "id": r[0], "title": r[1], "image_url": r[2], "category": r[3],
            "caption": r[4] or "", "display_order": r[5], "is_visible": r[6] == 1,
            "created_at": r[7]
        } for r in cursor.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # TESTIMONIALS
    # ══════════════════════════════════════════════════════════════════════════

    def get_public_testimonials(self, limit: int = 6) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT id, student_name, role_or_course, avatar_url, content, rating
            FROM testimonials
            WHERE is_approved = 1
            ORDER BY display_order ASC, id DESC
            LIMIT ?
        """, (limit,))
        return [{
            "id": r[0],
            "student_name": r[1],
            "role_or_course": r[2] or "",
            "avatar_url": r[3] or "",
            "content": r[4],
            "rating": r[5],
        } for r in cursor.fetchall()]

    def add_testimonial(self, student_name: str, content: str, role_or_course: str = "",
                        avatar_url: str = "", rating: int = 5, is_approved: bool = True) -> int:
        student_name = student_name.strip()
        content = content.strip()
        if not student_name:
            raise ValueError("Student name cannot be empty.")
        if not content:
            raise ValueError("Testimonial content cannot be empty.")

        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO testimonials (student_name, role_or_course, avatar_url, content, rating, is_approved)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (student_name, role_or_course.strip() or None, avatar_url.strip() or None,
              content, max(1, min(5, rating)), 1 if is_approved else 0))
        self.connection.commit()
        return cursor.lastrowid

    def delete_testimonial(self, testimonial_id: int):
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM testimonials WHERE id = ?", (testimonial_id,))
        self.connection.commit()

    def get_all_testimonials(self) -> list[dict]:
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT id, student_name, role_or_course, avatar_url, content, rating, is_approved, created_at
            FROM testimonials
            ORDER BY display_order ASC, id DESC
        """)
        return [{
            "id": r[0], "student_name": r[1], "role_or_course": r[2] or "",
            "avatar_url": r[3] or "", "content": r[4], "rating": r[5],
            "is_approved": r[6] == 1, "created_at": r[7]
        } for r in cursor.fetchall()]

    # ══════════════════════════════════════════════════════════════════════════
    # CONTACT MESSAGES
    # ══════════════════════════════════════════════════════════════════════════

    def submit_contact_message(self, name: str, email: str, subject: str, message: str, phone: str = "") -> int:
        name = name.strip() if name else ""
        email = email.strip().lower() if email else ""
        subject = subject.strip() if subject else ""
        message = message.strip() if message else ""

        if not name or len(name) < 2:
            raise ValueError("Name must be at least 2 characters long.")
        if not email or "@" not in email or "." not in email:
            raise ValueError("Please provide a valid email address.")
        if not subject or len(subject) < 3:
            raise ValueError("Subject must be at least 3 characters long.")
        if not message or len(message) < 10:
            raise ValueError("Message must be at least 10 characters long.")

        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO contact_messages (name, email, phone, subject, message)
            VALUES (?, ?, ?, ?, ?)
        """, (name, email, phone.strip() or None, subject, message))
        self.connection.commit()
        return cursor.lastrowid

    def get_contact_messages(self, status: str | None = None) -> list[dict]:
        cursor = self.connection.cursor()
        query = """
            SELECT cm.id, cm.name, cm.email, cm.phone, cm.subject, cm.message,
                   cm.status, cm.handled_at, cm.created_at, u.name AS handler_name
            FROM contact_messages cm
            LEFT JOIN users u ON cm.handled_by = u.id
        """
        params = []
        if status:
            query += " WHERE cm.status = ?"
            params.append(status)
        query += " ORDER BY cm.created_at DESC"
        cursor.execute(query, params)
        return [{
            "id": r[0], "name": r[1], "email": r[2], "phone": r[3] or "—",
            "subject": r[4], "message": r[5], "status": r[6],
            "handled_at": r[7], "created_at": r[8], "handler_name": r[9] or ""
        } for r in cursor.fetchall()]

    def update_contact_message_status(self, message_id: int, status: str, handled_by: int | None = None):
        valid = {"unread", "read", "handled", "archived"}
        if status not in valid:
            raise ValueError(f"Invalid status. Must be one of: {valid}")

        cursor = self.connection.cursor()
        cursor.execute("""
            UPDATE contact_messages
            SET status = ?, handled_by = COALESCE(?, handled_by),
                handled_at = CASE WHEN ? = 'handled' THEN datetime('now') ELSE handled_at END
            WHERE id = ?
        """, (status, handled_by, status, message_id))
        self.connection.commit()

    def delete_contact_message(self, message_id: int):
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM contact_messages WHERE id = ?", (message_id,))
        self.connection.commit()
