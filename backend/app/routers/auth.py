"""Authentication endpoints. Mounted at /api/auth."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import MediaToken, Token, UserCreate, UserLogin, UserOut
from ..security import (
    PasswordRejected,
    create_access_token,
    create_media_token,
    hash_password,
    validate_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for "no such email" and for "wrong password" alike. Two different
# messages would turn this endpoint into a way to discover which addresses have
# accounts, which is worth more to an attacker than it is to a typo'd user.
BAD_CREDENTIALS = "invalid credentials"


def _token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id, user.token_version),
        "token_type": "bearer",
        "media_token": create_media_token(user.id, user.token_version),
        "user": {"id": user.id, "email": user.email, "username": user.username},
    }


@router.post("/signup", response_model=Token, status_code=201)
def signup(data: UserCreate, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    username = data.username.strip()
    if not email or not username or not data.password:
        raise HTTPException(400, "email, username and password are required")
    try:
        validate_password(data.password)
    except PasswordRejected as exc:
        raise HTTPException(400, str(exc)) from exc

    exists = db.query(User).filter((User.email == email) | (User.username == username)).first()
    if exists:
        raise HTTPException(409, "email or username already taken")

    user = User(email=email, username=username, password=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.strip().lower()).first()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(401, BAD_CREDENTIALS)
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """Who am I? The SPA's bootstrap call on a page load with a stored token."""
    return {"id": user.id, "email": user.email, "username": user.username}


@router.get("/media-token", response_model=MediaToken)
def media_token(user: User = Depends(get_current_user)):
    """Mint a fresh short-lived token for <img>/<video> URLs."""
    return {
        "media_token": create_media_token(user.id, user.token_version),
        "expires_in": settings.MEDIA_TOKEN_EXPIRE_MINUTES * 60,
    }
