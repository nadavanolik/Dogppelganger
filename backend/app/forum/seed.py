"""Cold seeding: a few fake authors and posts so the forum isn't empty on a
fresh database (course guideline — "a few fake clients, with a few posts and
comments already there"). Runs once at app startup; a no-op once any post
exists, so it never overwrites real activity.
"""
from __future__ import annotations

from ..database import SessionLocal
from ..models import Comment, Post

_AUTHORS = [
    ("seed_moodyoak", "moodyoak"),
    ("seed_corgi_core", "corgi_core"),
    ("seed_hufflepupp", "hufflepupp"),
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


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        if db.query(Post).count() > 0:
            return

        posts: list[Post] = []
        for author_idx, body in _POSTS:
            author_id, author_name = _AUTHORS[author_idx]
            post = Post(author_id=author_id, author_name=author_name, body=body)
            db.add(post)
            posts.append(post)
        db.flush()  # assign post ids before the comments reference them

        for post_idx, author_idx, body in _COMMENTS:
            author_id, author_name = _AUTHORS[author_idx]
            db.add(
                Comment(post_id=posts[post_idx].id, author_id=author_id, author_name=author_name, body=body)
            )
        db.commit()
    finally:
        db.close()
