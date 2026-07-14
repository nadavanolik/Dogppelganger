# Dogpelganger — Technical Specification

**Team:** Nadav Anolik, Ilona Grayfer, Michal Kfir
**Scope of this document:** every page in the web app — its purpose, UI components, the data and API it uses, real-time channels, states, and access rules — plus how the user navigates from any page to any other.

---

## 1. Reference stack & conventions

These are assumed throughout the spec so each page can be described consistently.

- **Frontend:** React SPA (client-side routing).
- **Backend:** FastAPI (REST + WebSocket).
- **Database:** PostgreSQL.
- **Object storage:** MinIO locally / Azure Blob in prod (all user images, dog matches, attachments).
- **Queue:** Redis + Celery workers for image "dogify" processing.
- **ML service:** CLIP embedding + FAISS nearest-neighbor over the AFHQ dog-face corpus.
- **Real-time:** a single authenticated WebSocket connection per logged-in client, opened once after login and reused everywhere (notifications, DMs, multiplayer, queue updates). Messages are typed events: `{ "type": "...", "payload": {...} }`.

**Auth model:** JWT issued at login, sent as `Authorization: Bearer <token>` on REST calls and as a query/first-frame token on the WebSocket. Protected routes require a valid token; the frontend guards them and the backend re-checks on every call.

**Route access legend:** `PUBLIC` = reachable logged-out · `AUTH` = requires login.

---

## 2. Page specifications

### 2.1 Landing / Home — `/`  · PUBLIC

**Purpose:** first impression; explains the concept and drives sign-up.

**Components:** hero with a sample human→dog match, short "how it works" strip, a few example matches pulled from the public gallery, primary CTA ("Try it — Sign up") and secondary ("Log in"). Persistent top bar shows Log in / Sign up when logged out.

**Data / API:** `GET /api/gallery/featured?limit=6` for the sample matches (read-only, cached, no auth).

**States:** default; featured-load skeleton; if gallery empty, fall back to bundled static sample images.

**Navigation out:** → Sign-up, → Login. If an already-authenticated user lands here, redirect to Dashboard.

---

### 2.2 Sign-up — `/signup`  · PUBLIC

**Purpose:** create an account.

**Components:** form (username, email, password, confirm password), inline validation, submit button, link to Login.

**Data / API:** `POST /api/auth/signup` → creates user, returns JWT (auto-login) or a success requiring login. Validates uniqueness of username/email server-side.

**States:** empty; validating; field errors (taken username, weak password, mismatch); submitting; success.

**Navigation out:** on success → Dashboard (auto-logged-in). Link → Login.

---

### 2.3 Login — `/login`  · PUBLIC

**Purpose:** authenticate an existing user.

**Components:** form (username/email + password), submit, error banner, link to Sign-up.

**Data / API:** `POST /api/auth/login` → JWT on success. On success the frontend also opens the shared WebSocket.

**States:** empty; submitting; invalid-credentials error; rate-limited (too many attempts).

**Navigation out:** on success → the page the user originally requested (`?return_to=`) or Dashboard by default. Link → Sign-up.

---

### 2.4 Upload / Match — `/upload`  · AUTH

**Purpose:** the core action — turn a human photo into a dog match. Handles both a single quick match and a batch upload.

**Components:**
- Drag-and-drop / file-picker accepting multiple `png`/`jpg`.
- Per-file row with a thumbnail, a remove button, and an **"Urgent"** toggle.
- "Match" submit button.
- After submit, an inline progress area (or immediate redirect — see below).

**Data / API:**
- `POST /api/match` with one or more image files (multipart). Backend validates each file (type, size cap, decodes safely), stores the original in object storage, and enqueues a job per image with its `urgent` flag and byte-size (used by the queue for shortest-job-first ordering). Returns a list of `job_id`s and, for a single non-queued fast path, may return the match directly.
- Progress arrives over WebSocket as `queue_update` and `match_ready` events (see Notifications, 2.11).

**States:** idle; files staged; validating; rejected file (wrong type / too large) shown inline without blocking others; uploading; enqueued.

**Navigation out:**
- **Single image** → the Result page for that match once ready (or a spinner that resolves into it).
- **Multiple images** → Dashboard, where each dog appears as its job completes (avoids blocking the user on a batch). Notifications announce each completion regardless of what page they're on.

---

### 2.5 Result — `/result/:matchId`  · AUTH

**Purpose:** show a single completed human→dog match and let the user act on it.

