"""Interaction schemas."""
from pydantic import BaseModel, Field


class InteractionCreate(BaseModel):
    track_id: str
    interaction_type: int = Field(..., ge=1, le=4, description="1=play,2=like,3=skip,4=rate")
    rating: float | None = Field(None, ge=0, le=5)
    play_duration: int | None = Field(None, ge=0, description="ms")
    client_timestamp: int | None = None


class InteractionResponse(BaseModel):
    interaction_id: int
    track_id: str
    interaction_type: int
    rating: float | None = None
    play_duration: int | None = None
    completion_rate: float | None = None
    created_at: str

    class Config:
        from_attributes = True
