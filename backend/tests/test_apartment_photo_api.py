import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from app.repositories.owner import OwnerRepository
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.user import UserService
from tests.conftest import auth_headers_for


async def _create_owner(client: AsyncClient, headers: dict[str, str], **overrides: str) -> dict:
    payload = {
        "full_name": "Test Owner",
        "email": f"owner-{uuid.uuid4()}@example.com",
        "phone": "+34600000000",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/owners", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _create_apartment(
    client: AsyncClient, headers: dict[str, str], owner_id: str, **overrides: str
) -> dict:
    payload = {
        "owner_id": owner_id,
        "name": "Casa Azul",
        "address_line": "Rua da Praia 12",
        "city": "Porto",
        "country": "Portugal",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/apartments", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def _make_owner_with_linked_user(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_headers: dict[str, str],
    **overrides: str,
) -> tuple[dict, dict[str, str]]:
    """Same pattern as test_blocked_date_api.py's helper of the same name."""
    owner = await _create_owner(client, admin_headers, **overrides)
    user = await UserService(UserRepository(db_session)).create_user(
        UserCreate(
            email=f"owner-user-{uuid.uuid4()}@example.com",
            password="Sup3rSecret!",
            full_name="Owner User",
            role=UserRole.OWNER,
        )
    )
    owner_repo = OwnerRepository(db_session)
    owner_obj = await owner_repo.get_by_id(uuid.UUID(owner["id"]))
    assert owner_obj is not None
    owner_obj.user_id = user.id
    db_session.add(owner_obj)
    await db_session.commit()
    return owner, auth_headers_for(user)


class _FakeR2:
    """Records every call made to app.core.storage.upload_photo/delete_photo —
    same approach as test_payment_service.py's _FakeStripeCheckout. No real
    bucket is ever touched."""

    def __init__(self) -> None:
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []

    def upload_photo(self, file_bytes: bytes, key: str, content_type: str) -> None:
        self.uploaded.append(
            {"file_bytes": file_bytes, "key": key, "content_type": content_type}
        )

    def delete_photo(self, key: str) -> None:
        self.deleted.append(key)


@pytest.fixture
def fake_r2(monkeypatch: pytest.MonkeyPatch) -> _FakeR2:
    fake = _FakeR2()
    monkeypatch.setattr("app.core.storage.upload_photo", fake.upload_photo)
    monkeypatch.setattr("app.core.storage.delete_photo", fake.delete_photo)
    return fake


async def _upload_photo(
    client: AsyncClient,
    headers: dict[str, str],
    apartment_id: str,
    *,
    content: bytes = b"fake-image-bytes",
    content_type: str = "image/jpeg",
    filename: str = "photo.jpg",
) -> Response:
    return await client.post(
        f"/api/v1/apartments/{apartment_id}/photos",
        files={"file": (filename, content, content_type)},
        headers=headers,
    )


async def test_upload_apartment_photo(
    client: AsyncClient, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    response = await _upload_photo(client, admin_headers, apartment["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["apartment_id"] == apartment["id"]
    assert body["position"] == 0
    assert uuid.UUID(body["id"])
    assert "url" in body
    assert "storage_key" not in body
    assert len(fake_r2.uploaded) == 1


async def test_upload_apartment_photo_requires_auth(client: AsyncClient) -> None:
    response = await _upload_photo(client, {}, str(uuid.uuid4()))
    assert response.status_code == 401


async def test_upload_apartment_photo_apartment_not_found(
    client: AsyncClient, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    response = await _upload_photo(client, admin_headers, str(uuid.uuid4()))
    assert response.status_code == 404


async def test_upload_apartment_photo_rejects_bad_content_type(
    client: AsyncClient, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    response = await _upload_photo(
        client,
        admin_headers,
        apartment["id"],
        content_type="application/pdf",
        filename="doc.pdf",
    )

    assert response.status_code == 422
    assert fake_r2.uploaded == []


async def test_upload_apartment_photo_rejects_oversized_file(
    client: AsyncClient, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    oversized = b"a" * (8 * 1024 * 1024 + 1)
    response = await _upload_photo(client, admin_headers, apartment["id"], content=oversized)

    assert response.status_code == 422
    assert fake_r2.uploaded == []


async def test_upload_apartment_photo_rejects_over_limit(
    client: AsyncClient, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    for _ in range(20):
        response = await _upload_photo(client, admin_headers, apartment["id"])
        assert response.status_code == 201

    response = await _upload_photo(client, admin_headers, apartment["id"])
    assert response.status_code == 422


async def test_list_apartment_photos_ordered(
    client: AsyncClient, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    first = (await _upload_photo(client, admin_headers, apartment["id"])).json()
    second = (await _upload_photo(client, admin_headers, apartment["id"])).json()

    response = await client.get(
        f"/api/v1/apartments/{apartment['id']}/photos", headers=admin_headers
    )
    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == [first["id"], second["id"]]


async def test_delete_apartment_photo(
    client: AsyncClient, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    owner = await _create_owner(client, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    photo = (await _upload_photo(client, admin_headers, apartment["id"])).json()

    response = await client.delete(
        f"/api/v1/apartments/{apartment['id']}/photos/{photo['id']}", headers=admin_headers
    )
    assert response.status_code == 204
    assert len(fake_r2.deleted) == 1
    assert fake_r2.deleted[0].startswith(f"apartments/{apartment['id']}/")

    list_response = await client.get(
        f"/api/v1/apartments/{apartment['id']}/photos", headers=admin_headers
    )
    assert list_response.json() == []


async def test_delete_apartment_photo_not_found(
    client: AsyncClient, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    response = await client.delete(
        f"/api/v1/apartments/{uuid.uuid4()}/photos/{uuid.uuid4()}", headers=admin_headers
    )
    assert response.status_code == 404


# --- Authorization: owner cannot manage another owner's apartment's photos ---


async def test_owner_cannot_upload_photo_for_other_owners_apartment(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    owner, _owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])

    _other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await _upload_photo(client, other_owner_headers, apartment["id"])
    assert response.status_code == 403


async def test_owner_cannot_delete_other_owners_photo(
    client: AsyncClient, db_session: AsyncSession, admin_headers: dict[str, str], fake_r2: _FakeR2
) -> None:
    owner, owner_headers = await _make_owner_with_linked_user(client, db_session, admin_headers)
    apartment = await _create_apartment(client, admin_headers, owner["id"])
    photo = (await _upload_photo(client, admin_headers, apartment["id"])).json()

    _other_owner, other_owner_headers = await _make_owner_with_linked_user(
        client, db_session, admin_headers
    )

    response = await client.delete(
        f"/api/v1/apartments/{apartment['id']}/photos/{photo['id']}",
        headers=other_owner_headers,
    )
    assert response.status_code == 403

    own_response = await client.delete(
        f"/api/v1/apartments/{apartment['id']}/photos/{photo['id']}",
        headers=owner_headers,
    )
    assert own_response.status_code == 204
