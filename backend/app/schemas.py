"""Pydantic schemas — validate request bodies and shape responses."""
from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    username: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    username: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # Minted alongside the session token so the SPA can render private photos
    # immediately after login without a second round trip. Short-lived; the
    # client re-mints from /api/auth/media-token. See app/security.py.
    media_token: str
    user: UserOut


class MediaToken(BaseModel):
    media_token: str
    expires_in: int  # seconds


class MatchCreate(BaseModel):
    # `userId` is gone: the match belongs to whoever is holding the token, and
    # a client-supplied id was only ever a suggestion the server took on faith.
    image: str | None = None
