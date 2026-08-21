"""Sharing a match to the public gallery, and what deleting an account does.

These two live together because they are the same question from opposite ends:
what is visible to other people, and what survives when the person who put it
there is gone.
"""
from conftest import make_image

from app.database import SessionLocal
from app.models import Comment, Conversation, Message, Post, UploadJob, User
from app.storage import layout


def upload(client, user, **kwargs):
    files = [("files", ("me.jpg", make_image(200, 200), "image/jpeg"))]
    res = client.post(
        "/api/uploads", data={"urgent": "[]"}, files=files, headers=user["headers"]
    )
    assert res.status_code == 201, res.text
    return res.json()["created"][0]


def finish(job_id: int, dog_asset_id: int | None = 1):
    """Mark a job done, the way the queue worker would."""
    with SessionLocal() as db:
        job = db.get(UploadJob, job_id)
        job.status = "done"
        job.dog_asset_id = dog_asset_id
        job.score = 0.8
        db.commit()


def delete_account(client, password: str, headers: dict):
    """DELETE with a body — httpx's `.delete()` shorthand won't carry one."""
    return client.request(
        "DELETE", "/api/users/me", json={"password": password}, headers=headers
    )


def gallery_job_ids(client) -> list[int]:
    return [item["jobId"] for item in client.get("/api/gallery").json()["items"]]


# ------------------------------------------------------------------ sharing


def test_a_shared_match_appears_in_the_gallery(client, user, dog_corpus):
    job = upload(client, user)
    finish(job["id"])

    shared = client.post(f"/api/uploads/{job['id']}/share", headers=user["headers"])
    assert shared.status_code == 200
    assert shared.json()["shared"] is True

    body = client.get("/api/gallery").json()
    # Membership, not equality: the whole session shares one database, so other
    # tests' shared matches are legitimately in here too.
    mine = [item for item in body["items"] if item["jobId"] == job["id"]]
    assert len(mine) == 1
    assert mine[0]["owner"]["username"] == user["username"]


def test_the_gallery_is_readable_logged_out(client, user, dog_corpus):
    """The landing page shows a featured strip to visitors who have no account
    yet, so this endpoint has to work with no token at all."""
    job = upload(client, user)
    finish(job["id"])
    client.post(f"/api/uploads/{job['id']}/share", headers=user["headers"])

    assert client.get("/api/gallery").status_code == 200
    featured = client.get("/api/gallery/featured").json()
    assert job["id"] in [item["jobId"] for item in featured]


def test_an_unfinished_or_dogless_match_can_never_be_shared(client, user):
    """A queued job would render as an empty card, and a job that found no dog
    would put a photo of a person in the gallery with nothing beside it."""
    queued = upload(client, user)
    assert client.post(f"/api/uploads/{queued['id']}/share", headers=user["headers"]).status_code == 422

    dogless = upload(client, user)
    finish(dogless["id"], dog_asset_id=None)
    assert client.post(f"/api/uploads/{dogless['id']}/share", headers=user["headers"]).status_code == 422


def test_nothing_is_shared_by_default(client, user, dog_corpus):
    job = upload(client, user)
    finish(job["id"])

    assert job["id"] not in gallery_job_ids(client)


def test_only_the_owner_can_share(client, user, other_user, dog_corpus):
    job = upload(client, user)
    finish(job["id"])

    res = client.post(f"/api/uploads/{job['id']}/share", headers=other_user["headers"])

    assert res.status_code == 404


def test_a_shared_photo_is_readable_by_anyone_and_private_again_once_unshared(
    client, user, other_user, dog_corpus
):
    """The point of the whole feature, and the thing most likely to rot.

    Because the access check re-runs against the row on every request and the
    response is `no-store`, unsharing takes effect on the very next request
    rather than whenever some cache decides to expire.
    """
    job = upload(client, user)
    finish(job["id"])
    url = f"/api/uploads/{job['id']}/image"

    assert client.get(url).status_code == 404, "private to begin with"

    shared = client.post(f"/api/uploads/{job['id']}/share", headers=user["headers"])
    assert shared.json()["shared"] is True
    assert client.get(url).status_code == 200, "shared: anyone can see it"
    assert client.get(url, headers=other_user["headers"]).status_code == 200

    unshared = client.delete(f"/api/uploads/{job['id']}/share", headers=user["headers"])
    # The response body is what the UI feeds back into its job list. A client
    # that keeps its own copy instead goes stale, and then sends the *wrong*
    # request next time — which is how a photo once stayed public after the
    # button said it was private.
    assert unshared.json()["shared"] is False
    assert client.get(url).status_code == 404, "unshared: private again, immediately"


