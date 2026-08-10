"""Cloudflare R2 object storage client (S3-compatible API via boto3).

boto3 is synchronous. Callers in async route handlers must not call these
helpers directly on the event loop — either define the route as a plain
`def` (FastAPI runs those in a threadpool automatically) or wrap the call in
`fastapi.concurrency.run_in_threadpool`. See app/services/apartment_photo.py.
"""

import boto3
from botocore.client import BaseClient

from app.core.config import get_settings


def get_s3_client() -> BaseClient:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def upload_photo(file_bytes: bytes, key: str, content_type: str) -> None:
    settings = get_settings()
    client = get_s3_client()
    client.put_object(
        Bucket=settings.r2_bucket_name,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )


def delete_photo(key: str) -> None:
    settings = get_settings()
    client = get_s3_client()
    client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
