"""Database engine + session. Plain (synchronous) SQLAlchemy 2.0.

FastAPI runs the sync request handlers in a threadpool, so this stays simple
and familiar while the WebSocket endpoints remain fully async.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# SQLite needs this flag when used across threads; Postgres ignores it.
connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: hand out a DB session, always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
