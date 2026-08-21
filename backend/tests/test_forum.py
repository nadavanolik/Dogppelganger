"""Forum ownership: who can write, and who can delete.

Deleting your own words is the part that was missing entirely — you could post
a thing and then be stuck with it.
"""
from conftest import make_image

from app.database import SessionLocal
from app.models import Comment, Post, Reaction, UploadJob


def upload_done(client, user, dog_asset_id: int | None = None) -> int:
    """An upload, marked finished the way the queue worker would."""
    files = [("files", ("me.jpg", make_image(200, 200), "image/jpeg"))]
    res = client.post(
        "/api/uploads", data={"urgent": "[]"}, files=files, headers=user["headers"]
    )
    job_id = res.json()["created"][0]["id"]
    with SessionLocal() as db:
        job = db.get(UploadJob, job_id)
        job.status = "done"
        job.dog_asset_id = dog_asset_id
        db.commit()
    return job_id


def post_as(client, user, body="hello") -> dict:
    res = client.post("/api/forum", json={"body": body}, headers=user["headers"])
    assert res.status_code == 201, res.text
    return res.json()


# ----------------------------------------------------------------- authorship


def test_a_post_is_attributed_to_the_token_not_the_body(client, user):
    body = post_as(client, user, "mine")

    assert body["authorId"] == user["id"]
    assert body["authorName"] == user["username"]


def test_posting_needs_a_login(client):
    assert client.post("/api/forum", json={"body": "anon"}).status_code == 401


def test_you_cannot_attach_someone_elses_photo(client, user, other_user):
    """403 here, not the 404 used elsewhere: you picked this id out of your own
    list, so its existence is not a secret being leaked to you."""
    job_id = upload_done(client, user)

    res = client.post(
        "/api/forum",
        json={"body": "not mine", "imageJobId": job_id},
        headers=other_user["headers"],
    )

    assert res.status_code == 403


def test_renaming_yourself_renames_your_old_posts(client, user):
    """The username lives on the user row now, not copied onto every post."""
    body = post_as(client, user, "before the rename")
    client.patch("/api/users/me", json={"username": "renamed_dog"}, headers=user["headers"])

    fetched = client.get(f"/api/forum/{body['id']}", headers=user["headers"]).json()

    assert fetched["authorName"] == "renamed_dog"


# ------------------------------------------------------------------ deleting


def test_you_can_delete_your_own_post(client, user):
    body = post_as(client, user, "regrettable")

    res = client.delete(f"/api/forum/{body['id']}", headers=user["headers"])

    assert res.status_code == 204
    assert client.get(f"/api/forum/{body['id']}", headers=user["headers"]).status_code == 404


def test_deleting_a_post_takes_its_comments_and_reactions(client, user, other_user):
    body = post_as(client, user, "doomed")
    comment = client.post(
        f"/api/forum/{body['id']}/comments",
        json={"body": "shame about this"},
        headers=other_user["headers"],
    ).json()
    client.post(
        "/api/forum/react",
        json={"targetType": "post", "targetId": body["id"], "kind": "like"},
        headers=other_user["headers"],
    )

    client.delete(f"/api/forum/{body['id']}", headers=user["headers"])

    with SessionLocal() as db:
        assert db.get(Post, body["id"]) is None
        assert db.get(Comment, comment["id"]) is None
        # Reactions are a manual polymorphic reference — nothing cascades them,
        # so an orphan would sit there forever counting towards nothing.
        assert (
            db.query(Reaction)
            .filter_by(target_type="post", target_id=body["id"])
            .count()
            == 0
        )


def test_deleting_a_post_keeps_the_photo(client, user):
    """"I regret the caption" is not "delete my photo" — it goes back to being
    an unshared match on the profile, ready to post again."""
    job_id = upload_done(client, user)
    body = client.post(
        "/api/forum", json={"body": "look", "imageJobId": job_id}, headers=user["headers"]
    ).json()

    client.delete(f"/api/forum/{body['id']}", headers=user["headers"])

    assert client.get(f"/api/uploads/{job_id}", headers=user["headers"]).status_code == 200


def test_you_cannot_delete_someone_elses_post(client, user, other_user):
    body = post_as(client, user, "mine, thanks")

    res = client.delete(f"/api/forum/{body['id']}", headers=other_user["headers"])

    assert res.status_code == 404
    assert client.get(f"/api/forum/{body['id']}", headers=user["headers"]).status_code == 200


def test_you_can_delete_your_own_comment_without_touching_the_thread(
    client, user, other_user
):
    body = post_as(client, user, "a thread")
    mine = client.post(
        f"/api/forum/{body['id']}/comments", json={"body": "oops"}, headers=other_user["headers"]
    ).json()
    theirs = client.post(
        f"/api/forum/{body['id']}/comments", json={"body": "stays"}, headers=user["headers"]
    ).json()

    res = client.delete(f"/api/forum/comments/{mine['id']}", headers=other_user["headers"])

    assert res.status_code == 204
    thread = client.get(f"/api/forum/{body['id']}", headers=user["headers"]).json()
    assert [c["id"] for c in thread["comments"]] == [theirs["id"]]


def test_you_cannot_delete_someone_elses_comment(client, user, other_user):
    body = post_as(client, user, "a thread")
    comment = client.post(
        f"/api/forum/{body['id']}/comments", json={"body": "not yours"}, headers=user["headers"]
    ).json()

    res = client.delete(f"/api/forum/comments/{comment['id']}", headers=other_user["headers"])

    assert res.status_code == 404


