from datetime import datetime

from pydantic import BaseModel, field_validator

from app.schemas.validators import validate_password_strength


class OwnerInvitationCreated(BaseModel):
    invitation_link: str
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str
    full_name: str

    _validate_password = field_validator("password")(validate_password_strength)
