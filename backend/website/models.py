"""SQLAlchemy models — the database tables (same idea as the class example)."""
from datetime import datetime

from . import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # stored hashed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    matches = db.relationship("Match", backref="user", lazy=True)

    def to_dict(self):
        return {"id": self.id, "email": self.email, "username": self.username}


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    breed_name = db.Column(db.String(120), nullable=False)
    trait = db.Column(db.String(200))
    confidence = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "userId": self.user_id,
            "breedName": self.breed_name,
            "trait": self.trait,
            "confidence": self.confidence,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
