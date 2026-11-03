from __future__ import annotations

from app.services.workout.catalog import CATALOG, TIMED, validate_exercise
from app.services.workout.profile_model import planner_view

SOURCE_LABEL = "Local deterministic planner — not Muse Spark"

LOWER_BODY = {"quadriceps", "hamstrings", "glutes", "calves"}
UPPER_BODY = {"chest", "back", "shoulders", "arms"}
LOWER_SPORTS = {"running", "football", "basketball", "badminton", "tennis", "cycling"}
OLDER_ADULT = {"65_74", "75_plus"}
BALANCE_PRACTICE = ("single_leg_balance", "sit_to_stand")

SQUATS = ["barbell_squat", "goblet_squat", "bodyweight_squat"]
HINGES = ["romanian_deadlift", "hip_hinge_good_morning", "glute_bridge"]
SINGLE_LEG = ["walking_lunge", "leg_press", "glute_bridge"]
PUSH = ["bench_press", "dumbbell_bench_press", "push_up"]
PUSH_VERTICAL = ["overhead_press", "dumbbell_shoulder_press", "pike_push_up"]
ROWS = ["barbell_row", "seated_cable_row", "dumbbell_row", "band_row", "prone_y_raise"]
PULL_VERTICAL = ["pull_up", "lat_pulldown", "band_row", "prone_y_raise"]

# Each session is a main slot, required slots, and an optional pool used to fill the time.
TEMPLATES: dict[str, dict] = {
    "lower": {
        "name": "Lower Body",
        "main": SQUATS,
        "slots": [HINGES, SINGLE_LEG],
        "pool": ["leg_curl", "leg_extension", "glute_bridge", "calf_raise", "leg_press", "plank", "dead_bug"],
    },
    "legs": {
        "name": "Legs",
        "main": SQUATS,
        "slots": [HINGES, SINGLE_LEG],
        "pool": ["leg_curl", "leg_extension", "glute_bridge", "calf_raise", "leg_press", "plank", "dead_bug"],
    },
    "upper": {
        "name": "Upper Body",
        "main": PUSH,
        "slots": [ROWS, PUSH_VERTICAL, PULL_VERTICAL],
        "pool": ["dumbbell_curl", "triceps_pushdown", "push_up", "dumbbell_row", "plank", "dead_bug"],
    },
    "push": {
        "name": "Push",
        "main": PUSH,
        "slots": [PUSH_VERTICAL, ["dumbbell_bench_press", "push_up"]],
        "pool": ["triceps_pushdown", "pike_push_up", "push_up", "plank", "dead_bug"],
    },
    "pull": {
        "name": "Pull",
        "main": ROWS,
        "slots": [PULL_VERTICAL, HINGES],
        "pool": ["dumbbell_curl", "prone_y_raise", "dumbbell_row", "band_row", "dead_bug", "plank"],
    },
    "full_body_a": {
        "name": "Full Body A",
        "main": SQUATS,
        "slots": [PUSH, ROWS, HINGES],
        "pool": ["plank", "calf_raise", "dumbbell_shoulder_press", "dead_bug", "walking_lunge"],
    },
    "full_body_b": {
        "name": "Full Body B",
        "main": HINGES,
        "slots": [["walking_lunge", "goblet_squat", "leg_press", "bodyweight_squat"], PUSH_VERTICAL, PULL_VERTICAL],
        "pool": ["dead_bug", "plank", "push_up", "calf_raise", "glute_bridge"],
    },
}

ROTATIONS = {
    "full_body": ["full_body_a", "full_body_b"],
    "upper_lower": ["lower", "upper"],
    "push_pull_legs": ["legs", "push", "pull"],
}

FOCUS_TO_SESSION = {
    "legs": "legs",
    "lower": "lower",
    "upper": "upper",
    "push": "push",
    "pull": "pull",
    "full_body": "full_body_a",
}


