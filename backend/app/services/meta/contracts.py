"""Request bodies and output checks for Muse Spark.

The JSON schema is the contract we will send. It is validated offline with
Pydantic. A live response that fails these checks is rejected, not replaced
with a local plan and labeled as Muse.
"""

from __future__ import annotations

import json
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from app.schemas.coaching import CoachAction

from app.services.meta.errors import MetaRejected
from app.services.workout.catalog import CATALOG
from app.services.workout.context import build_workout_context, validate_model_plan, squat_first_requested
from app.services.workout.profile_model import planner_view
from app.services.workout.local_planner import resolve_split
from app.services.workout.quality import review_week, session_work_minutes

EXERCISE_IDS = sorted(CATALOG)
COACH_ACTIONS = [
    "KEEP_PLAN",
    "REDUCE_REPS",
    "EXTEND_REST",
    "REDUCE_LOAD_CONSERVATIVELY",
    "REQUEST_NEW_RECORDING",
    "NO_RECOMMENDATION",
    "STOP_AND_SEEK_PROFESSIONAL_ADVICE",
]
COACH_METRICS = [
    "torso_inclination",
    "relative_depth",
    "ascent_duration",
    "descent_duration",
    "similarity",
    "knee_angle",
    "hip_path",
    "tracking_confidence",
    "camera_quality",
]


class _Exercise(BaseModel):
    exercise_id: str
    sets: int = Field(ge=1, le=8)
    target_reps: int = Field(ge=1, le=50)
    rest_seconds: int = Field(ge=15, le=300)
    suggested_load_kg: float | None = None
    notes: str = Field(default="", max_length=400)


class _Session(BaseModel):
    workout_name: str = Field(min_length=1, max_length=80)
    session_type: str = Field(default="", max_length=24)
    duration_minutes: int = Field(ge=10, le=120)
    exercises: list[_Exercise] = Field(min_length=1, max_length=8)
    rationale: str = Field(default="", max_length=1200)
    warmup: list[str] = Field(default_factory=list, max_length=5)


class WeekPlan(BaseModel):
    summary: str = Field(default="", max_length=1600)
    sessions: list[_Session] = Field(min_length=1, max_length=7)


def workout_response_format(session_count: int | None = None) -> dict:
    """Chat Completions structured-output payload for a complete training week.

    Matches Meta Model API `response_format.json_schema` with `strict: true`:
    https://dev.meta.ai/docs/structured-output
    https://dev.meta.ai/docs/api-reference/chat-completions/schemas

    Strict subset: root object, additionalProperties false on every object,
    required lists every property. Nullable loads use type [number, null].
    minItems/maxItems keep a four-day week valid without forcing prose fields.
    """
    days = _bounded_session_count(session_count)
    exercise = {
        "type": "object",
        "additionalProperties": False,
        "required": ["exercise_id", "sets", "target_reps", "rest_seconds", "suggested_load_kg", "notes"],
        "properties": {
            "exercise_id": {"type": "string", "enum": EXERCISE_IDS},
            "sets": {"type": "integer", "minimum": 1, "maximum": 8},
            "target_reps": {"type": "integer", "minimum": 1, "maximum": 50},
            "rest_seconds": {"type": "integer", "minimum": 15, "maximum": 300},
            "suggested_load_kg": {"type": ["number", "null"]},
            "notes": {"type": "string", "maxLength": 400},
        },
    }
    session = {
        "type": "object",
        "additionalProperties": False,
        "required": ["workout_name", "session_type", "duration_minutes", "exercises", "rationale", "warmup"],
        "properties": {
            "workout_name": {"type": "string", "maxLength": 80},
            "session_type": {"type": "string", "maxLength": 24},
            "duration_minutes": {"type": "integer", "minimum": 10, "maximum": 120},
            "exercises": {"type": "array", "minItems": 1, "maxItems": 8, "items": exercise},
            "rationale": {"type": "string", "maxLength": 1200},
            "warmup": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string"}},
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ghostrep_week",
            "strict": True,
            "description": "Personalized complete training week, with a clear rationale and practical warm-up for each session.",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["summary", "sessions"],
                "properties": {
                    "summary": {"type": "string", "maxLength": 1600},
                    "sessions": {
                        "type": "array",
                        "minItems": days[0],
                        "maxItems": days[1],
                        "items": session,
                    },
                },
            },
        },
    }


