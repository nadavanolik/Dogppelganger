"""Authentication endpoints. Mounted at /api/auth."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import Token, UserCreate, UserLogin
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": {"id": user.id, "email": user.email, "username": user.username},
    }


@router.post("/signup", response_model=Token, status_code=201)
def signup(data: UserCreate, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    username = data.username.strip()
    if not email or not username or not data.password:
        raise HTTPException(400, "email, username and password are required")

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
        raise HTTPException(401, "invalid credentials")
    return _token_response(user)