**Components:** side-by-side of the uploaded human photo and the matched dog face; optional caption; action row — **Share to gallery**, **Download**, **Delete**, and "Match another."

**Data / API:**
- `GET /api/match/:matchId` → the human image URL, dog image URL, metadata, and whether it's already shared.
- `POST /api/match/:matchId/share` / `DELETE .../share` → toggle public-gallery visibility.
- `DELETE /api/match/:matchId` → remove.

**Access guard:** a user may only view/act on their own match (`matchId` ownership checked server-side); others get 403.

**States:** loading; loaded (shared vs not-shared variants); not-found/forbidden; deleting.

**Navigation out:** Share → confirmation, item now appears in Gallery. "Match another" → Upload. Any global-nav link.

---

### 2.6 Public Gallery — `/gallery`  · AUTH (browsable; featured subset also shown on Landing)

**Purpose:** browse all matches users chose to share; also the image pool the matching game draws from.

**Components:** responsive grid of shared human→dog pairs, each with owner handle (if public) and like affordance if you choose to allow it; lazy-loaded / paginated; optional filter or shuffle.

**Data / API:** `GET /api/gallery?page=n` → paginated shared matches. Images served from object storage via signed/static URLs.

**States:** loading (skeleton grid); loaded; empty ("no one has shared yet"); pagination loading-more.

**Navigation out:** → Play the matching game (uses this pool). Any global-nav link.

---

### 2.7 Personal Dashboard / "My Dogs" — `/dashboard`  · AUTH

**Purpose:** the logged-in user's private hub and the default post-login landing page.

**Components:**
- **My matches** grid — every completed dog, click-through to its Result page.
- **Processing queue** panel — images still being dogified, each with a live status (queued / processing / done) and its urgent flag; rows update in real time and turn into finished matches on completion.
- **Shared items** — which of my matches are public.
- **My forum activity** — my posts and my total likes/dislikes received.

**Data / API:**
- `GET /api/me/matches` → completed matches.
- `GET /api/me/jobs` → in-flight queue jobs (initial state; then live via WebSocket `queue_update` / `match_ready`).
- `GET /api/me/forum-stats` → post list + like/dislike totals.

**States:** loading; loaded; empty (new user — prompt to upload); live-updating rows.

**Navigation out:** click a match → Result. Click "Upload more" → Upload. Click a post → Post detail. Any global-nav link.

---

### 2.8 Single-player Game — `/game`  · AUTH

**Purpose:** the matching game from the proposal — guess which person goes with which dog, drawn from shared results.

