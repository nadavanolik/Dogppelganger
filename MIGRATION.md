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
| No backend                                    | **Flask** API (`backend/`) + **Postgres**    |
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
# Backend — Flask on :5000 (uses a local SQLite file, no Postgres needed)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py

# Frontend — React dev server on :5173 (auto-proxies /api to :5000)
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

backend/                 Flask API  (same app-factory shape as the class project)
  main.py                entry point (exposes `app`)
  requirements.txt
  website/
    __init__.py          create_app() + db setup
    views.py             API routes (JSON): /api/health, /api/match, /api/matches
    auth.py              /api/auth/signup, /api/auth/login
    models.py            SQLAlchemy tables (User, Match)
    model.py             the dog-matching model (placeholder for now)

Dockerfile               site image (build SPA -> serve with nginx + /api proxy)
backend/Dockerfile       model image (gunicorn)
nginx.conf               SPA fallback + proxy /api -> Flask
docker-compose.yml       site + model + db
.github/workflows/       ci.yml (checks) + deploy.yml (build -> GHCR -> SSH deploy)
DEPLOY.md                the deployment pipeline + VM setup steps
```

## The API (frontend ↔ backend contract)

The React app talks to Flask over `/api`. In dev, Vite proxies it to `:5000`;
in production, nginx proxies it to the `model` container. Current endpoints:

| Method | Path                | Purpose                          |
| ------ | ------------------- | -------------------------------- |
| GET    | `/api/health`       | liveness check                   |
| POST   | `/api/match`        | run the model, store a match     |
| GET    | `/api/matches`      | list recent matches              |
| POST   | `/api/auth/signup`  | create an account                |
| POST   | `/api/auth/login`   | log in                           |

The frontend store (`src/lib/store.tsx`) is still client-side/mock for now —
wiring the pages to these real endpoints is the natural next step.

## Deployment

Push to `main` → GitHub Actions builds both images, pushes to GHCR, and SSHes
into the VM to restart the stack. Full details and the one-time VM setup are in
**[DEPLOY.md](./DEPLOY.md)**.

## Good first tasks

- Replace the placeholder matcher in `backend/website/model.py` with the real ML model.
- Point a page (e.g. upload → result) at the real `POST /api/match` instead of the mock store.
- Add real auth wiring (the `/api/auth/*` endpoints already exist).
