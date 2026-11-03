from __future__ import annotations

from typing import Any

CATALOG: dict[str, dict[str, Any]] = {
    "barbell_squat": {
        "name": "Barbell Back Squat",
        "pattern": "squat",
        "muscles": ["quadriceps", "glutes", "core"],
        "equipment": ["barbell"],
        "video_analysis": True,
        "contraindications": ["knee pain", "acute back pain"],
    },
    "goblet_squat": {
        "name": "Goblet Squat",
        "pattern": "squat",
        "muscles": ["quadriceps", "glutes"],
        "equipment": ["dumbbells", "kettlebell"],
        "video_analysis": False,
        "contraindications": ["knee pain"],
    },
    "bodyweight_squat": {
        "name": "Bodyweight Squat",
        "pattern": "squat",
        "muscles": ["quadriceps", "glutes"],
        "equipment": ["bodyweight"],
        "video_analysis": False,
        "contraindications": ["knee pain"],
    },
    "romanian_deadlift": {
        "name": "Romanian Deadlift",
        "pattern": "hinge",
        "muscles": ["hamstrings", "glutes", "back"],
        "equipment": ["barbell", "dumbbells"],
        "video_analysis": False,
        "contraindications": ["acute back pain"],
    },
    "hip_hinge_good_morning": {
        "name": "Band / Empty-Bar Good Morning",
        "pattern": "hinge",
        "muscles": ["hamstrings", "back"],
        "equipment": ["barbell", "bodyweight"],
        "video_analysis": False,
        "contraindications": ["acute back pain"],
    },
    "walking_lunge": {
        "name": "Walking Lunge",
        "pattern": "lunge",
        "muscles": ["quadriceps", "glutes"],
        "equipment": ["dumbbells", "bodyweight"],
        "video_analysis": False,
        "contraindications": ["knee pain"],
    },
    "leg_press": {
        "name": "Leg Press",
        "pattern": "squat",
        "muscles": ["quadriceps", "glutes"],
        "equipment": ["machines"],
        "video_analysis": False,
        "contraindications": ["knee pain"],
    },
    "leg_curl": {
        "name": "Leg Curl",
        "pattern": "isolation",
        "muscles": ["hamstrings"],
        "equipment": ["machines"],
        "video_analysis": False,
        "contraindications": [],
    },
    "leg_extension": {
        "name": "Leg Extension",
        "pattern": "isolation",
        "muscles": ["quadriceps"],
        "equipment": ["machines"],
        "video_analysis": False,
        "contraindications": ["knee pain"],
    },
    "calf_raise": {
        "name": "Calf Raise",
        "pattern": "isolation",
        "muscles": ["calves"],
        "equipment": ["machines", "dumbbells", "bodyweight"],
        "video_analysis": False,
        "contraindications": [],
    },
    "plank": {
        "name": "Plank",
        "pattern": "core",
        "muscles": ["core"],
        "equipment": ["bodyweight"],
        "video_analysis": False,
        "contraindications": [],
    },
    "glute_bridge": {
        "name": "Glute Bridge",
        "pattern": "hinge",
        "muscles": ["glutes", "hamstrings"],
        "equipment": ["bodyweight", "dumbbells"],
        "video_analysis": False,
        "contraindications": [],
    },
    "push_up": {
        "name": "Push-Up",
        "pattern": "push",
        "muscles": ["chest", "shoulders", "arms"],
        "equipment": ["bodyweight"],
        "video_analysis": False,
        "contraindications": ["shoulder pain"],
    },
    "dumbbell_row": {
        "name": "Dumbbell Row",
        "pattern": "pull",
        "muscles": ["back", "arms"],
        "equipment": ["dumbbells"],
        "video_analysis": False,
        "contraindications": ["acute back pain"],
    },
    "bench_press": {
        "name": "Barbell Bench Press",
        "pattern": "push",
        "muscles": ["chest", "shoulders", "arms"],
        "equipment": ["barbell"],
        "video_analysis": False,
        "contraindications": ["shoulder pain"],
    },
    "dumbbell_bench_press": {
        "name": "Dumbbell Bench Press",
        "pattern": "push",
        "muscles": ["chest", "shoulders", "arms"],
        "equipment": ["dumbbells"],
        "video_analysis": False,
        "contraindications": ["shoulder pain"],
    },
    "overhead_press": {
        "name": "Barbell Overhead Press",
        "pattern": "push_vertical",
        "muscles": ["shoulders", "arms"],
        "equipment": ["barbell"],
        "video_analysis": False,
        "contraindications": ["shoulder pain"],
    },
    "dumbbell_shoulder_press": {
        "name": "Dumbbell Shoulder Press",
        "pattern": "push_vertical",
        "muscles": ["shoulders", "arms"],
        "equipment": ["dumbbells", "kettlebell"],
        "video_analysis": False,
        "contraindications": ["shoulder pain"],
    },
    "pike_push_up": {
        "name": "Pike Push-Up",
        "pattern": "push_vertical",
        "muscles": ["shoulders", "arms"],
        "equipment": ["bodyweight"],
        "video_analysis": False,
        "contraindications": ["shoulder pain"],
    },
    "barbell_row": {
        "name": "Barbell Row",
        "pattern": "pull",
        "muscles": ["back", "arms"],
        "equipment": ["barbell"],
        "video_analysis": False,
        "contraindications": ["acute back pain"],
    },
    "seated_cable_row": {
        "name": "Seated Cable Row",
        "pattern": "pull",
        "muscles": ["back", "arms"],
        "equipment": ["machines"],
        "video_analysis": False,
        "contraindications": [],
    },
    "band_row": {
        "name": "Resistance Band Row",
        "pattern": "pull",
        "muscles": ["back", "arms"],
        "equipment": ["bands"],
        "video_analysis": False,
        "contraindications": [],
    },
    "prone_y_raise": {
        "name": "Prone Y Raise",
        "pattern": "pull",
        "muscles": ["back", "shoulders"],
        "equipment": ["bodyweight"],
        "video_analysis": False,
        "contraindications": [],
    },
    "pull_up": {
        "name": "Pull-Up",
        "pattern": "pull_vertical",
        "muscles": ["back", "arms"],
        "equipment": ["pullup"],
        "video_analysis": False,
        "contraindications": ["shoulder pain"],
    },
    "lat_pulldown": {
        "name": "Lat Pulldown",
        "pattern": "pull_vertical",
        "muscles": ["back", "arms"],
        "equipment": ["machines"],
        "video_analysis": False,
        "contraindications": [],
    },
    "dumbbell_curl": {
        "name": "Dumbbell Curl",
        "pattern": "isolation_upper",
        "muscles": ["arms"],
        "equipment": ["dumbbells"],
        "video_analysis": False,
        "contraindications": [],
    },
    "triceps_pushdown": {
        "name": "Triceps Pushdown",
        "pattern": "isolation_upper",
        "muscles": ["arms"],
        "equipment": ["machines", "bands"],
        "video_analysis": False,
        "contraindications": [],
    },
    "dead_bug": {
        "name": "Dead Bug",
        "pattern": "core",
        "muscles": ["core"],
        "equipment": ["bodyweight"],
        "video_analysis": False,
        "contraindications": [],
    },
    "single_leg_balance": {
        "name": "Single-Leg Balance",
        "pattern": "balance",
        "muscles": ["core", "glutes"],
        "equipment": ["bodyweight"],
        "video_analysis": False,
        "contraindications": [],
    },
    "sit_to_stand": {
        "name": "Sit to Stand",
        "pattern": "functional",
        "muscles": ["quadriceps", "glutes"],
        "equipment": ["bodyweight"],
        "video_analysis": False,
        "contraindications": ["knee pain"],
    },
}


