"""Deterministic three-week demo history. Uses the local planner; never Muse or SAM.

Timezone: timestamps are stored in UTC. Calendar days are the athlete's local
dates in the timezone passed to ``build_dataset`` (default: the host's local
zone). Evening sessions at 18:00 in America/New_York stay on the same calendar
day in UTC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.services.demo.identity import DEMO_DISPLAY_NAME, DEMO_MARKER, DEMO_USER_ID, demo_id
from app.services.workout.catalog import validate_exercise
from app.services.workout.local_planner import TIMED, generate_local_plan, resolve_split
from app.services.workout.profile_model import planner_view

PREFERRED_DAYS = ["monday", "tuesday", "thursday", "saturday"]
VARIANTS = {
    ("lower", "b"): {"walking_lunge": "leg_press", "glute_bridge": "plank"},
    ("upper", "b"): {"bench_press": "dumbbell_bench_press", "barbell_row": "seated_cable_row", "push_up": "plank"},
}
LOADS: dict[str, float | None] = {
    "barbell_squat": 80.0,
    "romanian_deadlift": 90.0,
    "walking_lunge": 20.0,
    "leg_press": 140.0,
    "leg_curl": 42.5,
    "leg_extension": 45.0,
    "glute_bridge": 40.0,
    "calf_raise": 60.0,
    "plank": None,
    "bench_press": 60.0,
    "dumbbell_bench_press": 22.5,
    "barbell_row": 70.0,
    "seated_cable_row": 65.0,
    "overhead_press": 40.0,
    "pull_up": None,
    "dumbbell_curl": 12.5,
    "triceps_pushdown": 25.0,
    "push_up": None,
}


@dataclass
class SetSpec:
    id: str
    exercise_id: str
    set_index: int
    load_kg: float | None
    target_reps: int
    completed_reps: int
    reported_rpe: float | None
    created_at: datetime


@dataclass
class SessionSpec:
    key: str
    id: str
    plan_id: str
    name: str
    focus: str
    variant: str
    status: str
    local_date: date
    started_at: datetime
    paused_at: datetime | None
    completed_at: datetime | None
    plan_created_at: datetime
    duration_minutes: int
    estimated_minutes: int
    notes: str
    extra_note: str | None
    exercises: list[dict]
    sets: list[SetSpec] = field(default_factory=list)


@dataclass
class DemoDataset:
    user_id: str
    profile_id: str
    marker: str
    display_name: str
    timezone: str
    anchor: date
    assessment: dict
    profile_flat: dict
    sessions: list[SessionSpec]
    missed: list[dict]


def demo_assessment() -> dict:
    return {
        "identity": {
            "display_name": DEMO_DISPLAY_NAME,
            "preferred_weight_unit": "kg",
            "training_environment": "commercial_gym",
            "age_range": "30_39",
            "adult_confirmed": True,
            "height_cm": None,
            "weight_kg": None,
        },
        "goals": {
            "primary": "increase_strength",
            "secondary": "build_muscle",
            "priority_muscles": [],
            "ambitions": [],
            "personal_objective": None,
            "planning_horizon_weeks": 8,
        },
        "experience": {
            "level": "intermediate",
            "training_history": "regular",
            "consistency": "most_weeks",
            "current_split": "upper_lower",
            "exercise_familiarity": {
                "barbell_squat": "regular",
                "bench_press": "regular",
                "romanian_deadlift": "regular",
            },
            "working_sets": {"barbell_squat": {"weight_kg": 82.5, "reps": 6, "sets": 3}},
        },
        "schedule": {
            "days_per_week": 4,
            "preferred_days": list(PREFERRED_DAYS),
            "session_minutes": 50,
            "duration_band": "45_60",
        },
        "preferences": {
            "training_style": "barbell",
            "preferred_split": "upper_lower",
            "intensity": "moderate",
            "other_activities": [],
            "enjoyed_exercises": ["barbell_squat"],
            "disliked_exercises": [],
            "sport": None,
        },
        "equipment": {
            "preset": "full_gym",
            "available": [
                "barbell",
                "dumbbells",
                "kettlebells",
                "weight_plates",
                "squat_rack",
                "leg_press",
                "cable_machine",
                "leg_extension",
                "leg_curl",
                "lat_pulldown",
                "chest_press",
                "adjustable_bench",
                "pull_up_bar",
                "bodyweight",
            ],
        },
        "considerations": {
            "avoided_exercises": [],
            "movement_restrictions": [],
            "limitation_note": None,
        },
        "_demo_dataset": DEMO_MARKER,
    }


def profile_flat(assessment: dict) -> dict:
    view = planner_view({"assessment": assessment})
    return {
        "goal": "build_strength",
        "experience": "intermediate",
        "days_per_week": 4,
        "session_duration_minutes": 50,
        "equipment": list(view["equipment"]),
        "current_squat_load_kg": 82.5,
        "optional_height_cm": None,
        "optional_weight_kg": None,
        "limitations": [],
        "age_range": "30_39",
    }


def build_dataset(anchor: date, tz: ZoneInfo) -> DemoDataset:
    """Three weeks around ``anchor`` (the athlete's local today)."""
    assessment = demo_assessment()
    flat = profile_flat(assessment)
    monday = anchor - timedelta(days=anchor.weekday())
    profile = {"assessment": assessment, **flat}
    assert resolve_split("upper_lower", 4, "intermediate") == "upper_lower"

    specs = [
        _session(profile, tz, monday, week=-2, weekday=0, focus="lower", variant="a", status="completed", start=time(18, 5)),
        _session(profile, tz, monday, week=-2, weekday=1, focus="upper", variant="a", status="completed", start=time(18, 20)),
        _session(profile, tz, monday, week=-2, weekday=3, focus="lower", variant="b", status="completed", start=time(17, 50)),
        _session(
            profile, tz, monday, week=-2, weekday=5, focus="upper", variant="b", status="completed",
            start=time(9, 40), short=True, extra_note=None,
        ),
        _session(profile, tz, monday, week=-1, weekday=0, focus="lower", variant="a", status="completed", start=time(18, 15)),
        # Tuesday of week -1 is the missed session: no row on purpose.
        _session(
            profile, tz, monday, week=-1, weekday=3, focus="lower", variant="b", status="abandoned",
            start=time(19, 10), extra_note="Short on time.", complete_through=1, partial_sets=1,
        ),
        _session(
            profile, tz, monday, week=-1, weekday=5, focus="upper", variant="b", status="completed",
            start=time(10, 5), extra_note="Last set was tough.", last_set_drop=True,
        ),
        _session(
            profile, tz, monday, week=0, weekday=0, focus="lower", variant="a", status="completed",
            start=time(18, 0), squat_kg=82.5, rdl_kg=92.5, extra_note="Kept the same weight on everything except squat and RDL.",
        ),
        _session(profile, tz, monday, week=0, weekday=1, focus="upper", variant="a", status="completed", start=time(18, 25)),
        _session(
            profile, tz, monday, week=0, weekday=3, focus="lower", variant="b", status="paused",
            start=time(17, 55), squat_kg=82.5, rdl_kg=92.5, complete_through=1, partial_sets=2,
        ),
    ]
    # Fix the week=0 Monday call: I used week=-1+1 which is 0. Good.
    missed = [
        {
            "local_date": (monday + timedelta(days=-7 + 1)).isoformat(),
            "weekday": "tuesday",
            "reason": "No session. Preferred Upper A day was skipped; not stored as a completed or abandoned workout.",
        }
    ]
    return DemoDataset(
        user_id=DEMO_USER_ID,
        profile_id=demo_id("profile"),
        marker=DEMO_MARKER,
        display_name=DEMO_DISPLAY_NAME,
        timezone=str(tz),
        anchor=anchor,
        assessment=assessment,
        profile_flat=flat,
        sessions=specs,
        missed=missed,
    )


def _session(
    profile: dict,
    tz: ZoneInfo,
    current_monday: date,
    *,
    week: int,
    weekday: int,
    focus: str,
    variant: str,
    status: str,
    start: time,
    squat_kg: float = 80.0,
    rdl_kg: float = 90.0,
    short: bool = False,
    extra_note: str | None = None,
    complete_through: int | None = None,
    partial_sets: int | None = None,
    last_set_drop: bool = False,
) -> SessionSpec:
    local_date = current_monday + timedelta(days=week * 7 + weekday)
    key = f"w{week}:{local_date.isoformat()}:{focus}{variant}"
    start_local = datetime.combine(local_date, start, tz)
    plan_created = start_local - timedelta(hours=6, minutes=20)
    raw = generate_local_plan(profile, focus=focus, session_index=0 if focus == "lower" else 1)
    exercises = _vary(raw["exercises"], focus, variant, profile)
    if short and len(exercises) > 1:
        exercises = exercises[:-1]
    exercises = _with_loads(exercises, squat_kg, rdl_kg)
    label = f"{'Lower' if focus == 'lower' else 'Upper'} {variant.upper()}"
    notes = raw["notes"]
    if extra_note:
        notes = f"{notes} {extra_note}"
    spec = SessionSpec(
        key=key,
        id=demo_id("session", key),
        plan_id=demo_id("plan", key),
        name=label,
        focus=focus,
        variant=variant,
        status=status,
        local_date=local_date,
        started_at=_utc(start_local),
        paused_at=None,
        completed_at=None,
        plan_created_at=_utc(plan_created),
        duration_minutes=int(raw["duration_minutes"]),
        estimated_minutes=int(raw["estimated_minutes"]),
        notes=notes,
        extra_note=extra_note,
        exercises=exercises,
    )
    spec.sets = _sets_for(spec, complete_through, partial_sets, last_set_drop)
    last_at = spec.sets[-1].created_at if spec.sets else spec.started_at
    if status == "completed":
        spec.completed_at = last_at + timedelta(minutes=4)
    elif status == "abandoned":
        spec.completed_at = last_at + timedelta(minutes=2)
    elif status == "paused":
        spec.paused_at = last_at + timedelta(minutes=1)
    return spec


def _vary(exercises: list[dict], focus: str, variant: str, profile: dict) -> list[dict]:
    swaps = VARIANTS.get((focus, variant), {})
    equipment = list(profile.get("equipment") or [])
    limitations = list(profile.get("limitations") or [])
    used = {item["exercise_id"] for item in exercises}
    out = []
    for item in exercises:
        replacement = swaps.get(item["exercise_id"])
        if replacement and replacement not in used and validate_exercise(replacement, equipment, limitations)[0]:
            used.discard(item["exercise_id"])
            used.add(replacement)
            item = {**item, "exercise_id": replacement, "notes": item.get("notes")}
            if replacement in TIMED:
                item["target_reps"] = 40
                item["rest_seconds"] = 45
                item["suggested_load_kg"] = None
                item["notes"] = "Hold for the target in seconds."
        out.append(item)
    return out


def _with_loads(exercises: list[dict], squat_kg: float, rdl_kg: float) -> list[dict]:
    out = []
    for position, item in enumerate(exercises):
        exercise_id = item["exercise_id"]
        load = LOADS.get(exercise_id, None)
        if exercise_id == "barbell_squat":
            load = squat_kg
        elif exercise_id == "romanian_deadlift":
            load = rdl_kg
        elif exercise_id in TIMED:
            load = None
        out.append(
            {
                "exercise_id": exercise_id,
                "position": position,
                "sets": int(item["sets"]),
                "target_reps": int(item["target_reps"]),
                "rest_seconds": int(item["rest_seconds"]),
                "suggested_load_kg": load,
                "notes": item.get("notes"),
            }
        )
    return out


def _sets_for(
    spec: SessionSpec,
    complete_through: int | None,
    partial_sets: int | None,
    last_set_drop: bool,
) -> list[SetSpec]:
    sets: list[SetSpec] = []
    cursor = spec.started_at + timedelta(minutes=6)
    last_index = len(spec.exercises) - 1 if complete_through is None else complete_through
    for position, exercise in enumerate(spec.exercises):
        if position > last_index:
            break
        planned = int(exercise["sets"])
        logged = planned if position < last_index else (partial_sets if partial_sets is not None else planned)
        for index in range(1, logged + 1):
            target = int(exercise["target_reps"])
            completed = target
            rpe = None
            if last_set_drop and position == 0 and index == logged:
                completed = max(1, target - 1)
                rpe = 8.5
            elif position == 0 and index == logged and spec.status == "completed" and spec.variant == "a" and spec.focus == "lower":
                completed = max(1, target - 1)
            cursor += timedelta(seconds=exercise["rest_seconds"] + (25 if exercise["exercise_id"] not in TIMED else 10))
            sets.append(
                SetSpec(
                    id=demo_id("set", spec.key, exercise["exercise_id"], str(index)),
                    exercise_id=exercise["exercise_id"],
                    set_index=index,
                    load_kg=exercise["suggested_load_kg"],
                    target_reps=target,
                    completed_reps=completed,
                    reported_rpe=rpe,
                    created_at=cursor,
                )
            )
    return sets


def fingerprint(dataset: DemoDataset) -> str:
    parts = [f"{row.id}:{row.status}:{len(row.sets)}" for row in dataset.sessions]
    return "|".join(sorted(parts))


def _utc(value: datetime) -> datetime:
    return value.astimezone(ZoneInfo("UTC"))
