"""Local-only demo account switch. Not a general impersonation API."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import attach_session_cookie, demo_switch_allowed, optional_user, session_token, settings_dep
from app.config import Settings
from app.database import get_db
from app.models.entities import User, UserSession
from app.services.demo.identity import DEMO_USER_ID, RETURN_COOKIE, is_demo_user

router = APIRouter(prefix="/demo", tags=["demo"])


def return_cookie_name(settings: Settings) -> str:
    return RETURN_COOKIE if settings.session_cookie == "ghostrep_session" else f"{settings.session_cookie}_return"


def return_token(request: Request, settings: Settings = Depends(settings_dep)) -> str | None:
    return request.cookies.get(return_cookie_name(settings))


@router.get("/status")
def demo_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    user: User | None = Depends(optional_user),
    ghostrep_return: str | None = Depends(return_token),
) -> dict:
    if not demo_switch_allowed(settings):
        return {"available": False, "active": False, "seeded": False, "can_return": False}
    seeded = db.get(User, DEMO_USER_ID) is not None
    return {
        "available": True,
        "active": is_demo_user(user),
        "seeded": seeded,
        "can_return": bool(ghostrep_return),
        "display_name": "Jordan" if seeded else None,
    }


@router.post("/enter")
def enter_demo(
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    user: User | None = Depends(optional_user),
    ghostrep_session: str | None = Depends(session_token),
    ghostrep_return: str | None = Depends(return_token),
) -> dict:
    _require_local(settings)
    demo = db.get(User, DEMO_USER_ID)
    if demo is None:
        raise HTTPException(status_code=409, detail="Seed the demo account first: uv run python -m app.demo seed")
    if is_demo_user(user):
        return {"ok": True, "active": True, "already": True}
    token = _demo_token(db, settings)
    if ghostrep_session and not ghostrep_return:
        _set_cookie(response, settings, return_cookie_name(settings), ghostrep_session)
    _set_cookie(response, settings, settings.session_cookie, token)
    return {"ok": True, "active": True, "already": False}


@router.post("/exit")
def exit_demo(
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
    user: User | None = Depends(optional_user),
    ghostrep_return: str | None = Depends(return_token),
) -> dict:
    _require_local(settings)
    if not is_demo_user(user):
        response.delete_cookie(return_cookie_name(settings))
        return {"ok": True, "active": False, "already": True}
    if ghostrep_return and _valid_return(db, settings, ghostrep_return):
        _set_cookie(response, settings, settings.session_cookie, ghostrep_return)
    else:
        response.delete_cookie(settings.session_cookie)
    response.delete_cookie(return_cookie_name(settings))
    return {"ok": True, "active": False, "already": False}


def _require_local(settings: Settings) -> None:
    if not demo_switch_allowed(settings):
        raise HTTPException(status_code=404, detail="Not found")


def _demo_token(db: Session, settings: Settings) -> str:
    row = (
        db.query(UserSession)
        .filter(UserSession.user_id == DEMO_USER_ID)
        .order_by(UserSession.created_at.desc())
        .first()
    )
    now = datetime.now(timezone.utc)
    if row and row.expires_at.replace(tzinfo=timezone.utc) > now:
        return row.token
    token = secrets.token_hex(24)
    db.add(
        UserSession(
            user_id=DEMO_USER_ID,
            token=token,
            expires_at=now + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    return token


def _valid_return(db: Session, settings: Settings, token: str) -> bool:
    row = db.query(UserSession).filter(UserSession.token == token).one_or_none()
    if not row or row.user_id == DEMO_USER_ID:
        return False
    now = datetime.now(timezone.utc)
    return row.expires_at.replace(tzinfo=timezone.utc) > now


def _set_cookie(response: Response, settings: Settings, name: str, value: str) -> None:
    attach_session_cookie(response, settings, value, name=name)
