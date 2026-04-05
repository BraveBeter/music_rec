"""User ORM model."""
from sqlalchemy import Column, Integer, String, SmallInteger, TIMESTAMP, func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    age = Column(Integer, nullable=True)
    gender = Column(SmallInteger, nullable=True)
    country = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    last_login = Column(TIMESTAMP, nullable=True)