def generate_local_plan(profile: dict, focus: str | None = None, session_index: int = 0) -> dict:
    """Rule-based planner. Uses the athlete's actual profile; not a hardcoded athlete.

    Priority when answers conflict:
    1. Hard constraints: available equipment, excluded exercises, and movement
       restrictions.
    2. Experience and primary goal set the set and rep scheme.
    3. Weekly frequency and preferred split choose the session type. A split
       that needs more days than the weekly frequency falls back to one that fits.
       ``session_index`` (completed planned sessions) rotates through the split.
    4. Requested session length decides how many exercises and sets fit.
    5. Priority muscles and enjoyed exercises change accessory order and volume.
       An enjoyed exercise that is also excluded is left out.
    6. Preferred days, training style, and sports are preferences.
    7. Age range, when provided, does not change loads, reps, or which main
       lifts are allowed. Adults 65 and older also get a balance or
       functional-strength exercise alongside the session they asked for.
    """
    view = planner_view(profile)
    equipment = list(view["equipment"])
    limitations = list(view["limitations"])
    avoided = set(view["avoided_exercises"])
    if "avoid_impact" in view["limitations"]:
        avoided.add("walking_lunge")
    if "avoid_overhead" in view["limitations"]:
        avoided.update({"bench_press", "overhead_press", "dumbbell_shoulder_press", "pike_push_up"})
    experience = view["experience"]
    duration = int(view["session_duration_minutes"] or 45)
    primary = view["primary_goal"]
    muscles = view["priority_muscles"]
    days = int(view["days_per_week"] or 3)
    enjoyed = set(view.get("enjoyed_exercises") or [])

    split = resolve_split(view.get("preferred_split"), days, experience)
    session_type = FOCUS_TO_SESSION.get(focus or "") or ROTATIONS[split][session_index % len(ROTATIONS[split])]
    template = TEMPLATES[session_type]

    sets, reps, rest = _volume(experience, primary)
    if view.get("intensity") in {"moderate", "gradual"}:
        rest += 15
    acc_sets = max(2, sets - 1)
    acc_reps = _accessory_reps(experience, primary)

    def ok(ex_id: str, used: set[str]) -> bool:
        if ex_id in avoided or ex_id in used:
            return False
        return validate_exercise(ex_id, equipment, limitations)[0]

    used: set[str] = set()
    main_candidates = template["main"]
    if main_candidates is SQUATS:
        main_candidates = SQUATS if view.get("training_focus") == "lower_body" and view["familiarity"].get("barbell_squat") != "new" else _squat_order(view["familiarity"])
    main_id = next((ex_id for ex_id in main_candidates if ok(ex_id, used)), None)

    exercises: list[dict] = []
    lower_main = bool(main_id and CATALOG[main_id]["pattern"] in {"squat", "hinge"})
    fatigue = lower_main and _lower_body_fatigue(view["other_activities"])
    if main_id:
        used.add(main_id)
        exercises.append(
            {
                "exercise_id": main_id,
                "sets": max(2, sets - 1) if fatigue else sets,
                "target_reps": reps,
                "rest_seconds": rest,
                "suggested_load_kg": _conservative_load(view, main_id),
                "notes": _main_note(main_id, view),
                "_role": "main",
            }
        )

    for slot in template["slots"]:
        choice = next((ex_id for ex_id in slot if ok(ex_id, used)), None)
        if choice:
            used.add(choice)
            exercises.append(_accessory(choice, acc_sets, acc_reps, muscles, primary, "slot"))

    balance_note = ""
    if view.get("age_range") in OLDER_ADULT:
        balance_id = next((ex_id for ex_id in BALANCE_PRACTICE if ok(ex_id, used)), None)
        if balance_id:
            used.add(balance_id)
            exercises.append(
                {
                    "exercise_id": balance_id,
                    "sets": 2,
                    "target_reps": 8,
                    "rest_seconds": 45,
                    "suggested_load_kg": None,
                    "notes": "Balance and functional strength alongside the main session. This is not a medical exercise.",
                    "_role": "balance",
                }
            )
            balance_note = " Added balance practice for an adult 65 or older, without changing the main lifts."

    # Fit to the requested time: drop optional slots first, then trim sets.
    while estimate_minutes(exercises) > duration and _drop_last(exercises, "slot", keep=1):
        pass
    while estimate_minutes(exercises) > duration and _trim_sets(exercises):
        pass

    pool = sorted(template["pool"], key=lambda ex_id: _rank(ex_id, muscles, primary, enjoyed))
    for ex_id in [*sorted(enjoyed & set(template["pool"])), *pool]:
        if len(exercises) >= _max_exercises(duration, days):
            break
        if not ok(ex_id, used):
            continue
        candidate = _accessory(ex_id, acc_sets, acc_reps, muscles, primary, "pool")
        if estimate_minutes([*exercises, candidate]) <= duration:
            used.add(ex_id)
            exercises.append(candidate)
    _fill_sets(exercises, duration)

    estimated = estimate_minutes(exercises)
    spare = ""
    if estimated < duration - 10:
        spare = (
            f" The programmed work takes about {estimated} min; use the remaining time for a longer warm-up,"
            " mobility, or easy conditioning."
        )
    focus_label = ", ".join(muscles) if view.get("priority_specified") else "balanced, no muscle priority selected"
    split_note = _split_note(view.get("preferred_split"), split, days)
    fatigue_note = " Extra lower-body sport sessions reduced main-lift volume." if fatigue else ""
    horizon = view.get("planning_horizon_weeks")
    block = f" Planned as a {horizon}-week block." if isinstance(horizon, int) else ""
    day_note = ""
    preferred = view.get("preferred_days") or []
    if preferred and len(preferred) != days:
        day_note = " Preferred days are flexible and do not have to match the weekly session count."
    analysis_note = (
        " Barbell squat sets can be recorded for movement analysis; log the rest by hand."
        if main_id == "barbell_squat"
        else " Log these sets by hand. Video analysis covers barbell squat only."
    )
    notes = (
        f"{template['name']} in your {_split_label(split)} rotation, {days} day"
        f"{'s' if days != 1 else ''} a week.{split_note} Estimated {estimated} min against a {duration} min request. "
        f"Focus: {focus_label}.{spare}{fatigue_note}{block}{day_note}{balance_note}{analysis_note}"
    )
    for item in exercises:
        item.pop("_role", None)
    return {
        "name": _plan_name(template["name"], muscles, view.get("priority_specified"), exercises),
        "source": "local",
        "source_label": SOURCE_LABEL,
        "duration_minutes": duration,
        "estimated_minutes": estimated,
        "session_type": session_type,
        "split": split,
        "notes": notes,
        "exercises": exercises,
    }



