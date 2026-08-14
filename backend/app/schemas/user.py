import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.user import UserRole
from app.schemas.validators import validate_password_strength


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: UserRole

    _validate_password = field_validator("password")(validate_password_strength)


class AdminPasswordResetRequest(BaseModel):
    email: str
    new_password: str

    _validate_new_password = field_validator("new_password")(validate_password_strength)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
