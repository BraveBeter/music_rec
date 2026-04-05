"""UserInteraction ORM model."""
from sqlalchemy import Column, BigInteger, Integer, String, SmallInteger, Float, TIMESTAMP, func
from app.database import Base


class UserInteraction(Base):
    __tablename__ = "user_interactions"

    interaction_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    track_id = Column(String(64), nullable=False, index=True)
    interaction_type = Column(SmallInteger, nullable=False)
    rating = Column(Float, nullable=True)
    play_duration = Column(Integer, nullable=True)
    completion_rate = Column(Float, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