def generate_local_week(profile: dict, focus: str | None = None, session_index: int = 0) -> dict:
    """Build the whole reviewable week while keeping the next session explicit."""
    view = planner_view(profile)
    days = max(1, min(7, int(view.get("days_per_week") or 3)))
    position = session_index % days
    start = session_index - position
    if view.get("training_focus") == "lower_body":
        start = 0
    sessions = [generate_local_plan(profile, session_index=start + i) for i in range(days)]
    if focus:
        sessions[position] = generate_local_plan(profile, focus, session_index)
    selected = dict(sessions[position])
    selected["week_session_index"] = position
    selected["schedule"] = [{
        "workout_name": row["name"], "session_type": row["session_type"],
        "duration_minutes": row["duration_minutes"], "estimated_minutes": row["estimated_minutes"],
        "exercises": row["exercises"], "rationale": row.get("rationale") or "", "warmup": row.get("warmup") or [],
    } for row in sessions]
    return selected

def resolve_split(preferred: str | None, days: int, experience: str) -> str:
    if preferred == "push_pull_legs":
        return "push_pull_legs" if days >= 3 else "full_body"
    if preferred == "upper_lower":
        return "upper_lower" if days >= 2 else "full_body"
    if preferred == "full_body":
        return "full_body"
    # GhostRep decides, body-part split, or no answer.
    if days <= 3:
        return "full_body"
    if days == 4 or experience == "beginner":
        return "upper_lower"
    return "push_pull_legs"


def estimate_minutes(exercises: list[dict]) -> int:
    """Warm-up plus working sets, rest between sets, and a minute to change stations."""
    seconds = 5 * 60
    for item in exercises:
        per_rep = 1 if item["exercise_id"] in TIMED else 3
        sets = int(item["sets"])
        seconds += sets * item["target_reps"] * per_rep + max(0, sets - 1) * item["rest_seconds"] + 60
    return round(seconds / 60)


SET_CAPS = {"slot": 4, "pool": 4}


def _fill_sets(exercises: list[dict], duration: int) -> None:
    """Use leftover time for more accessory sets. The main lift keeps its experience-based scheme."""
    while True:
        open_items = [
            item
            for item in exercises
            if item["_role"] in SET_CAPS
            and item["sets"] < (3 if CATALOG[item["exercise_id"]]["pattern"] == "core" else SET_CAPS[item["_role"]])
        ]
        if not open_items:
            return
        target = min(open_items, key=lambda item: (item["sets"], item["_role"] != "slot"))
        target["sets"] += 1
        if estimate_minutes(exercises) > duration:
            target["sets"] -= 1
            return


def _max_exercises(duration: int, days: int) -> int:
    count = 5 if duration <= 30 else 6 if duration <= 45 else 7 if duration <= 60 else 8
    return count - 1 if days >= 5 else count


def _drop_last(exercises: list[dict], role: str, keep: int) -> bool:
    removable = [i for i, item in enumerate(exercises) if item.get("_role") == role]
    if len(removable) <= keep:
        return False
    exercises.pop(removable[-1])
    return True


def _trim_sets(exercises: list[dict]) -> bool:
    for item in reversed(exercises):
        if item.get("_role") != "main" and item["sets"] > 2:
            item["sets"] -= 1
            return True
    main = next((item for item in exercises if item.get("_role") == "main"), None)
    if main and main["sets"] > 2:
        main["sets"] -= 1
        return True
    return _drop_last(exercises, "slot", keep=0)


