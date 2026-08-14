# Dogppelganger

Upload a photo, find out what dog you'd be — plus a gallery, forum, DMs and
match games.

## Architecture

Three containers, orchestrated by `docker-compose.yml`:

| Service | Stack                    | Role                                       |
| ------- | ------------------------ | ------------------------------------------ |
| `site`  | React (Vite SPA) + nginx | The web UI; also proxies `/api` → model    |
| `model` | FastAPI (Python)         | Auth (JWT), the model, real-time WebSocket |
| `db`    | Postgres                 | Persistent storage                         |

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

Two games, each playable alone at `/game` or with other people at `/lobbies` —
a real server-authoritative room you join with a 4-letter code.

**Mix & match** deals four people and four dogs and asks you to link them up.
In a room, making a pairing _claims that exact combination_: nobody else can use
it, though both tiles stay in play for any other combination, and you can un-pair
to hand it back. Everyone sees everyone else's lines appear in real time, and
nobody learns who was right until the round closes. That makes the board shared
mutable state, so the server arbitrates every claim — two players going for the
same combination is settled by arrival order and the loser is told who beat them
(ProjectPlan 2.10). Solo it's the same board, three lives, no clock.

**Spot the double** is the Kahoot-style race: one person, four dogs, everyone
answers at once and faster correct answers score more. Solo it's Streak survival —
no timer, three lives, get as far as you can.

Each mode keeps its own leaderboard (four in total), because a Streak survival
score counts answers and a Mix & match score counts points. All of them are
shared and persist across restarts.

The game runs entirely on in-memory dummy content for now, behind seams that swap
for real gallery matches and a real database later without touching anything else
— `backend/app/game/__init__.py` documents each one.

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest                        # game engine + API + WebSocket
```
