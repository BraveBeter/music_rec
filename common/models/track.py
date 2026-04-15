"""Track ORM model."""
from sqlalchemy import Column, Integer, String, SmallInteger, TIMESTAMP, func
from common.database import Base


class Track(Base):
    __tablename__ = "tracks"

    track_id = Column(String(64), primary_key=True)
    title = Column(String(255), nullable=False)
    artist_name = Column(String(255), nullable=True)
    album_name = Column(String(255), nullable=True)
    release_year = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    play_count = Column(Integer, nullable=False, default=0)
    status = Column(SmallInteger, nullable=False, default=1)
    preview_url = Column(String(512), nullable=True)
    cover_url = Column(String(512), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
