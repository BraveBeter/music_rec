"""Recommendation schemas."""
from pydantic import BaseModel


class RecommendationItem(BaseModel):
    track_id: str
    title: str
    artist_name: str | None = None
    album_name: str | None = None
    duration_ms: int | None = None
    preview_url: str | None = None
    cover_url: str | None = None
    score: float | None = None

    class Config:
        from_attributes = True


class RecommendationResponse(BaseModel):
    strategy_matched: str
    is_fallback: bool = False
    items: list[RecommendationItem]


class SimilarRecommendationResponse(BaseModel):
    source_tracks: list[RecommendationItem]
    items: list[RecommendationItem]
