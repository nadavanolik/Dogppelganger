# Making users real, end to end

> **Status:** approved 2026-08-20, not yet started. Implementation deferred to a
> later session. Nothing in this plan has been built.
>
> Target branch: `feat/real-users`, cut from `main` at `9e5eda8`. No PR yet — so
> nothing here triggers a deploy until it lands on `main`.

## Context

Users don't work. The app already has a genuine account system — a `users`
table, bcrypt hashing, JWT issuing, and a `get_current_user` dependency — and
**none of it is connected to anything**. `grep` confirms
`backend/app/deps.py:13`'s `get_current_user` is imported by zero routers.
Every other feature identifies the caller by a string the browser makes up:

- `UploadJob.owner_id` is `String(64)`, not a foreign key. Ownership of a
  private photo is string equality at `backend/app/uploads/router.py:184`.
- `Post.author_id`, `Comment.author_id`, `Reaction.user_id` — same.
- `Match.user_id` is a real FK but nullable, populated from `MatchCreate.userId`,
  a number the client types in.
- `GET /api/matches` returns the 50 most recent matches **globally**.
- The SPA's login (`src/lib/store.tsx:236-240`) never checks the password.
  `src/routes/login.tsx:20` says so on screen: *"Prototype: any password works."*

The docs already admit it. `MIGRATION.md:116` lists as a good first task:
*"Wire login/signup to `/api/auth/*` and store the JWT; send it on the
WebSocket."* `MIGRATION.md:117` adds *"route DM events to recipients."*
`ProjectPlan.md:20` specifies the intended model exactly.

**Outcome:** real accounts with hashed passwords; every photo, post and game
player owned by a real user row through a real foreign key; private photos that
stay private; and the direct-messaging system the docs promise — persisted
history with image and video attachments, retrievable per user, with live
in-app notification of new messages.

Lands on a **feature branch, no PR yet**. Nothing reaches `main`, so no deploy
fires until you decide.

---

## Decisions

| Decision | Choice |
|---|---|
| Identity reach | Everything — uploads, matches, forum, comments, reactions, games |
| Existing data | Wipe and start clean; no backfill |
| Token storage | `localStorage` + `Authorization: Bearer` |
| Account deletion | **Anonymize** — content survives as `[deleted user]`; photos and personal data erased |
| DM attachments | **In scope** — images ≤10MB, video ≤25MB |
| Admins | **Dropped** — no `is_admin`, no admin screen, nothing references a role |
| User discovery | Search by username; returns id + username only, never email |
| Gallery | Shared human↔dog **matches** only |
| Leaderboards | Stay in the JSON file store, keyed by `str(user.id)` |
| HEIC / iPhone photos | **Deferred** — recorded with the other pending fixes, not built here |

---

## 1. Schema

All in `backend/app/models.py`.

### 1.1 `User`

Add `updated_at` and `token_version` (Integer, NOT NULL, default 0), and an
index on `username` for the directory search.

`create_access_token` embeds a `tv` claim; `get_current_user` rejects a token
whose `tv` doesn't match the row. Six lines, and it's the only thing that makes
"change your password and other sessions die" true — otherwise a stolen 24-hour
token outlives the password it was issued against and the endpoint is theatre.

Add a password validator: minimum 8 characters, **maximum 72 bytes**. bcrypt
silently truncates past 72 and `bcrypt==4.2.1` raises on some inputs. Signup
currently accepts anything non-empty.

No avatar column, no roles, no soft-delete.

### 1.2 The identity columns become real foreign keys

The wipe is what makes this possible — `VARCHAR(64)` holding `"u_moodyoak"`
cannot be migrated to an integer FK by any sensible `USING` expression.

The anonymize decision splits them in two. The rule: **a row that is *about* the
person dies with them; a row *addressed to other people* survives without them.**

**Nullable, `ondelete="SET NULL"` — survives as `[deleted user]`:**
`posts.author_id`, `comments.author_id`, `messages.sender_id`,
`conversations.user_a_id`, `conversations.user_b_id`.

**NOT NULL, `ondelete="CASCADE"` — dies with the account:**

| Table | Why |
|---|---|
| `upload_jobs.owner_id` | The photo *is* the personal data. `DATA_STORAGE.md:274` already sets the retention rule. |
| `matches.user_id` | A private result about one person's face. Also stops being nullable. |
| `notifications.user_id` | Addressed to that person alone. |
| `reactions.user_id` | It records what a specific person liked — that's the data being erased. Also, a NULL would break `uq_reaction_target_user`, since NULLs don't collide: one ghost could accumulate unlimited likes on one post. Counts drop when someone leaves; that's the honest outcome. |

