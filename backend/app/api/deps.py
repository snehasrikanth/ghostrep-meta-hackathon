from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models.entities import User, UserSession
from app.services.meta.gateway import MetaGateway
from app.services.video.jobs import VideoJobRunner

_runner: VideoJobRunner | None = None


def settings_dep() -> Settings:
    return get_settings()


def job_runner(settings: Settings = Depends(settings_dep)) -> VideoJobRunner:
    global _runner
    if _runner is None:
        _runner = VideoJobRunner(settings)
    return _runner


def demo_switch_allowed(settings: Settings) -> bool:
    """Cookie switch is local development only. Production always 404s the demo routes."""
    return settings.app_env.lower() not in {"production", "prod"}


def lookup_session_user(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = db.query(UserSession).filter(UserSession.token == token).one_or_none()
    now = datetime.now(timezone.utc)
    if not row or row.expires_at.replace(tzinfo=timezone.utc) <= now:
        return None
    return db.get(User, row.user_id)


def session_token(request: Request, settings: Settings = Depends(settings_dep)) -> str | None:
    return request.cookies.get(settings.session_cookie)


def optional_user(
    db: Session = Depends(get_db),
    token: str | None = Depends(session_token),
) -> User | None:
    """Read the current cookie without creating a user."""
    return lookup_session_user(db, token)


def session_cookie_params(settings: Settings) -> dict:
    """SameSite=Lax cookies are first-party. Secure follows an HTTPS frontend origin.

    Split hosts (app.example vs api.example) will not send Lax cookies on fetch,
    even over HTTPS. Prefer one reverse-proxied origin.
    """
    origin = (settings.frontend_origin or "").strip().lower()
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": origin.startswith("https://"),
        "max_age": settings.session_days * 86400,
        "path": "/",
    }


def attach_session_cookie(response: Response, settings: Settings, token: str, name: str | None = None) -> None:
    response.set_cookie(name or settings.session_cookie, token, **session_cookie_params(settings))


def current_user(
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    token: str | None = Depends(session_token),
) -> User:
    user = lookup_session_user(db, token)
    if user:
        return user
    user = User()
    db.add(user)
    db.flush()
    token = secrets.token_hex(24)
    db.add(
        UserSession(
            user_id=user.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    db.refresh(user)
    attach_session_cookie(response, settings, token)
    return user


def require_owner(resource_user_id: str, user: User) -> None:
    if resource_user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")


def meta_gateway(db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)) -> MetaGateway:
    return MetaGateway(settings, db)
