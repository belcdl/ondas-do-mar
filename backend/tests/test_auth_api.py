import uuid
from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate
from app.services.user import UserService

DEFAULT_PASSWORD = "Sup3rSecret!"


async def _create_user(
    db_session: AsyncSession, *, role: UserRole = UserRole.OWNER, **overrides: object
) -> User:
    service = UserService(UserRepository(db_session))
    payload = {
        "email": f"user-{uuid.uuid4()}@example.com",
        "password": DEFAULT_PASSWORD,
        "full_name": "Test User",
        "role": role,
    }
    payload.update(overrides)
    return await service.create_user(UserCreate(**payload))


async def _create_inactive_user(db_session: AsyncSession, **overrides: object) -> User:
    user = await _create_user(db_session, **overrides)
    user.is_active = False
    db_session.add(user)
    await db_session.commit()
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


async def test_login_success(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _create_user(db_session)
    response = await client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _create_user(db_session)
    response = await client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_login_nonexistent_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login", data={"username": "nobody@example.com", "password": "whatever"}
    )
    assert response.status_code == 401


async def test_login_inactive_user(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _create_inactive_user(db_session)
    response = await client.post(
        "/api/v1/auth/login", data={"username": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 401


async def test_get_me_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_get_me_with_valid_token(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _create_user(db_session)
    response = await client.get("/api/v1/auth/me", headers=_auth_headers(user))
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert "hashed_password" not in body
    assert "password" not in body


async def test_get_me_with_expired_token(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _create_user(db_session)
    expired_token = create_access_token(subject=str(user.id), expires_delta=timedelta(seconds=-1))
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401


async def test_get_me_with_garbage_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


async def test_get_me_inactive_user_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _create_inactive_user(db_session)
    response = await client.get("/api/v1/auth/me", headers=_auth_headers(user))
    assert response.status_code == 401


async def test_logout_requires_token(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401


async def test_logout_with_valid_token(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _create_user(db_session)
    response = await client.post("/api/v1/auth/logout", headers=_auth_headers(user))
    assert response.status_code == 200


async def test_admin_only_allows_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    response = await client.get("/api/v1/auth/admin-only", headers=_auth_headers(admin))
    assert response.status_code == 200


async def test_admin_only_rejects_owner(client: AsyncClient, db_session: AsyncSession) -> None:
    owner_user = await _create_user(db_session, role=UserRole.OWNER)
    response = await client.get("/api/v1/auth/admin-only", headers=_auth_headers(owner_user))
    assert response.status_code == 403


async def test_admin_only_requires_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/admin-only")
    assert response.status_code == 401


async def test_owner_only_allows_owner(client: AsyncClient, db_session: AsyncSession) -> None:
    owner_user = await _create_user(db_session, role=UserRole.OWNER)
    response = await client.get("/api/v1/auth/owner-only", headers=_auth_headers(owner_user))
    assert response.status_code == 200


async def test_owner_only_rejects_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    response = await client.get("/api/v1/auth/owner-only", headers=_auth_headers(admin))
    assert response.status_code == 403


async def test_admin_reset_password_allows_login_with_new_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    user = await _create_user(db_session)

    response = await client.post(
        "/api/v1/auth/admin/reset-password",
        json={"email": user.email, "new_password": "BrandNewPass1!"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 204

    login_response = await client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": "BrandNewPass1!"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"]


async def test_admin_reset_password_invalidates_old_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    user = await _create_user(db_session)

    response = await client.post(
        "/api/v1/auth/admin/reset-password",
        json={"email": user.email, "new_password": "BrandNewPass1!"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 204

    old_password_login = await client.post(
        "/api/v1/auth/login",
        data={"username": user.email, "password": DEFAULT_PASSWORD},
    )
    assert old_password_login.status_code == 401


async def test_admin_reset_password_rejects_non_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_user = await _create_user(db_session, role=UserRole.OWNER)
    target = await _create_user(db_session)

    response = await client.post(
        "/api/v1/auth/admin/reset-password",
        json={"email": target.email, "new_password": "BrandNewPass1!"},
        headers=_auth_headers(owner_user),
    )
    assert response.status_code == 403


async def test_admin_reset_password_requires_token(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/admin/reset-password",
        json={"email": "nobody@example.com", "new_password": "BrandNewPass1!"},
    )
    assert response.status_code == 401


async def test_admin_reset_password_rejects_weak_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    user = await _create_user(db_session)

    response = await client.post(
        "/api/v1/auth/admin/reset-password",
        json={"email": user.email, "new_password": "short"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 422


async def test_admin_reset_password_unknown_email_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _create_user(db_session, role=UserRole.ADMIN)

    response = await client.post(
        "/api/v1/auth/admin/reset-password",
        json={"email": "nobody@example.com", "new_password": "BrandNewPass1!"},
        headers=_auth_headers(admin),
    )
    assert response.status_code == 404
