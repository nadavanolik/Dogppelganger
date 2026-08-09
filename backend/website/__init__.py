"""App factory — mirrors the class tutorial structure, but the app is a
JSON API (no templates/static) because the frontend is a separate React SPA.
"""
import os

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

# One shared SQLAlchemy handle, imported by models.py and the blueprints.
db = SQLAlchemy()


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    # In Docker this points at the Postgres container; locally it falls back to
    # a throwaway SQLite file so you can run the backend with zero setup.
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///dev.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Let the browser call the API. In production everything is same-origin
    # (nginx proxies /api to Flask), but in dev the React server is on :5173.
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    db.init_app(app)

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix="/api")
    app.register_blueprint(auth, url_prefix="/api/auth")

    # Import models so SQLAlchemy knows about the tables, then create them.
    from . import models  # noqa: F401

    with app.app_context():
        db.create_all()

    return app