def test_a_photo_behind_a_forum_post_is_visible_to_other_members(
    client, user, other_user, dog_corpus
):
    """Without this the forum feed would 404 every thumbnail.

    It used to 'work' because the frontend passed the *author's* id as the
    owner, which meant the ownership check could be defeated by anyone who read
    the post JSON.
    """
    job = upload(client, user)
    finish(job["id"])
    client.post(
        "/api/forum", json={"body": "look at my dog", "imageJobId": job["id"]},
        headers=user["headers"],
    )

    url = f"/api/uploads/{job['id']}/image"
    assert client.get(url, headers=other_user["headers"]).status_code == 200
    assert client.get(url).status_code == 404, "but still not to the logged-out world"


# ---------------------------------------------------------- deleting a photo


def test_deleting_a_photo_erases_the_files_and_the_post_that_shared_it(
    client, user, dog_corpus
):
    """Unlike deleting a post, this really does take the picture with it — so
    the post that was built around that picture has to go too, or it would be a
    caption pointing at nothing."""
    job = upload(client, user)
    finish(job["id"])
    post = client.post(
        "/api/forum",
        json={"body": "here it is", "imageJobId": job["id"]},
        headers=user["headers"],
    ).json()
    display = layout.upload_path(job["id"], "display")
    assert display.exists()

    res = client.delete(f"/api/uploads/{job['id']}", headers=user["headers"])

    assert res.status_code == 204
    assert not display.exists()
    assert client.get(f"/api/uploads/{job['id']}", headers=user["headers"]).status_code == 404
    assert client.get(f"/api/forum/{post['id']}", headers=user["headers"]).status_code == 404


def test_you_cannot_delete_someone_elses_photo(client, user, other_user, dog_corpus):
    job = upload(client, user)

    res = client.delete(f"/api/uploads/{job['id']}", headers=other_user["headers"])

    assert res.status_code == 404
    assert layout.upload_path(job["id"], "display").exists()


def test_deleting_a_shared_photo_removes_it_from_the_gallery(client, user, dog_corpus):
    job = upload(client, user)
    finish(job["id"])
    client.post(f"/api/uploads/{job['id']}/share", headers=user["headers"])
    assert job["id"] in gallery_job_ids(client)

    client.delete(f"/api/uploads/{job['id']}", headers=user["headers"])

    assert job["id"] not in gallery_job_ids(client)


# --------------------------------------------------------- deleting an account


def test_deleting_an_account_erases_the_photos_but_keeps_the_conversation(
    client, user, other_user, dog_corpus
):
    """The rule: erase the person, keep the conversation.

    A thread other people replied to stops making sense with holes punched in
    it, so posts and comments survive as "[deleted user]" while everything that
    is *about* the person is destroyed.
    """
    job = upload(client, user)
    finish(job["id"])
    display = layout.upload_path(job["id"], "display")
    assert display.exists()

    post = client.post(
        "/api/forum", json={"body": "farewell", "imageJobId": job["id"]},
        headers=user["headers"],
    ).json()
    client.post(
        f"/api/forum/{post['id']}/comments", json={"body": "bye"},
        headers=other_user["headers"],
    )
    # A comment this user left on somebody *else's* thread.
    theirs = client.post(
        "/api/forum", json={"body": "their thread"}, headers=other_user["headers"]
    ).json()
    client.post(
        f"/api/forum/{theirs['id']}/comments", json={"body": "my parting words"},
        headers=user["headers"],
    )
    client.post("/api/forum/react", json={
        "targetType": "post", "targetId": theirs["id"], "kind": "like"
    }, headers=user["headers"])

    res = delete_account(client, user["password"], user["headers"])
    assert res.status_code == 204

    # The photo is gone from disk, and so is the row.
    assert not display.exists(), "their photo must not survive them"
    with SessionLocal() as db:
        assert db.query(UploadJob).filter_by(id=job["id"]).first() is None
        assert db.get(User, user["id"]) is None

    # The post survives, anonymised and without its picture.
    body = client.get(f"/api/forum/{post['id']}", headers=other_user["headers"]).json()
    assert body["authorId"] is None
    assert body["authorName"] == "[deleted user]"
    assert body["body"] == "farewell"
    assert body["image"] is None, "the photo went with the account"
    assert [c["body"] for c in body["comments"]] == ["bye"], "the reply is intact"

    # Their comment on someone else's thread survives too.
    other_thread = client.get(f"/api/forum/{theirs['id']}", headers=other_user["headers"]).json()
    assert [c["authorName"] for c in other_thread["comments"]] == ["[deleted user]"]
    assert other_thread["likeCount"] == 0, "a vote from a deleted account is withdrawn"


