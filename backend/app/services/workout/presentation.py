"""Stable week/session metadata, using the saved plan rather than edited preferences."""
from __future__ import annotations

from app.services.workout.local_planner import resolve_split
from app.services.workout.profile_model import planner_view


def _family(value: str | None) -> str | None:
    value = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if value.startswith("full_body"):
        return "full_body"
    if value.startswith("upper") or value.startswith("lower"):
        return "upper_lower"
    if value.startswith(("push", "pull", "leg")):
        return "push_pull_legs"
    return None


def training_structure(profile: dict, plan: dict, session_index: int = 0) -> dict:
    view = planner_view(profile)
    schedule = list(plan.get("schedule") or [])
    expected = resolve_split(view.get("preferred_split"), int(view.get("days_per_week") or 3), view.get("experience") or "beginner")
    families = {_family(item.get("session_type")) for item in schedule if isinstance(item, dict)} - {None}
    split = next(iter(families)) if len(families) == 1 else "mixed" if len(families) > 1 else plan.get("split") or expected
    selected = plan.get("week_session_index")
    if selected is None:
        selected = next((i for i, item in enumerate(schedule) if item.get("workout_name") == plan.get("name")), session_index % max(len(schedule), 1))
    return {
        "split": split,
        "sessions_per_week": len(schedule) or int(view.get("days_per_week") or 3),
        "session_index": int(selected),
        "preferred_days": list(view.get("preferred_days") or []),
        "proposal_kind": plan.get("proposal_kind") or "week",
    }
