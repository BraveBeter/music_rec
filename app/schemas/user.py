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


class PlaybackHistoryItem(BaseModel):
    """User playback history with track details."""
    interaction_id: int
    track_id: str
    title: str
    artist_name: str | None = None
    cover_url: str | None = None
    duration_ms: int | None = None
    interaction_type: int
    play_duration: int | None = None
    completion_rate: float | None = None
    created_at: str
