"""User schemas."""
from pydantic import BaseModel
from datetime import datetime


class UserProfile(BaseModel):
    user_id: int
    username: str
    role: str
    age: int | None = None
    gender: int | None = None
    country: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    age: int | None = None
    gender: int | None = None
    country: str | None = None
