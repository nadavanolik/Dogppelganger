"""Cold seeding: a few demo accounts and posts so the forum isn't empty on a
fresh database (course guideline — "a few fake clients, with a few posts and
comments already there"). Runs once at app startup; a no-op once any post
exists, so it never overwrites real activity.

These are **real user rows** now, not string labels, because `Post.author_id` is
a foreign key. That has a consequence worth being deliberate about: they are
login-capable accounts. Each therefore gets a long random password that is
generated at seed time and never written down anywhere — nobody, including us,
can log in as them. If you want to demo signing in as one, sign up normally
instead.
"""
from __future__ import annotations

import secrets

from ..database import SessionLocal
from ..models import Comment, Post, User
from ..security import hash_password

# (username, email)
_AUTHORS = [
    ("moodyoak", "moodyoak@dogppelganger.invalid"),
    ("corgi_core", "corgi_core@dogppelganger.invalid"),
    ("hufflepupp", "hufflepupp@dogppelganger.invalid"),
]

# (author index, body) — text-only, since seed authors have no real uploaded
# photos to share.
_POSTS = [
    (
        0,
        "I got matched with a Shiba Inu and my life makes sense now. For 32 years I thought "
        "I was a Golden. Turns out I've been misreading myself the whole time.",
    ),
    (
        1,
        "Best strategy for the multiplayer match game? I keep losing to my roommate. Any tips "
        "beyond 'squint at the ears'?",
    ),
    (2, "Petition to add Alaskan Klee Kai. The tiny husky lobby demands representation."),
]

# (post index, author index, body)
_COMMENTS = [
    (0, 1, "same energy as me and my Corgi result honestly"),
    (0, 2, "the polite chaos slander in these replies is unwarranted"),
    (1, 0, "claim the human faster than you think, works for me"),
]


def _seed_users(db) -> list[User]:
    """Get or create the demo accounts, so re-seeding never duplicates them."""
    users: list[User] = []
    for username, email in _AUTHORS:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            user = User(
                username=username,
                email=email,
                # Unguessable and unrecorded — see the module docstring.
                password=hash_password(secrets.token_urlsafe(32)),
            )
            db.add(user)
        users.append(user)
    db.flush()  # assign ids before posts reference them
    return users


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        if db.query(Post).count() > 0:
            return

        authors = _seed_users(db)

        posts: list[Post] = []
        for author_idx, body in _POSTS:
            post = Post(author_id=authors[author_idx].id, body=body)
            db.add(post)
            posts.append(post)
        db.flush()  # assign post ids before the comments reference them

        for post_idx, author_idx, body in _COMMENTS:
            db.add(
                Comment(
                    post_id=posts[post_idx].id,
                    author_id=authors[author_idx].id,
                    body=body,
                )
            )
        db.commit()
    finally:
        db.close()
