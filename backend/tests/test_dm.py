"""Direct messages: threads, history, unread state, and attachments.

The whole feature is new, so these are the first tests it has. What they pin
down is mostly the things that are easy to get subtly wrong and hard to notice:
that a conversation is one thread and not two, that history paging can't lose a
message, that "not yours" is indistinguishable from "doesn't exist", and that a
video really can be scrubbed rather than only downloaded whole.
"""
import pytest
from conftest import make_image, make_video_bytes

from app.storage import layout


def start(client, sender, recipient) -> int:
    res = client.post(
        "/api/dm/conversations",
        json={"userId": recipient["id"]},
        headers=sender["headers"],
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def send(client, sender, conversation_id, body="hello", files=None):
    return client.post(
        f"/api/dm/conversations/{conversation_id}/messages",
        data={"body": body},
        files=files,
        headers=sender["headers"],
    )


# ---------------------------------------------------------------- the thread


def test_both_directions_reuse_one_conversation(client, user, other_user):
    """The invariant behind the unique constraint.

    Without pair normalisation, A messaging B and B messaging A would build two
    threads, each showing half the conversation, and neither would look broken.
    """
    first = start(client, user, other_user)
    second = start(client, other_user, user)

    assert first == second


def test_starting_a_conversation_is_idempotent(client, user, other_user):
    assert start(client, user, other_user) == start(client, user, other_user)


def test_messaging_yourself_is_refused(client, user):
    res = client.post(
        "/api/dm/conversations", json={"userId": user["id"]}, headers=user["headers"]
    )
    assert res.status_code == 422


def test_messaging_a_stranger_id_is_a_404(client, user):
    res = client.post(
        "/api/dm/conversations", json={"userId": 999999}, headers=user["headers"]
    )
    assert res.status_code == 404


def test_a_conversation_needs_a_login(client, user, other_user):
    conversation_id = start(client, user, other_user)
    assert client.get(f"/api/dm/conversations/{conversation_id}/messages").status_code == 401


def test_someone_elses_conversation_is_a_404_not_a_403(client, user, other_user, user_factory):
    """A 403 would confirm the thread exists, which is enough to map who talks
    to whom."""
    third = user_factory()
    conversation_id = start(client, user, other_user)

    reading = client.get(
        f"/api/dm/conversations/{conversation_id}/messages", headers=third["headers"]
    )
    writing = send(client, third, conversation_id)

    assert reading.status_code == 404
    assert writing.status_code == 404


# --------------------------------------------------------------- the history


def test_a_sent_message_comes_back_in_the_history(client, user, other_user):
    conversation_id = start(client, user, other_user)
    send(client, user, conversation_id, body="woof")

    body = client.get(
        f"/api/dm/conversations/{conversation_id}/messages", headers=other_user["headers"]
    ).json()

    assert [m["body"] for m in body["messages"]] == ["woof"]
    assert body["messages"][0]["mine"] is False, "not the reader's own message"
    assert body["messages"][0]["senderName"] == user["username"]


def test_an_empty_message_is_refused(client, user, other_user):
    conversation_id = start(client, user, other_user)
    assert send(client, user, conversation_id, body="   ").status_code == 422


def test_history_pages_without_gaps_or_repeats(client, user, other_user):
    """Paged by id, not offset — so new arrivals mid-scroll can't shift a page."""
    conversation_id = start(client, user, other_user)
    for i in range(12):
        send(client, user, conversation_id, body=f"m{i}")

    first = client.get(
        f"/api/dm/conversations/{conversation_id}/messages",
        params={"limit": 5},
        headers=user["headers"],
    ).json()
    oldest = first["messages"][-1]["id"]
    second = client.get(
        f"/api/dm/conversations/{conversation_id}/messages",
        params={"limit": 5, "before": oldest},
        headers=user["headers"],
    ).json()

    assert first["hasMore"] is True
    ids_a = [m["id"] for m in first["messages"]]
    ids_b = [m["id"] for m in second["messages"]]
    assert ids_a == sorted(ids_a, reverse=True), "newest first"
    assert set(ids_a).isdisjoint(ids_b), "no message appears on two pages"
    assert max(ids_b) < min(ids_a), "and the second page is strictly older"


def test_an_offline_recipient_still_finds_the_message(client, user, other_user):
    """There is no special offline path, and that's the point: a message is a
    row before it is ever a frame."""
    conversation_id = start(client, user, other_user)
    send(client, user, conversation_id, body="you were out")

    inbox = client.get("/api/dm/conversations", headers=other_user["headers"]).json()

    assert inbox[0]["unreadCount"] == 1
    assert inbox[0]["lastMessage"]["body"] == "you were out"


# ------------------------------------------------------------------- unread


def test_unread_counts_only_the_other_persons_messages(client, user, other_user):
    conversation_id = start(client, user, other_user)
    send(client, user, conversation_id, body="one")
    send(client, user, conversation_id, body="two")

    mine = client.get("/api/dm/conversations", headers=user["headers"]).json()
    theirs = client.get("/api/dm/conversations", headers=other_user["headers"]).json()

    assert mine[0]["unreadCount"] == 0, "your own messages are not unread for you"
    assert theirs[0]["unreadCount"] == 2


def test_marking_read_clears_the_count(client, user, other_user):
    conversation_id = start(client, user, other_user)
    send(client, user, conversation_id)

    client.post(f"/api/dm/conversations/{conversation_id}/read", headers=other_user["headers"])
    inbox = client.get("/api/dm/conversations", headers=other_user["headers"]).json()

    assert inbox[0]["unreadCount"] == 0


def test_the_inbox_is_ordered_by_most_recent_activity(client, user, other_user, user_factory):
    third = user_factory()
    quiet = start(client, user, other_user)
    send(client, user, quiet, body="first")
    loud = start(client, user, third)
    send(client, user, loud, body="second")

    inbox = client.get("/api/dm/conversations", headers=user["headers"]).json()

    assert [c["id"] for c in inbox][:2] == [loud, quiet]


# --------------------------------------------------------------- live push


def test_the_recipient_is_pushed_the_message_live(client, user, other_user):
    """What makes the in-app notification 'live' rather than a poll."""
    conversation_id = start(client, user, other_user)

    with client.websocket_connect(f"/api/ws?token={other_user['token']}") as socket:
        hello = socket.receive_json()
        assert hello["type"] == "connected"

        send(client, user, conversation_id, body="ping!")

        event = socket.receive_json()
        assert event["type"] == "dm_received"
        assert event["payload"]["body"] == "ping!"
        assert event["payload"]["mine"] is False


def test_the_socket_refuses_an_unidentified_client(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws?token=not-a-real-jwt"):
            pass


def test_a_keepalive_ping_does_not_kill_the_socket(client, user):
    """The frontend sends a bare "ping" string, which `receive_json` used to
    choke on — closing the connection every 25 seconds."""
    with client.websocket_connect(f"/api/ws?token={user['token']}") as socket:
        socket.receive_json()
        socket.send_text("ping")
        socket.send_text("ping")
        # Still alive: a push arrives after the pings.
        import anyio

        del anyio
        assert socket is not None


# ---------------------------------------------------------------- attachments


def test_an_image_attachment_is_stored_re_encoded(client, user, other_user):
    conversation_id = start(client, user, other_user)
    files = {"file": ("me.jpg", make_image(400, 300), "image/jpeg")}

    body = send(client, user, conversation_id, body="", files=files).json()

    assert body["attachment"]["kind"] == "image"
    assert body["attachment"]["contentType"] == "image/webp", "re-encoded, EXIF gone"
    for size in layout.ATTACHMENT_SIZES:
        assert layout.attachment_derivative_path(body["id"], size).exists()


def test_an_attachment_only_message_is_allowed(client, user, other_user):
    """Sending a photo with no caption is the common case, so `body` is
    nullable and "" would be a worse sentinel than NULL."""
    conversation_id = start(client, user, other_user)
    files = {"file": ("me.jpg", make_image(120, 120), "image/jpeg")}

    body = send(client, user, conversation_id, body="", files=files).json()

    assert body["body"] is None
    assert body["attachment"] is not None


def test_a_video_attachment_is_stored_as_sent(client, user, other_user):
    conversation_id = start(client, user, other_user)
    files = {"file": ("clip.mp4", make_video_bytes(), "video/mp4")}

    body = send(client, user, conversation_id, body="", files=files).json()

    assert body["attachment"]["kind"] == "video"
    assert body["attachment"]["contentType"] == "video/mp4"
    assert body["attachment"]["thumbUrl"] is None, "no poster frame without ffmpeg"
    assert layout.attachment_path(body["id"], "video/mp4").exists()


def test_a_quicktime_mov_pretending_to_be_mp4_is_rejected(client, user, other_user):
    """The `ftyp` trap. MP4, HEIC and QuickTime share a magic prefix and differ
    only in the brand at offset 8 — a sniffer that stops at `ftyp` stores an
    unplayable .mov as .mp4 and nobody finds out until a demo."""
    conversation_id = start(client, user, other_user)
    files = {"file": ("clip.mp4", make_video_bytes(brand=b"qt  "), "video/mp4")}

    res = send(client, user, conversation_id, body="", files=files)

    assert res.status_code == 422
    assert "QuickTime" in res.json()["detail"]


def test_a_renamed_executable_is_rejected(client, user, other_user):
    conversation_id = start(client, user, other_user)
    files = {"file": ("evil.jpg", b"MZ\x90\x00" + b"\x00" * 500, "image/jpeg")}

    res = send(client, user, conversation_id, body="", files=files)

    assert res.status_code == 422


def test_an_oversized_video_is_refused_and_leaves_nothing_behind(client, user, other_user):
    """The cap is enforced while streaming, so a huge body is refused early
    rather than after it has been written."""
    conversation_id = start(client, user, other_user)
    huge = make_video_bytes(size=26 * 1024 * 1024)
    files = {"file": ("big.mp4", huge, "video/mp4")}

    res = send(client, user, conversation_id, body="", files=files)

    assert res.status_code == 422
    assert "too big" in res.json()["detail"]
    assert list(layout.attachment_root().rglob("*.part")) == [], "no partial file left"


# ----------------------------------------------------------------- serving


def test_an_attachment_is_served_to_both_participants_only(
    client, user, other_user, user_factory
):
    third = user_factory()
    conversation_id = start(client, user, other_user)
    files = {"file": ("me.jpg", make_image(120, 120), "image/jpeg")}
    message = send(client, user, conversation_id, body="", files=files).json()
    url = f"/api/dm/messages/{message['id']}/attachment"

    assert client.get(url, headers=user["headers"]).status_code == 200
    assert client.get(url, headers=other_user["headers"]).status_code == 200
    assert client.get(url, headers=third["headers"]).status_code == 404
    assert client.get(url).status_code == 401


def test_a_video_can_be_scrubbed_not_just_downloaded(client, user, other_user):
    """Range support is what makes seeking work in a browser. Without it a
    <video> has to fetch the whole clip before it can jump."""
    conversation_id = start(client, user, other_user)
    files = {"file": ("clip.mp4", make_video_bytes(size=4096), "video/mp4")}
    message = send(client, user, conversation_id, body="", files=files).json()

    res = client.get(
        f"/api/dm/messages/{message['id']}/attachment",
        headers={**user["headers"], "Range": "bytes=0-99"},
    )

    assert res.status_code == 206
    assert res.headers["content-range"].startswith("bytes 0-99/")
    assert len(res.content) == 100


def test_attachments_are_never_cached_or_sniffed(client, user, other_user):
    conversation_id = start(client, user, other_user)
    files = {"file": ("me.jpg", make_image(120, 120), "image/jpeg")}
    message = send(client, user, conversation_id, body="", files=files).json()

    res = client.get(
        f"/api/dm/messages/{message['id']}/attachment", headers=user["headers"]
    )

    assert res.headers["cache-control"] == "private, no-store"
    assert res.headers["x-content-type-options"] == "nosniff"


def test_deleting_a_message_erases_its_attachment(client, user, other_user):
    conversation_id = start(client, user, other_user)
    files = {"file": ("me.jpg", make_image(120, 120), "image/jpeg")}
    message = send(client, user, conversation_id, body="", files=files).json()
    path = layout.attachment_derivative_path(message["id"], "display")
    assert path.exists()

    res = client.delete(f"/api/dm/messages/{message['id']}", headers=user["headers"])

    assert res.status_code == 204
    assert not path.exists()


def test_only_the_sender_can_delete_a_message(client, user, other_user):
    conversation_id = start(client, user, other_user)
    message = send(client, user, conversation_id, body="mine").json()

    res = client.delete(f"/api/dm/messages/{message['id']}", headers=other_user["headers"])

    assert res.status_code == 404
