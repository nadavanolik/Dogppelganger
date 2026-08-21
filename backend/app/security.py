"""Password hashing (bcrypt) and JWT tokens.

Two kinds of token are minted here and they are deliberately not
interchangeable:

* a **session token**, sent as ``Authorization: Bearer`` on REST calls, and
* a **media token**, carried in a query string because an ``<img>`` or
  ``<video>`` element cannot set a header.

The media token is the weaker of the two — it ends up in nginx access logs and
browser history — so it carries ``scope: "media"`` and is short-lived, and the
two decoders each refuse the other's tokens. Without that mutual refusal the
"weaker" token would simply *be* a session token that leaks into logs.
"""
import datetime as dt

import bcrypt
import jwt

from .config import settings

MEDIA_SCOPE = "media"

# bcrypt hashes at most 72 bytes and silently ignores the rest, so "correct
# horse battery staple …" and the same string with a different 100th character
# are the same password. Rejecting is honest; truncating is a trap.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


class PasswordRejected(ValueError):
    """A password that cannot be safely hashed or is too weak to accept."""


def validate_password(password: str) -> str:
    """Check a new password, returning it unchanged. Raises PasswordRejected."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordRejected(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PasswordRejected(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
            "(bcrypt ignores anything past that, so a longer one would be a lie)."
        )
    return password


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def _encode(payload: dict, expires: dt.timedelta, scope: str | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    body = {**payload, "iat": now, "exp": now + expires}
    if scope is not None:
        body["scope"] = scope
    return jwt.encode(body, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _decode(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def create_access_token(user_id: int, token_version: int = 0) -> str:
    """A session token. ``tv`` is checked against the user row on every request."""
    return _encode(
        {"sub": str(user_id), "tv": token_version},
        dt.timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    )


def create_media_token(user_id: int, token_version: int = 0) -> str:
    """A short-lived token that only ``decode_media_token`` will accept."""
    return _encode(
        {"sub": str(user_id), "tv": token_version},
        dt.timedelta(minutes=settings.MEDIA_TOKEN_EXPIRE_MINUTES),
        scope=MEDIA_SCOPE,
    )


def _claims(token: str, *, want_media: bool) -> tuple[int, int] | None:
    payload = _decode(token)
    if payload is None:
        return None
    # The mutual refusal. A media token must never authorise a REST call, and a
    # session token must never be pasted into a URL and still work.
    if (payload.get("scope") == MEDIA_SCOPE) != want_media:
        return None
    try:
        return int(payload["sub"]), int(payload.get("tv", 0))
    except (KeyError, TypeError, ValueError):
        return None


def decode_token(token: str) -> int | None:
    """Return the user id from a valid *session* token, or None.

    Kept returning a bare id because `app/routers/ws.py` and `app/game/ws.py`
    already call it that way; `decode_token_claims` is the version that also
    reports the token version.
    """
    claims = _claims(token, want_media=False)
    return None if claims is None else claims[0]


def decode_token_claims(token: str) -> tuple[int, int] | None:
    """``(user_id, token_version)`` from a valid session token, or None."""
    return _claims(token, want_media=False)


def decode_media_token(token: str) -> tuple[int, int] | None:
    """``(user_id, token_version)`` from a valid media token, or None."""
    return _claims(token, want_media=True)
