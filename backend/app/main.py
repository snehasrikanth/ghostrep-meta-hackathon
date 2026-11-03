from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, coach_chat, coaching, demo, health, meta, profiles, program, sessions, videos, workouts
from app.config import get_settings
from app.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="GhostRep API",
        version="0.1.0",
        description="Local-first movement analysis. Meta Model API is gated and off by default.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(demo.router)
    app.include_router(meta.router)
    app.include_router(profiles.router)
    app.include_router(workouts.router)
    app.include_router(program.router)
    app.include_router(sessions.router)
    app.include_router(videos.router)
    app.include_router(analysis.router)
    app.include_router(coaching.router)
    app.include_router(coach_chat.router)
    return app


app = create_app()
