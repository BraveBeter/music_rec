"""Shared data contracts between backend and ML pipeline."""
from pydantic import BaseModel
from typing import Optional


class InteractionEvent(BaseModel):
    """Unified interaction event schema used across all system boundaries."""
    user_id: int
    track_id: str
    interaction_type: int  # 1=play, 2=like, 3=skip, 4=rate
    rating: Optional[float] = None
    play_duration: Optional[int] = None
    completion_rate: Optional[float] = None
    client_timestamp: Optional[int] = None


class TrackFeatureVector(BaseModel):
    """Track feature representation for ML models."""
    track_id: str
    danceability: float = 0.0
    energy: float = 0.0
    tempo: float = 0.0
    valence: float = 0.0
    acousticness: float = 0.0


class UserFeatureVector(BaseModel):
    """User feature representation for DeepFM input."""
    user_id: int
    age: int = 0
    gender: int = 0
    country_encoded: int = 0
    interaction_count: int = 0
    avg_completion_rate: float = 0.0
