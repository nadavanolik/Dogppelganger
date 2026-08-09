# Dogppelganger

Upload a photo, find out what dog you'd be — plus a gallery, forum, DMs and
match games.

## Architecture

Three containers, orchestrated by `docker-compose.yml`:

| Service | Stack                     | Role                                   |
| ------- | ------------------------- | -------------------------------------- |
| `site`  | React (Vite SPA) + nginx  | The web UI; also proxies `/api` → model |
| `model` | Flask (Python) API        | Auth, the dog-matching model, data      |
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
backend/        Flask API (app-factory: website/__init__.py, views, auth, models, model)
.github/workflows/   CI (lint/typecheck/build) + CD (build→GHCR→SSH deploy)
Dockerfile           site image (build SPA, serve with nginx)
backend/Dockerfile   model image (gunicorn)
docker-compose.yml   site + model + db
```
