"""Isolated demo athlete dataset. Never called from application startup."""

from app.services.demo.identity import DEMO_DISPLAY_NAME, DEMO_MARKER, DEMO_USER_ID, is_demo_user
from app.services.demo.seed import cleanup_demo, seed_demo

__all__ = [
    "DEMO_DISPLAY_NAME",
    "DEMO_MARKER",
    "DEMO_USER_ID",
    "cleanup_demo",
    "is_demo_user",
    "seed_demo",
]
