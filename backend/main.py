"""FastAPI entry point.

Local dev:   python main.py            (http://localhost:5000, auto-reload)
             or: uvicorn main:app --reload --port 5000
Production:  uvicorn main:app --host 0.0.0.0 --port 5000   (see Dockerfile)

Interactive API docs are auto-generated at /docs.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app import models  # noqa: F401  (import so tables register on Base)
from app.forum import router as forum_router
from app.forum.seed import seed_if_empty
from app.game import router as game_router
from app.routers import auth, dogs, views, ws
from app.storage import layout
from app.uploads import router as uploads_router
from app.uploads import queue as upload_queue
from app.uploads.ws import notifier as upload_notifier

# Create tables on startup (fine for a project; use migrations later if needed).
Base.metadata.create_all(bind=engine)
seed_if_empty()


@asynccontextmanager
async def lifespan(app: FastAPI):
    upload_queue.start_workers(upload_notifier.send)
    yield
    await upload_queue.stop_workers()


# Mount the auto-docs under /api so they're reachable through the nginx proxy
# (nginx only forwards /api/* to this backend).
app = FastAPI(
    title="Dogppelganger API",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Let the browser call the API. In production everything is same-origin (nginx
# proxies /api to this service), but in dev the React server is on :5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(views.router)
app.include_router(ws.router)
# Games (REST + their own WebSocket). Self-contained in app/game — see that
# package's docstring for how it folds into ws.py's socket later.
app.include_router(game_router)
app.include_router(uploads_router)
app.include_router(forum_router)
app.include_router(dogs.router)

# Dog photos in local development only. In production nginx owns /dogs/ and
# serves it off the read-only `dogdata` mount — requests never reach here (it
# only forwards /api/*). This mount exists so `npm run dev` + `python main.py`
# shows real dogs without anyone having to run nginx. Skipped when the corpus
# hasn't been ingested, because StaticFiles refuses to start on a missing dir.
if layout.dog_root().is_dir():
    app.mount("/dogs", StaticFiles(directory=layout.dog_root()), name="dogs")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
