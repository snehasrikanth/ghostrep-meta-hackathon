from __future__ import annotations

import json
from datetime import datetime, timezone

from app.models.entities import (
    AnalysisResult,
    CoachingDecision,
    Profile,
    RecordedSet,
    WorkoutExercise,
    WorkoutPlan,
    WorkoutSession,
)
from app.services.coaching.prescription import attach_prescription, prescription_for_set
from app.services.coaching.compatibility import recommendation_context, supported_problem
from app.services.coaching.interpretation import display_interpretation, record_context
from app.services.workout.catalog import CATALOG, labeled_exercises
from app.services.workout.local_planner import TIMED
from app.services.workout.profile_model import assessment_from_legacy
from app.services.workout.proposals import why_this_workout
from app.services.workout.presentation import training_structure
from app.services.coaching.measurement_guard import recording_problem, suppress_unreliable
from app.services.recording_provenance import SAMPLE_READ_ONLY, is_performed_set, is_sample_set


def _iso(value: datetime | None) -> str | None:
    """SQLite drops tzinfo; every stored time is UTC, so say so on the wire."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def profile_out(row: Profile) -> dict:
    assessment = json.loads(row.assessment_json) if getattr(row, "assessment_json", None) else assessment_from_legacy({
        "goal": row.goal,
        "experience": row.experience,
        "days_per_week": row.days_per_week,
        "session_duration_minutes": row.session_duration_minutes,
        "equipment": json.loads(row.equipment_json),
        "current_squat_load_kg": row.current_squat_load_kg,
        "optional_height_cm": row.optional_height_cm,
        "optional_weight_kg": row.optional_weight_kg,
        "limitations": json.loads(row.limitations_json or "[]"),
        "display_name": getattr(row, "user", None).display_name if getattr(row, "user", None) else None,
    })
    stored_age = getattr(row, "age_range", None)
    identity = dict(assessment.get("identity") or {})
    if stored_age and not identity.get("age_range"):
        identity["age_range"] = stored_age
        assessment = {**assessment, "identity": identity}
    return {
        "id": row.id,
        "user_id": row.user_id,
        "goal": row.goal,
        "experience": row.experience,
        "days_per_week": row.days_per_week,
        "session_duration_minutes": row.session_duration_minutes,
        "equipment": json.loads(row.equipment_json),
        "current_squat_load_kg": row.current_squat_load_kg,
        "optional_height_cm": row.optional_height_cm,
        "optional_weight_kg": row.optional_weight_kg,
        "limitations": json.loads(row.limitations_json or "[]"),
        "display_name": getattr(row, "user", None).display_name if getattr(row, "user", None) else None,
        "age_range": stored_age or identity.get("age_range"),
        "assessment": assessment,
    }


def plan_out(plan: WorkoutPlan) -> dict:
    warnings = _json_list(getattr(plan, "warnings_json", None))
    try:
        context = json.loads(plan.context_json or "{}")
        guidance = context.get("guidance") or {}
    except (ValueError, TypeError):
        context, guidance = {}, {}
    structure = context.get("training_structure") or training_structure(
        {"assessment": {"preferences": {"preferred_split": (context.get("inputs") or {}).get("preferred_split")},
                        "schedule": {"days_per_week": (context.get("inputs") or {}).get("days_per_week") or len(_schedule(plan) or []) or 3}}},
        {"name": plan.name, "schedule": _schedule(plan), "session_type": plan.session_type},
    )
    structure = {**structure, "week_id": structure.get("week_id") or plan.id}
    return {
        "id": plan.id,
        "name": plan.name,
        "status": plan.status,
        "source": plan.source,
        "source_label": _source_label(plan.source),
        "duration_minutes": plan.duration_minutes,
        "estimated_minutes": plan.estimated_minutes,
        "session_type": plan.session_type,
        "created_at": _iso(plan.created_at),
        "notes": plan.notes,
        "schedule": _schedule(plan),
        "warnings": warnings,
        "why": why_this_workout(plan),
        "training_structure": structure,
        "rationale": guidance.get("rationale") or "",
        "warmup": guidance.get("warmup") or [],
        "exercises": [exercise_out(ex) for ex in plan.exercises],
    }


def exercise_out(ex: WorkoutExercise) -> dict:
    catalog = CATALOG.get(ex.exercise_id, {})
    return {
        "id": ex.id,
        "exercise_id": ex.exercise_id,
        "name": catalog.get("name", ex.exercise_id),
        "video_analysis": bool(catalog.get("video_analysis")),
        "measure": "seconds" if ex.exercise_id in TIMED else "reps",
        "position": ex.position,
        "sets": ex.sets,
        "target_reps": ex.target_reps,
        "rest_seconds": ex.rest_seconds,
        "suggested_load_kg": ex.suggested_load_kg,
        "notes": ex.notes,
    }


def session_out(row: WorkoutSession) -> dict:
    plan = row.plan
    return {
        "id": row.id,
        "plan_id": row.plan_id,
        "plan_name": plan.name if plan else None,
        "session_type": plan.session_type if plan else None,
        "status": row.status,
        "started_at": _iso(row.started_at),
        "paused_at": _iso(row.paused_at),
        "completed_at": _iso(row.completed_at),
        "summary": session_summary(row),
        "sample_only": bool(row.recorded_sets) and all(is_sample_set(s) for s in row.recorded_sets),
        "sets": [set_out(s) for s in row.recorded_sets],
    }


def is_done_set(s: RecordedSet) -> bool:
    """A logged set with reps, or a recording whose analysis counted at least one rep."""
    return is_performed_set(s)


def session_summary(row: WorkoutSession) -> dict:
    """Totals from sets that actually happened. Timed holds are not counted as reps."""
    done = [s for s in row.recorded_sets if is_done_set(s)]
    lifting = [s for s in done if s.exercise_id not in TIMED]
    timed = [s for s in done if s.exercise_id in TIMED]
    volume = sum((s.load_kg or 0) * (s.completed_reps or 0) for s in lifting)
    planned = sum(ex.sets for ex in row.plan.exercises) if row.plan else None
    return {
        "completed_sets": len(done),
        "planned_sets": planned,
        "total_reps": sum(s.completed_reps or 0 for s in lifting),
        "timed_seconds": sum(s.completed_reps or 0 for s in timed),
        "volume_kg": round(volume, 1),
        "exercises": sorted({s.exercise_id for s in done}),
    }


def set_out(row: RecordedSet) -> dict:
    analysis = row.analysis
    coaching = row.coaching
    sample = is_sample_set(row)
    return {
        "id": row.id,
        "session_id": row.session_id,
        "exercise_id": row.exercise_id,
        "exercise_name": CATALOG.get(row.exercise_id, {}).get("name", row.exercise_id),
        "entry_source": row.entry_source or "video",
        "set_index": row.set_index,
        "load_kg": row.load_kg,
        "target_reps": row.target_reps,
        "completed_reps": row.completed_reps,
        "reported_rpe": row.reported_rpe,
        "processing_status": row.processing_status,
        "processing_message": row.processing_message,
        "duration_seconds": row.duration_seconds,
        "created_at": _iso(row.created_at),
        "raw_deleted": bool(row.raw_deleted_at),
        "has_video": bool(row.normalized_path),
        "analysis_requested": bool(row.analysis_requested and row.entry_source != "manual"),
        "has_analysis": analysis is not None,
        "is_sample": sample,
        "reference_rep": analysis.reference_rep if analysis else None,
        "sam_status": analysis.sam_status if analysis else None,
        "coaching_decision": coaching.user_decision if coaching else None,
        "coaching_action": coaching.proposed_action if coaching else None,
        "coaching_source": coaching.source if coaching else None,
    }


def analysis_out(rec: RecordedSet, analysis: AnalysisResult | None) -> dict:
    session = rec.session
    warning=recording_problem(rec)
    reps = []
    for metric in rec.reps:
        data=json.loads(metric.metrics_json)
        reps.append(
            {
                "rep_id": metric.rep_index,
                "start_seconds": metric.start_seconds,
                "bottom_seconds": metric.bottom_seconds,
                "end_seconds": metric.end_seconds,
                "descent_seconds": metric.descent_seconds,
                "ascent_seconds": metric.ascent_seconds,
                "is_complete": metric.is_complete,
                "is_reference": metric.is_reference and not warning,
                "confidence": metric.confidence,
                "metrics": {k:v for k,v in data.items() if v is None or (isinstance(v,(int,float)) and not isinstance(v,bool))},
                "comparison_eligible":data.get("comparison_eligible",True),
                "movement_status":data.get("movement_status", "complete" if metric.is_complete else "partial"),
                "reliability":data.get("reliability"),
            }
        )
    quality = json.loads(analysis.quality_json) if analysis else None
    drift = json.loads(analysis.drift_json) if analysis else []
    if warning and quality:
        quality={**quality,"comparison_usable":False}
        drift=[]
        for rep in reps:
            rep["comparison_eligible"]=False
            for key in ["relative_depth","min_knee_angle_deg","max_torso_inclination_deg"]:
                rep["metrics"][key]=None
    return {
        "id": analysis.id if analysis else rec.id,
        "set_id": rec.id,
        "session_id": rec.session_id,
        "plan_id": session.plan_id if session else None,
        "session_status": session.status if session else None,
        "session_paused_at": _iso(session.paused_at) if session else None,
        "status": rec.processing_status,
        "message": rec.processing_message,
        "processing_started_at": _iso(rec.processing_started_at),
        "stage_started_at": _iso(rec.stage_started_at),
        "stage_timings": json.loads(rec.stage_timings_json or "{}"),
        "processing_stalled": bool(rec.stage_started_at and (datetime.now(timezone.utc)-rec.stage_started_at.replace(tzinfo=timezone.utc)).total_seconds()>600 and rec.processing_status not in {"COMPLETED","FAILED","SAVED"}),
        "planned_reps": rec.target_reps,
        "exercise_id": rec.exercise_id,
        "duration_seconds": rec.duration_seconds,
        "set_index": rec.set_index,
        "completed_reps": rec.completed_reps,
        "detected_reps": sum(r.is_complete for r in rec.reps),
        "partial_movements": sum(r["movement_status"]=="partial" for r in reps),
        "uncertain_movements": sum(r["movement_status"]=="uncertain" for r in reps),
        "measurement_warning": recording_problem(rec),
        "reference_rep": analysis.reference_rep if analysis and not warning else None,
        "tracking_quality": quality,
        "reps": reps,
        "drift": drift,
        "pose_available": analysis.pose_available if analysis else False,
        "sam_available": analysis.sam_available if analysis else False,
        "sam_status": analysis.sam_status if analysis else "unavailable",
        "analysis_version": analysis.analysis_version if analysis else "pending",
        "mode": "demo" if is_sample_set(rec) else "real",
        "is_sample": is_sample_set(rec),
    }


def coaching_out(
    row: CoachingDecision,
    *,
    rec: RecordedSet | None = None,
    session: WorkoutSession | None = None,
    applied: dict | None = None,
    stored_versions: list[dict] | None = None,
) -> dict:
    payload = json.loads(row.payload_json)
    session = session or (rec.session if rec is not None else None)
    effective={**payload,"suggested_action":row.proposed_action,"summary":row.summary,"reason":row.reason}
    problem = supported_problem(rec, effective) if rec is not None else None
    if rec is not None and payload.get("recommendation_context") and payload["recommendation_context"] != recommendation_context(rec):
        problem = "The analysis or workout targets changed; refresh and review a compatible recommendation."
    if rec is not None and rec.processing_status != "COMPLETED":
        problem = "Analysis is not ready."
    if session and session.status not in {"active", "paused"}:
        problem = "The workout is already closed."
    sample = rec is not None and is_sample_set(rec)
    if sample:
        problem = SAMPLE_READ_ONLY
    payload.update(
        {
            "id": row.id,
            "set_id": row.set_id,
            "plan_id": session.plan_id if session else None,
            "session_status": session.status if session else None,
            "user_decision": row.user_decision,
            "suggested_action": row.proposed_action,
            "reason": row.reason,
            "summary": row.summary,
            "source": row.source,
            "actionable": row.user_decision == "pending" and problem is None,
            "state": "already_decided" if row.user_decision != "pending" else "actionable" if problem is None else "review_only",
            "action_blocked_reason": problem if row.user_decision == "pending" else None,
            "revision": row.revision,
            "active_version_id": row.active_version_id,
            "applied_change": applied or payload.get("applied_change"),
            "stored_versions": stored_versions or [],
            "is_sample": sample,
        }
    )
    if sample:
        payload.update(actionable=False, state="review_only", action_blocked_reason=SAMPLE_READ_ONLY)
    if rec is not None:
        attach_prescription(payload, prescription_for_set(rec, session))
        payload = display_interpretation(payload, record_context(rec))
        if recording_problem(rec):
            payload = suppress_unreliable(payload, recording_problem(rec))
        from app.services.coaching.presentation import presentation_contract
        payload['presentation'] = presentation_contract(rec, payload, record_context(rec))
    return payload


def _json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _schedule(plan: WorkoutPlan):
    raw = getattr(plan, "schedule_json", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return [
        {**day, "exercises": labeled_exercises(day["exercises"])}
        if isinstance(day, dict) and isinstance(day.get("exercises"), list) else day
        for day in data
    ] or None


def _source_label(source: str) -> str:
    return {
        "local": "Local deterministic planner — not Muse Spark",
        "fixture": "Saved Muse Spark fixture — not a live call",
        "muse_spark": "Muse Spark 1.3 (live)",
    }.get(source, source)