**Conversation nullability is forced, not chosen.** If the participant columns
stayed NOT NULL, deleting one person would require deleting the conversation,
cascading away the *other* person's messages — contradicting the whole decision.
Two consequences accepted deliberately: `uq_conversation_pair` stops preventing
duplicates once a side is NULL (harmless — the get-or-create helper only ever
looks up two live ids, and a NULL side can never be re-paired), and the
`CHECK (user_a_id < user_b_id)` still holds, because a comparison with NULL is
NULL and both engines treat a NULL CHECK as satisfied.

**`Post.image_job_id` must become `ondelete="SET NULL"`** — upload jobs cascade
away, so without this a surviving post points at a deleted job. The behaviour
that falls out is exactly right: **a deleted user's post keeps its words and
loses its photo.** `_image_dict()` at `backend/app/forum/router.py:57` already
returns `None` for a missing job, so the read path needs no change.

**Drop `Post.author_name` and `Comment.author_name`.** Denormalised snapshots
that existed only because there was no user row to join to. Serialise
`post.author.username` with `joinedload(Post.author)` so the feed stays one
query — which is also what makes a rename propagate to every post the user
ever made.

**Cascades are a safety net, not the mechanism.** SQLite doesn't enforce
`ondelete` without `PRAGMA foreign_keys=ON`, which `backend/app/database.py`
never issues — so cascades fire in production Postgres and silently don't under
pytest. Deletion is done explicitly in Python so the tests exercise the
production path.

**Email and username are reclaimable with no extra work.** `delete_user`
removes the `users` row outright (anonymization happens on *other* tables), so
the unique indexes release both values immediately. Say so in the confirmation
dialog. A tombstone row would need the unique columns scrambled to free them and
would give every serializer a third state — rejected.

### 1.3 `Match` stays

`models.py:161-165` already flags the `Match`/`UploadJob` overlap as a
follow-up. It stays one — collapsing them means rewriting the synchronous
`POST /api/match` path and has no bearing on "users are real". Two cheap fixes
only: `user_id` comes from `Depends(get_current_user)` (delete `userId` from
`schemas.MatchCreate`), and `GET /api/matches` returns the caller's own.

### 1.4 `UploadJob.shared_at` — the gallery flag

Nullable indexed DateTime. NULL means private, which is the default.

A timestamp rather than a boolean: `shared: bool` plus `shared_at: datetime`
would be two columns for one fact that can disagree, and the timestamp carries
both — "is it shared" is `IS NOT NULL`, and it gives the gallery the right sort
key. A photo uploaded last week and shared today belongs at the top of
"recently shared", which `created_at` cannot express.

Two sharing concepts now live independently on the job: `shared_at IS NOT NULL`
means it's in the public gallery; `Post.image_job_id == job.id` means it backs a
forum post. `GET /api/forum/shareable` is unaffected.

`ProjectPlan.md:104` already specs the endpoints and `:99` puts a "Share to
gallery" button on the result page. Note **`shareMatch` exists in
`src/lib/store.tsx:244` but no page calls it** — the button has to be built, not
just rewired.

### 1.5 DM tables — `conversations` + `messages`

Two tables, not one. A single `messages(sender_id, recipient_id, …)` table looks
simpler until the inbox query: grouping by an unordered pair needs
`LEAST/GREATEST` on Postgres and `MIN/MAX` on SQLite — different function names,
which breaks the "tests on SQLite, production on Postgres" arrangement this repo
depends on, in the one query that must not be wrong. A conversation row also
gives `/messages/:id` (already a route at `src/router.tsx:47`) a stable id.

**`conversations`** — `id`, `user_a_id`, `user_b_id`, `created_at`,
`last_message_at` (indexed; denormalised so the inbox sorts without a correlated
subquery per row). Invariant `user_a_id < user_b_id`, enforced by a
`CheckConstraint` and by the get-or-create helper — that's what makes
`UniqueConstraint(user_a_id, user_b_id)` mean "one thread per pair" rather than
"one per direction".

**`messages`** — `id`, `conversation_id`, `sender_id`, `body` (nullable),
`created_at`, `read_at` (NULL = unread), plus the attachment columns in §1.6.
Indexes on `(conversation_id, id)` for history and `(conversation_id, read_at)`
for unread counts, and
`CheckConstraint("body IS NOT NULL OR attachment_kind IS NOT NULL")` so a
completely empty row is impossible.

**`body` is nullable** because an attachment-only message (send a clip, no
caption) is the common case, and the empty string is a worse sentinel — it makes
"no caption" and "caption of whitespace" indistinguishable after `.strip()`.

Ordering and pagination are by `id`, not `created_at` — `datetime.utcnow` ties
are real at this write rate and the id is monotonic. Cursor is `?before=<id>`,
matching `ProjectPlan.md` §2.16. Unread for the whole inbox is one grouped query:
`WHERE conversation_id IN (:ids) AND sender_id != :me AND read_at IS NULL`.

### 1.6 Message attachments

