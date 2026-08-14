"""Shared Pydantic field validators for schemas across entities."""

import re

_UPPERCASE_RE = re.compile(r"[A-Z]")
_DIGIT_RE = re.compile(r"\d")
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def validate_password_strength(password: str) -> str:
    """Enforce minimum password strength: at least 8 characters, one
    uppercase letter, one digit, and one non-alphanumeric character.

    Raising ValueError here is intentional — Pydantic v2 turns a ValueError
    raised inside a field_validator into a 422 response with the message
    as detail, so callers get a clear, actionable error automatically.
    """
    missing = []
    if len(password) < 8:
        missing.append("be at least 8 characters long")
    if not _UPPERCASE_RE.search(password):
        missing.append("contain at least one uppercase letter")
    if not _DIGIT_RE.search(password):
        missing.append("contain at least one number")
    if not _SPECIAL_RE.search(password):
        missing.append("contain at least one special character")

    if missing:
        raise ValueError("Password must " + ", ".join(missing))

    return password