**Components:** a round shows a set of people and a set of dogs; the player links each person to a dog (drag lines or tap-pairing, matching the proposal's visual); submit; score/feedback; "next round."

**Data / API:**
- `GET /api/game/round` → a set of shared human/dog pairs, shuffled, with the correct mapping withheld (server keeps the answer keyed to a round token).
- `POST /api/game/round/:token/answer` → the player's pairing; returns correctness and score.

**States:** loading round; playing; submitted/reveal; next-round.

**Navigation out:** → Multiplayer lobbies ("Play with others"). Any global-nav link.

---

### 2.9 Multiplayer Lobby — `/game/lobbies`  · AUTH

**Purpose:** create or join a shared game room.

**Components:** list of open lobbies (name, host, player count), "Create lobby" button, "Join" per row.

**Data / API:**
- `GET /api/lobbies` → open lobbies (may also live-update over WebSocket).
- `POST /api/lobbies` → create, returns `lobbyId`.
- `POST /api/lobbies/:id/join` → join.

**States:** loading; list; empty ("no open games — create one"); creating; joining; join-failed (full/closed).

**Navigation out:** create or join → Game room `/game/room/:lobbyId`.

---

### 2.10 Multiplayer Game Room — `/game/room/:lobbyId`  · AUTH

**Purpose:** the live shared game; players act on their own screens and everyone sees updates in real time, with server-authoritative state preventing contradictions.

**Components:** player list / ready states, the shared board (people ↔ dogs), each player's actions reflected live, round timer/score, leave button.

**Data / API + real-time:**
- Initial state: `GET /api/lobbies/:id/state`.
- All in-game actions flow over the WebSocket, scoped to the lobby: client sends `game_action` events (e.g. a proposed pairing); the **server validates against authoritative shared state**, applies or rejects, and broadcasts `game_state_update` to all players in the room. Rejection of a contradicting action is echoed back so no two clients diverge.
- Events: `player_joined`, `player_left`, `game_state_update`, `round_start`, `round_end`.

**States:** connecting; waiting-for-players; in-round; between-rounds; disconnected/reconnecting; game-over.

**Navigation out:** leave → Lobbies. On disconnect, attempt reconnect to the same room before dropping to Lobbies.

---

### 2.11 Notifications (global) — dropdown from the top bar, optional page `/notifications`  · AUTH

**Purpose:** live, no-refresh alerts, reused across the whole app.

**Triggers (WebSocket events):**
- `match_ready` — a dog you uploaded finished processing (jump to its Result).
- `dm_received` — a new direct message (jump to that conversation).
- `post_reaction` — someone liked/disliked your post or comment.

**Components:** bell icon with unread badge in the top bar; dropdown list of recent notifications, each linking to its target; "mark all read."

**Data / API:** `GET /api/notifications` for history/backfill; live events via WebSocket; `POST /api/notifications/read`.

**Navigation out:** each notification deep-links to Result, DM conversation, or Post detail.

---

### 2.12 Forum Feed — `/forum`  · AUTH

**Purpose:** the social hub; all posts visible to everyone.

**Components:** chronological/scored list of posts (title, author, snippet, thumbnail if it has media, like/dislike counts, comment count); "New post" button; each card links to the post.

**Data / API:** `GET /api/forum/posts?page=n`.

**States:** loading; list; empty (won't happen in practice because of seeding); pagination.

**Navigation out:** → Post detail; → Create post; any global-nav link.

---

### 2.13 Post Detail — `/forum/post/:postId`  · AUTH

**Purpose:** read a full post and its comments; react and comment.

**Components:**
- Full post: title, body, image/video attachments, author, like/dislike buttons with counts.
- Comment list: each with body, optional image/video, author, like/dislike counts.
- Add-comment composer (body + optional media).

**Data / API:**
- `GET /api/forum/posts/:id` → post + comments.
- `POST /api/forum/posts/:id/comments` → add comment (multipart if media).
- `POST /api/forum/posts/:id/react` and `.../comments/:cid/react` → like/dislike (toggle).

**States:** loading; loaded; posting comment; reaction pending; not-found.

**Navigation out:** author handles could link to a profile view (optional); back to Feed; any global-nav link.

---

### 2.14 Create Post — `/forum/new` (or a modal over the Feed)  · AUTH

**Purpose:** compose a new forum post.

**Components:** title field, body editor, attach image/video (with client-side size check mirroring the server cap), submit.

**Data / API:** `POST /api/forum/posts` (multipart). Server enforces media size/type limits and rate limits to prevent spam/oversized uploads.

**States:** empty; editing; media too large/rejected; submitting; success.

**Navigation out:** on success → the new Post detail (or back to Feed with the post at top).

---

### 2.15 Direct Messages — Inbox — `/messages`  · AUTH

**Purpose:** list of the user's private conversations.

**Components:** conversation list (other participant, last-message preview, unread badge), "new message" entry (pick a recipient).

**Data / API:** `GET /api/dm/conversations`. Unread counts update live via `dm_received`.

**States:** loading; list; empty; selecting recipient.

**Navigation out:** open a conversation → DM conversation page.

---

### 2.16 DM Conversation — `/messages/:conversationId`  · AUTH

**Purpose:** a private 1:1 chat, delivered live with no page refresh, history persisted.

**Components:** message thread (body + optional image/video, sender-aligned), composer with attach, live "new message" insertion.

**Data / API + real-time:**
- `GET /api/dm/conversations/:id/messages?before=cursor` → paginated history (retrievable/saved).
- Send: `POST /api/dm/conversations/:id/messages` (multipart) **or** a WebSocket `dm_send` event; the server persists and pushes `dm_received` to the recipient's socket for live delivery.

**States:** loading history; live thread; sending; media rejected (too large); recipient offline (message still stored and delivered on their next connect).

**Navigation out:** back to Inbox; any global-nav link.

---

## 3. Global navigation shell

Once authenticated, a **persistent top bar** is present on every `AUTH` page:

- Logo → Dashboard
- Links: **Upload**, **Gallery**, **Game**, **Forum**, **Messages**
- **Notifications** bell (dropdown, 2.11)
- Profile menu → (optional profile view) + **Log out**

Logged-out pages (Landing, Login, Sign-up) show a minimal bar with **Log in** / **Sign up** only.

**Guard rules:**
- Unauthenticated request to any `AUTH` route → redirect to `/login?return_to=<path>`.
- Authenticated user visiting `/login`, `/signup`, or `/` → redirect to `/dashboard`.
- Log out → clear JWT, close WebSocket, redirect to `/`.
- Accessing a resource you don't own (someone else's `matchId`, a conversation you're not in) → 403 / "not found" page.

---

## 4. Route table

| Route | Access | Primary purpose | Main transitions out |
|---|---|---|---|
| `/` | PUBLIC | Landing | → `/signup`, `/login` (authed → `/dashboard`) |
| `/signup` | PUBLIC | Register | success → `/dashboard`; → `/login` |
| `/login` | PUBLIC | Authenticate | success → `return_to` or `/dashboard`; → `/signup` |
| `/dashboard` | AUTH | Personal hub (default home) | → `/result/:id`, `/upload`, `/forum/post/:id` |
| `/upload` | AUTH | Single/batch match | single → `/result/:id`; batch → `/dashboard` |
| `/result/:matchId` | AUTH | View a match | share → stays; → `/gallery`, `/upload` |
| `/gallery` | AUTH | Shared matches | → `/game` |
| `/game` | AUTH | Single-player game | → `/game/lobbies` |
| `/game/lobbies` | AUTH | Lobby list | create/join → `/game/room/:id` |
| `/game/room/:lobbyId` | AUTH | Live multiplayer | leave → `/game/lobbies` |
| `/forum` | AUTH | Post feed | → `/forum/post/:id`, `/forum/new` |
| `/forum/post/:postId` | AUTH | Post + comments | → `/forum` |
| `/forum/new` | AUTH | Compose post | success → `/forum/post/:id` |
| `/messages` | AUTH | DM inbox | → `/messages/:id` |
| `/messages/:conversationId` | AUTH | 1:1 chat | → `/messages` |
| `/notifications` | AUTH | Alerts (mainly a dropdown) | deep-links to Result / DM / Post |

---

## 5. Navigation flow diagram

```mermaid
flowchart TD
    Landing["/ Landing"] --> Login["/login"]
    Landing --> Signup["/signup"]
    Signup -->|success| Dash
    Login -->|success| Dash["/dashboard"]

    subgraph AUTH["Authenticated app (persistent top bar)"]
        Dash --> Upload["/upload"]
        Upload -->|single| Result["/result/:id"]
        Upload -->|batch| Dash
        Result -->|share| Gallery["/gallery"]
        Dash --> Result
        Gallery --> Game["/game (single-player)"]
        Game --> Lobbies["/game/lobbies"]
        Lobbies -->|create/join| Room["/game/room/:id"]
        Room -->|leave| Lobbies

        Dash --> Forum["/forum"]
        Forum --> NewPost["/forum/new"]
        NewPost -->|success| PostDetail["/forum/post/:id"]
        Forum --> PostDetail

        Dash --> Inbox["/messages"]
        Inbox --> DM["/messages/:id"]

        Bell["🔔 Notifications"] -.->|match ready| Result
        Bell -.->|new DM| DM
        Bell -.->|reaction| PostDetail
    end

    Logout["Log out"] --> Landing
```

Solid arrows are explicit user clicks; dotted arrows are deep-links fired by live notifications from anywhere in the app.

---

## 6. Cross-cutting behaviors referenced by the pages

These aren't pages but are relied on by several of the specs above, collected here so each page section stays focused:

- **Priority queue** — powers the Upload batch flow and the Dashboard queue panel. Orders jobs by urgent-first, then shortest-job-first (image byte size as the duration proxy), with per-client fairness so one user's large batch can't starve another's single image. Emits `queue_update` / `match_ready` over the WebSocket.
- **ML matching service** — the CLIP→FAISS retrieval over AFHQ dog faces that each `POST /api/match` job ultimately calls. Human uploads are face-cropped before embedding to mirror the dog-face corpus.
- **WebSocket backbone** — one connection per client, opened at login, multiplexing queue updates, notifications, DMs, and multiplayer game events by `type`.
- **Security** — every upload endpoint (match images, forum media, DM media) enforces type + size limits and safe decoding; write endpoints are rate-limited to resist spam/flooding.
- **Cold seeding** — the DB ships with fake users, forum posts/comments, and shared gallery matches so the Feed, Gallery, and Game are populated on first run.
