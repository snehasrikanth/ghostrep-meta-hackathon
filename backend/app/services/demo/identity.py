"""Stable demo identity. Cleanup matches this user id only."""

from __future__ import annotations

import uuid

from app.models.entities import User

DEMO_NAMESPACE = uuid.UUID("d0e00000-1111-4222-8333-000000000001")
DEMO_MARKER = "ghostrep-demo-v1"
DEMO_DISPLAY_NAME = "Jordan"
DEMO_USER_ID = str(uuid.uuid5(DEMO_NAMESPACE, "user"))
RETURN_COOKIE = "ghostrep_return"


def demo_id(*parts: str) -> str:
    return str(uuid.uuid5(DEMO_NAMESPACE, ":".join(parts)))


def is_demo_user(user: User | None) -> bool:
    return bool(user) and user.id == DEMO_USER_ID
