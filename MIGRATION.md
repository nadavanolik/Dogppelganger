# What changed — read this first (for the team)

We restructured the project from the original Lovable-generated template into a
clean, deployable **frontend + backend + database** app with CI/CD. If you had
the old repo checked out, here's what moved and how to work now.

## TL;DR

| Before (Lovable template)                     | Now                                          |
| --------------------------------------------- | -------------------------------------------- |
| TanStack Start (server-side rendering)        | Plain **React SPA** (Vite build)             |
| TanStack Router                               | **react-router-dom**                         |
| TanStack Query (unused)                       | removed                                       |
| **Bun** package manager                       | **npm**                                       |
| Cloudflare / Nitro build target               | **nginx** serving static files               |
| No backend                                    | **FastAPI** (`backend/`) + **Postgres**      |
| No deployment                                 | **Docker Compose** + **GitHub Actions CI/CD** |

Nothing about how the site *looks or behaves* changed — only how it's built,
served, and deployed. All the pages/components are the same.

## How to run it now

**Everything in Docker (closest to production):**

```bash
docker compose up --build
# site -> http://localhost/     api -> http://localhost/api/health
```

**Or the two halves separately while developing:**

```bash
# Backend — FastAPI on :5001 (uses a local SQLite file, no Postgres needed)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py

# Frontend — React dev server on :5173 (auto-proxies /api to :5001)
npm install
npm run dev
```

> ⚠️ We use **npm now, not Bun.** Delete any old `node_modules` and run
> `npm install` after pulling. There is no more `bun.lock`.

## What you need installed

- **Node.js 22+** (frontend)
- **Python 3.12+** (backend)
- **Docker Desktop** (to run the full stack / test containers)

## Where things live

```
src/                     React SPA
  main.tsx               app entry (mounts React, sets up the router)
  router.tsx             all routes (react-router-dom)
  RootLayout / ErrorPage / NotFound
  routes/                one file per page (Link/useNavigate/useParams)
  components/ , lib/      UI + client-side store (unchanged)

backend/                 FastAPI backend
  main.py                creates the app, includes routers, runs uvicorn
  requirements.txt
  app/
    config.py            settings (DATABASE_URL, SECRET_KEY) from env
    database.py          SQLAlchemy engine + session
    models.py            SQLAlchemy tables (User, Match)
    schemas.py           Pydantic request/response models
    security.py          bcrypt password hashing + JWT tokens
    deps.py              get_current_user dependency (JWT auth)
    model.py             the dog-matching model (placeholder for now)
    routers/
      views.py           /api/health, /api/match, /api/matches
      auth.py            /api/auth/signup, /api/auth/login  (returns JWT)
      ws.py              /api/ws  WebSocket (live DMs / multiplayer backbone)

Dockerfile               site image (build SPA -> serve with nginx + /api proxy)
backend/Dockerfile       model image (uvicorn)
nginx.conf               SPA fallback + proxy /api (incl. WebSocket) -> FastAPI
docker-compose.yml       site + model + db
.github/workflows/       ci.yml (checks) + deploy.yml (build -> GHCR -> SSH deploy)
DEPLOY.md                the deployment pipeline + VM setup steps
```

## The API (frontend ↔ backend contract)

The React app talks to FastAPI over `/api`. In dev, Vite proxies it to `:5001`;
in production, nginx proxies it to the `model` container. Current endpoints:

Everything below except the four marked PUBLIC requires
`Authorization: Bearer <jwt>`.

| Method | Path                          | Purpose                                          |
| ------ | ----------------------------- | ------------------------------------------------ |
| GET    | `/api/health`                 | liveness check · PUBLIC                          |
| POST   | `/api/auth/signup`            | create an account → returns JWT · PUBLIC         |
| POST   | `/api/auth/login`             | log in → returns JWT · PUBLIC                    |
| GET    | `/api/auth/me`                | who am I (the SPA's bootstrap call)              |
| GET    | `/api/auth/media-token`       | short-lived token for `<img>`/`<video>` URLs     |
| POST   | `/api/match`                  | run the model, store a match                     |
| GET    | `/api/matches`                | list **my** matches                              |
| POST   | `/api/uploads`                | queue a batch of photos                          |
| GET    | `/api/uploads/{id}/image`     | one photo, access-checked                        |
| POST   | `/api/uploads/{id}/share`     | publish a match to the gallery (DELETE to undo)  |
| GET    | `/api/gallery`                | shared matches · PUBLIC                          |
| GET    | `/api/users?q=`               | find people to message (id + username only)      |
| PATCH  | `/api/users/me`               | change username / email                          |
| POST   | `/api/users/me/password`      | change password, ending other sessions           |
| DELETE | `/api/users/me`               | delete account (anonymises what you wrote)       |
| GET    | `/api/dm/conversations`       | inbox, with unread counts                        |
| POST   | `/api/dm/conversations/{id}/messages` | send a message, optionally with a file    |
| GET    | `/api/notifications`          | the bell                                         |
| WS     | `/api/ws?token=JWT`           | real-time channel (DMs, notifications, uploads)  |
| WS     | `/api/game/ws?token=JWT`      | multiplayer rooms                                |

Interactive API docs are auto-generated by FastAPI at `/api/docs`.

## Deployment

Push to `main` → GitHub Actions builds both images, pushes to GHCR, and SSHes
into the VM to restart the stack. Full details and the one-time VM setup are in
**[DEPLOY.md](./DEPLOY.md)**.

## Good first tasks

All four of the original ones are done:

- ~~Replace the placeholder matcher in `backend/app/model.py` with the real ML model.~~ CLIP retrieval over the AFHQ corpus.
- ~~Point a page at the real `POST /api/match` instead of the mock store.~~ Every page reads the API; `src/lib/store.tsx` and `src/lib/mock.ts` are gone.
- ~~Wire login/signup to `/api/auth/*` and store the JWT; send it on the WebSocket.~~ See `src/lib/auth.tsx` and `src/lib/api.ts`.
- ~~Build real-time features on `/api/ws` (route DM events to recipients).~~ One socket per client carries DMs, notifications and upload progress.

What's left:

- Fold `/api/game/ws` into `/api/ws` — the hook is documented in `backend/app/game/hub.py`. Deferred because it changes what "the player's last socket closed" means once the socket is open app-wide instead of per room.
- Collapse `Match` into `UploadJob`; they overlap (see the note in `backend/app/models.py`).
- Adopt Alembic. `backend/scripts/migrate_schema.py` says to switch once the schema changes regularly, and it now does.
- Move the leaderboards out of `data/leaderboards.json` and into SQL.