def coaching_response_format() -> dict:
    observation = {
        "type": "object",
        "additionalProperties": False,
        "required": ["metric", "statement", "evidence_seconds", "magnitude"],
        "properties": {
            "metric": {"type": "string", "enum": COACH_METRICS},
            "statement": {"type": "string"},
            "evidence_seconds": {"type": "array", "maxItems": 3, "items": {"type": "number"}},
            "magnitude": {"type": ["number", "null"]},
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ghostrep_coaching",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "summary",
                    "observations",
                    "uncertainties",
                    "suggested_action",
                    "explanation",
                    "suggested_reps",
                    "suggested_rest_seconds",
                    "suggested_load_kg",
                    "primary_cue",
                    "decision_basis",
                    "explanation_id",
                    "explanation_evidence_ids",
                ],
                "properties": {
                    "summary": {"type": "string"},
                    "observations": {"type": "array", "maxItems": 3, "items": observation},
                    "uncertainties": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
                    "suggested_action": {"type": "string", "enum": COACH_ACTIONS},
                    "explanation": {"type": "string"},
                    "suggested_reps": {"type": ["integer", "null"]},
                    "suggested_rest_seconds": {"type": ["integer", "null"]},
                    "suggested_load_kg": {"type": ["number", "null"]},
                    "primary_cue": {"type": ["string", "null"]},
                    "decision_basis": {"type": ["string", "null"], "enum": ["reported_effort", "relative_depth", "ascent_duration", "descent_duration", "keep", "unavailable", None]},
                    "explanation_id": {"type": ["string", "null"], "enum": ["effort_rest", "effort_scope", "timing_change", "range_change", "keep_targets", "review_evidence", None]},
                    "explanation_evidence_ids": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
                },
            },
        },
    }


def build_workout_messages(profile: dict, focus: str | None, session_index: int) -> list[dict]:
    context = build_workout_context(profile)
    # response_format ghostrep_week is the output contract. The local single-session
    # output_schema contradicts it and burns reasoning tokens reconciling the two.
    context.pop("output_schema", None)
    days = int((context.get("hard_constraints") or {}).get("days_per_week") or 0)
    minutes = int((context.get("hard_constraints") or {}).get("session_minutes") or 0)
    view = planner_view(profile)
    context["requested_training_structure"] = resolve_split(view.get("preferred_split"), days or 3, view.get("experience") or "beginner")
    context["next_session_index"] = session_index
    context["output_contract"] = {
        "name": "ghostrep_week",
        "sessions": days,
        "session_minutes": minutes,
        "complete_json_only": True,
    }
    if focus:
        context["requested_focus"] = focus
    day_clause = f"Return exactly {days} sessions, one per training day. " if days else "One session per training day. "
    minute_clause = f"Each session duration_minutes is {minutes}. " if minutes else ""
    return [
        {
            "role": "system",
            "content": (
                "Return one complete ghostrep_week JSON object and nothing else. "
                "No markdown or chain of thought. Explain choices only in summary and rationale fields. "
                + day_clause
                + minute_clause
                + "You are an experienced strength coach building a thoughtful, usable week for this athlete. "
                "Use only exercise_id values from the allowed exercise_catalog AND the schema enum. "
                "Prioritize the stated primary goal, preferred split, actual equipment, available time, and experience. "
                "When user_preferences.training_focus is lower_body, begin the week with a lower-body or full-body session led by a lower-body compound movement. "
                "When opening_exercise is barbell_squat, start the week with a lower-body or full-body session and make barbell_squat its first working exercise. "
                "This is the athlete's lower-body training preference. Keep upper-body days consistent with their selected split. "
                "In lower-body sessions that include barbell_squat, put it first, before hinges and accessories. "
                "Follow requested_training_structure exactly. For full_body, every session combines upper- and lower-body working movements. "
                "For upper_lower, alternate clearly labeled upper and lower sessions; do not substitute full-body sessions. "
                "The priority muscle choice full_body means balanced development across the week, not a request for full-body sessions. "
                "Use session_type full_body_a/full_body_b for a full-body split, upper/lower for upper_lower, or push/pull/legs for push_pull_legs. "
                "For strength, make the primary compound lift the first working exercise; order accessory work after it. "
                "When barbell squats are available and not excluded, include an appropriate squat session with an actionable setup/tempo cue. "
                "Fill each session so working sets, rest, a short warm-up, and transitions use the requested minutes. "
                "For plank, target_reps is hold seconds, not repetitions. "
                "Enjoyed exercises are optional preferences, not a checklist. "
                "Keep loaded primary lifts on a strength week; do not add a maintenance or deload day unless asked. "
                "Do not stack the same movement pattern in one session. "
                "Do not invent injuries, equipment bans, or overhead restrictions. "
                "Honor experience, equipment, exclusions, and recent sessions. "
                "Vary stress sensibly across the week rather than repeating maximal work on consecutive days. "
                "Choose a complete dose: working sets, reps, rest, and known load. Explain the session's role in the week in rationale. "
                "Do not invent a load above a stated working weight. "
                "Leave suggested_load_kg null when no working weight was given. "
                "Give each session 2-4 practical warm-up steps using the available equipment, including gradual practice sets for the main lift. "
                "Include a useful coaching cue in exercise notes; avoid generic filler. "
                "Self-check the completed plan before returning it: correct number of days; selected split; no invented restrictions; "
                "no excluded exercise; realistic time; no duplicated exercise within a session; timed holds measured in seconds. "
                "Estimate time as 5 minutes warm-up + sets*reps*(4 seconds compound, 3 seconds isolation) + "
                "(sets-1)*rest for each exercise + 90 seconds between exercises. Aim within 7 minutes of the request. "
                "Write a short personalized week summary that explains the actual choices without claiming guaranteed results. "
                "Age is context only: do not lower loads or drop a lift because of age. "
                "For an age range of 65 or older, include balance work. This is not medical advice."
            ),
        },
        {"role": "user", "content": json.dumps(context)},
    ]


