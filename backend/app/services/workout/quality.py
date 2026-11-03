"""Programming-quality checks for a Muse week.

Hard safety stays in contracts.week_issues. This module flags weak programming
and applies a few explicit, recorded transforms. It does not silently replace
exercises or invent a different session.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.services.workout.catalog import CATALOG
from app.services.workout.local_planner import TIMED
from app.services.workout.profile_model import planner_view

WARMUP_SECONDS = 5 * 60
TRANSITION_SECONDS = 90
COMPOUND_SECONDS_PER_REP = 4
ISOLATION_SECONDS_PER_REP = 3
MIN_TIMED_SECONDS = 15
SHORT_SESSION_SLACK_MINUTES = 10
LONG_SESSION_SLACK_MINUTES = 15

_HOLD_SECONDS = re.compile(r"(?:hold|for)\s+(\d+)\s*(?:seconds|second|secs|sec|s)\b", re.I)
_INVENTED = [
    (re.compile(r"\bno overhead(?: work| pressing| press)?\b", re.I), "overhead"),
    (re.compile(r"\bavoid(?:ing)? overhead\b", re.I), "overhead"),
    (re.compile(r"\bbecause of (?:an? )?(?:injury|pain|limitation)\b", re.I), "injury"),
    (re.compile(r"\bno (?:jumping|impact|running)\b", re.I), "impact"),
]

_STRENGTH_GOALS = {"increase_strength", "build_strength", "athletic_performance"}
_SOFT_DAYS = re.compile(r"maintenance|deload|recovery|easy day", re.I)
_COMPOUND_PATTERNS = {"squat", "hinge", "lunge", "push", "push_vertical", "pull", "pull_vertical"}


def review_week(week, profile: dict) -> dict[str, Any]:
    """Normalize timed holds, then return warnings and recorded transforms."""
    view = planner_view(profile)
    transforms: list[str] = []
    sessions = []
    for session in week.sessions:
        exercises = []
        for item in session.exercises:
            data = item.model_dump()
            data, notes = _normalize_timed(data)
            transforms.extend(notes)
            exercises.append(item.model_copy(update=data))
        sessions.append(session.model_copy(update={"exercises": exercises}))
    week = week.model_copy(update={"sessions": sessions})
    invented = invented_restriction_claims(week.summary, view)
    summary, summary_notes = _strip_invented_claims(week.summary, view)
    transforms.extend(summary_notes)
    if summary != week.summary:
        week = week.model_copy(update={"summary": summary})
    warnings = _warnings(week, view)
    for kind in invented:
        message = f"Notes invent a '{kind}' restriction the athlete did not report."
        if message not in warnings:
            warnings.append(message)
    return {"week": week, "warnings": warnings, "transforms": transforms}


def session_work_minutes(exercises: list[dict]) -> int:
    """Warm-up, working sets, prescribed rest, and station changes."""
    seconds = WARMUP_SECONDS
    for index, item in enumerate(exercises):
        if index:
            seconds += TRANSITION_SECONDS
        seconds += _work_seconds(item) + _rest_seconds(item)
    return max(1, round(seconds / 60))


def _normalize_timed(item: dict) -> tuple[dict, list[str]]:
    if item.get("exercise_id") not in TIMED:
        return item, []
    current = int(item.get("target_reps") or 0)
    hold = _hold_from_notes(str(item.get("notes") or ""))
    if current >= MIN_TIMED_SECONDS:
        return item, []
    if hold and hold >= MIN_TIMED_SECONDS:
        updated = deepcopy(item)
        updated["target_reps"] = hold
        note = str(updated.get("notes") or "").strip()
        unit = "rep" if current == 1 else "reps"
        marker = f"Recorded as a {hold}-second hold, not {current} {unit}."
        updated["notes"] = f"{note} {marker}".strip() if note else marker
        return updated, [
            f"{item['exercise_id']} target_reps {current} -> {hold} seconds (explicit timed-hold normalization)."
        ]
    return item, []


def _hold_from_notes(notes: str) -> int | None:
    # Multiple different durations or alternatives are ambiguous; keep the raw dose.
    matches = {int(value) for value in _HOLD_SECONDS.findall(notes)}
    if len(matches) != 1 or re.search(r"\b(or|between|up to|optional|maybe)\b|\d\s*[-–]\s*\d", notes, re.I):
        return None
    return matches.pop()


def normalize_saved_exercises(exercises: list[dict]) -> tuple[list[dict], list[str]]:
    rows, transforms = [], []
    for item in exercises:
        row, notes = _normalize_timed(deepcopy(item))
        rows.append(row)
        transforms.extend(notes)
    return rows, transforms


def invented_restriction_claims(text: str, view: dict) -> list[str]:
    allowed = " ".join(
        str(item).lower()
        for item in (view.get("avoided_exercises") or []) + (view.get("limitations") or [])
    )
    found: list[str] = []
    for pattern, kind in _INVENTED:
        if pattern.search(text or "") and kind not in allowed:
            found.append(kind)
    return found


def _strip_invented_claims(text: str, view: dict) -> tuple[str, list[str]]:
    claims = invented_restriction_claims(text, view)
    if not claims:
        return text, []
    cleaned = text
    for pattern, kind in _INVENTED:
        if kind in claims:
            cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).replace(" .", ".").strip(" ,")
    if cleaned and not cleaned.endswith("."):
        cleaned += "."
    return cleaned, [f"Removed unverified '{kind}' restriction from the summary." for kind in claims]


def _warnings(week, view: dict) -> list[str]:
    warnings: list[str] = []
    requested = int(view.get("session_duration_minutes") or 0)
    goal = str(view.get("primary_goal") or "")
    enjoyed = set(view.get("enjoyed_exercises") or [])
    used_enjoyed: set[str] = set()
    loaded_sessions = 0
    for session in week.sessions:
        exercises = [item.model_dump() for item in session.exercises]
        estimated = session_work_minutes(exercises)
        if requested and estimated < requested - SHORT_SESSION_SLACK_MINUTES:
            warnings.append(
                f"{session.workout_name} estimates {estimated} min against a {requested}-min request."
            )
        warnings.extend(_pattern_warnings(session.workout_name, exercises))
        warnings.extend(_timed_warnings(session.workout_name, exercises))
        for item in exercises:
            used_enjoyed.add(item["exercise_id"])
        if _has_loaded_compound(exercises):
            loaded_sessions += 1
        if goal in _STRENGTH_GOALS and _SOFT_DAYS.search(session.workout_name or ""):
            warnings.append(f"{session.workout_name} is labeled as easy work on a strength week.")
        if goal in _STRENGTH_GOALS and exercises and exercises[0]["exercise_id"] == "bodyweight_squat":
            warnings.append(f"{session.workout_name} leads with an unloaded squat on a strength week.")
        blob = " ".join([week.summary, session.workout_name, *(item.get("notes") or "" for item in exercises)])
        for kind in invented_restriction_claims(blob, view):
            message = f"Notes invent a '{kind}' restriction the athlete did not report."
            if message not in warnings:
                warnings.append(message)
    if enjoyed and enjoyed <= used_enjoyed:
        warnings.append("Every enjoyed exercise was included; treat that list as a preference, not a checklist.")
    if goal in _STRENGTH_GOALS and week.sessions and loaded_sessions < len(week.sessions):
        warnings.append("At least one session has no loaded compound lift for a strength goal.")
    return warnings


def _pattern_warnings(name: str, exercises: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    ids: dict[str, int] = {}
    for item in exercises:
        catalog = CATALOG.get(item["exercise_id"]) or {}
        pattern = str(catalog.get("pattern") or "")
        if pattern in _COMPOUND_PATTERNS:
            counts[pattern] = counts.get(pattern, 0) + 1
        ids[item["exercise_id"]] = ids.get(item["exercise_id"], 0) + 1
    warnings = []
    for pattern, count in counts.items():
        if count >= 2:
            warnings.append(f"{name} repeats the {pattern} pattern {count} times.")
    for exercise_id, count in ids.items():
        if count >= 2:
            warnings.append(f"{name} lists {exercise_id} more than once.")
    return warnings


def _timed_warnings(name: str, exercises: list[dict]) -> list[str]:
    warnings = []
    for item in exercises:
        if item["exercise_id"] not in TIMED:
            continue
        if int(item.get("target_reps") or 0) < MIN_TIMED_SECONDS:
            warnings.append(
                f"{name} prescribes {item['exercise_id']} as {item.get('target_reps')} reps; timed holds use seconds."
            )
    return warnings


def _has_loaded_compound(exercises: list[dict]) -> bool:
    for item in exercises:
        catalog = CATALOG.get(item["exercise_id"]) or {}
        if catalog.get("pattern") not in _COMPOUND_PATTERNS:
            continue
        equipment = set(catalog.get("equipment") or [])
        if equipment - {"bodyweight"}:
            return True
    return False


def _work_seconds(item: dict) -> int:
    sets = max(1, int(item.get("sets") or 1))
    amount = max(1, int(item.get("target_reps") or 1))
    if item.get("exercise_id") in TIMED:
        return sets * amount
    catalog = CATALOG.get(item.get("exercise_id") or "") or {}
    per_rep = COMPOUND_SECONDS_PER_REP if catalog.get("pattern") in _COMPOUND_PATTERNS else ISOLATION_SECONDS_PER_REP
    return sets * amount * per_rep


def _rest_seconds(item: dict) -> int:
    sets = max(1, int(item.get("sets") or 1))
    return max(0, sets - 1) * int(item.get("rest_seconds") or 0)
