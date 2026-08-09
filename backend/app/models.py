"""Database tables (SQLAlchemy models)."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(150), unique=True, nullable=False, index=True)
    username = Column(String(80), unique=True, nullable=False)
    password = Column(String(255), nullable=False)  # bcrypt hash
    created_at = Column(DateTime, default=datetime.utcnow)

    matches = relationship("Match", back_populates="user")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    breed_name = Column(String(120), nullable=False)
    trait = Column(String(200))
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="matches")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "userId": self.user_id,
            "breedName": self.breed_name,
            "trait": self.trait,
            "confidence": self.confidence,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
