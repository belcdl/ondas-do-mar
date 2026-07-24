import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import DataError, IntegrityError

from app.core.config import get_settings
from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError, ValidationError
from app.core.security import (
    create_access_token,
    generate_invitation_token,
    hash_invitation_token,
    hash_password,
)
from app.models.owner import Owner
from app.models.owner_invitation import OwnerInvitation
from app.models.user import User, UserRole
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.user import UserRepository
from app.schemas.owner import OwnerCreate, OwnerUpdate


class OwnerNotFoundError(NotFoundError):
    """Raised when no owner exists for the given id."""


class OwnerEmailAlreadyExistsError(ConflictError):
    """Raised when an email is already registered to a different owner."""


class OwnerAlreadyOnboardedError(ConflictError):
    """Raised when inviting an owner that already has a linked user."""


class InvitationNotFoundError(NotFoundError):
    """Raised when no invitation exists for the given token."""


class InvitationExpiredError(BusinessRuleError):
    """Raised when an invitation's expires_at has passed."""


class InvitationAlreadyUsedError(ConflictError):
    """Raised when an invitation has already been accepted."""


class OwnerService:
    """Business rules for Owner. Delegates all persistence to OwnerRepository.

    Also owns the owner-invitation lifecycle (invite_owner/accept_invitation):
    both touch Owner, User, and OwnerInvitation, so this depends on all three
    repositories — the same multi-repository pattern BookingService already
    uses for Apartment/Owner (see get_booking_service in api/deps.py).
    """

    def __init__(
        self,
        repository: OwnerRepository,
        invitation_repository: OwnerInvitationRepository,
        user_repository: UserRepository,
    ) -> None:
        self.repository = repository
        self.invitation_repository = invitation_repository
        self.user_repository = user_repository

    async def create_owner(self, data: OwnerCreate) -> Owner:
        if await self.repository.get_by_email(data.email) is not None:
            raise OwnerEmailAlreadyExistsError(f"Owner with email {data.email} already exists")

        owner = Owner(full_name=data.full_name, email=data.email, phone=data.phone)
        try:
            return await self.repository.create(owner)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise OwnerEmailAlreadyExistsError(
                f"Owner with email {data.email} already exists"
            ) from exc

    async def get_owner(self, owner_id: uuid.UUID) -> Owner:
        owner = await self.repository.get_by_id(owner_id)
        if owner is None:
            raise OwnerNotFoundError(f"Owner {owner_id} not found")
        return owner

    async def get_owner_for_user(self, user_id: uuid.UUID) -> Owner | None:
        """None is a normal, expected result here (e.g. an admin with no
        linked Owner) — not an error condition."""
        return await self.repository.get_by_user_id(user_id)

    async def list_owners(self, *, include_inactive: bool = False) -> list[Owner]:
        owners = await self.repository.list_all(include_inactive=include_inactive)
        return list(owners)

    async def update_owner(self, owner_id: uuid.UUID, data: OwnerUpdate) -> Owner:
        owner = await self.get_owner(owner_id)

        updates = data.model_dump(exclude_unset=True)
        new_email = updates.get("email")
        if new_email is not None and new_email != owner.email:
            if await self.repository.get_by_email(new_email) is not None:
                raise OwnerEmailAlreadyExistsError(f"Owner with email {new_email} already exists")

        for field, value in updates.items():
            setattr(owner, field, value)

        try:
            return await self.repository.update(owner)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name == "owners_user_id_fkey":
                raise NotFoundError(f"User {owner.user_id} not found") from exc
            if constraint_name == "owners_user_id_key":
                raise ConflictError("This user is already linked to a different owner") from exc
            raise OwnerEmailAlreadyExistsError(
                f"Owner with email {owner.email} already exists"
            ) from exc

    async def deactivate_owner(self, owner_id: uuid.UUID) -> Owner:
        owner = await self.get_owner(owner_id)
        if owner.is_active:
            owner.is_active = False
            owner = await self.repository.update(owner)
        return owner

    async def invite_owner(self, owner_id: uuid.UUID) -> tuple[str, OwnerInvitation]:
        """Generate a one-time invitation for an owner who has no login yet.
        Returns the raw token alongside the persisted row — this is the only
        place the raw token ever exists; only its hash is stored."""
        owner = await self.get_owner(owner_id)
        if owner.user_id is not None:
            raise OwnerAlreadyOnboardedError(f"Owner {owner_id} already has a linked user")

        settings = get_settings()
        raw_token = generate_invitation_token()
        invitation = OwnerInvitation(
            owner_id=owner.id,
            email=owner.email,
            token_hash=hash_invitation_token(raw_token),
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.invitation_token_expire_hours),
        )
        try:
            created = await self.invitation_repository.create(invitation)
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise ConflictError("Could not create invitation") from exc
        return raw_token, created

    async def accept_invitation(
        self, raw_token: str, password: str, full_name: str
    ) -> tuple[User, str]:
        """Redeem an invitation: creates the User, links owner.user_id, and
        marks the invitation used, atomically — if any step fails, nothing
        is left half-applied. Returns the new user plus a fresh access
        token so the owner is logged in immediately after setting their
        password, without a separate login round trip."""
        invitation = await self.invitation_repository.get_by_token_hash(
            hash_invitation_token(raw_token)
        )
        if invitation is None:
            raise InvitationNotFoundError("Invitation not found")
        if invitation.used_at is not None:
            raise InvitationAlreadyUsedError("Invitation has already been used")
        if invitation.expires_at < datetime.now(timezone.utc):
            raise InvitationExpiredError("Invitation has expired")

        owner = await self.get_owner(invitation.owner_id)

        user = User(
            email=invitation.email,
            hashed_password=hash_password(password),
            full_name=full_name,
            role=UserRole.OWNER,
        )
        try:
            user = await self.user_repository.create(user, commit=False)

            owner.user_id = user.id
            await self.repository.update(owner, commit=False)

            invitation.used_at = datetime.now(timezone.utc)
            await self.invitation_repository.mark_used(invitation, commit=False)

            await self.repository.commit()
        except DataError as exc:
            raise ValidationError(
                "One or more fields exceed the maximum allowed length"
            ) from exc
        except IntegrityError as exc:
            raise ConflictError("Could not accept invitation") from exc

        access_token = create_access_token(subject=str(user.id))
        return user, access_token
