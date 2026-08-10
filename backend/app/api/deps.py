import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import PermissionDeniedError
from app.db.session import get_db
from app.models.apartment import Apartment
from app.models.apartment_photo import ApartmentPhoto
from app.models.blocked_date import BlockedDate
from app.models.booking import Booking
from app.models.owner import Owner
from app.models.rate_rule import RateRule
from app.models.user import User, UserRole
from app.repositories.apartment import ApartmentRepository
from app.repositories.apartment_photo import ApartmentPhotoRepository
from app.repositories.blocked_date import BlockedDateRepository
from app.repositories.booking import BookingRepository
from app.repositories.owner import OwnerRepository
from app.repositories.owner_invitation import OwnerInvitationRepository
from app.repositories.payment import PaymentRepository
from app.repositories.rate_rule import RateRuleRepository
from app.repositories.user import UserRepository
from app.services.apartment import ApartmentService
from app.services.apartment_photo import ApartmentPhotoService
from app.services.availability import AvailabilityService
from app.services.blocked_date import BlockedDateService
from app.services.booking import BookingService
from app.services.owner import OwnerService
from app.services.payment import PaymentService
from app.services.rate_rule import RateRuleService
from app.services.user import AuthenticationError, UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{get_settings().api_v1_str}/auth/login")


def get_owner_repository(db: AsyncSession = Depends(get_db)) -> OwnerRepository:
    return OwnerRepository(db)


def get_owner_invitation_repository(
    db: AsyncSession = Depends(get_db),
) -> OwnerInvitationRepository:
    return OwnerInvitationRepository(db)


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_owner_service(
    repository: OwnerRepository = Depends(get_owner_repository),
    invitation_repository: OwnerInvitationRepository = Depends(get_owner_invitation_repository),
    user_repository: UserRepository = Depends(get_user_repository),
) -> OwnerService:
    return OwnerService(repository, invitation_repository, user_repository)


def get_apartment_repository(db: AsyncSession = Depends(get_db)) -> ApartmentRepository:
    return ApartmentRepository(db)


def get_apartment_service(
    repository: ApartmentRepository = Depends(get_apartment_repository),
    owner_repository: OwnerRepository = Depends(get_owner_repository),
) -> ApartmentService:
    return ApartmentService(repository, owner_repository)


def get_booking_repository(db: AsyncSession = Depends(get_db)) -> BookingRepository:
    return BookingRepository(db)


def get_rate_rule_repository(db: AsyncSession = Depends(get_db)) -> RateRuleRepository:
    return RateRuleRepository(db)


def get_rate_rule_service(
    repository: RateRuleRepository = Depends(get_rate_rule_repository),
    booking_repository: BookingRepository = Depends(get_booking_repository),
) -> RateRuleService:
    return RateRuleService(repository, booking_repository)


def get_blocked_date_repository(db: AsyncSession = Depends(get_db)) -> BlockedDateRepository:
    return BlockedDateRepository(db)


def get_blocked_date_service(
    repository: BlockedDateRepository = Depends(get_blocked_date_repository),
) -> BlockedDateService:
    return BlockedDateService(repository)


def get_apartment_photo_repository(
    db: AsyncSession = Depends(get_db),
) -> ApartmentPhotoRepository:
    return ApartmentPhotoRepository(db)


def get_apartment_photo_service(
    repository: ApartmentPhotoRepository = Depends(get_apartment_photo_repository),
) -> ApartmentPhotoService:
    return ApartmentPhotoService(repository)


def get_availability_service(
    apartment_repository: ApartmentRepository = Depends(get_apartment_repository),
    booking_repository: BookingRepository = Depends(get_booking_repository),
    blocked_date_repository: BlockedDateRepository = Depends(get_blocked_date_repository),
    rate_rule_service: RateRuleService = Depends(get_rate_rule_service),
) -> AvailabilityService:
    return AvailabilityService(
        apartment_repository, booking_repository, blocked_date_repository, rate_rule_service
    )


def get_booking_service(
    repository: BookingRepository = Depends(get_booking_repository),
    apartment_repository: ApartmentRepository = Depends(get_apartment_repository),
    owner_repository: OwnerRepository = Depends(get_owner_repository),
    rate_rule_service: RateRuleService = Depends(get_rate_rule_service),
) -> BookingService:
    return BookingService(repository, apartment_repository, owner_repository, rate_rule_service)


def get_payment_repository(db: AsyncSession = Depends(get_db)) -> PaymentRepository:
    return PaymentRepository(db)


def get_payment_service(
    repository: PaymentRepository = Depends(get_payment_repository),
    apartment_repository: ApartmentRepository = Depends(get_apartment_repository),
    booking_service: BookingService = Depends(get_booking_service),
) -> PaymentService:
    return PaymentService(repository, apartment_repository, booking_service)


