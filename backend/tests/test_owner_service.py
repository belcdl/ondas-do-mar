import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.security import hash_invitation_token
from app.models.owner_invitation import OwnerInvitation
from app.models.user import UserRole
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.user import UserRepository
from app.schemas.owner import OwnerCreate, OwnerUpdate
from app.services.owner import (
    InvitationAlreadyUsedError,
    InvitationExpiredError,
    InvitationNotFoundError,
    OwnerAlreadyOnboardedError,
    OwnerEmailAlreadyExistsError,
    OwnerNotFoundError,
    OwnerService,
)
from app.services.user import UserService


def _owner_service(db_session: AsyncSession) -> OwnerService:
    return OwnerService(
        OwnerRepository(db_session),
        OwnerInvitationRepository(db_session),
        UserRepository(db_session),
    )


async def test_owner_service_lifecycle(db_session: AsyncSession) -> None:
    service = _owner_service(db_session)
    email = f"test-{uuid.uuid4()}@example.com"

    created = await service.create_owner(
        OwnerCreate(full_name="Test Owner", email=email, phone=None)
    )
    assert created.is_active is True

    with pytest.raises(OwnerEmailAlreadyExistsError):
        await service.create_owner(OwnerCreate(full_name="Duplicate", email=email, phone=None))

    fetched = await service.get_owner(created.id)
    assert fetched.email == email

    owners = await service.list_owners()
    assert any(o.id == created.id for o in owners)

    updated = await service.update_owner(created.id, OwnerUpdate(phone="+34123456789"))
    assert updated.phone == "+34123456789"

    deactivated = await service.deactivate_owner(created.id)
    assert deactivated.is_active is False

    active_owners = await service.list_owners()
    assert all(o.id != created.id for o in active_owners)

    with pytest.raises(OwnerNotFoundError):
        await service.get_owner(uuid.uuid4())


async def test_create_owner_full_name_too_long_raises_validation_error(
    db_session: AsyncSession,
) -> None:
    """full_name has no Pydantic max_length, so this exercises the DataError
    -> app ValidationError translation added in Sprint 5.4, not just a 422
    seen from the HTTP layer."""
    service = _owner_service(db_session)
    with pytest.raises(ValidationError):
        await service.create_owner(
            OwnerCreate(full_name="A" * 500, email=f"toolong-{uuid.uuid4()}@example.com")
        )


# --- Owner invitations ---------------------------------------------------------------


async def test_invite_owner_returns_raw_token_and_persists_hash_only(
    db_session: AsyncSession,
) -> None:
    service = _owner_service(db_session)
    owner = await service.create_owner(
        OwnerCreate(full_name="Fresh Owner", email=f"fresh-{uuid.uuid4()}@example.com")
    )

    raw_token, invitation = await service.invite_owner(owner.id)

    assert raw_token
    assert invitation.owner_id == owner.id
    assert invitation.email == owner.email
    assert invitation.used_at is None
    assert invitation.token_hash == hash_invitation_token(raw_token)
    assert invitation.token_hash != raw_token


async def test_invite_already_onboarded_owner_raises(db_session: AsyncSession) -> None:
    service = _owner_service(db_session)
    owner = await service.create_owner(
        OwnerCreate(full_name="Onboarded Owner", email=f"onboarded-{uuid.uuid4()}@example.com")
    )
    _raw_token, _invitation = await service.invite_owner(owner.id)
    await service.accept_invitation(_raw_token, "Sup3rSecret!", "Onboarded Owner")

    with pytest.raises(OwnerAlreadyOnboardedError):
        await service.invite_owner(owner.id)


async def test_accept_invitation_unknown_token_raises(db_session: AsyncSession) -> None:
    service = _owner_service(db_session)
    with pytest.raises(InvitationNotFoundError):
        await service.accept_invitation("not-a-real-token", "Sup3rSecret!", "Nobody")


async def test_accept_invitation_expired_token_raises(db_session: AsyncSession) -> None:
    service = _owner_service(db_session)
    owner = await service.create_owner(
        OwnerCreate(full_name="Expired Owner", email=f"expired-{uuid.uuid4()}@example.com")
    )

    raw_token = "expired-raw-token"
    expired_invitation = OwnerInvitation(
        owner_id=owner.id,
        email=owner.email,
        token_hash=hash_invitation_token(raw_token),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    await OwnerInvitationRepository(db_session).create(expired_invitation)

    with pytest.raises(InvitationExpiredError):
        await service.accept_invitation(raw_token, "Sup3rSecret!", "Expired Owner")


async def test_accept_invitation_already_used_token_raises(db_session: AsyncSession) -> None:
    service = _owner_service(db_session)
    owner = await service.create_owner(
        OwnerCreate(full_name="Used Owner", email=f"used-{uuid.uuid4()}@example.com")
    )
    raw_token, _invitation = await service.invite_owner(owner.id)
    await service.accept_invitation(raw_token, "Sup3rSecret!", "Used Owner")

    with pytest.raises(InvitationAlreadyUsedError):
        await service.accept_invitation(raw_token, "AnotherPassword!", "Used Owner")


async def test_accept_invitation_success(db_session: AsyncSession) -> None:
    service = _owner_service(db_session)
    owner = await service.create_owner(
        OwnerCreate(full_name="Accepting Owner", email=f"accept-{uuid.uuid4()}@example.com")
    )
    raw_token, invitation = await service.invite_owner(owner.id)

    user, access_token = await service.accept_invitation(raw_token, "Sup3rSecret!", "Real Name")

    assert user.email == owner.email
    assert user.full_name == "Real Name"
    assert user.role == UserRole.OWNER

    reloaded_owner = await service.get_owner(owner.id)
    assert reloaded_owner.user_id == user.id

    reloaded_invitation = await OwnerInvitationRepository(db_session).get_by_token_hash(
        invitation.token_hash
    )
    assert reloaded_invitation is not None
    assert reloaded_invitation.used_at is not None

    # The token really authenticates — same mechanism GET /auth/me relies on.
    resolved_user = await UserService(UserRepository(db_session)).get_user_from_token(
        access_token
    )
    assert resolved_user.id == user.id
