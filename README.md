# Dogppelganger

Upload a photo, find out what dog you'd be — plus a gallery, forum, DMs and
match games.

## Architecture

Three containers, orchestrated by `docker-compose.yml`:

| Service | Stack                     | Role                                   |
| ------- | ------------------------- | -------------------------------------- |
| `site`  | React (Vite SPA) + nginx  | The web UI; also proxies `/api` → model |
| `model` | FastAPI (Python)          | Auth (JWT), the model, real-time WebSocket |
| `db`    | Postgres                  | Persistent storage                      |

## Quick start

```bash
docker compose up --build     # http://localhost/
```

Or run the two halves separately for development — see **[DEPLOY.md](./DEPLOY.md)**,
which also documents the CI/CD pipeline and VM setup.

## Layout

```
src/            React SPA (routes/, components/, lib/)
backend/        FastAPI (app/: routers/, models, schemas, security, model, database)
backend/app/game/    the two games — self-contained, in-memory (see its docstring)
backend/tests/       pytest suite for the games (see tests/README.md)
.github/workflows/   CI (lint/typecheck/build) + CD (build→GHCR→SSH deploy)
Dockerfile           site image (build SPA, serve with nginx)
backend/Dockerfile   model image (uvicorn)
docker-compose.yml   site + model + db
```

## The games

`/game` is single-player **Streak survival** (no timer, three lives, get as far
as you can) and `/lobbies` is a **Kahoot-style multiplayer race** — a real
server-authoritative room you join with a 4-letter code, where faster correct
answers score more. Both leaderboards are shared and persist across restarts.

The game runs entirely on in-memory dummy content for now, behind seams that swap
for real gallery matches and a real database later without touching anything else
— `backend/app/game/__init__.py` documents each one.

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest                        # game engine + API + WebSocket
```
