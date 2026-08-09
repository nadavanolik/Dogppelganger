"""FastAPI entry point.

Local dev:   python main.py            (http://localhost:5000, auto-reload)
             or: uvicorn main:app --reload --port 5000
Production:  uvicorn main:app --host 0.0.0.0 --port 5000   (see Dockerfile)

Interactive API docs are auto-generated at /docs.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app import models  # noqa: F401  (import so tables register on Base)
from app.routers import auth, views, ws

# Create tables on startup (fine for a project; use migrations later if needed).
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Dogppelganger API")

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