def get_user_service(repository: UserRepository = Depends(get_user_repository)) -> UserService:
    return UserService(repository)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.get_user_from_token(token)


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise AuthenticationError("User is inactive")
    return current_user


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise PermissionDeniedError("Admin role required")
    return current_user


def require_owner(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != UserRole.OWNER:
        raise PermissionDeniedError("Owner role required")
    return current_user


# --- Ownership-scoped authorization ------------------------------------------------
#
# An admin can touch any Owner/Apartment/Booking. An owner-role user can only
# touch resources belonging to the single Owner record linked to their User
# (owner.user_id). These helpers centralize that comparison so it's written
# once, not once per router — see docs/decisions.md for why 404 is never used
# to hide a resource that exists but isn't the caller's.


async def get_current_owner_or_none(
    current_user: User = Depends(get_current_active_user),
    owner_service: OwnerService = Depends(get_owner_service),
) -> Owner | None:
    """The Owner linked to the current user, or None (admins and not-yet-linked
    owner-role users legitimately have no linked Owner — not an error here)."""
    return await owner_service.get_owner_for_user(current_user.id)


def authorize_owner_match(
    current_user: User, caller_owner: Owner | None, target_owner_id: uuid.UUID
) -> None:
    """Raise PermissionDeniedError unless current_user is an admin or
    caller_owner is exactly the owner that owns the resource in question."""
    if current_user.role == UserRole.ADMIN:
        return
    if caller_owner is None or caller_owner.id != target_owner_id:
        raise PermissionDeniedError("You do not have access to this resource")


async def get_authorized_owner(
    owner_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: OwnerService = Depends(get_owner_service),
) -> Owner:
    """Fetch-then-authorize for /owners/{owner_id} routes: 404 if the owner
    genuinely doesn't exist, 403 if it exists but isn't the caller's."""
    target = await service.get_owner(owner_id)
    authorize_owner_match(current_user, caller_owner, target.id)
    return target


async def get_authorized_apartment(
    apartment_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: ApartmentService = Depends(get_apartment_service),
) -> Apartment:
    """Fetch-then-authorize for /apartments/{apartment_id} routes."""
    apartment = await service.get_apartment(apartment_id)
    authorize_owner_match(current_user, caller_owner, apartment.owner_id)
    return apartment


async def get_authorized_booking(
    booking_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: BookingService = Depends(get_booking_service),
) -> Booking:
    """Fetch-then-authorize for /bookings/{booking_id} management routes.
    Does not apply to POST /bookings or GET /bookings/by-confirmation/{code},
    which stay unauthenticated by design — guests have no accounts."""
    booking = await service.get_booking(booking_id)
    authorize_owner_match(current_user, caller_owner, booking.owner_id)
    return booking


async def get_authorized_rate_rule(
    rate_rule_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: RateRuleService = Depends(get_rate_rule_service),
    apartment_service: ApartmentService = Depends(get_apartment_service),
) -> RateRule:
    """Fetch-then-authorize for /rate-rules/{rate_rule_id} routes. A rate
    rule has no owner_id of its own, so authorization is checked against its
    parent apartment's owner, same rule as apartments/bookings."""
    rate_rule = await service.get_rate_rule(rate_rule_id)
    apartment = await apartment_service.get_apartment(rate_rule.apartment_id)
    authorize_owner_match(current_user, caller_owner, apartment.owner_id)
    return rate_rule


async def get_authorized_blocked_date(
    blocked_date_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: BlockedDateService = Depends(get_blocked_date_service),
    apartment_service: ApartmentService = Depends(get_apartment_service),
) -> BlockedDate:
    """Fetch-then-authorize for /blocked-dates/{blocked_date_id} routes. A
    blocked date has no owner_id of its own, so authorization is checked
    against its parent apartment's owner, same rule as rate rules."""
    blocked_date = await service.get_blocked_date(blocked_date_id)
    apartment = await apartment_service.get_apartment(blocked_date.apartment_id)
    authorize_owner_match(current_user, caller_owner, apartment.owner_id)
    return blocked_date


async def get_authorized_apartment_photo(
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    caller_owner: Owner | None = Depends(get_current_owner_or_none),
    service: ApartmentPhotoService = Depends(get_apartment_photo_service),
    apartment_service: ApartmentService = Depends(get_apartment_service),
) -> ApartmentPhoto:
    """Fetch-then-authorize for /apartments/{apartment_id}/photos/{photo_id}
    routes. An apartment photo has no owner_id of its own, so authorization
    is checked against its parent apartment's owner, same rule as rate rules
    and blocked dates."""
    photo = await service.get_photo(photo_id)
    apartment = await apartment_service.get_apartment(photo.apartment_id)
    authorize_owner_match(current_user, caller_owner, apartment.owner_id)
    return photo
