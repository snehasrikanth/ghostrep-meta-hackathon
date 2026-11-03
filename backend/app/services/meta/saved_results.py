"""Read authorized live Meta artifacts without making another call.

A ledger file is not a fixture. Local and fixture payloads are rejected.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from app.config import Settings
from app.services.meta.contracts import parse_week
from app.services.workout.catalog import labeled_exercises
from app.services.workout.quality import review_week, normalize_saved_exercises

# Keep these in sync with live_preflight.kind_ledger. Do not import that module
# here — it imports the workout routes, which import this file.
WORKOUT_LIVE_ATTEMPT_ID = "attempt-002-reasoning-budget"
COACHING_LIVE_ATTEMPT_ID = "coaching-attempt-002-reasoning-budget"


class SavedResultError(ValueError):
    """The on-disk artifact cannot be shown as a live Meta result."""


def saved_workout_path(settings: Settings) -> Path:
    return settings.data_dir / "live-tests" / f"workout-{WORKOUT_LIVE_ATTEMPT_ID}" / "workout-live.json"


def saved_coaching_path(settings: Settings) -> Path:
    return settings.data_dir / "live-tests" / COACHING_LIVE_ATTEMPT_ID / "coaching-live.json"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SavedResultError("Saved result is not valid JSON.") from exc
    return data if isinstance(data, dict) else None


def require_live_artifact(raw: dict, *, kind: str) -> dict:
    if not raw.get("ok"):
        raise SavedResultError("Saved result is a failed call, not a usable output.")
    result = raw.get("result")
    if not isinstance(result, dict):
        raise SavedResultError("Saved result is missing a payload.")
    source = str(result.get("source") or raw.get("source") or "")
    source_label = str(result.get("source_label") or "").lower()
    if source in {"local", "fixture"} or "not a live call" in source_label:
        raise SavedResultError("This file is not a live Muse Spark result.")
    if source != "muse_spark":
        raise SavedResultError("Saved result is not labeled as Muse Spark.")
    calls = int(raw.get("chat_calls") or 0)
    if calls < 1:
        raise SavedResultError("Saved result does not record a completed model call.")
    if kind == "workout" and not (result.get("exercises") or result.get("schedule")):
        raise SavedResultError("Saved workout has no exercises.")
    return result


def workout_warnings(result: dict, profile: dict) -> list[str]:
    sessions = result.get("schedule") or []
    if not isinstance(sessions, list) or not sessions:
        sessions = [
            {
                "workout_name": result.get("name") or "Workout",
                "session_type": result.get("session_type") or "",
                "duration_minutes": result.get("duration_minutes"),
                "exercises": result.get("exercises") or [],
            }
        ]
    try:
        week = parse_week({"summary": result.get("notes") or "", "sessions": sessions})
        return list(review_week(week, profile).get("warnings") or [])
    except Exception:
        return list(result.get("quality_warnings") or [])


def _label_schedule(schedule: list) -> list:
    days = []
    for day in schedule:
        if not isinstance(day, dict):
            days.append(day)
            continue
        row = dict(day)
        if isinstance(row.get("exercises"), list):
            row["exercises"] = labeled_exercises(row["exercises"])
        days.append(row)
    return days


def public_workout(raw: dict, profile: dict) -> dict:
    result = require_live_artifact(raw, kind="workout")
    warnings = workout_warnings(result, profile)
    schedule = result.get("schedule") if isinstance(result.get("schedule"), list) else None
    if schedule:
        schedule = _label_schedule(schedule)
    transforms = []
    for day in schedule or []:
        day["exercises"], changes = normalize_saved_exercises(day.get("exercises") or [])
        transforms.extend(changes)
    first = schedule[0] if schedule else {}
    exercises = labeled_exercises(list(result.get("exercises") or first.get("exercises") or []))
    exercises, changes = normalize_saved_exercises(exercises)
    transforms = list(dict.fromkeys([*transforms, *changes]))
    return {
        "available": True,
        "attempt_id": raw.get("attempt_id") or WORKOUT_LIVE_ATTEMPT_ID,
        "source": "muse_spark",
        "source_label": result.get("source_label") or "Muse Spark 1.3 (live)",
        "name": result.get("name") or first.get("workout_name"),
        "notes": result.get("notes"),
        "session_type": result.get("session_type") or first.get("session_type"),
        "duration_minutes": result.get("duration_minutes") or first.get("duration_minutes"),
        "estimated_minutes": result.get("estimated_minutes") or first.get("estimated_minutes"),
        "exercises": exercises,
        "schedule": schedule,
        "warnings": list(dict.fromkeys([*warnings, *transforms])),
        "transforms": transforms,
        "chat_calls": raw.get("chat_calls"),
        "schema_validation": raw.get("schema_validation"),
    }


def plan_data_from_public(public: dict) -> dict:
    schedule = public.get("schedule") or []
    first = schedule[0] if schedule else {}
    exercises = list(public.get("exercises") or first.get("exercises") or [])
    if not exercises:
        raise SavedResultError("Saved workout has no exercises.")
    return {
        "name": public.get("name") or first.get("workout_name") or "Saved Muse week",
        "source": "muse_spark",
        "source_label": public.get("source_label") or "Muse Spark 1.3 (live)",
        "duration_minutes": public.get("duration_minutes") or first.get("duration_minutes") or 45,
        "estimated_minutes": public.get("estimated_minutes") or first.get("estimated_minutes"),
        "session_type": public.get("session_type") or first.get("session_type"),
        "notes": public.get("notes"),
        "schedule": schedule,
        "exercises": exercises,
        "quality_warnings": public.get("warnings") or [],
    }


def public_coaching(raw: dict) -> dict:
    result = require_live_artifact(raw, kind="coaching")
    if raw.get("chat_calls") != 1 or raw.get("schema_validation") != "ok" or raw.get("http_status") != 200:
        raise SavedResultError("Coaching requires one successful, schema-validated model call.")
    if raw.get("model") != "muse-spark-1.3" or raw.get("request_schema") != "ghostrep_coaching":
        raise SavedResultError("Coaching model or schema provenance is missing or incompatible.")
    if not result.get("set_id") or not isinstance(result.get("recommendation_context"), dict):
        raise SavedResultError("Coaching is missing its recording and analysis/prescription context.")
    return {
        "attempt_id": raw.get("attempt_id") or COACHING_LIVE_ATTEMPT_ID,
        "source": "muse_spark",
        "source_label": result.get("source_label") or "Muse Spark 1.3 (live)",
        "suggested_action": result.get("suggested_action"),
        "summary": result.get("summary"),
        "reason": result.get("reason") or result.get("explanation"),
        "observations": result.get("observations") or [],
        "uncertainties": result.get("uncertainties") or [],
        "payload": result,
        "chat_calls": raw.get("chat_calls"),
        "set_id": result.get("set_id"),
    }


def http_error(exc: SavedResultError, status: int = 409) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))
