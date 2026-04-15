"""TrackFeature ORM model."""
from sqlalchemy import Column, String, Float, TIMESTAMP, func
from common.database import Base


class TrackFeature(Base):
    __tablename__ = "track_features"

    track_id = Column(String(64), primary_key=True)
    danceability = Column(Float, nullable=True)
    energy = Column(Float, nullable=True)
    tempo = Column(Float, nullable=True)
    valence = Column(Float, nullable=True)
    acousticness = Column(Float, nullable=True)
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
