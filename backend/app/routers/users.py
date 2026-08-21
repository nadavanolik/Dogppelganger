"""Account management and the user directory. Mounted at /api/users."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import UserOut
from ..security import (
    PasswordRejected,
    create_access_token,
    create_media_token,
    hash_password,
    validate_password,
    verify_password,
)
from ..services.users import delete_user

router = APIRouter(prefix="/api/users", tags=["users"])


class ProfileUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    currentPassword: str | None = None


class PasswordChange(BaseModel):
    currentPassword: str
    newPassword: str


class AccountDelete(BaseModel):
    password: str


def _out(user: User) -> dict:
    return {"id": user.id, "email": user.email, "username": user.username}


@router.get("")
def search_users(
    q: str = Query(default="", max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Find people to start a conversation with.

    Returns **id and username only**. Never the email: this is reachable by any
    logged-in user, and an endpoint that hands out addresses in bulk is a
    mailing list, not a directory.
    """
    query = db.query(User).filter(User.id != user.id)
    term = q.strip()
    if term:
        query = query.filter(User.username.ilike(f"{term}%"))
    rows = query.order_by(User.username).limit(limit).all()
    return [{"id": u.id, "username": u.username} for u in rows]


@router.patch("/me", response_model=UserOut)
def update_me(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change username and/or email.

    Changing the **email** requires the current password; changing the username
    does not. The asymmetry is deliberate: the email is the login identifier,
    so taking it over is taking over the account, while a username is a display
    name. Anyone who walks up to an unlocked laptop should not be able to
    redirect the account to their own address.
    """
    if data.username is not None:
        username = data.username.strip()
        if not username:
            raise HTTPException(400, "username cannot be blank")
        clash = db.query(User).filter(User.username == username, User.id != user.id).first()
        if clash:
            raise HTTPException(409, "that username is taken")
        user.username = username

    if data.email is not None:
        email = data.email.strip().lower()
        if not email:
            raise HTTPException(400, "email cannot be blank")
        if email != user.email:
            if not data.currentPassword or not verify_password(
                data.currentPassword, user.password
            ):
                raise HTTPException(400, "changing your email needs your current password")
            clash = db.query(User).filter(User.email == email, User.id != user.id).first()
            if clash:
                raise HTTPException(409, "that email is taken")
            user.email = email

    db.commit()
    db.refresh(user)
    return _out(user)


@router.post("/me/password")
def change_password(
    data: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change the password and end every other session.

    Bumping `token_version` invalidates every token minted before now — which
    is the point — so a fresh pair is returned for the tab that made the
    request. Without that the caller would log themselves out by changing their
    own password, which nobody expects.
    """
    if not verify_password(data.currentPassword, user.password):
        raise HTTPException(400, "current password is incorrect")
    try:
        validate_password(data.newPassword)
    except PasswordRejected as exc:
        raise HTTPException(400, str(exc)) from exc

    user.password = hash_password(data.newPassword)
    user.token_version += 1
    db.commit()
    db.refresh(user)
    return {
        "access_token": create_access_token(user.id, user.token_version),
        "token_type": "bearer",
        "media_token": create_media_token(user.id, user.token_version),
        "user": _out(user),
    }


@router.delete("/me", status_code=204)
def delete_me(
    data: AccountDelete,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete this account.

    Requires the password: this is irreversible, and a stolen token should not
    be enough to destroy someone's data.

    What actually happens is in `app/services/users.py` — photos, matches and
    reactions are erased, while posts, comments and sent messages survive as
    "[deleted user]". The UI must say so plainly before calling this.
    """
    if not verify_password(data.password, user.password):
        raise HTTPException(400, "password is incorrect")
    delete_user(db, user)
    return None
