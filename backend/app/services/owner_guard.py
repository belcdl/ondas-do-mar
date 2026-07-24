import uuid

from app.core.exceptions import BusinessRuleError
from app.models.owner import Owner
from app.repositories.owner import OwnerRepository
from app.services.owner import OwnerNotFoundError


class InactiveOwnerError(BusinessRuleError):
    """Raised when a resource is being assigned to an owner that is not active."""


async def ensure_owner_is_active(owner_repository: OwnerRepository, owner_id: uuid.UUID) -> Owner:
    """Validate that an owner exists and is active, locking the row while doing so.

    SELECT ... FOR UPDATE makes this check atomic with respect to a concurrent
    deactivate_owner() call: the deactivating UPDATE needs the same row lock,
    so it blocks until this transaction (the one creating/updating the
    Apartment or Booking that references this owner) commits. Without the
    lock, "is_active" could flip to false in the gap between this check and
    the write, silently creating a resource under a now-inactive owner with
    no error at all — the same class of race Decision 009/027 closed for
    Owner email uniqueness and Booking overlap, applied here via locking
    instead of a constraint, since there is no constraint to violate for
    "is this referenced row currently active".

    Shared by ApartmentService and BookingService to avoid duplicating this
    rule (previously implemented independently in each, with a subtle
    inconsistency: Booking used to collapse "owner not found" and "owner
    inactive" into a single error).
    """
    owner = await owner_repository.get_by_id_for_update(owner_id)
    if owner is None:
        raise OwnerNotFoundError(f"Owner {owner_id} not found")
    if not owner.is_active:
        raise InactiveOwnerError(f"Owner {owner_id} is not active")
    return owner
