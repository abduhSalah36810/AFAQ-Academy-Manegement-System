"""Configuration helpers for application session signing."""


def get_session_secret(environ=None):
    """Return the configured session-signing secret or fail closed."""
    import os

    values = os.environ if environ is None else environ
    secret = values.get("AFAQ_SECRET_KEY")
    if not isinstance(secret, str) or not secret.strip():
        raise RuntimeError(
            "AFAQ_SECRET_KEY must be configured before the application can start."
        )
    return secret
