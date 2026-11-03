"""Small, inference-free checks shared by saved coaching and decision writes."""

from __future__ import annotations

import hashlib
import json
import math

from fastapi import HTTPException

from app.models.entities import RecordedSet
from app.services.coaching.prescription import matching_exercise
from app.services.coaching.measurement_guard import recording_problem
from app.services.coaching.interpretation import interpretation_problem, record_context
from app.services.recording_provenance import SAMPLE_READ_ONLY, is_sample_set

CHANGE_ACTIONS = {"REDUCE_REPS", "EXTEND_REST", "REDUCE_LOAD_CONSERVATIVELY"}
SUPPORTED_ACTIONS = CHANGE_ACTIONS | {"KEEP_PLAN"}


def targets(exercise) -> dict:
    return {
        "target_reps": exercise.target_reps,
        "rest_seconds": exercise.rest_seconds,
        "suggested_load_kg": exercise.suggested_load_kg,
    }


def recommendation_context(rec: RecordedSet, *, analysis=None) -> dict:
    analysis = analysis or rec.analysis
    exercise = matching_exercise(rec)
    measured = None if analysis is None else {
        "id": analysis.id,
        "version": analysis.analysis_version,
        "quality": analysis.quality_json,
        "drift": analysis.drift_json,
        "overlay": analysis.overlay_json,
        "reference_rep": analysis.reference_rep,
        "pose_available": analysis.pose_available,
    }
    return {
        "set_id": rec.id,
        "session_id": rec.session_id,
        "plan_id": rec.session.plan_id if rec.session else None,
        "exercise_id": rec.exercise_id,
        "exercise_row_id": exercise.id if exercise else None,
        "planned_set_reps": rec.target_reps,
        "planned_set_load_kg": rec.load_kg,
        "completed_reps": rec.completed_reps,
        "analysis_sha256": hashlib.sha256(json.dumps(measured, sort_keys=True).encode()).hexdigest(),
        "targets": targets(exercise) if exercise else None,
    }


def require_ready(rec: RecordedSet) -> None:
    if is_sample_set(rec):
        raise HTTPException(409, SAMPLE_READ_ONLY)
    if recording_problem(rec):
        raise HTTPException(409, recording_problem(rec))
    if rec.processing_status != "COMPLETED" or rec.analysis is None or rec.exercise_id != "barbell_squat":
        raise HTTPException(409, "A completed squat analysis is required.")


def require_context(rec: RecordedSet, saved: dict) -> None:
    if not saved or saved != recommendation_context(rec):
        raise HTTPException(409, "The analysis or workout targets changed. This recommendation is stale; no decision was saved.")


def supported_problem(rec: RecordedSet, payload: dict) -> str | None:
    """Do not make incomplete, unsupported, or ungrounded changes actionable."""
    if is_sample_set(rec):
        return SAMPLE_READ_ONLY
    if recording_problem(rec):
        return recording_problem(rec)
    if problem := interpretation_problem(payload, record_context(rec)):
        return problem
    action = payload.get("suggested_action")
    if action not in SUPPORTED_ACTIONS:
        return "This output is review-only and does not contain a supported prescription."
    if rec.analysis is None or not rec.analysis.pose_available or not json.loads(rec.analysis.quality_json).get("usable") or not rec.completed_reps:
        return "Usable pose tracking and complete repetitions are required."
    exercise = matching_exercise(rec)
    session = rec.session
    if not exercise or not session or session.user_id != rec.user_id or exercise.plan.user_id != rec.user_id:
        return "No owned matching workout exercise is available."
    # Repeated catalog ids cannot safely identify a prescription from a recording.
    if sum(ex.exercise_id == rec.exercise_id for ex in exercise.plan.exercises) != 1:
        return "The workout has multiple matching exercise rows; the prescription is ambiguous."
    if not payload.get("summary") or not payload.get("reason") or payload.get("requires_confirmation") is not True:
        return "The saved recommendation is incomplete."
    if action == "KEEP_PLAN":
        return None
    observations = payload.get("observations") or []
    if not any(item.get("metric") != "camera_quality" and item.get("evidence_seconds") for item in observations):
        return "No replayable measured evidence supports a target change."
    field, current, predicate = {
        "REDUCE_REPS": ("suggested_reps", exercise.target_reps, lambda n, c: 1 <= n < c and n == int(n)),
        "EXTEND_REST": ("suggested_rest_seconds", exercise.rest_seconds, lambda n, c: c < n <= 300 and n == int(n)),
        "REDUCE_LOAD_CONSERVATIVELY": ("suggested_load_kg", exercise.suggested_load_kg, lambda n, c: 0 <= n < c and n >= c * 0.8),
    }[action]
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or current is None or not predicate(value, current):
        return "The suggested target is missing or outside the supported conservative range."
    return None
