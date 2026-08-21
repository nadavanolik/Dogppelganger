"""Shared FastAPI dependencies (e.g. 'who is the logged-in user?')."""
from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_media_token, decode_token_claims

bearer = HTTPBearer(auto_error=False)

_INVALID = "Invalid or expired token"


def _user_for(db: Session, claims: tuple[int, int] | None) -> User | None:
    """Resolve decoded claims to a live user, enforcing the token version."""
    if claims is None:
        return None
    user_id, token_version = claims
    user = db.get(User, user_id)
    if user is None:
        return None
    # The revocation check. A token minted before a password change carries the
    # old version and stops working here, even though its signature and expiry
    # are both still perfectly valid.
    if user.token_version != token_version:
        return None
    return user


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Require a valid 'Authorization: Bearer <jwt>' header on a route."""
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = _user_for(db, decode_token_claims(creds.credentials))
    if user is None:
        raise HTTPException(status_code=401, detail=_INVALID)
    return user


def get_media_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    t: str = Query(default="", description="Short-lived media token"),
    db: Session = Depends(get_db),
) -> User:
    """Identify the caller for a request a browser makes on its own.

    An ``<img src>`` or ``<video src>`` cannot carry an Authorization header, so
    these routes also accept ``?t=<media token>``. The header is tried first so
    that ordinary fetches, and the tests, need nothing special.
    """
    user = None
    if creds is not None:
        user = _user_for(db, decode_token_claims(creds.credentials))
    if user is None and t:
        user = _user_for(db, decode_media_token(t))
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_media_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    t: str = Query(default="", description="Short-lived media token"),
    db: Session = Depends(get_db),
) -> User | None:
    """Like ``get_media_user`` but returns None instead of raising.

    Needed by routes that serve *some* objects to anonymous callers — a match
    shared to the public gallery — while still wanting to know who is asking
    when it is someone. Raising there would break the logged-out landing page.
    """
    if creds is not None:
        user = _user_for(db, decode_token_claims(creds.credentials))
        if user is not None:
            return user
    if t:
        return _user_for(db, decode_media_token(t))
    return None
