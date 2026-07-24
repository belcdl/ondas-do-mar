import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def generate_invitation_token() -> str:
    """High-entropy raw token, shown to the caller exactly once."""
    return secrets.token_urlsafe(32)


def hash_invitation_token(raw_token: str) -> str:
    """SHA-256 hex digest, not bcrypt: unlike a password, this token already
    has enough entropy (32 random bytes) that a fast deterministic hash is
    fine — and necessary, since accepting an invitation needs an exact
    lookup by hash, which a salted bcrypt hash can't do."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
