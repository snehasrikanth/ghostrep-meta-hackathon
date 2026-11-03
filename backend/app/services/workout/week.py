"""Build a visible training week without calling Muse or SAM.

Precedence: saved weekly schedule with exercise details, then the existing
local planner for missing sessions. Nothing here is persisted. Viewing a
saved Muse week is not a new live call.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.workout.catalog import CATALOG
from app.services.workout.local_planner import ROTATIONS, TIMED, generate_local_plan, resolve_split
from app.services.workout.profile_model import planner_view

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
WEEKDAY_LABELS = {
    "monday": "Monday",
    "tuesday": "Tuesday",
    "wednesday": "Wednesday",
    "thursday": "Thursday",
    "friday": "Friday",
    "saturday": "Saturday",
    "sunday": "Sunday",
}
DEFAULT_DAYS = {
    1: ["wednesday"],
    2: ["tuesday", "friday"],
    3: ["monday", "wednesday", "friday"],
    4: ["monday", "tuesday", "thursday", "saturday"],
    5: ["monday", "tuesday", "wednesday", "friday", "saturday"],
    6: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
    7: list(WEEKDAYS),
}
LOWER = {"lower", "legs"}
SOURCE_LABELS = {
    "saved_muse": "Saved Muse Spark week — not a new live call",
    "saved_fixture": "Saved Muse Spark fixture — not a live call",
    "saved_local": "Saved local workout",
    "local_preview": "Local workout preview — not Muse Spark",
    "sample": "Sample workout template — not your saved program",
}
PLAN_SOURCE_KIND = {
    "muse_spark": "saved_muse",
    "fixture": "saved_fixture",
    "local": "saved_local",
}
RECOVERY_COPY = "Recovery day. Walk, sleep, or easy mobility. GhostRep does not analyze recovery sessions."


def parse_today(value: str | None) -> date:
    """Calendar date from YYYY-MM-DD. Rejects timezone-shifted ISO datetimes."""
    if not value:
        raise ValueError("today is required as YYYY-MM-DD from the athlete's local calendar.")
    text = value.strip()
    if "T" in text or " " in text or len(text) != 10:
        raise ValueError("today must be YYYY-MM-DD, not a timestamp.")
    year, month, day = (int(part) for part in text.split("-"))
    return date(year, month, day)


def week_monday(today: date) -> date:
    return today - timedelta(days=today.weekday())


def place_training_days(preferred: list[str] | None, days: int) -> tuple[list[str], str]:
    """Return calendar-ordered training weekdays and whether they came from the profile."""
    days = max(1, min(7, int(days or 3)))
    seen: set[str] = set()
    valid: list[str] = []
    for item in preferred or []:
        key = str(item).strip().lower()
        if key in WEEKDAYS and key not in seen:
            seen.add(key)
            valid.append(key)
    if len(valid) == days:
        return [day for day in WEEKDAYS if day in seen], "preferred"
    defaults = DEFAULT_DAYS.get(days, DEFAULT_DAYS[3])
    placed = [day for day in valid if day in WEEKDAYS]
    for day in defaults:
        if day not in placed:
            placed.append(day)
        if len(placed) >= days:
            break
    return [day for day in WEEKDAYS if day in placed], "suggested"


def same_focus(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    return left in LOWER and right in LOWER


def has_exercise_details(session: dict | None) -> bool:
    exercises = (session or {}).get("exercises") or []
    if not isinstance(exercises, list) or not exercises:
        return False
    first = exercises[0]
    if not isinstance(first, dict):
        return False
    return bool(first.get("exercise_id")) and first.get("sets") is not None and first.get("target_reps") is not None


_SAVED_STATUSES = {"active", "completed", "replaced"}


def select_saved_schedule(plans: list[dict]) -> tuple[dict | None, list[dict] | None]:
    """Newest accepted plan whose saved week lists more than one session.

    Proposed and discarded plans keep their schedule for review, but they do
    not replace the visible weekly program until the athlete accepts.
    """
    for plan in plans:
        if plan.get("status") not in _SAVED_STATUSES:
            continue
        schedule = plan.get("schedule")
        if isinstance(schedule, list) and len(schedule) > 1:
            return plan, schedule
    return None, None


def build_program(
    *,
    profile: dict,
    today: date,
    week_count: int = 1,
    saved_schedule: list[dict] | None = None,
    saved_source: str | None = None,
    next_plan: dict | None = None,
    open_session: dict | None = None,
    history: list[dict] | None = None,
    saved_structure: dict | None = None,
) -> dict:
    view = planner_view(profile)
    days_per_week = max(1, min(7, int(view.get("days_per_week") or 3)))
    split = resolve_split(view.get("preferred_split"), days_per_week, view.get("experience") or "beginner")
    if saved_structure:
        days_per_week = int(saved_structure.get("sessions_per_week") or days_per_week)
        split = saved_structure.get("split") or split
    rotation = ROTATIONS.get(split, ROTATIONS[resolve_split(view.get("preferred_split"), days_per_week, view.get("experience") or "beginner")])
    preferred = list((saved_structure or {}).get("preferred_days", view.get("preferred_days")) or [])
    training_days, placement_mode = place_training_days(preferred, days_per_week)
    sessions, session_notes = _week_sessions(
        profile,
        days_per_week,
        rotation,
        saved_schedule,
        saved_source,
    )
    monday = week_monday(today)
    week0 = _assemble_week(
        monday=monday,
        today=today,
        training_days=training_days,
        sessions=sessions,
        session_notes=session_notes,
        placement_mode=placement_mode,
        is_repeat=False,
    )
    _overlay_history(week0["days"], history)
    _overlay_real_plan(week0["days"], next_plan, open_session, today=today)
    weeks = [week0]
    count = 4 if week_count >= 4 else 1
    for index in range(1, count):
        weeks.append(
            _assemble_week(
                monday=monday + timedelta(days=7 * index),
                today=today,
                training_days=training_days,
                sessions=sessions,
                session_notes=session_notes,
                placement_mode=placement_mode,
                is_repeat=True,
            )
        )
    weeks = _assemble_week_indexes(weeks)
    return {
        "split": split,
        "days_per_week": days_per_week,
        "preferred_days": preferred,
        "training_days": training_days,
        "placement_mode": placement_mode,
        "placement_note": _placement_note(placement_mode, preferred, days_per_week),
        "today": today.isoformat(),
        "week_count": count,
        "weeks": weeks,
    }


def _week_sessions(
    profile: dict,
    days_per_week: int,
    rotation: list[str],
    saved_schedule: list[dict] | None,
    saved_source: str | None,
) -> tuple[list[dict], list[str | None]]:
    sessions: list[dict] = []
    notes: list[str | None] = []
    saved = list(saved_schedule or [])[:days_per_week]
    kind = PLAN_SOURCE_KIND.get(saved_source or "", "local_preview") if saved_source else None
    for index in range(days_per_week):
        if index < len(saved):
            row = saved[index]
            if has_exercise_details(row):
                sessions.append(_from_saved(row, kind or "local_preview"))
                notes.append(None)
                continue
            focus = row.get("session_type") or rotation[index % len(rotation)]
            sessions.append(_from_local(generate_local_plan(profile, focus=str(focus), session_index=index)))
            notes.append("This saved week named the session but did not include exercise details.")
            continue
        sessions.append(_from_local(generate_local_plan(profile, session_index=index)))
        notes.append(None)
    return sessions, notes


def _from_local(plan: dict) -> dict:
    exercises = [_exercise_out(item, position) for position, item in enumerate(plan.get("exercises") or [])]
    return {
        "name": plan.get("name") or "Workout",
        "session_type": plan.get("session_type"),
        "duration_minutes": int(plan.get("duration_minutes") or 45),
        "estimated_minutes": plan.get("estimated_minutes"),
        "notes": plan.get("notes"),
        "rationale": plan.get("rationale") or "",
        "warmup": plan.get("warmup") or [],
        "exercises": exercises,
        "source_kind": "local_preview",
        "source_label": SOURCE_LABELS["local_preview"],
    }


def _from_saved(row: dict, kind: str) -> dict:
    exercises = [_exercise_out(item, position) for position, item in enumerate(row.get("exercises") or [])]
    duration = int(row.get("duration_minutes") or 45)
    estimated = row.get("estimated_minutes")
    if estimated is None:
        from app.services.workout.local_planner import estimate_minutes

        estimated = estimate_minutes(
            [
                {
                    "exercise_id": item["exercise_id"],
                    "sets": item["sets"],
                    "target_reps": item["target_reps"],
                    "rest_seconds": item["rest_seconds"],
                }
                for item in exercises
            ]
        ) if exercises else duration
    return {
        "name": row.get("workout_name") or row.get("name") or "Workout",
        "session_type": row.get("session_type") or None,
        "duration_minutes": duration,
        "estimated_minutes": estimated,
        "notes": row.get("notes"),
        "rationale": row.get("rationale") or "",
        "warmup": row.get("warmup") or [],
        "exercises": exercises,
        "source_kind": kind,
        "source_label": SOURCE_LABELS.get(kind, SOURCE_LABELS["local_preview"]),
    }


def _from_plan(plan: dict) -> dict:
    kind = PLAN_SOURCE_KIND.get(plan.get("source") or "local", "saved_local")
    exercises = list(plan.get("exercises") or [])
    return {
        "name": plan.get("name") or "Workout",
        "session_type": plan.get("session_type"),
        "duration_minutes": int(plan.get("duration_minutes") or 45),
        "estimated_minutes": plan.get("estimated_minutes"),
        "notes": plan.get("notes"),
        "rationale": plan.get("rationale") or "",
        "warmup": plan.get("warmup") or [],
        "exercises": [_exercise_out(item, index) for index, item in enumerate(exercises)],
        "source_kind": kind,
        "source_label": plan.get("source_label") or SOURCE_LABELS[kind],
    }


def _exercise_out(item: dict, position: int) -> dict:
    exercise_id = str(item.get("exercise_id") or "")
    catalog = CATALOG.get(exercise_id, {})
    return {
        "id": item.get("id") or f"preview:{exercise_id}:{position}",
        "exercise_id": exercise_id,
        "name": catalog.get("name", exercise_id.replace("_", " ")),
        "video_analysis": bool(catalog.get("video_analysis")),
        "measure": "seconds" if exercise_id in TIMED else "reps",
        "position": int(item.get("position") if item.get("position") is not None else position),
        "sets": int(item.get("sets") or 1),
        "target_reps": int(item.get("target_reps") or 1),
        "rest_seconds": int(item.get("rest_seconds") or 60),
        "suggested_load_kg": item.get("suggested_load_kg"),
        "notes": item.get("notes"),
    }


def _assemble_week(
    *,
    monday: date,
    today: date,
    training_days: list[str],
    sessions: list[dict],
    session_notes: list[str | None],
    placement_mode: str,
    is_repeat: bool,
) -> dict:
    days = []
    for offset, weekday in enumerate(WEEKDAYS):
        current = monday + timedelta(days=offset)
        if weekday in training_days:
            slot = training_days.index(weekday)
            session = sessions[slot]
            workout = _workout_payload(session, preview=True)
            days.append(
                {
                    "date": current.isoformat(),
                    "weekday": weekday,
                    "weekday_label": WEEKDAY_LABELS[weekday],
                    "kind": "training",
                    "is_today": current == today,
                    "is_next": False,
                    "is_preview": True,
                    "plan_id": None,
                    "session_status": None,
                    "source": session.get("source_kind") or "local_preview",
                    "source_label": session.get("source_label") or SOURCE_LABELS["local_preview"],
                    "placement_note": None if placement_mode == "preferred" else "Suggested day — your preferred days were incomplete or did not match training frequency.",
                    "detail_note": session_notes[slot],
                    "recovery_copy": None,
                    "workout": workout,
                }
            )
        else:
            days.append(
                {
                    "date": current.isoformat(),
                    "weekday": weekday,
                    "weekday_label": WEEKDAY_LABELS[weekday],
                    "kind": "recovery",
                    "is_today": current == today,
                    "is_next": False,
                    "is_preview": True,
                    "plan_id": None,
                    "session_status": None,
                    "source": "local_preview",
                    "source_label": SOURCE_LABELS["local_preview"],
                    "placement_note": None,
                    "detail_note": None,
                    "recovery_copy": RECOVERY_COPY,
                    "workout": None,
                }
            )
        if is_repeat:
            days[-1]["is_next"] = False
            days[-1]["plan_id"] = None
            days[-1]["session_status"] = None
            days[-1]["is_preview"] = True
            if days[-1]["kind"] == "training":
                days[-1]["detail_note"] = "Schedule preview — this repeats this week's structure. It is not a new plan or a completed workout."
    label = "This week" if not is_repeat else f"Week of {monday.isoformat()}"
    return {
        "week_index": 0,
        "start": monday.isoformat(),
        "label": label,
        "is_repeat": is_repeat,
        "days": days,
    }


def _overlay_history(days: list[dict], history: list[dict] | None) -> None:
    by_date = {day["date"]: day for day in days}
    training = [day for day in days if day["kind"] == "training"]
    for row in history or []:
        actual = by_date.get(row.get("date"))
        if not actual:
            continue
        structure = (row.get("plan") or {}).get("training_structure") or {}
        slot = structure.get("session_index")
        target = training[slot] if isinstance(slot, int) and 0 <= slot < len(training) else actual
        if target["kind"] == "training":
            _apply_real_workout(target, row["plan"], session_status=row.get("status"), is_next=False)


def _overlay_real_plan(
    days: list[dict],
    next_plan: dict | None,
    open_session: dict | None,
    *,
    today: date | None = None,
) -> None:
    if not next_plan:
        return
    training = [day for day in days if day["kind"] == "training"]
    if not training:
        return
    slot = (next_plan.get("training_structure") or {}).get("session_index")
    target = training[slot] if isinstance(slot, int) and 0 <= slot < len(training) else None
    open_date = (open_session or {}).get("date")
    if target is None and open_date:
        target = next((day for day in days if day["date"] == open_date), None)
    if target is None:
        matching = [
            day
            for day in training
            if same_focus(day["workout"]["session_type"] if day.get("workout") else None, next_plan.get("session_type"))
            and (day["is_preview"] or day.get("plan_id") in {None, next_plan.get("id")})
        ]
        if today is not None:
            upcoming = [day for day in matching if day["date"] >= today.isoformat()]
            target = (upcoming or matching or training)[0]
        else:
            target = (matching or training)[0]
    _apply_real_workout(
        target,
        next_plan,
        session_status=(open_session or {}).get("status") if (open_session or {}).get("plan_id") == next_plan.get("id") else target.get("session_status"),
        is_next=True,
    )


def _apply_real_workout(day: dict, plan: dict, *, session_status: str | None, is_next: bool) -> None:
    workout = _workout_payload(_from_plan(plan), preview=False)
    day["kind"] = "training"
    day["recovery_copy"] = None
    day["plan_id"] = plan.get("id")
    day["is_preview"] = False
    day["is_next"] = is_next
    day["source"] = PLAN_SOURCE_KIND.get(plan.get("source") or "local", "saved_local")
    day["source_label"] = plan.get("source_label") or SOURCE_LABELS[day["source"]]
    day["workout"] = workout
    day["detail_note"] = None
    if session_status:
        day["session_status"] = session_status


def _workout_payload(session: dict, *, preview: bool) -> dict:
    exercises = list(session.get("exercises") or [])
    return {
        "name": session.get("name") or "Workout",
        "session_type": session.get("session_type"),
        "duration_minutes": session.get("duration_minutes"),
        "estimated_minutes": session.get("estimated_minutes"),
        "notes": session.get("notes"),
        "rationale": session.get("rationale") or "",
        "warmup": session.get("warmup") or [],
        "exercises": exercises,
        "has_video_analysis": any(item.get("video_analysis") for item in exercises),
        "is_preview": preview,
    }


def _placement_note(mode: str, preferred: list[str], days: int) -> str | None:
    if mode == "preferred":
        return None
    if not preferred:
        return f"Training days are suggested for a {days}-day week. Add preferred days in your profile if you want a fixed calendar."
    return (
        f"Your profile lists {len(preferred)} preferred day{'s' if len(preferred) != 1 else ''} "
        f"for a {days}-day week, so GhostRep suggested the remaining training days. The profile was not changed."
    )


def _assemble_week_indexes(weeks: list[dict]) -> list[dict]:
    for index, week in enumerate(weeks):
        week["week_index"] = index
        if index == 0:
            week["label"] = "This week"
        else:
            week["label"] = f"Week {index + 1} · schedule preview"
    return weeks
