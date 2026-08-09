"""Main API endpoints (JSON). Mounted at /api."""
from flask import Blueprint, request, jsonify

from . import db
from .models import Match
from .model import predict_breed

views = Blueprint("views", __name__)


@views.get("/health")
def health():
    """Liveness probe used by Docker / the deploy checks."""
    return jsonify({"status": "ok"})


@views.post("/match")
def match():
    """Run the dog-matching model on an uploaded image and store the result."""
    data = request.get_json(silent=True) or {}
    result = predict_breed(data.get("image"))

    record = Match(
        user_id=data.get("userId"),
        breed_name=result["breedName"],
        trait=result["trait"],
        confidence=result["confidence"],
    )
    db.session.add(record)
    db.session.commit()

    return jsonify(record.to_dict()), 201


@views.get("/matches")
def matches():
    """Return recent matches (newest first)."""
    recent = Match.query.order_by(Match.created_at.desc()).limit(50).all()
    return jsonify([m.to_dict() for m in recent])