def test_the_old_token_stops_working_and_the_name_is_free_again(client, user):
    email, username = user["email"], user["username"]

    delete_account(client, user["password"], user["headers"])

    assert client.get("/api/auth/me", headers=user["headers"]).status_code == 401
    # No tombstone row is holding the unique columns, so someone can sign up as
    # them again.
    again = client.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "hunter2hunter2"},
    )
    assert again.status_code == 201


def test_deleting_an_account_needs_the_password(client, user):
    res = delete_account(client, "not-it", user["headers"])

    assert res.status_code == 400
    with SessionLocal() as db:
        assert db.get(User, user["id"]) is not None


def test_a_dm_thread_survives_one_side_leaving(client, user, other_user):
    conv = client.post(
        "/api/dm/conversations", json={"userId": other_user["id"]}, headers=user["headers"]
    ).json()
    client.post(
        f"/api/dm/conversations/{conv['id']}/messages",
        data={"body": "last word"},
        headers=user["headers"],
    )

    delete_account(client, user["password"], user["headers"])

    inbox = client.get("/api/dm/conversations", headers=other_user["headers"]).json()
    assert len(inbox) == 1
    assert inbox[0]["other"]["username"] == "[deleted user]"
    assert inbox[0]["canReply"] is False, "there is nobody left to reply to"

    history = client.get(
        f"/api/dm/conversations/{conv['id']}/messages", headers=other_user["headers"]
    ).json()
    assert [m["body"] for m in history["messages"]] == ["last word"]


def test_a_conversation_goes_when_both_participants_do(client, user_factory):
    a, b = user_factory(), user_factory()
    conv = client.post(
        "/api/dm/conversations", json={"userId": b["id"]}, headers=a["headers"]
    ).json()
    client.post(
        f"/api/dm/conversations/{conv['id']}/messages",
        data={"body": "just us"},
        headers=a["headers"],
    )

    delete_account(client, a["password"], a["headers"])
    delete_account(client, b["password"], b["headers"])

    with SessionLocal() as db:
        assert db.get(Conversation, conv["id"]) is None
        assert db.query(Message).filter_by(conversation_id=conv["id"]).count() == 0


def test_a_sent_attachment_is_erased_but_the_message_stays(client, user, other_user):
    """A video of the sender's face is their personal data wherever it sits."""
    conv = client.post(
        "/api/dm/conversations", json={"userId": other_user["id"]}, headers=user["headers"]
    ).json()
    message = client.post(
        f"/api/dm/conversations/{conv['id']}/messages",
        data={"body": "a picture of me"},
        files={"file": ("me.jpg", make_image(120, 120), "image/jpeg")},
        headers=user["headers"],
    ).json()
    path = layout.attachment_derivative_path(message["id"], "display")
    assert path.exists()

    delete_account(client, user["password"], user["headers"])

    assert not path.exists(), "the image goes"
    history = client.get(
        f"/api/dm/conversations/{conv['id']}/messages", headers=other_user["headers"]
    ).json()
    assert history["messages"][0]["body"] == "a picture of me", "the words stay"
    assert history["messages"][0]["attachment"] is None
    assert history["messages"][0]["senderName"] == "[deleted user]"


def test_a_deleted_account_leaves_the_leaderboard(client, user):
    """The leaderboard is a JSON file, not a table, so nothing cascades into it.

    `store.forget_player` is the hand-written stand-in for the foreign key it
    doesn't have; without it a deleted account keeps its high score forever
    under an id nobody can claim.
    """
    from app.game import store

    # Scores are recorded when a run *ends*, so put one on the board directly
    # rather than playing a whole game to death here.
    store.record_solo_run(str(user["id"]), user["username"], 7, 5)
    assert any(e["playerId"] == str(user["id"]) for e in store.top(store.BOARD_SOLO))

    delete_account(client, user["password"], user["headers"])

    assert not any(e["playerId"] == str(user["id"]) for e in store.top(store.BOARD_SOLO))