def build_coaching_model_input(context: dict) -> dict:
    """Measurements the coach is allowed to see. No video, landmarks, or invented stats."""
    all_reps = list(context.get("reps") or [])
    reps = [r for r in all_reps if r.get("comparison_eligible") is not False]
    drift = [d for d in context.get("drift") or [] if d.get("comparison_valid") is not False]
    quality = context.get("quality") or {}
    present = _metrics_present(drift, quality)
    athlete = planner_view(context.get("profile") or {})
    return {
        "detected_reps": len(all_reps),
        "comparable_reps": len(reps),
        "completed_reps": len(reps),
        "reference_rep": context.get("reference_rep"),
        "repetitions": [
            {
                "rep": rep.get("rep_id"),
                "start_seconds": rep.get("start_seconds"),
                "bottom_seconds": rep.get("bottom_seconds"),
                "end_seconds": rep.get("end_seconds"),
                "descent_seconds": rep.get("descent_seconds"),
                "ascent_seconds": rep.get("ascent_seconds"),
                "confidence": rep.get("confidence"),
                "reliability": rep.get("reliability"),
                "comparison_eligible": rep.get("comparison_eligible"),
                "observed_range": rep.get("observed_range"),
            }
            for rep in reps
        ],
        "comparisons": [{**{k:v for k,v in d.items() if k!="torso_lean_difference_deg"},
            "torso_angle_rmse_deg":d.get("torso_angle_rmse_deg",d.get("torso_lean_difference_deg")),
            "upper_body_comparison":d.get("upper_body_comparison") or {"direction":"unavailable","reason":"Legacy unsigned RMS magnitude has no direction."}} for d in drift],
        "measurement_definitions": {"torso_angle_rmse_deg":"Unsigned phase-aligned RMS difference in degrees. A positive value means different, never more forward or more upright.",
            "upper_body_comparison":"Direction is relative to image vertical, from valid matched samples in both phases. No anatomical forward/backward direction or technique judgment is supplied."},
        "explanation_options": {
            "effort_rest": "Explain an independently supported rest suggestion using the actual reported effort, not fatigue or posture claims.",
            "effort_scope": "When rest alone changes and the rep target is known and unchanged, explain high reported effort while reassuring the user that their rep target stays the same. Choose this focus when it better answers the user's likely concern.",
            "timing_change": "Explain the proposed conservative change using a supported timing observation; differences do not establish faulty technique.",
            "range_change": "Explain the proposed conservative change using measured range differences, without an instruction to squat deeper.",
            "keep_targets": "Keep the existing targets; no supported correction is established.",
            "review_evidence": "Review evidence or improve recording quality before changing targets.",
        },
        "evidence_ids": [f"{metric}:r{d['rep_id']}" for d in drift for metric, field in
                         [("ascent_duration", "ascent_duration_difference_percent"), ("descent_duration", "descent_duration_difference_percent"), ("relative_depth", "depth_difference_percent")]
                         if d.get(field) is not None and any(r.get('rep_id') == d.get('rep_id') for r in reps)],
        "tracking": {
            "usable": bool(quality.get("usable")),
            "comparison_usable": quality.get("comparison_usable"),
            "unreliable_intervals": quality.get("unreliable_intervals", []),
            "score": quality.get("score"),
            "issues": [issue.get("message") for issue in quality.get("issues") or [] if isinstance(issue, dict)],
        },
        "metrics_present": sorted(present),
        "athlete": {"goal": athlete.get("primary_goal"), "experience": athlete.get("experience"),
                    "limitations": athlete.get("limitations") or []},
        "within_set_trend": _coaching_trend(reps),
        "prescription": {
            "planned_set_reps": context.get("planned_set_reps"),
            "completed_reps": context.get("completed_reps", len(reps)),
            "target_reps": context.get("current_reps"),
            "rest_seconds": context.get("current_rest"),
            "load_kg": context.get("current_load"),
            "reported_rpe": context.get("reported_rpe"),
        },
        "rules": [
            "Use only validated measurements; unavailable comparisons do not support reassurance or a movement change.",
            "No worsening trend does not imply all repetitions are consistent. Name supported middle-set variation with its rep and timestamp.",
            "Reported effort is separate from movement evidence. Explain an effort-based rest change explicitly.",
            "A personal reference is observed, not an ideal or safe-form standard.",
            "Do not invent joint angles, repetitions, or timestamps.",
            "Do not diagnose pain, injury, or medical conditions.",
            "Do not increase load, reps, or remove rest.",
            "Every observation needs an evidence timestamp from the repetitions above.",
            "Difference from a personal reference is variation, not automatically bad technique or fatigue.",
            "A later best rep does not prove earlier reps deteriorated. Check actual early-to-late timing.",
            "A recommendation must be confirmed by the athlete before it changes the plan.",
        ],
    }