TIMED = {"plank"}


def display_name(exercise_id: str) -> str:
    eid = str(exercise_id or "")
    item = CATALOG.get(eid)
    if item and item.get("name"):
        return str(item["name"])
    return eid.replace("_", " ") if eid else "Unknown exercise"


def labeled_exercise(item: dict[str, Any]) -> dict[str, Any]:
    """Keep catalog ids; add a readable name and timed-hold measure for display."""
    row = dict(item)
    eid = str(row.get("exercise_id") or "")
    catalog = CATALOG.get(eid) or {}
    row["exercise_id"] = eid
    row["name"] = display_name(eid)
    row["measure"] = "seconds" if eid in TIMED else "reps"
    if "video_analysis" not in row:
        row["video_analysis"] = bool(catalog.get("video_analysis"))
    return row


def labeled_exercises(items: list) -> list:
    return [labeled_exercise(item) if isinstance(item, dict) else item for item in items]


def get_exercise(exercise_id: str) -> dict[str, Any] | None:
    return CATALOG.get(exercise_id)


def validate_exercise(
    exercise_id: str,
    equipment: list[str],
    limitations: list[str],
) -> tuple[bool, str]:
    item = CATALOG.get(exercise_id)
    if not item:
        return False, f"Unknown exercise '{exercise_id}'."
    if not any(eq in equipment or eq == "bodyweight" for eq in item["equipment"]):
        if "bodyweight" not in item["equipment"]:
            return False, f"{item['name']} needs unavailable equipment."
    lowered = [lim.lower() for lim in limitations]
    for flag in item["contraindications"]:
        if any(flag in lim for lim in lowered):
            return False, f"{item['name']} skipped because of declared limitation: {flag}."
    return True, ""
