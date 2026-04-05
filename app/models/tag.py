"""Tag and TrackTag ORM models."""
from sqlalchemy import Column, Integer, String
from app.database import Base


class Tag(Base):
    __tablename__ = "tags"

    tag_id = Column(Integer, primary_key=True, autoincrement=True)
    tag_name = Column(String(100), unique=True, nullable=False)


class TrackTag(Base):
    __tablename__ = "track_tags"

    track_id = Column(String(64), primary_key=True)
    tag_id = Column(Integer, primary_key=True)