**Columns on `messages`, not an attachments table.** One message carries at most
one attachment — the composer at `src/routes/messages.$id.tsx:96-130` is a
single file input, and that's the product. A 1:1 table whose rows are always
created and destroyed with their parent is a join pretending to be a decision.
If attachments are ever wanted on forum posts too, promote to a table then; the
columns are purely additive.

`attachment_kind` (`"image"`/`"video"`/NULL — the all-or-nothing flag),
`attachment_content_type` (from **our** allowlist, never the client's header),
`attachment_byte_size`, `attachment_width`/`_height` (images only),
`attachment_name` (original filename, display only, never used to build a path).

**No path column.** The path is a pure function of `(message.id, content_type)`,
the same principle `UploadJob` and `DogAsset.slug` already follow. Storing a path
invites the row and the disk to disagree.

**Disk layout** — new helpers in `backend/app/storage/layout.py`, mirroring the
upload section exactly, including `SHARD_SIZE = 1000` sharding on the row id and
the deliberate "nothing user-identifying in the path" property:
`attachment_root()` (`$ATTACHMENT_DATA_DIR`, default `data/attachments`),
`attachment_shard()`, `attachment_path()`, `attachment_derivative_path()`,
`ensure_attachment_dirs()`, and `delete_attachment_files()` with the same
signature and FileNotFoundError-tolerant contract as `delete_upload_files`.

In Docker: `ATTACHMENT_DATA_DIR: /app/data/attachments` on the existing
`gamedata` volume. In tests: the same variable in `conftest.py`'s env block,
**before any app import**.

**Images reuse `backend/app/storage/imaging.py` unchanged** — `decode()` (which
proves the bytes really are an image, applies EXIF orientation, then drops
EXIF/GPS), `write_derivatives()`, and `ImageRejected`. An image attachment is
stored as a `display` (512) + `thumb` (256) webp pair. No `orig`: no ML runs on
a DM photo, so a full-size copy is pure disk cost.

**Video is stored byte-for-byte after sniffing, and that limitation must be
stated in the code.** We cannot prove an `.mp4` is a video the way `decode()`
proves a JPEG is an image. Layered mitigations instead:

1. **`Content-Length` pre-check** → 413 before reading a byte.
2. **Magic-byte sniff on the first 32 bytes**, before anything is written. The
   client's `Content-Type` and filename are hints, never used to pick the stored
   extension or the served media type.
   **The `ftyp` trap:** HEIC images, MP4 video *and* iPhone `.mov` all begin with
   a size field followed by `ftyp` at offset 4. They are told apart only by the
   brand at offset 8 — `isom`/`iso2`/`mp41`/`mp42`/`avc1`/`mp4v` → `video/mp4`;
   `qt  ` → QuickTime, **rejected** (Chrome can't play it). A sniffer that stops
   at `ftyp` will happily store an unplayable `.mov` as `.mp4`. WebM/Matroska is
   EBML magic `1A 45 DF A3`.
3. **Streamed size cap, not buffered.** `backend/app/uploads/router.py` does
   `data = await upload.read()` — the whole file into memory. At 25MB on a 1GB VM
   that's a footgun, so attachments read in 1MB chunks and abort mid-write when
   the running total exceeds the cap, unlinking the partial file.
4. **We choose the extension and the served `media_type`** from our own
   allowlist; `X-Content-Type-Options: nosniff` on the response; and nginx never
   serves this directory, so there is no path where a stored file is returned
   without the FastAPI gate running.

Move the image magic table out of `uploads/router.py:41-44` into a shared
sniffer so the two upload paths can't drift about what a PNG is.

**Serving:** `GET /api/dm/messages/{id}/attachment?size=`. Gated on "am I a
participant in this conversation" → otherwise **404**.
**Range support is confirmed, not assumed**: `fastapi==0.115.6` pins Starlette
0.41.3, whose `FileResponse` sets `accept-ranges: bytes`, parses `Range` and
`If-Range`, and emits `206` with `Content-Range` (and `416` when unsatisfiable).
So video scrubbing works with no extra code — **do not wrap it in
`StreamingResponse`**, which would throw all of that away.
Headers: `Cache-Control: private, no-store`, `nosniff`.

**No ffmpeg, no transcoding.** It adds 100MB+ to an image already carrying a
350MB ONNX encoder, costs minutes of CPU per clip on a 1GB VM also running
Postgres and an ML matcher, and needs its own job queue — a second
`uploads/queue.py` for "attach a clip to a chat message".
**Consequence, stated plainly: no server-generated poster frame.** Fallbacks:
in the bubble, `<video preload="metadata" controls src="…#t=0.1">` — the media
fragment makes every current browser fetch just enough (via the Range support
above) to paint the frame at 0.1s as the poster; overlay a play glyph. In the
inbox preview line (`messages.index.tsx:47-49`), show `🎬 Video` / `🖼 Photo` /
the body text — loading 25MB to draw a 40px list preview would be the actual bug.

### 1.7 `notifications` table

`id`, `user_id`, `kind`, `text`, `href`, `read_at`, `created_at`.

**No notification row per DM.** That would be one row per chat message and two
competing unread models. The 💌 badge reads the DM unread total; the 🔔 badge
reads this table — which is already how `src/components/AppShell.tsx:36-43`
renders them.

---

## 2. Backend route changes

`◆` = drops a client-supplied identity parameter in favour of `Depends(get_current_user)`.

| Endpoint | Becomes |
|---|---|
| `POST /api/uploads` | ◆ drop the `ownerId` form field, `_clean_owner_id`, `MAX_OWNER_ID` |
| `GET /api/uploads`, `/{id}` | ◆ 404 (not 403) when it isn't yours |
| `GET /api/uploads/{id}/image` | media-token auth; three-arm rule in §3 |
| `POST/DELETE /api/uploads/{id}/share` | **new**, owner only; 422 unless `status == "done"` and it has a dog |
| `GET /api/gallery` | **new, public**; `?limit=&offset=` |
| `POST /api/match`, `GET /api/matches` | ◆ caller's own only |
| `GET/POST /api/forum*`, `/react`, `/shareable` | ◆ every identity param removed from bodies and query strings |
| `POST /api/game/rooms`, `/solo/start`, `/solo/match/start` | ◆ `PlayerRef` deleted from `backend/app/game/router.py` |
| `POST /api/game/solo/answer`, `/solo/match/submit` | + reject a `runToken` whose run belongs to someone else (`solo.Run.player_id` already exists) |
| `GET /api/dogs/*`, `/api/health`, `/api/game/leaderboard/{b}` | stay anonymous |

**403 vs 404.** `ProjectPlan.md:107` says 403; `backend/tests/test_matching.py:327`
asserts 404 and explains why (*"a 403 would confirm the id exists"*). Keep the
404 and **fix the doc** — a 403 on a nonexistent id versus a 404 on a real one
is a working enumeration oracle for other people's photos, exactly what
`DATA_STORAGE.md:63-66` promises against. Same rule for DM conversations.
The one exception: posting a forum image you don't own stays **403**, because you
picked it from your own list, so its existence is not a secret.

### WebSockets

| Socket | Becomes |
|---|---|
| `/api/ws` | the one real-time channel: `dm_received`, `dm_read`, `notification`, `upload_update` |
| `/api/uploads/ws` | **deleted**; its notifier merges into `ConnectionManager` |
| `/api/game/ws` | `?token=` only — delete `_identify`'s fallback (`backend/app/game/ws.py:64-77`), which its own docstring asks for |

Token reaches a socket as `?token=` — browsers can't set headers on a
`WebSocket` handshake. **Pass the short-lived media token, not the 24-hour access
token**, so what lands in nginx's access log expires in 15 minutes and is
useless against REST anyway (the scope claim blocks it). That beats turning off
`access_log`, which would cost real debugging visibility and still wouldn't
address browser history.

### Two bugs fixed on the way

1. **`/api/ws` crashes on the ping the frontend already sends.**
   `backend/app/routers/ws.py` uses `receive_json()`; `src/lib/uploadSocket.ts:38`
   sends the bare string `"ping"`. → `receive_text()` + a guarded parse.
2. **A socket leak.** `manager.disconnect()` is only called in the
   `except WebSocketDisconnect` branch, so any other exception leaves a
   registration forever. → move it to `finally`. Also take the resilient `send`
   from `backend/app/uploads/ws.py:41-49`, which discards dead sockets;
   `send_to_user` currently lets one dead tab abort a whole fan-out.

---

## 3. Photo access — the rule, and the bug it replaces

Today `src/routes/forum.index.tsx:70` and `forum.$id.tsx:110` render other
people's uploads by calling `uploadImageUrl(post.authorId, …)` — passing **the
author's** id as `ownerId`. The ownership check is defeated by anyone who reads
the post JSON. That's a live bug, and it means the new rule cannot be
"owner only" or every forum thumbnail 404s the moment auth is real.

> An upload's image is returned if the match is **shared to the gallery** (no
> authentication required), **or** the requester is the **owner**, **or** the job
> **backs a forum post** and the requester is logged in. Everything else is a 404.

The unauthenticated arm is required by the docs, not invented:
`ProjectPlan.md` §2.6 marks `/gallery` AUTH, but §2.1 marks the landing page
PUBLIC and specifies `GET /api/gallery/featured` as *"read-only, cached, no
auth"* — and `src/routes/index.tsx:19-21` really does render shared matches to
logged-out visitors. That's coherent: sharing is an opt-in publication by the
owner. `DATA_STORAGE.md:63-66` needs one amended sentence saying so.

**Unsharing takes effect immediately.** A media token only says *who you are*;
it never grants access to an object. The share/owner/post check re-runs against
the DB on every request. Keep `Cache-Control: private, no-store`
(`uploads/router.py:222`) on the shared arm too — a grid of 256px webps doesn't
need caching badly enough to make unsharing take an hour.

---

## 4. New endpoints

### 4.1 Account management

`PATCH /api/users/me` (username/email; 409 on conflict; require
`currentPassword` for an email change since it's the login identifier),
`POST /api/users/me/password` (verify → rehash → bump `token_version` → return a
**fresh** token so the caller's own tab survives while other sessions 401),
`DELETE /api/users/me` (requires the password), and
`GET /api/users?q=&limit=20` — the DM directory, returning `[{id, username}]`
only, never emails. That last one replaces `state.users.filter(...)` at
`src/routes/messages.index.tsx:24`.

### 4.2 DMs — `backend/app/routers/dm.py`, prefix `/api/dm`

`GET /conversations` (ordered by `last_message_at desc`; two queries total),
`POST /conversations` (get-or-create, idempotent; 422 for yourself, 404 for an
unknown id), `GET /conversations/{id}/messages?before=&limit=50`,
`POST /conversations/{id}/messages` (multipart: body and/or file),
`POST /conversations/{id}/read`, `DELETE /messages/{id}` (sender only),
`GET /messages/{id}/attachment`.

**Send over REST, not over the socket.** `ProjectPlan.md` §2.16 allows either;
REST gives one persistence path, works when the socket is flapping, and is
testable with `TestClient` without a WebSocket dance. The socket becomes a pure
push channel — which is what `backend/app/uploads/ws.py` already is.

The handler is `async def` with the indexed SQLAlchemy calls inline and the
Pillow work in `asyncio.to_thread` — precedent at
`backend/app/uploads/router.py::upload_images`, which does exactly this.

### 4.3 Deletion — `backend/app/services/users.py::delete_user`

One transaction, every step explicit:

1. `store.forget_player(str(user.id))` — a new function in
   `backend/app/game/store.py`, the one non-SQL store.
2. Erase upload files via `layout.delete_upload_files`, and **null
   `Post.image_job_id` for those jobs first** — Postgres enforces that FK and
   would raise, even though SQLite wouldn't.
3. Erase the attachment files of every message this user **sent**, and null the
   `attachment_*` columns — a video of the sender's face is their personal data
   no matter whose inbox it sits in. The bubble then shows the caption, or a
   muted "attachment removed".
4. Delete rows: reactions, notifications, matches, upload jobs.
5. **Null** `posts.author_id`, `comments.author_id`, `messages.sender_id`.
6. Delete a conversation (and its messages and files) only when **both**
   participants are gone.
7. Delete the user row — freeing the email and username for reuse.
8. `await manager.disconnect_user(user_id)` — otherwise a socket authenticated a
   minute ago keeps receiving pushes for an account that no longer exists.

**The confirmation dialog must say this verbatim**, or it reads as a dark
pattern: *"Your photos, matches and reactions are erased, including photos and
videos you sent in chats. Posts, comments and messages you sent stay, credited
to [deleted user]."*

### 4.4 Serialization contract

**The API never sends a null display name.** Every author/sender field is a pair
— `authorId: number | null` plus `authorName: string`, where the name is
`"[deleted user]"` when the id is null. One ~6-line helper (`author_ref`), used
by `_comment_dict` (`forum/router.py:69`), `_post_dict` (`:80`), and the new DM
serializers. The frontend then does exactly one null check, and only for
*affordances* — the profile link, the "message this author" button — never for
rendering text. `mine = msg.sender_id == me.id` must be an id compare, never a
name compare. Conversations gain `"canReply": other is not None` so the client
doesn't have to infer it.

---

## 5. Frontend

### 5.1 `src/lib/auth.tsx` — the real session

`status: "loading" | "authed" | "anon"`. Token in
`localStorage["dogppelganger_token"]`; the media token in memory only; the user
object **not** persisted, so a renamed or deleted account doesn't linger.
Bootstrap re-fetches `GET /api/auth/me`.

**`status: "loading"` is load-bearing.** Without it every guard sees
`user === null` on the first frame after a hard refresh and bounces a logged-in
user to `/login`. This is the most common bug in this refactor — comment it.

### 5.2 `src/lib/api.ts` — one request helper

Injects the Bearer header, unwraps FastAPI's `detail`, routes 401 to logout,
keeps the existing "Can't reach the server. Is the backend running?" message.
Replaces three near-identical helpers at `src/lib/uploadApi.ts:83`,
`forumApi.ts:50`, `gameApi.ts:147`.

⚠️ **Must not set `Content-Type` for a `FormData` body** — the browser has to
supply the multipart boundary. `uploadApi.ts:105` gets this right today by
omitting headers; preserve that.

A module-level token plus a setter, not a hook — these are plain modules called
from effects, and threading a token through every call site is a much larger diff.

### 5.3 `<img>` and `<video>` can't send headers

Solved with a **short-lived scoped media token**:
`create_media_token(user_id, minutes=15)` issues a JWT carrying `scope: "media"`;
`decode_token` refuses a token *with* that scope and `decode_media_token`
refuses one *without*, so neither can be replayed as the other. Minted by
`GET /api/auth/media-token` and returned by login/signup/`me`; appended as `&t=`.

**Video settles this decision.** The alternative — `fetch` +
`URL.createObjectURL` — would force the entire 25MB clip to download before the
first frame plays and would discard Range seeking completely. It also kills HTTP
caching and `loading="lazy"` for images and touches every render site.

The token must still be valid for the browser's *second* request — the Range
request fired when someone drags the scrub bar minutes later. 15 minutes covers a
viewing session; if it expires mid-scrub the `<video>` fires `error` and a ~3-line
`onError` re-mints and re-assigns `src`, resuming from the same `currentTime`.

`uploadImageUrl(jobId, size)` loses its `ownerId` argument entirely.

### 5.4 Router guards — `src/router.tsx`

Replace the per-page `RequireAuth` card (`src/components/AppShell.tsx:213`, used
by only 3 of 18 routes and which never redirects or preserves the destination)
with two layout routes: `PublicOnly` (login/signup) and `Protected` (renders
nothing while loading, else `<Navigate to={"/login?return_to=" + …} replace/>`).
`/` and `/gallery` stay public.

This is `ProjectPlan.md` §3 verbatim, and it removes every `state.user!`
assertion (`game.tsx:115`, `lobbies.index.tsx:30`, `messages.index.tsx:21`,
`notifications.tsx:19`) and every `state.user ?? state.users[0]` fallback
(`forum.*.tsx`, `upload.tsx:31`, `result.$id.tsx:36`) — each of which currently
makes an anonymous visitor act as a seeded fake user.

### 5.5 Draining `src/lib/store.tsx`

Two steps, so every phase compiles:

1. **Shim (phase 2).** `state.user` becomes a passthrough of `useAuth()`, and
   `login`/`signup`/`logout` proxy to the real API. Delete the three seeded
   accounts and the password-ignoring `login()`. Every page keeps working.
   `User.id` goes `string → number`, which surfaces every stale call site —
   a feature, and CI already runs `npm run typecheck`.
2. **Drain (phases 5–8).** Each phase deletes its slice: gallery kills
   `state.matches`, DMs kill `state.conversations` and `state.users`,
   notifications kill `state.notifications` and the fake queue-progression
   effect at `store.tsx:177-227` (which fabricates queued→processing→done
   transitions the real backend already sends). Then delete `store.tsx` and
   `src/lib/mock.ts`.

`DogCard.tsx` takes the mock `DogMatch` type — widen it to plain props so it
serves both the gallery and the landing page.

### 5.6 Sockets and pages

One `src/lib/appSocket.tsx` provider mounted in `RootLayout`, connecting only
when authed, reusing the reconnect-with-backoff and 25s keep-alive loop from
`src/lib/uploadSocket.ts:24-70` — that file is deleted, but its loop is the good
part (25s because nginx closes idle proxied connections at 60s).

New or rewritten: real `login.tsx`/`signup.tsx` (delete the "any password works"
copy and the seeded-account buttons), `/settings`, both `messages` pages, a share
toggle on the result page and profile, real `gallery.tsx` and landing,
`notifications.tsx` and the bell.

---

## 6. Reset

`backend/scripts/migrate_schema.py` cannot express this — its `ADDED`/`DROPPED`
dicts add and drop columns; they cannot turn `VARCHAR(64)` into an integer FK.
That's exactly why wiping was the right call.

**Don't adopt Alembic during this change — adopt it immediately after.** The
script's own docstring says to switch when the schema starts changing regularly,
and a new table plus five type changes is that moment. Doing it now means
debugging Alembic and a schema rewrite simultaneously. Sequence: wipe → land the
new schema → generate an Alembic baseline as a follow-up commit.

**New `backend/scripts/reset_db.py`**, deliberately hard to run by accident:
requires `--yes` **and** `ALLOW_DB_RESET=1`, prints the target `DATABASE_URL` and
the directories it will empty first, then `drop_all`/`create_all` and removes
`layout.upload_root()`, `layout.attachment_root()` and `leaderboards.json`
(which is full of dead strings like `"p_a"` and `"u_moodyoak"`).
**It never touches `layout.dog_root()`** — 226MB of ingested corpus you don't
want to re-download — and says so out loud.

⚠️ **`docker compose down -v` is the wrong tool** — it destroys the `dogdata`
volume too.

On the VM this runs **once, manually, at merge time**, between
`docker compose pull` and `up -d`. Never in `deploy.yml` — a destructive step
must not run on every push. `deploy.yml` keeps its `migrate_schema.py` line;
after the reset it's a no-op that prints "nothing to do".

**`SECRET_KEY` must stop defaulting.** `backend/app/config.py` defaults to
`dev-secret-change-me` and `docker-compose.yml` to `change-me`. Harmless while
auth was dead; token forgery for anyone once it's live. Refuse to start when
it's a known default against a Postgres URL. (Side note: `SECRET_KEY` also salts
the game's answer key in `app/game/content.py`, so rotating it changes in-flight
game answers — harmless, but surprising.)

**`nginx.conf` needs `client_max_body_size 30m;` in the `location /api/` block.**
See §8 — this is a pre-existing production bug, not a new requirement.

---

## 7. Testing

**There is currently no auth test at all** — zero tests touch `/api/auth`,
hashing, JWT or `get_current_user`.

New fixtures in `backend/tests/conftest.py`: `ATTACHMENT_DATA_DIR` in the env
block before any app import; a `user_factory` that signs up through the real API;
`user`, `other_user`, `auth_client`; and a `make_video_bytes(brand=b"isom")`
helper producing a minimal valid `ftyp` box — about six lines, no binary
committed, the same philosophy as the existing `make_image()`.

⚠️ **Emails must be unique per fixture call.** The `client` fixture reuses one
SQLite file for the whole session and nothing truncates `users`, so a fixed
address 409s on the second test that uses it.

**`test_auth.py`** (new): the stored column is a bcrypt hash, not the plaintext;
duplicate email and username → 409; an over-72-byte password is rejected rather
than silently truncated; wrong password and unknown email return the **same**
detail string (no enumeration); missing, malformed, wrong-key, expired and
deleted-user tokens all 401; `token_version` invalidates old tokens after a
password change; a username change shows up in that user's forum posts (proving
`author_name` is gone); every newly-protected route 401s with no header.

**Deletion tests** are the valuable ones: files gone from disk for every size in
`layout.UPLOAD_SIZES`; attachment files gone; the old token 401s; the email and
username are immediately re-registrable; **the post still returns 200** with
`authorId: null`, `authorName: "[deleted user]"` and `image: null`; a comment
they left on someone else's post survives; a post they liked has its count
decremented; a DM thread with a survivor keeps its history with `canReply: false`;
a conversation where *both* users are deleted is gone; and
`store.top(...)` no longer contains their id.

**`test_dm.py`** (new): pair normalisation (both directions reuse one
conversation); self-message and empty-message 422; non-participant → 404 on read
and write; `before` pagination with no overlap; unread counts; live delivery over
`/api/ws`; an offline recipient still finding the message in history. Then
attachments: EXIF stripped from an image (reuse `make_image(exif=True)`);
attachment-only message; a renamed non-image rejected with nothing left on disk;
**a `.mov` masquerading as `.mp4` rejected** — the test that proves the brand
check exists; over-cap video rejected with **no partial file remaining**; the
image cap applied to images and the video cap to video; participant 200 /
stranger 404 / anonymous 401; and **`Range: bytes=0-99` → 206 with
`Content-Range` and exactly 100 bytes**, the one test that proves scrubbing will
work in a browser.

**`test_gallery.py`** (new): a done+shared job appears; queued, errored, and
done-without-a-dog do not; unshare removes it *and* 404s the image endpoint on
the very next request; anonymous `GET /api/gallery` → 200; a non-owner can't
share someone else's job.

**Existing tests:** `test_matching.py` (~12 sites — `_upload()` drops `ownerId`;
`test_someone_elses_upload_is_a_404_not_a_403` stays exactly as it is) and
`test_api.py` (~13 sites — game bodies lose `playerId`, sockets take `?token=`).
The five engine files (`test_rooms.py`, `test_match_rooms.py`, `test_solo.py`,
`test_solo_match.py`, `test_board.py` — roughly 1,000 lines) need **zero
changes**, because `Player` keeps its `{id: str, name: str}` shape and the
leaderboard stays in the file store. That is the main argument for both of those
decisions.

**Leaderboards stay in the JSON file.** Moving them to SQL would force
`test_rooms.py:229`, `test_solo.py:108,127` and `test_solo_match.py:148` — which
score fake players `"p_a"`/`"p1"` — to create real `User` rows, and would put
blocking SQLAlchemy writes inside the async room loop via
`record_multiplayer_result`. Identity is already the real user id either way;
the only thing the file store loses is referential integrity on delete, and
`forget_player` closes that directly.

---

## 8. Two pre-existing bugs this surfaces

Neither is caused by this work; both are worth fixing here and calling out in
the eventual PR description, because neither is obvious from the diff.

1. **`nginx.conf` sets no `client_max_body_size`**, so nginx's 1MB default
   applies to `/api/`. **Any photo over 1MB is already being 413'd on the VM
   today**, before FastAPI's 10MB cap is ever consulted — which means the upload
   path has probably never worked properly in production. Needs
   `client_max_body_size 30m;`, mandatory before 25MB attachments and a fix
   regardless.
2. **The forum defeats the photo ownership check** by passing the author's id as
   `ownerId` (§3).

---

## 9. Phases

Each ends with `pytest` green in `backend/` and `npm run lint && typecheck && build`
green, and is committable. Note the branch gets **no CI until a PR is opened**
(`ci.yml` runs on `pull_request` and pushes to `main`), so run both locally at
every boundary.

| # | Scope | Independently testable |
|---|---|---|
| 1 | **Auth core, backend only.** `token_version`, media tokens, `/api/auth/me`, password rules, `reset_db.py`, conftest fixtures, `test_auth.py`. No existing route changes. | **Yes, fully** — the best first commit: adds tests to code that has none and breaks nothing |
| 2 | **Uploads + matches own a real user.** FKs, uploads router, `/api/match`. Frontend in the same commit: `auth.tsx`, `api.ts`, real login/signup, router guards, store shim. Run `reset_db.py` here. | Backend yes; front and back **must land together** — this is the one phase that breaks the SPA if split |
| 3 | **Forum identity.** FKs, drop `author_name`, the "backs a post" arm, `backend/app/forum/seed.py` creating real users instead of `"seed_moodyoak"` strings. | Yes |
| 4 | **Game identity.** Delete the `_identify` fallback and `PlayerRef`; run-ownership checks; `forget_player`. Retires the TODO at `game/ws.py:8-12`. | Yes |
| 5 | **Gallery.** `shared_at`, share/unshare, `DELETE /api/uploads/{id}`, public `GET /api/gallery`, the share button, real gallery and landing. | Yes |
| 6 | **Account management.** `PATCH/DELETE /api/users/me`, password change, `delete_user` with anonymization, `GET /api/users?q=`, `/settings`. | Yes — the deletion test is the valuable one |
| 7a | **Text DMs.** Models (attachment columns present but unused), `/api/dm/*`, the `/api/ws` merge and its two bug fixes, `appSocket.tsx`, both messages pages. A complete, demoable chat. | Yes |
| 7b | **Attachments.** `layout` helpers, the sniffer, the multipart branch, the serving endpoint, `client_max_body_size`, `ATTACHMENT_DATA_DIR`, composer and bubble UI. 7a keeps working if this is dropped. | Yes |
| 8 | **Notifications and the last of the mock.** Table, endpoints, bell; delete `store.tsx` and `mock.ts`. | Partly — mostly UI |
| 9 | **Docs.** `ProjectPlan.md:107` 403→404 and mark `/gallery` public; document the `users`, DM, attachment and gallery schemas (**no doc specifies any of them today**); `DATA_STORAGE.md` gets the shared-photo amendment and an attachments section; tick off `MIGRATION.md:112-117`; `DEPLOY.md` gets the reset recipe, `SECRET_KEY` and the nginx fix. | n/a |

Demo checkpoints: after 2 you have real login with real private photos; after 5
a real public gallery; after 7a a real chat.

**Explicitly not in scope:** collapsing `Match` into `UploadJob`; leaderboards in
SQL; merging `/api/game/ws` into `/api/ws` (the hook stays documented at
`hub.py:12-18` — merging changes reconnect semantics, since "last socket for a
player" would start meaning "last tab of the whole app"); ffmpeg; avatars;
Alembic; login rate limiting; email verification and password reset (no mail
service exists); **HEIC support** (deferred with the other pending fixes).

---

## 10. Verification

- `cd backend && pytest`
- `npm run lint && npm run typecheck && npm run build` — what CI runs
- **End to end locally**, two browsers (one normal, one private window):
  1. Sign up two accounts. Confirm in the DB that `users.password` is a bcrypt
     hash and not the plaintext.
  2. Upload a photo as A → `upload_jobs.owner_id` is A's integer id.
  3. As B, request A's image URL directly → **404**. Logged out → 401.
  4. Share the match as A → it appears in B's gallery and on the logged-out
     landing page. Unshare → gone, and the URL stops working on the next request.
  5. B sends A a DM with a photo and a short video. A receives it live without
     refreshing, the video scrubs, and the history survives both logging out
     and back in.
  6. Change A's password → B is unaffected; A's other tab 401s; A's current tab
     keeps working.
  7. Delete B's account → B's photos and sent attachments are gone from disk,
     B's forum post still renders as `[deleted user]` with no image, and the
     thread A replied in is intact.
- Deploy is **not** part of this — feature branch only, and the VM is off by
  choice.
