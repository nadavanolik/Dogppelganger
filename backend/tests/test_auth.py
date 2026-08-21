"""Signup, login, and what a token is and isn't good for.

None of this was covered before: `/api/auth` shipped working code with no test
at all, and `get_current_user` was never imported by a single route, so the
dependency had never run in anger.
"""
import datetime as dt

import jwt
import pytest

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.security import (
    MEDIA_SCOPE,
    create_access_token,
    create_media_token,
    verify_password,
)


def signup(client, **overrides):
    payload = {
        "email": "new@test.dog",
        "username": "newcomer",
        "password": "hunter2hunter2",
        **overrides,
    }
    return client.post("/api/auth/signup", json=payload)


# --------------------------------------------------------------------- signup


def test_signup_returns_a_token_and_the_user(client):
    res = signup(client, email="a1@test.dog", username="a1")
    assert res.status_code == 201
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["media_token"]
    assert body["user"]["email"] == "a1@test.dog"
    assert body["user"]["username"] == "a1"


def test_the_password_is_never_echoed_back(client):
    res = signup(client, email="a2@test.dog", username="a2")
    assert "password" not in res.json()["user"]
    assert "hunter2hunter2" not in res.text


def test_the_stored_password_is_a_bcrypt_hash_not_the_plaintext(client):
    signup(client, email="a3@test.dog", username="a3")
    with SessionLocal() as db:
        row = db.query(User).filter(User.email == "a3@test.dog").one()
    assert row.password != "hunter2hunter2"
    assert row.password.startswith("$2")  # bcrypt marker
    assert verify_password("hunter2hunter2", row.password)


def test_the_email_is_normalised(client):
    signup(client, email="  MiXeD@Test.Dog  ", username="a4")
    res = client.post(
        "/api/auth/login", json={"email": "mixed@test.dog", "password": "hunter2hunter2"}
    )
    assert res.status_code == 200


@pytest.mark.parametrize("field", ["email", "username"])
def test_a_duplicate_is_a_409(client, field):
    # Distinct per parametrised run: the whole session shares one database, so
    # reusing "dup@test.dog" would make the second run collide on its *first*
    # signup and test nothing.
    first = {"email": f"dup-{field}@test.dog", "username": f"dup_{field}"}
    assert signup(client, **first).status_code == 201
    # Change the *other* field, so only the one under test collides.
    second = dict(first)
    if field == "email":
        second["username"] = f"dup_{field}_other"
    else:
        second["email"] = f"dup-{field}-other@test.dog"
    assert signup(client, **second).status_code == 409


@pytest.mark.parametrize("blank", ["email", "username", "password"])
def test_blank_fields_are_rejected(client, blank):
    payload = {
        "email": f"blank-{blank}@test.dog",
        "username": f"blank_{blank}",
        "password": "hunter2hunter2",
    }
    payload[blank] = "" if blank == "password" else "   "
    assert signup(client, **payload).status_code == 400


def test_a_short_password_is_rejected(client):
    res = signup(client, email="b2@test.dog", username="b2", password="short")
    assert res.status_code == 400
    assert "at least" in res.json()["detail"]


def test_a_password_past_bcrypts_72_byte_limit_is_rejected_not_truncated(client):
    """bcrypt ignores everything past 72 bytes, so accepting it would be a lie.

    Without this check the user's 200-character passphrase and its first 72
    characters would open the same account, which is not what anybody typing
    200 characters believes they are getting.
    """
    res = signup(client, email="b3@test.dog", username="b3", password="x" * 200)
    assert res.status_code == 400
    assert "72" in res.json()["detail"]


# ---------------------------------------------------------------------- login


def test_login_with_the_right_password_returns_a_token(client, user):
    res = client.post(
        "/api/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    assert res.status_code == 200
    assert res.json()["user"]["id"] == user["id"]


def test_a_wrong_password_and_an_unknown_email_are_indistinguishable(client, user):
    """Different messages here would leak which addresses have accounts."""
    wrong = client.post(
        "/api/auth/login", json={"email": user["email"], "password": "not-the-password"}
    )
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@test.dog", "password": "not-the-password"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


# ------------------------------------------------------------ get_current_user


def test_me_round_trips_the_account(auth_client, user):
    body = auth_client.get("/api/auth/me").json()
    assert body == {"id": user["id"], "email": user["email"], "username": user["username"]}


def test_no_header_is_a_401(client):
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        "",
        # Correctly formed, signed with the wrong key.
        jwt.encode({"sub": "1", "tv": 0}, "a-different-secret", algorithm="HS256"),
    ],
)
def test_a_bad_token_is_a_401(client, token):
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_an_expired_token_is_a_401(client, user):
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    expired = jwt.encode(
        {"sub": str(user["id"]), "tv": 0, "iat": past, "exp": past},
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401


def test_a_token_for_a_user_who_no_longer_exists_is_a_401(client, user):
    with SessionLocal() as db:
        db.delete(db.get(User, user["id"]))
        db.commit()
    res = client.get("/api/auth/me", headers=user["headers"])
    assert res.status_code == 401


def test_a_token_from_an_older_token_version_is_a_401(client, user):
    """What makes 'changing your password logs out other devices' true."""
    with SessionLocal() as db:
        row = db.get(User, user["id"])
        row.token_version += 1
        db.commit()

    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401

    with SessionLocal() as db:
        row = db.get(User, user["id"])
        fresh = create_access_token(row.id, row.token_version)
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"})
    assert res.status_code == 200


# --------------------------------------------------------------- media tokens


def test_a_media_token_is_refused_as_a_session_token(client, user):
    """The two token kinds must not be interchangeable.

    A media token rides in query strings, so it lands in nginx logs and browser
    history. If it also authorised REST calls, that leak would be a full
    session handover.
    """
    media = create_media_token(user["id"], 0)
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {media}"})
    assert res.status_code == 401


def test_a_session_token_is_refused_where_a_media_token_belongs(user):
    from app.security import decode_media_token

    assert decode_media_token(create_access_token(user["id"], 0)) is None


def test_the_media_token_endpoint_mints_a_scoped_token(auth_client, user):
    body = auth_client.get("/api/auth/media-token").json()
    assert body["expires_in"] == settings.MEDIA_TOKEN_EXPIRE_MINUTES * 60
    claims = jwt.decode(
        body["media_token"], settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    assert claims["scope"] == MEDIA_SCOPE
    assert claims["sub"] == str(user["id"])


def test_minting_a_media_token_needs_a_session(client):
    assert client.get("/api/auth/media-token").status_code == 401


# ------------------------------------------------------ the config guardrail


def test_a_placeholder_secret_key_is_refused_against_a_real_database():
    from app.config import Settings

    bad = Settings(
        DATABASE_URL="postgresql://dogapp:dogapp@db:5432/dogppelganger",
        SECRET_KEY="change-me",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        bad.check_production_secrets()


def test_a_placeholder_secret_key_is_tolerated_on_sqlite():
    """Local development must stay zero-setup."""
    from app.config import Settings

    Settings(
        DATABASE_URL="sqlite:///./dev.db", SECRET_KEY="dev-secret-change-me"
    ).check_production_secrets()
