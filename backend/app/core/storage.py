"""Local filesystem storage for apartment photos.

Filesystem I/O is synchronous. Callers in async route handlers must not call
these helpers directly on the event loop — either define the route as a
plain `def` (FastAPI runs those in a threadpool automatically) or wrap the
call in `fastapi.concurrency.run_in_threadpool`. See
app/services/apartment_photo.py.
"""

from pathlib import Path

from app.core.config import get_settings


def upload_photo(file_bytes: bytes, key: str, content_type: str) -> None:
    settings = get_settings()
    path = Path(settings.media_root) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(file_bytes)


def delete_photo(key: str) -> None:
    settings = get_settings()
    path = Path(settings.media_root) / key
    path.unlink(missing_ok=True)