def build_coaching_messages(context: dict) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "Act as a thoughtful squat coach. Explain only the supplied measurements in plain, supportive language. "
                "Write for someone without exercise terminology: use upper body instead of bare torso, "
                "time standing up instead of bare ascent, and time lowering down instead of bare descent. "
                "If a technical term helps, put it in parentheses after its everyday meaning once. "
                "No bracing-quality assessment or ideal-form standard is supplied. Do not invent one or call a reference strong/perfect. "
                "State the most useful observed difference clearly and identify the specific reps/timestamps supplied. "
                "Keep observations, explanation and action separate. Set primary_cue to null: no validated technique-correction assessment is supplied. "
                "A visible difference, including a more upright upper body, does not by itself establish incorrect posture, "
                "future injury, or that the athlete should lean farther forward. Do not make those claims. "
                "Do not invent numbers, diagnose injuries, or claim to detect fatigue from video alone. "
                "Do not increase the load or the rep target. Return complete JSON matching the schema. "
                "Compare early and late reps before describing a worsening trend. Differences from the personal reference "
                "are not a universal form score: the reference may be the final rep. "
                "Use the reported effort/RPE if present. Without it, do not infer that a short or trimmed set was a failed set. "
                "Do not reduce reps just because fewer reps appear in the recording than the prescribed target. "
                "Prefer KEEP_PLAN when the evidence does not clearly support changing the next-set dose. "
                "Never infer direction from positive torso_angle_rmse_deg. Use upper_body_comparison.direction only; if unavailable, state only an upper-body angle difference. "
                "Use decision_basis to identify independent evidence for a target change; upper-body angle or similarity alone cannot justify reps/load/rest changes. Do not invent a correction. "
                "A change needs a concrete observed reason; otherwise keep the targets or request evidence review without filling the gap with generic form advice. "
                "For KEEP_PLAN preserve prescription.target_reps, rest_seconds and load_kg exactly, not completed or planned-set reps. "
                "Choose explanation_id from explanation_options to match suggested_action and decision_basis. For timing/range changes cite matching explanation_evidence_ids from evidence_ids. These selections are validated and rendered using trusted facts; unsupported selections fall back without another request. "
                "Explain the decision and its practical benefit instead of repeating that consent is needed. "
                "Give one short explanation connecting the recommendation to its validated decision basis, with necessary uncertainty. Prefer actual paired phase durations when supplied; never reconstruct missing seconds from percentages. "
                "Include at most three observations, with one short statement and at most three "
                "evidence timestamps each, and at most three short uncertainties. "
                "Select the strongest evidence instead of listing every rep and metric."
            ),
        },
        {"role": "user", "content": json.dumps(build_coaching_model_input(context))},
    ]


