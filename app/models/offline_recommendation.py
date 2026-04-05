"""OfflineRecommendation ORM model."""
from sqlalchemy import Column, Integer, JSON, TIMESTAMP, func
from app.database import Base


class OfflineRecommendation(Base):
    __tablename__ = "offline_recommendations"

    user_id = Column(Integer, primary_key=True)
    recommended_track_ids = Column(JSON, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
