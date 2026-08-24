import io
import logging
import uuid

import pytest
from fastapi import UploadFile
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.repositories.apartment import ApartmentRepository
from app.repositories.apartment_photo import ApartmentPhotoRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.user import UserRepository
from app.schemas.apartment import ApartmentCreate
from app.schemas.owner import OwnerCreate
from app.services.apartment import ApartmentService
from app.services.apartment_photo import (
    ApartmentPhotoNotFoundError,
    ApartmentPhotoService,
    InvalidPhotoContentTypeError,
    PhotoTooLargeError,
    TooManyPhotosError,
)
from app.services.owner import OwnerService


def _owner_service(db_session: AsyncSession) -> OwnerService:
    return OwnerService(
        OwnerRepository(db_session),
        OwnerInvitationRepository(db_session),
        UserRepository(db_session),
    )


async def _make_owner(db_session: AsyncSession, **overrides: str | None):
    service = _owner_service(db_session)
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": None,
    }
    payload.update(overrides)
    return await service.create_owner(OwnerCreate(**payload))


async def _make_apartment(db_session: AsyncSession, owner_id: uuid.UUID, **overrides: str):
    service = ApartmentService(ApartmentRepository(db_session), OwnerRepository(db_session))
    payload = {
        "owner_id": owner_id,
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    payload.update(overrides)
    return await service.create_apartment(ApartmentCreate(**payload))


def _apartment_photo_service(db_session: AsyncSession) -> ApartmentPhotoService:
    return ApartmentPhotoService(ApartmentPhotoRepository(db_session))


def _upload_file(
    content: bytes = b"fake-image-bytes",
    content_type: str = "image/jpeg",
    filename: str = "photo.jpg",
) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


class _FakeR2:
    """Records every call made to app.core.storage.upload_photo/delete_photo,
    same approach as test_payment_service.py's _FakeStripeCheckout — no real
    bucket is ever touched."""

    def __init__(self) -> None:
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []
        self.fail_delete = False

    def upload_photo(self, file_bytes: bytes, key: str, content_type: str) -> None:
        self.uploaded.append(
            {"file_bytes": file_bytes, "key": key, "content_type": content_type}
        )

    def delete_photo(self, key: str) -> None:
        if self.fail_delete:
            raise RuntimeError("R2 delete failed")
        self.deleted.append(key)


def _patch_r2(monkeypatch: pytest.MonkeyPatch) -> _FakeR2:
    fake = _FakeR2()
    monkeypatch.setattr("app.core.storage.upload_photo", fake.upload_photo)
    monkeypatch.setattr("app.core.storage.delete_photo", fake.delete_photo)
    return fake


async def test_upload_photo_success(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fake bytes here aren't a decodable image, so this exercises the
    WebP-conversion fallback path: Pillow fails to decode them and the
    original bytes/content_type/extension are kept."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    fake = _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)

    photo = await service.upload_photo(apartment.id, _upload_file())

    assert photo.apartment_id == apartment.id
    assert photo.position == 0
    assert photo.storage_key.startswith(f"apartments/{apartment.id}/")
    assert photo.storage_key.endswith(".jpg")
    assert len(fake.uploaded) == 1
    assert fake.uploaded[0]["key"] == photo.storage_key
    assert fake.uploaded[0]["content_type"] == "image/jpeg"


async def test_upload_photo_converts_real_image_to_webp(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    fake = _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)

    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buffer, format="JPEG")

    photo = await service.upload_photo(apartment.id, _upload_file(content=buffer.getvalue()))

    assert photo.storage_key.endswith(".webp")
    assert fake.uploaded[0]["content_type"] == "image/webp"


async def test_upload_photo_conversion_failure_falls_back_to_original(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    fake = _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)

    with caplog.at_level(logging.WARNING):
        photo = await service.upload_photo(apartment.id, _upload_file())

    assert photo.storage_key.endswith(".jpg")
    assert fake.uploaded[0]["content_type"] == "image/jpeg"
    assert any(
        "WebP" in record.getMessage() and str(apartment.id) in record.getMessage()
        for record in caplog.records
    )


async def test_upload_photo_positions_increment(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)

    first = await service.upload_photo(apartment.id, _upload_file())
    second = await service.upload_photo(apartment.id, _upload_file())

    assert first.position == 0
    assert second.position == 1


async def test_upload_photo_rejects_bad_content_type(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    fake = _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)

    with pytest.raises(InvalidPhotoContentTypeError):
        await service.upload_photo(
            apartment.id, _upload_file(content_type="application/pdf", filename="doc.pdf")
        )

    assert fake.uploaded == []


async def test_upload_photo_rejects_oversized_file(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    fake = _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)

    oversized = b"a" * (8 * 1024 * 1024 + 1)
    with pytest.raises(PhotoTooLargeError):
        await service.upload_photo(apartment.id, _upload_file(content=oversized))

    assert fake.uploaded == []


async def test_upload_photo_rejects_over_limit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)

    for _ in range(20):
        await service.upload_photo(apartment.id, _upload_file())

    with pytest.raises(TooManyPhotosError):
        await service.upload_photo(apartment.id, _upload_file())


async def test_list_photos_ordered_by_position(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)

    first = await service.upload_photo(apartment.id, _upload_file())
    second = await service.upload_photo(apartment.id, _upload_file())

    photos = await service.list_photos(apartment.id)
    assert [p.id for p in photos] == [first.id, second.id]


async def test_delete_photo_success(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    fake = _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)
    photo = await service.upload_photo(apartment.id, _upload_file())

    await service.delete_photo(photo.id)

    assert fake.deleted == [photo.storage_key]
    with pytest.raises(ApartmentPhotoNotFoundError):
        await service.get_photo(photo.id)


async def test_delete_photo_keeps_record_when_r2_delete_fails(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If R2 deletion fails, the DB record must survive — an orphaned bucket
    object is preferable to a record pointing at nothing."""
    owner = await _make_owner(db_session)
    apartment = await _make_apartment(db_session, owner.id)
    fake = _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)
    photo = await service.upload_photo(apartment.id, _upload_file())

    fake.fail_delete = True
    with pytest.raises(RuntimeError):
        await service.delete_photo(photo.id)

    still_there = await service.get_photo(photo.id)
    assert still_there.id == photo.id


async def test_delete_photo_not_found(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_r2(monkeypatch)
    service = _apartment_photo_service(db_session)
    with pytest.raises(ApartmentPhotoNotFoundError):
        await service.delete_photo(uuid.uuid4())
