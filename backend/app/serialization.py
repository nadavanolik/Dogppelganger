"""How a person is named on the wire, including when they no longer exist.

Deleting an account anonymises what that person wrote rather than deleting it,
so `Post.author_id`, `Comment.author_id` and `Message.sender_id` are all
nullable. Every response that names an author therefore has to answer "who?"
when the answer is nobody.

**The contract: the API never sends a null display name.** An author is always
a pair — an id that may be null, and a name that never is. That way the
frontend does exactly one null check, and only for *affordances* (link to a
profile, offer to message them), never for rendering text. Any comparison of
"is this mine?" must use the id; comparing names would make a second person
called `[deleted user]` indistinguishable from the first.
"""
from __future__ import annotations

DELETED_USER_NAME = "[deleted user]"


def author_ref(user) -> dict:
    """`{id, username}` for a user, or the anonymous stand-in for None."""
    if user is None:
        return {"id": None, "username": DELETED_USER_NAME}
    return {"id": user.id, "username": user.username}


def author_name(user) -> str:
    return DELETED_USER_NAME if user is None else user.username
