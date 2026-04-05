"""Auth schemas."""
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    age: int | None = None
    gender: int | None = Field(None, ge=0, le=2)
    country: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
