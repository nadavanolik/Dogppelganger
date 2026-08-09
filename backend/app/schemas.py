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
    user: UserOut


class MatchCreate(BaseModel):
    image: str | None = None
    userId: int | None = None