def _accessory(ex_id: str, sets: int, reps: int, muscles: list[str], primary: str, role: str) -> dict:
    item = CATALOG[ex_id]
    pattern = item["pattern"]
    priority = bool(set(item.get("muscles") or []) & set(muscles)) and "full_body" not in muscles
    if pattern == "core":
        return {
            "exercise_id": ex_id,
            "sets": 2 if ex_id != "plank" else 3,
            "target_reps": 40 if ex_id in TIMED else 10,
            "rest_seconds": 45,
            "suggested_load_kg": None,
            "notes": "Hold for the target in seconds." if ex_id in TIMED else "Slow, controlled reps on each side.",
            "_role": role,
        }
    extra = 1 if priority and primary in {"build_muscle", "lose_body_fat"} else 0
    return {
        "exercise_id": ex_id,
        "sets": min(4, sets + extra),
        "target_reps": max(reps, 10) if pattern in {"isolation", "isolation_upper"} else reps,
        "rest_seconds": 60 if pattern in {"isolation", "isolation_upper"} else 75,
        "suggested_load_kg": None,
        "notes": "Priority muscle. Use a controlled movement." if priority else "Use a controlled movement.",
        "_role": role,
    }


def _volume(experience: str, primary: str) -> tuple[int, int, int]:
    strength = primary in {"increase_strength", "build_strength", "athletic_performance"}
    muscle = primary in {"build_muscle", "lose_body_fat"}
    if experience == "beginner":
        return (3, 8, 120) if strength else (3, 10, 90)
    if experience == "advanced" and strength:
        return (4, 5, 150)
    if muscle:
        return (3, 10, 90)
    if strength:
        return (3, 6, 150)
    return (3, 8, 90)


def _accessory_reps(experience: str, primary: str) -> int:
    if experience == "beginner":
        return 10
    if primary in {"build_muscle", "lose_body_fat"}:
        return 12
    if primary in {"increase_strength", "build_strength"} and experience == "advanced":
        return 6
    return 8


def _squat_order(familiarity: dict) -> list[str]:
    if familiarity.get("barbell_squat") == "new":
        return ["goblet_squat", "bodyweight_squat", "barbell_squat"]
    return SQUATS


def _rank(ex_id: str, muscles: list[str], primary: str, enjoyed: set[str] | None = None) -> tuple[int, int]:
    tags = set(CATALOG[ex_id].get("muscles") or [])
    enjoy = -2 if enjoyed and ex_id in enjoyed else 0
    if "full_body" in muscles or not muscles:
        return (enjoy, 0)
    overlap = len(tags & set(muscles))
    if primary in {"build_muscle", "lose_body_fat"} and overlap:
        overlap += 1
    return (-overlap + enjoy, 0)


def _conservative_load(view: dict, exercise_id: str) -> float | None:
    if exercise_id != "barbell_squat":
        return None
    working = (view.get("working_sets") or {}).get("barbell_squat") or {}
    load = working.get("weight_kg")
    if load is None:
        load = view.get("current_squat_load_kg")
    if load is None:
        return None
    load = float(load)
    if view["experience"] == "beginner" or view["familiarity"].get("barbell_squat") == "new":
        return round(load * 0.8, 1)
    return load


def _lower_body_fatigue(activities: list) -> bool:
    total = 0
    for item in activities:
        if not isinstance(item, dict):
            continue
        if item.get("activity") in LOWER_SPORTS:
            total += int(item.get("sessions_per_week") or 0)
    return total >= 2


def _split_label(split: str) -> str:
    return {"full_body": "full-body", "upper_lower": "upper/lower", "push_pull_legs": "push/pull/legs"}[split]


def _split_note(preferred: str | None, split: str, days: int) -> str:
    if preferred in {"push_pull_legs", "upper_lower"} and preferred != split:
        return f" Your preferred split needs more than {days} day{'s' if days != 1 else ''} a week, so this uses full-body sessions."
    if preferred == "body_part":
        return " Body-part splits are not built yet, so GhostRep chose a split for your frequency."
    return ""


def _plan_name(base: str, muscles: list[str], specified: bool | None, exercises: list[dict]) -> str:
    if not specified or "full_body" in muscles:
        return base
    trained = set()
    for item in exercises:
        trained |= set(CATALOG[item["exercise_id"]].get("muscles") or [])
    focus = [m for m in muscles if m in trained][:2]
    if not focus:
        return base
    return f"{base} · {' + '.join(m.replace('_', ' ').title() for m in focus)} focus"


def _main_note(exercise_id: str, view: dict) -> str:
    depth = " Stay at a comfortable depth." if "limited_squat_depth" in view["limitations"] else ""
    if exercise_id == "barbell_squat":
        return "Record this set from the side for movement analysis. Select a manageable load." + depth
    if CATALOG[exercise_id]["pattern"] == "squat":
        if view["experience"] == "beginner":
            return "Practice a comfortable squat depth. Stop if a movement feels painful."
        return "Use a controlled squat." + depth
    return "Main lift for this session. Leave one or two reps in reserve."