def _coaching_trend(reps: list[dict]) -> dict | None:
    if len(reps) < 4:
        return None
    early, late = reps[:2], reps[-2:]
    def ascent(items):
        return sum(max(0, float(rep.get("end_seconds") or 0) - float(rep.get("bottom_seconds") or 0)) for rep in items) / len(items)
    start, end = ascent(early), ascent(late)
    return {"early_rep_ids": [r.get("rep_id") for r in early], "late_rep_ids": [r.get("rep_id") for r in late],
            "early_mean_ascent_seconds": round(start, 4), "late_mean_ascent_seconds": round(end, 4),
            "ascent_change_percent": round((end - start) / start * 100, 2) if start > 0 else None}


def parse_week(payload: dict) -> WeekPlan:
    try:
        if "sessions" in payload:
            return WeekPlan.model_validate(payload)
        return WeekPlan(
            summary=str(payload.get("summary") or payload.get("notes") or ""),
            sessions=[
                _Session.model_validate(
                    {
                        "workout_name": payload.get("workout_name") or payload.get("name") or "Workout",
                        "session_type": payload.get("session_type") or "",
                        "duration_minutes": payload.get("duration_minutes"),
                        "exercises": payload.get("exercises") or [],
                    }
                )
            ],
        )
    except ValidationError as exc:
        raise MetaRejected("The model output did not match the workout schema.") from exc


def accept_week(payload: dict, profile: dict, session_index: int, source: str, source_label: str) -> dict:
    week = parse_week(payload)
    review = review_week(week, profile)
    week = review["week"]
    issues = week_issues(week, profile)
    if issues:
        raise MetaRejected("Rejected model plan: " + " ".join(issues))
    chosen = week.sessions[session_index % len(week.sessions)]
    chosen_exercises = [item.model_dump() for item in chosen.exercises]
    estimated = session_work_minutes(chosen_exercises)
    schedule = [
        {
            "workout_name": session.workout_name,
            "session_type": session.session_type or None,
            "duration_minutes": session.duration_minutes,
            "estimated_minutes": session_work_minutes([item.model_dump() for item in session.exercises]),
            "exercises": [item.model_dump() for item in session.exercises],
            "rationale": session.rationale,
            "warmup": session.warmup,
        }
        for session in week.sessions
    ]
    note = week.summary.strip()
    position = f"Week session {session_index % len(week.sessions) + 1} of {len(week.sessions)}."
    if review["transforms"]:
        note = (note + " " + " ".join(review["transforms"])).strip()
    notes = f"{note} {position}".strip() if note else position
    return {
        "name": chosen.workout_name,
        "source": source,
        "source_label": source_label,
        "duration_minutes": chosen.duration_minutes,
        "estimated_minutes": estimated,
        "session_type": chosen.session_type or None,
        "notes": notes,
        "schedule": schedule,
        "exercises": chosen_exercises,
        "quality_warnings": review["warnings"],
        "quality_transforms": review["transforms"],
        "rationale": chosen.rationale,
        "warmup": chosen.warmup,
    }


