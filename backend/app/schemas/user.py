import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: UserRole


class AdminPasswordResetRequest(BaseModel):
    email: str
    new_password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