def test_the_comments_route_is_not_swallowed_by_the_post_route(client, user):
    """`/comments/{id}` is declared before `/{post_id}`. The other way round,
    FastAPI matches the int-typed post route first and 422s on "comments"
    instead of falling through."""
    body = post_as(client, user, "thread")
    comment = client.post(
        f"/api/forum/{body['id']}/comments", json={"body": "c"}, headers=user["headers"]
    ).json()

    res = client.delete(f"/api/forum/comments/{comment['id']}", headers=user["headers"])

    assert res.status_code == 204, "a 422 here means the routes are in the wrong order"


# --------------------------------------------------------------- live updates
#
# The forum used to be fetch-on-mount only, so somebody else's post appeared
# only if you reloaded. These cover the push half; see app/forum/router.py.


def comment_as(client, user, post_id: int, body="nice") -> dict:
    res = client.post(
        f"/api/forum/{post_id}/comments", json={"body": body}, headers=user["headers"]
    )
    assert res.status_code == 201, res.text
    return res.json()


def like(client, user, target_type: str, target_id: int, kind="like"):
    return client.post(
        "/api/forum/react",
        json={"targetType": target_type, "targetId": target_id, "kind": kind},
        headers=user["headers"],
    )


def test_a_new_post_reaches_everyone_else_live(client, user, other_user):
    """The forum is public to every signed-in user, so this broadcasts rather
    than targeting one recipient the way a DM does."""
    with client.websocket_connect(f"/api/ws?token={other_user['token']}") as socket:
        assert socket.receive_json()["type"] == "connected"

        post_as(client, user, "live from the kennel")

        event = socket.receive_json()

    assert event["type"] == "forum_post"
    assert event["payload"]["body"] == "live from the kennel"


def test_a_new_comment_reaches_everyone_else_live(client, user, other_user):
    body = post_as(client, user, "a thread")

    with client.websocket_connect(f"/api/ws?token={other_user['token']}") as socket:
        socket.receive_json()

        comment_as(client, user, body["id"], "first")

        event = socket.receive_json()

    assert event["type"] == "forum_comment"
    assert event["payload"]["postId"] == body["id"]
    assert event["payload"]["body"] == "first"


def test_a_reaction_broadcasts_counts_but_never_whose(client, user, other_user):
    """`myReaction` is computed per viewer. Pushing it would light up everyone
    else's thumb as though they had been the one to click it."""
    body = post_as(client, user, "vote on me")

    with client.websocket_connect(f"/api/ws?token={other_user['token']}") as socket:
        socket.receive_json()

        # Their own post, so no notification competes for the next frame.
        like(client, user, "post", body["id"])

        event = socket.receive_json()

    assert event["type"] == "forum_reaction"
    assert event["payload"]["likeCount"] == 1
    assert "myReaction" not in event["payload"], "that value is only true for one viewer"


def test_deleting_a_post_tells_the_room(client, user, other_user):
    """Otherwise a post you removed sits on everyone else's screen until they
    reload, and clicking it 404s."""
    body = post_as(client, user, "regrettable")

    with client.websocket_connect(f"/api/ws?token={other_user['token']}") as socket:
        socket.receive_json()

        client.delete(f"/api/forum/{body['id']}", headers=user["headers"])

        event = socket.receive_json()

    assert event["type"] == "forum_post_deleted"
    assert event["payload"]["id"] == body["id"]


# ------------------------------------------------------------- notifications
#
# The bell, its badge and /notifications were all built and wired to a
# `notify()` that nothing ever called. The forum is its first caller.


def bell(client, user) -> dict:
    return client.get("/api/notifications", headers=user["headers"]).json()


def test_commenting_notifies_the_post_author(client, user, other_user):
    body = post_as(client, user, "say something")

    comment_as(client, other_user, body["id"])

    inbox = bell(client, user)
    assert inbox["unread"] == 1
    assert inbox["items"][0]["kind"] == "comment"
    assert inbox["items"][0]["href"] == f"/forum/{body['id']}"
    assert other_user["username"] in inbox["items"][0]["text"]


def test_liking_notifies_the_author_of_a_comment_too(client, user, other_user):
    """The href points at the post, because that is where a comment is read."""
    body = post_as(client, other_user, "a thread")
    mine = comment_as(client, user, body["id"], "my two cents")

    like(client, other_user, "comment", mine["id"], "dislike")

    inbox = bell(client, user)
    assert inbox["unread"] == 1
    assert inbox["items"][0]["kind"] == "reaction"
    assert "disliked your comment" in inbox["items"][0]["text"]
    assert inbox["items"][0]["href"] == f"/forum/{body['id']}"


def test_your_own_doing_never_rings_your_own_bell(client, user):
    body = post_as(client, user, "talking to myself")
    comment_as(client, user, body["id"])
    like(client, user, "post", body["id"])

    assert bell(client, user)["unread"] == 0


def test_taking_a_like_back_is_not_news(client, user, other_user):
    """Reacting the same way twice clears the reaction. Treating that as news
    would ring the bell for something that just stopped being true."""
    body = post_as(client, user, "fickle audience")

    like(client, other_user, "post", body["id"])
    like(client, other_user, "post", body["id"])  # clears it

    assert bell(client, user)["unread"] == 1


def test_toggling_the_same_like_does_not_stack_the_bell(client, user, other_user):
    """`collapse_unread`: one person fiddling with a button is one piece of
    news, however many times they click."""
    body = post_as(client, user, "fickle audience")

    for _ in range(3):
        like(client, other_user, "post", body["id"])  # on, off, on again

    inbox = bell(client, user)
    assert inbox["unread"] == 1
    assert len(inbox["items"]) == 1