def week_issues(week: WeekPlan, profile: dict) -> list[str]:
    view = planner_view(profile)
    issues: list[str] = []
    if view.get("training_focus") == "lower_body" and week.sessions:
        first = week.sessions[0].exercises[0].exercise_id
        if CATALOG.get(first, {}).get("pattern") not in {"squat", "hinge", "lunge"}:
            issues.append("The selected lower-body focus requires a lower-body opening exercise.")
    if squat_first_requested(profile):
        if not week.sessions or week.sessions[0].exercises[0].exercise_id != "barbell_squat":
            issues.append("The selected lower-body focus requires barbell squat as the first exercise of the opening session.")
        for session in week.sessions:
            ids = [item.exercise_id for item in session.exercises]
            if "barbell_squat" in ids and ids[0] != "barbell_squat":
                issues.append("Barbell squat must lead each session in which it is programmed for this lower-body focus.")
    days = int(view.get("days_per_week") or 0)
    if days and len(week.sessions) > days:
        issues.append(f"The week has {len(week.sessions)} sessions but the athlete trains {days} days.")
    caps = _load_caps(view)
    for session in week.sessions:
        plan = {
            "duration_minutes": session.duration_minutes,
            "exercises": [item.model_dump() for item in session.exercises],
        }
        issues.extend(validate_model_plan(plan, profile))
        for item in session.exercises:
            cap = caps.get(item.exercise_id)
            if cap is not None and item.suggested_load_kg is not None and item.suggested_load_kg > cap + 0.05:
                issues.append(f"{item.exercise_id} load {item.suggested_load_kg} is above the stated {cap} kg.")
    return issues


def workout_session_count(profile: dict) -> int | None:
    days = int(planner_view(profile).get("days_per_week") or 0)
    return days if days else None


def strict_schema_issues(payload: dict) -> list[str]:
    """Offline check against Meta's strict JSON Schema subset. Does not call Meta."""
    issues: list[str] = []
    if payload.get("type") != "json_schema":
        issues.append("response_format.type must be json_schema for Chat Completions structured output.")
        return issues
    spec = payload.get("json_schema") or {}
    name = str(spec.get("name") or "")
    if spec.get("strict") is not True:
        issues.append("json_schema.strict must be true.")
    if not name or len(name) > 64 or any(ch not in _SCHEMA_NAME_CHARS for ch in name):
        issues.append("json_schema.name must be 1-64 letters, digits, underscores, or dashes.")
    schema = spec.get("schema") or {}
    if schema.get("type") != "object":
        issues.append("strict root must be a plain object.")
    for key in ("anyOf", "oneOf", "allOf", "enum", "not"):
        if key in schema:
            issues.append(f"strict root cannot use {key}.")
    issues.extend(_strict_object_issues(schema, "$"))
    return issues


def _bounded_session_count(session_count: int | None) -> tuple[int, int]:
    if session_count:
        count = max(1, min(7, int(session_count)))
        return count, count
    return 1, 7


_SCHEMA_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _strict_object_issues(node: Any, path: str) -> list[str]:
    issues: list[str] = []
    if not isinstance(node, dict):
        return issues
    is_object = node.get("type") == "object" or "properties" in node
    if is_object:
        if node.get("additionalProperties") is not False:
            issues.append(f"{path} must set additionalProperties false.")
        props = node.get("properties") or {}
        required = set(node.get("required") or [])
        missing = [key for key in props if key not in required]
        if missing:
            issues.append(f"{path} required must list every property: {missing}.")
        if "allOf" in node or "oneOf" in node:
            issues.append(f"{path} allOf/oneOf are not in the strict subset.")
        for key, child in props.items():
            issues.extend(_strict_object_issues(child, f"{path}.{key}"))
    items = node.get("items")
    if isinstance(items, dict):
        issues.extend(_strict_object_issues(items, f"{path}[]"))
    return issues


