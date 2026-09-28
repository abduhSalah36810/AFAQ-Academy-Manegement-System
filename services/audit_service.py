class AuditService:
    """
    Lightweight audit trail.
    Records who did what, to which entity, and when.
    Never logs passwords or sensitive credentials.
    """

    def __init__(self, connection):
        self.connection = connection

    def log(self, actor, action: str, entity: str, entity_id=None, detail: str = None):
        """
        Log an auditable action.

        Args:
            actor: user dict from session  {'id': ..., 'name': ..., 'role': ...}
            action: verb string e.g. 'created_user', 'deactivated_course'
            entity: domain noun e.g. 'user', 'course', 'enrollment'
            entity_id: integer PK of the affected entity (optional)
            detail: human-readable summary (optional, no sensitive data)
        """
        try:
            actor_id   = actor.get("id")   if actor else None
            actor_name = actor.get("name") if actor else "system"

            cursor = self.connection.cursor()
            cursor.execute(
                """
                INSERT INTO audit_log
                    (actor_id, actor_name, action, entity, entity_id, detail)
                VALUES
                    (?, ?, ?, ?, ?, ?)
                """,
                (actor_id, actor_name, action, entity, entity_id, detail)
            )
            self.connection.commit()
        except Exception:
            # Audit failure must NEVER break a primary operation
            pass

    def get_recent(self, limit=100):
        """Return recent audit entries, newest first."""
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, actor_name, action, entity, entity_id, detail, timestamp
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,)
        )
        return cursor.fetchall()
