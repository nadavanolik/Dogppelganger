"""Authentication endpoints (JSON). Mounted at /api/auth."""
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from . import db
from .models import User

auth = Blueprint("auth", __name__)


@auth.post("/signup")
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not email or not username or not password:
        return jsonify({"error": "email, username and password are required"}), 400

    if User.query.filter((User.email == email) | (User.username == username)).first():
        return jsonify({"error": "email or username already taken"}), 409

    user = User(
        email=email,
        username=username,
        password=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@auth.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "invalid credentials"}), 401

    return jsonify(user.to_dict()), 200
