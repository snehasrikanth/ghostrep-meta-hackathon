"""Store saved Muse coaching without replacing a pending local decision."""

from __future__ import annotations

import json
import hashlib

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from app.config import Settings
from app.models.entities import CoachingVersion, Profile, RecordedSet
from app.services.coaching.evidence import ground_coaching
from app.services.coaching.interpretation import display_interpretation, record_context
from app.services.coaching.prescription import coach_input_targets
from app.services.coaching.compatibility import recommendation_context, require_context, require_ready, supported_problem
from app.schemas.coaching import CoachingPayload
from app.services.meta.saved_results import (
    SavedResultError,
    load_json,
    public_coaching,
    saved_coaching_path,
)
from app.services.workout.history import recent_training_context
from app.services.recording_provenance import SAMPLE_READ_ONLY, is_sample_set


def list_versions(db: Session, set_id: str) -> list[dict]:
    rows = (
        db.query(CoachingVersion)
        .filter(CoachingVersion.set_id == set_id)
        .order_by(CoachingVersion.created_at.desc())
        .all()
    )
    rec = db.get(RecordedSet, set_id)
    return [version_out(row, rec) for row in rows]


def version_out(row: CoachingVersion, rec: RecordedSet | None = None) -> dict:
    payload = json.loads(row.payload_json)
    decision = rec.coaching if rec else None
    active = bool(decision and decision.active_version_id == row.id)
    state = "already_decided" if row.user_decision != "pending" else "actionable" if active else "superseded" if row.activated_at else "review_only"
    problem = None
    if rec:
        problem = supported_problem(rec, {**payload,"suggested_action":row.proposed_action,"summary":row.summary,"reason":row.reason})
        if json.loads(row.context_json or "null") != recommendation_context(rec):
            problem = "The analysis or workout targets changed; this version is stale."
        if rec.processing_status != "COMPLETED":
            problem = "Analysis is not ready."
        if rec.session.status not in {"active", "paused"}:
            problem = "The workout is already closed."
        if decision and decision.user_decision != "pending":
            problem = "The current recommendation has already been decided."
    if not row.verified:
        problem = "This version has not been verified for activation."
    if rec and is_sample_set(rec):
        problem = SAMPLE_READ_ONLY
        state = "review_only"
    output = {
        **payload,
        "id": row.id,
        "set_id": row.set_id,
        "source": row.source,
        "source_label": row.source_label,
        "suggested_action": row.proposed_action,
        "summary": row.summary,
        "reason": row.reason,
        "observations": payload.get("observations") or [],
        "uncertainties": payload.get("uncertainties") or [],
        "artifact_id": row.artifact_id,
        "actionable": active and row.user_decision == "pending" and problem is None,
        "state": state,
        "can_activate": bool(rec and decision and not active and not row.activated_at and not problem),
        "activation_blocked_reason": problem,
        "user_decision": row.user_decision,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

    return display_interpretation(output, record_context(rec)) if rec else output


def _profile_dict(db: Session, user_id: str) -> dict:
    row = db.query(Profile).filter(Profile.user_id == user_id).one_or_none()
    if not row:
        return {}
    return {
        "goal": row.goal,
        "experience": row.experience,
        "days_per_week": row.days_per_week,
        "session_duration_minutes": row.session_duration_minutes,
        "equipment": json.loads(row.equipment_json),
        "current_squat_load_kg": row.current_squat_load_kg,
        "limitations": json.loads(row.limitations_json or "[]"),
        "assessment": json.loads(row.assessment_json) if row.assessment_json else None,
        "display_name": None,
        "recent_sessions": recent_training_context(db, user_id),
    }


def import_saved_coaching(db: Session, settings: Settings, rec: RecordedSet) -> CoachingVersion:
    require_ready(rec)
    if rec.exercise_id != "barbell_squat":
        raise HTTPException(status_code=409, detail="Saved coaching can only attach to a barbell squat recording.")
    if rec.analysis is None or rec.processing_status != "COMPLETED":
        raise HTTPException(status_code=409, detail="Analysis is not ready for this recording.")
    try:
        raw = load_json(saved_coaching_path(settings))
        if raw is None:
            raise HTTPException(status_code=404, detail="No saved live Muse coaching result is on disk.")
        public = public_coaching(raw)
        CoachingPayload.model_validate(public["payload"], strict=True)
    except SavedResultError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(409, "The saved coaching payload is incomplete or malformed.") from exc
    artifact_set = public.get("set_id")
    if artifact_set != rec.id:
        raise HTTPException(status_code=409, detail="Saved coaching belongs to a different recording.")
    require_ready(rec)
    saved_context = public["payload"].get("recommendation_context")
    require_context(rec, saved_context)
    existing = (
        db.query(CoachingVersion)
        .filter(CoachingVersion.set_id == rec.id, CoachingVersion.artifact_id == public["attempt_id"])
        .one_or_none()
    )
    if existing:
        if json.loads(existing.context_json or "null") != saved_context or json.loads(existing.payload_json).get("artifact_sha256") != hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest():
            raise HTTPException(409, "The artifact identity was reused with different content or context.")
        return existing
    context = {
        "quality": json.loads(rec.analysis.quality_json) if rec.analysis.quality_json else {"usable": False, "issues": []},
        "drift": json.loads(rec.analysis.drift_json) if rec.analysis.drift_json else [],
        "reps": [
            {
                "rep_id": r.rep_index,
                "start_seconds": r.start_seconds,
                "bottom_seconds": r.bottom_seconds,
                "end_seconds": r.end_seconds,
                "is_complete": r.is_complete,
            }
            for r in rec.reps
            if r.is_complete
        ],
        "reference_rep": rec.analysis.reference_rep,
        "profile": _profile_dict(db, rec.user_id),
        "reported_rpe": rec.reported_rpe,
        **coach_input_targets(rec),
    }
    grounded = ground_coaching(dict(public["payload"]), context, context["profile"])
    # Guarding may remove unsupported claims, but must not manufacture a missing change.
    raw_problem = supported_problem(rec, public["payload"])
    grounded["recommendation_context"] = saved_context
    grounded["artifact_sha256"] = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    row = CoachingVersion(
        set_id=rec.id,
        source="muse_spark",
        source_label=public["source_label"],
        proposed_action=grounded.get("suggested_action") or public["suggested_action"],
        summary=grounded.get("summary") or public["summary"] or "",
        reason=grounded.get("reason") or public["reason"] or "",
        payload_json=json.dumps(grounded),
        artifact_id=public["attempt_id"],
        context_json=json.dumps(saved_context),
        verified=raw_problem is None and supported_problem(rec, grounded) is None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.query(CoachingVersion).filter_by(set_id=rec.id, artifact_id=public["attempt_id"]).one()
    db.refresh(row)
    return row
