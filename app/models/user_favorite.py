"""UserFavorite ORM model."""
from sqlalchemy import Column, Integer, String, TIMESTAMP, func
from app.database import Base


class UserFavorite(Base):
    __tablename__ = "user_favorites"

    user_id = Column(Integer, primary_key=True)
    track_id = Column(String(64), primary_key=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