def _load_caps(view: dict) -> dict[str, float]:
    caps: dict[str, float] = {}
    if view.get("current_squat_load_kg") is not None:
        caps["barbell_squat"] = float(view["current_squat_load_kg"])
    for key, value in (view.get("working_sets") or {}).items():
        if isinstance(value, dict) and value.get("weight_kg") is not None:
            caps[str(key)] = float(value["weight_kg"])
    return caps


def _metrics_present(drift: list[dict], quality: dict) -> set[str]:
    present: set[str] = set()
    mapping = {
        "torso_lean_difference_deg": "torso_inclination",
        "depth_difference_percent": "relative_depth",
        "ascent_duration_difference_percent": "ascent_duration",
        "descent_duration_difference_percent": "descent_duration",
        "similarity": "similarity",
        "knee_angle_rmse_deg": "knee_angle",
        "hip_rmse": "hip_path",
    }
    for item in drift:
        if item.get("comparison_valid") is False:
            continue
        for key, metric in mapping.items():
            value = item.get(key)
            if isinstance(value, (int, float)) and math.isfinite(value):
                present.add(metric)
    if quality.get("usable") is False:
        present.add("camera_quality")
    return present


class _MuseObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    metric: str
    statement: str
    evidence_seconds: list[float] = Field(max_length=3)
    magnitude: float | None


class _MuseCoaching(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    summary: str
    observations: list[_MuseObservation] = Field(max_length=3)
    uncertainties: list[str] = Field(max_length=3)
    suggested_action: CoachAction
    explanation: str
    suggested_reps: int | None
    suggested_rest_seconds: int | None
    suggested_load_kg: float | None
    primary_cue: str | None = None
    decision_basis: Literal["reported_effort","relative_depth","ascent_duration","descent_duration","keep","unavailable"] | None = None
    explanation_id: Literal["effort_rest","effort_scope","timing_change","range_change","keep_targets","review_evidence"] | None = None
    explanation_evidence_ids: list[str] = Field(default_factory=list, max_length=3)


def parse_coaching_payload(raw: dict, context: dict) -> dict[str, Any]:
    try:
        raw = _MuseCoaching.model_validate(raw).model_dump()
    except ValidationError as exc:
        raise MetaRejected("The model output did not match the strict coaching schema.") from exc
    try:
        summary = str(raw["summary"])
        explanation = str(raw["explanation"] if "explanation" in raw else raw["reason"])
        action = str(raw["suggested_action"])
        observations = list(raw.get("observations") or [])
        uncertainties = [str(item) for item in raw.get("uncertainties") or []]
    except (KeyError, TypeError) as exc:
        raise MetaRejected("The model output did not match the coaching schema.") from exc
    if action not in COACH_ACTIONS:
        raise MetaRejected("The model proposed an action outside the allowed set.")
    return {
        "source": "muse_spark",
        "source_label": "Muse Spark 1.3 (live)",
        "summary": summary,
        "observations": observations,
        "evidence_references": [],
        "confidence_notes": [],
        "uncertainties": uncertainties,
        "suggested_action": action,
        "reason": explanation,
        "primary_cue": raw.get("primary_cue"),
        "decision_basis": raw.get("decision_basis"),
        "explanation_id": raw.get("explanation_id"),
        "explanation_evidence_ids": raw.get("explanation_evidence_ids") or [],
        "requires_confirmation": True,
        "suggested_reps": raw.get("suggested_reps", context.get("current_reps")),
        "suggested_rest_seconds": raw.get("suggested_rest_seconds", context.get("current_rest")),
        "suggested_load_kg": raw.get("suggested_load_kg", context.get("current_load")),
        "current_reps": context.get("current_reps"),
        "current_rest_seconds": context.get("current_rest"),
        "current_load_kg": context.get("current_load"),
        "planned_set_reps": context.get("planned_set_reps"),
        "planned_set_load_kg": context.get("planned_set_load_kg"),
        "completed_reps": context.get("completed_reps"),
        "workout_reps": context.get("workout_reps", context.get("current_reps")),
        "workout_rest_seconds": context.get("workout_rest_seconds", context.get("current_rest")),
        "workout_load_kg": context.get("workout_load_kg", context.get("current_load")),
        "reported_rpe": context.get("reported_rpe"),
    }
