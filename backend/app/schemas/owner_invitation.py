from datetime import datetime

from pydantic import BaseModel


class OwnerInvitationCreated(BaseModel):
    invitation_link: str
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str
    full_name: str
