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
.github/workflows/   CI (lint/typecheck/build) + CD (build→GHCR→SSH deploy)
Dockerfile           site image (build SPA, serve with nginx)
backend/Dockerfile   model image (uvicorn)
docker-compose.yml   site + model + db
```
