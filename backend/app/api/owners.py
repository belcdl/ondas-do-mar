import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_apartment_service,
    get_authorized_owner,
    get_current_active_user,
    get_owner_service,
    require_admin,
)
from app.core.exceptions import PermissionDeniedError
from app.models.apartment import Apartment
from app.models.owner import Owner
from app.models.user import User, UserRole
from app.schemas.apartment import ApartmentRead
from app.schemas.owner import OwnerCreate, OwnerRead, OwnerUpdate
from app.schemas.owner_invitation import OwnerInvitationCreated
from app.services.apartment import ApartmentService
from app.services.owner import OwnerService

router = APIRouter(prefix="/owners", tags=["owners"])


@router.post("", response_model=OwnerRead, status_code=status.HTTP_201_CREATED)
async def create_owner(
    data: OwnerCreate,
    _current_user: User = Depends(require_admin),
    service: OwnerService = Depends(get_owner_service),
) -> Owner:
    """Admin-only. Register a new owner. Returns 409 if the email is already registered."""
    return await service.create_owner(data)


@router.get("", response_model=list[OwnerRead])
async def list_owners(
    include_inactive: bool = Query(
        False, description="Include deactivated owners in the results."
    ),
    _current_user: User = Depends(require_admin),
    service: OwnerService = Depends(get_owner_service),
) -> list[Owner]:
    """Admin-only. List owners. Only active owners are returned unless include_inactive=true."""
    return await service.list_owners(include_inactive=include_inactive)


@router.get("/{owner_id}", response_model=OwnerRead)
async def get_owner(owner: Owner = Depends(get_authorized_owner)) -> Owner:
    """Fetch a single owner. An owner may only fetch their own profile; an
    admin may fetch any. 404 if the owner doesn't exist, 403 if it exists
    but isn't the caller's."""
    return owner


@router.patch("/{owner_id}", response_model=OwnerRead)
async def update_owner(
    data: OwnerUpdate,
    current_user: User = Depends(get_current_active_user),
    owner: Owner = Depends(get_authorized_owner),
    service: OwnerService = Depends(get_owner_service),
) -> Owner:
    """Partially update an owner. An owner may only update their own profile;
    an admin may update any. Changing user_id (linking/relinking the account)
    is admin-only regardless of whose profile is being edited."""
    if "user_id" in data.model_fields_set and current_user.role != UserRole.ADMIN:
        raise PermissionDeniedError("Only an admin can change the linked user")
    return await service.update_owner(owner.id, data)


@router.post("/{owner_id}/deactivate", response_model=OwnerRead)
async def deactivate_owner(
    owner: Owner = Depends(get_authorized_owner),
    service: OwnerService = Depends(get_owner_service),
) -> Owner:
    """Deactivate an owner (sets is_active=false). Does not delete any data."""
    return await service.deactivate_owner(owner.id)


@router.post("/{owner_id}/invite", response_model=OwnerInvitationCreated)
async def invite_owner(
    owner_id: uuid.UUID,
    _current_user: User = Depends(require_admin),
    service: OwnerService = Depends(get_owner_service),
) -> OwnerInvitationCreated:
    """Admin-only. Generate a one-time invitation link for an owner who has
    no login yet. The raw token is returned exactly once, here — only its
    hash is ever stored. 404 if the owner doesn't exist, 409 if they already
    have a linked user. No email is sent — copy the link from the response."""
    raw_token, invitation = await service.invite_owner(owner_id)
    invitation_link = f"/accept-invitation?token={raw_token}"
    return OwnerInvitationCreated(
        invitation_link=invitation_link, expires_at=invitation.expires_at
    )


@router.get("/{owner_id}/apartments", response_model=list[ApartmentRead])
async def list_owner_apartments(
    include_inactive: bool = Query(
        False, description="Include deactivated apartments in the results."
    ),
    owner: Owner = Depends(get_authorized_owner),
    apartment_service: ApartmentService = Depends(get_apartment_service),
) -> list[Apartment]:
    """List apartments belonging to an owner. Same access rule as GET /owners/{owner_id}."""
    return await apartment_service.list_apartments_by_owner(
        owner.id, include_inactive=include_inactive
    )
