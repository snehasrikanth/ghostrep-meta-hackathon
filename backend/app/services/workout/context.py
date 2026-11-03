"""Build the payload a future Muse Spark call would receive.

This module never contacts the Meta Model API.
"""

from __future__ import annotations

from app.services.workout.catalog import CATALOG, validate_exercise
from app.services.workout.profile_model import compact_planning_context, planner_view


OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["workout_name", "duration_minutes", "exercises"],
    "properties": {
        "workout_name": {"type": "string"},
        "duration_minutes": {"type": "integer"},
        "exercises": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["exercise_id", "sets", "target_reps", "rest_seconds"],
            },
        },
    },
}


def squat_first_requested(profile: dict) -> bool:
    view = planner_view(profile)
    return (
        view.get("training_focus") == "lower_body"
        and "barbell_squat" not in view["avoided_exercises"]
        and view.get("familiarity", {}).get("barbell_squat") != "new"
        and validate_exercise("barbell_squat", view["equipment"], view["limitations"])[0]
    )


def build_workout_context(profile: dict) -> dict:
    context = compact_planning_context(profile)
    allowed = []
    equipment = set(context["constraints"]["equipment"])
    avoided = set(context["constraints"]["avoided_exercises"])
    for exercise_id, item in CATALOG.items():
        if exercise_id in avoided:
            continue
        if any(eq in equipment or eq == "bodyweight" for eq in item["equipment"]):
            allowed.append({
                "id": exercise_id, "name": item["name"], "muscles": item.get("muscles", []),
                "pattern": item.get("pattern"), "equipment_any_of": item.get("equipment", []),
                "measure": "seconds" if exercise_id == "plank" else "reps",
            })
    return {
        "opening_exercise": "barbell_squat" if squat_first_requested(profile) else None,
        "age_range": context.get("age_range"),
        "user_preferences": context["preferences"],
        "hard_constraints": context["constraints"],
        "training_history": {
            **context["training_history"],
            "recent_completed_sessions": list(profile.get("recent_sessions") or [])[:4],
        },
        "missing_optional_fields": context["missing"],
        "exercise_catalog": allowed,
        "rules": [
            "Do not invent equipment, experience, or injuries.",
            "Do not recommend an avoided exercise.",
            "Do not increase load above a stated working weight.",
            "Leave suggested load empty when no working weight was provided.",
            "Treat missing fields as unknown.",
            "Age is context, not a reason to lower loads, lengthen rest, or drop a lift.",
            "Do not infer an age when it is missing or the athlete preferred not to say.",
            "For adults 65 and older, add balance or functional-strength work beside the stated goal.",
            "Experience, equipment, training history, limitations, and goals outrank age.",
        ],
        "output_schema": OUTPUT_SCHEMA,
        "provider": "unsent",
        "priority": [
            "Hard constraints beat preferences: equipment, exclusions, and movement restrictions.",
            "Age never overrides those constraints and does not set the working weight.",
            "Primary goal and experience set sets and reps.",
            "Muscle priority and enjoyed exercises only reorder allowed movements.",
            "Preferred days are flexible and do not have to equal weekly frequency.",
        ],
    }


def validate_model_plan(plan: dict, profile: dict) -> list[str]:
    """Check a future model plan against the stored profile. Does not call Meta."""
    view = planner_view(profile)
    issues: list[str] = []
    requested = int(view["session_duration_minutes"] or 0)
    duration = plan.get("duration_minutes")
    if isinstance(duration, int) and requested and duration > requested + 15:
        issues.append("Session is longer than the athlete requested.")
    avoided = set(view["avoided_exercises"])
    for item in plan.get("exercises") or []:
        exercise_id = str(item.get("exercise_id") or "")
        if exercise_id in avoided:
            issues.append(f"{exercise_id} is excluded.")
            continue
        ok, reason = validate_exercise(exercise_id, list(view["equipment"]), list(view["limitations"]))
        if not ok:
            issues.append(reason)
    return issues
