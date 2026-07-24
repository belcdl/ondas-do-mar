from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import (
    get_current_active_user,
    get_owner_service,
    get_user_service,
    require_admin,
    require_owner,
)
from app.models.user import User
from app.schemas.owner_invitation import AcceptInvitationRequest
from app.schemas.token import Token
from app.schemas.user import UserRead
from app.services.owner import OwnerService
from app.services.user import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    service: UserService = Depends(get_user_service),
) -> Token:
    """Authenticate with email (as username) and password. Returns 401 on any
    failure — wrong password, unknown email, or inactive account are all
    indistinguishable to the caller."""
    access_token = await service.login(form_data.username, form_data.password)
    return Token(access_token=access_token)


@router.post("/accept-invitation", response_model=Token)
async def accept_invitation(
    data: AcceptInvitationRequest,
    service: OwnerService = Depends(get_owner_service),
) -> Token:
    """Public by design — the caller has no account yet, that's the whole
    point of an invitation (mirrors POST /bookings staying public for the
    same reason: the caller can't authenticate before this call succeeds).
    Sets the owner's password and logs them in immediately. 404 if the token
    is unknown, 409 if already used, 422 if expired."""
    _user, access_token = await service.accept_invitation(
        data.token, data.password, data.full_name
    )
    return Token(access_token=access_token)


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)) -> dict[str, str]:
    """No-op beyond requiring a valid token: JWTs are stateless, so there is
    nothing to invalidate server-side. Kept as an endpoint for API symmetry
    and so a future refresh-token/blacklist mechanism has somewhere to live."""
    return {"message": "Logged out"}


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_active_user)) -> User:
    """Return the authenticated user's own profile."""
    return current_user


@router.get("/admin-only")
async def admin_only(current_user: User = Depends(require_admin)) -> dict[str, str]:
    """Demonstrates require_admin. Not a real business endpoint — proves the
    RBAC dependency chain works end to end; applying it to real endpoints is
    a follow-up sprint."""
    return {"message": f"Hello admin {current_user.email}"}


@router.get("/owner-only")
async def owner_only(current_user: User = Depends(require_owner)) -> dict[str, str]:
    """Demonstrates require_owner. Same purpose as /admin-only above."""
    return {"message": f"Hello owner {current_user.email}"}
