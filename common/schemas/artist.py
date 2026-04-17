"""Artist schemas."""
from pydantic import BaseModel


class ArtistItem(BaseModel):
    artist_name: str
    track_count: int
    cover_url: str | None = None


class ArtistListResponse(BaseModel):
    items: list[ArtistItem]
    total: int
