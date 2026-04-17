"""ArtistFavorite ORM model."""
from sqlalchemy import Column, Integer, String, TIMESTAMP, func
from common.database import Base


class ArtistFavorite(Base):
    __tablename__ = "artist_favorites"

    user_id = Column(Integer, primary_key=True)
    artist_name = Column(String(255), primary_key=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
