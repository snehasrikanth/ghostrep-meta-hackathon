from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, settings_dep
from app.api.serialize import coaching_out
from app.config import Settings
from app.models.entities import CoachingDecision, CoachingVersion, RecordedSet, User
from app.schemas.coaching import CoachingActivationIn, CoachingDecisionIn
from app.services.coaching.compatibility import (
    recommendation_context, require_context, require_ready, supported_problem, targets,
)
from app.services.coaching.prescription import matching_exercise
from app.services.coaching.versions import import_saved_coaching, list_versions, version_out

router = APIRouter(tags=["coaching"])


def _record(db: Session, set_id: str, user: User) -> RecordedSet:
    rec = db.get(RecordedSet, set_id)
    if not rec or rec.user_id != user.id or not rec.coaching:
        raise HTTPException(404, "Not found")
    return rec


def _lock(db: Session, set_id: str, user: User) -> RecordedSet:
    # First acquire the SQLite writer lock, then read the slot and prescription.
    # The no-op UPDATE also serializes on databases with row locks. No read/modify
    # race can accept a different version or apply two changes from stale targets.
    db.execute(update(CoachingDecision).where(
        CoachingDecision.set_id == set_id,
        CoachingDecision.set_id.in_(db.query(RecordedSet.id).filter(RecordedSet.user_id == user.id)),
    ).values(revision=CoachingDecision.revision).execution_options(synchronize_session=False))
    db.expire_all()
    return _record(db, set_id, user)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(503, "Could not save the recommendation. No change was saved; retry after refreshing.") from exc


def _out(db: Session, rec: RecordedSet) -> dict:
    return coaching_out(rec.coaching, rec=rec, session=rec.session, stored_versions=list_versions(db, rec.id))


@router.get("/coaching/{set_id}")
def get_coaching(set_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return _out(db, _record(db, set_id, user))


@router.post("/coaching/{set_id}/import-saved")
def import_saved(
    set_id: str, db: Session = Depends(get_db), user: User = Depends(current_user),
    settings: Settings = Depends(settings_dep),
) -> dict:
    rec = _record(db, set_id, user)
    row = import_saved_coaching(db, settings, rec)
    return {**version_out(row, rec), "pending_decision_preserved": rec.coaching.user_decision == "pending"}


@router.post("/coaching/{set_id}/versions/{version_id}/activate")
def activate(
    set_id: str, version_id: str, payload: CoachingActivationIn,
    db: Session = Depends(get_db), user: User = Depends(current_user),
) -> dict:
    rec = _lock(db, set_id, user)
    require_ready(rec)
    slot = rec.coaching
    version = db.get(CoachingVersion, version_id)
    if not version or version.set_id != rec.id:
        raise HTTPException(404, "Not found")
    if slot.user_decision != "pending":
        raise HTTPException(409, "The current recommendation has already been decided; it cannot be replaced.")
    # A retry of the same explicit activation is a read of the same active slot.
    if slot.active_version_id == version.id and payload.recommendation_id == slot.id and payload.expected_revision in {slot.revision, slot.revision - 1}:
        return _out(db, rec)
    if payload.recommendation_id != slot.id or payload.expected_revision != slot.revision:
        raise HTTPException(409, "The actionable recommendation changed. Refresh before choosing a version.")
    if not version.verified or version.activated_at or version.user_decision != "pending":
        raise HTTPException(409, "This version is unverified, superseded, or already decided.")
    if rec.session.status not in {"active", "paused"} or not rec.session.plan or rec.session.plan.status != "active":
        raise HTTPException(409, "Only an open workout with an active plan can use a saved version.")
    require_context(rec, json.loads(version.context_json or "null"))
    body = json.loads(version.payload_json)
    if body.get("recommendation_context") != json.loads(version.context_json or "null") or body.get("suggested_action") != version.proposed_action:
        raise HTTPException(409, "The saved version payload does not match its verified context or action.")
    effective={**body,"suggested_action":version.proposed_action,"summary":version.summary,"reason":version.reason}
    if problem := supported_problem(rec, effective):
        raise HTTPException(409, problem)
    # Preserve the complete previous payload, source, and decision metadata.
    # Existing decided slots are refused above, never silently overwritten.
    if slot.active_version_id is None:
        db.add(CoachingVersion(
            set_id=rec.id, source=slot.source,
            source_label=json.loads(slot.payload_json).get("source_label", slot.source),
            proposed_action=slot.proposed_action, summary=slot.summary, reason=slot.reason,
            payload_json=slot.payload_json, artifact_id=f"previous:{slot.id}:{slot.revision}",
            verified=False, context_json=json.dumps(recommendation_context(rec)),
            user_decision=slot.user_decision, activated_at=slot.created_at, decided_at=slot.decided_at,
        ))
    slot.source = version.source
    slot.proposed_action = version.proposed_action
    slot.summary = version.summary
    slot.reason = version.reason
    slot.payload_json = version.payload_json
    slot.active_version_id = version.id
    slot.revision += 1
    version.activated_at = datetime.now(timezone.utc)
    _commit(db)
    return _out(db, rec)


@router.post("/coaching/{set_id}/decision")
def decide(
    set_id: str, payload: CoachingDecisionIn,
    db: Session = Depends(get_db), user: User = Depends(current_user),
) -> dict:
    rec = _lock(db, set_id, user)
    require_ready(rec)
    slot = rec.coaching
    if slot.user_decision != "pending":
        raise HTTPException(409, "This recommendation was already decided.")
    # Legacy local clients are safe only before the first explicit activation.
    if (payload.recommendation_id is not None and payload.recommendation_id != slot.id) or (
        payload.expected_revision is not None and payload.expected_revision != slot.revision
    ) or (slot.revision > 0 and (payload.expected_revision is None or payload.recommendation_id is None)):
        raise HTTPException(409, "The actionable recommendation changed. Refresh before deciding.")
    body = json.loads(slot.payload_json)
    applied = {"applied": False, "action": slot.proposed_action, "reason": "rejected"}
    if payload.decision == "accepted":
        applied = _apply_decision(rec, body)
    slot.user_decision = payload.decision
    slot.decided_at = datetime.now(timezone.utc)
    body["applied_change"] = applied
    slot.payload_json = json.dumps(body)
    if slot.active_version_id:
        version = db.get(CoachingVersion, slot.active_version_id)
        version.user_decision = payload.decision
        version.decided_at = slot.decided_at
    _commit(db)
    return _out(db, rec)


def _apply_decision(rec: RecordedSet, body: dict) -> dict:
    require_ready(rec)
    action = rec.coaching.proposed_action
    session = rec.session
    result = {"applied": False, "action": action, "plan_id": session.plan_id, "session_status": session.status}
    if session.status not in {"active", "paused"} or not session.plan or session.plan.status != "active":
        return {**result, "reason": "workout_closed"}
    effective={**body,"suggested_action":rec.coaching.proposed_action,"summary":rec.coaching.summary,"reason":rec.coaching.reason}
    if problem := supported_problem(rec, effective):
        raise HTTPException(409, problem)
    exercise = matching_exercise(rec)
    before = targets(exercise)
    if saved := body.get("recommendation_context"):
        require_context(rec, saved)
    else:
        # Existing local recommendations predate context hashes. Never rebase
        # their adjustment onto newly edited targets.
        original = {"target_reps": body.get("current_reps"), "rest_seconds": body.get("current_rest_seconds"), "suggested_load_kg": body.get("current_load_kg")}
        if original != before:
            raise HTTPException(409, "The workout targets changed. This recommendation is stale; no decision was saved.")
    if action == "REDUCE_REPS":
        exercise.target_reps = int(body["suggested_reps"])
    elif action == "EXTEND_REST":
        exercise.rest_seconds = int(body["suggested_rest_seconds"])
    elif action == "REDUCE_LOAD_CONSERVATIVELY":
        exercise.suggested_load_kg = float(body["suggested_load_kg"])
    after = targets(exercise)
    return {**result, "applied": before != after, "reason": "applied" if before != after else "no_target_change", "exercise_id": rec.exercise_id, "exercise_row_id": exercise.id, "before": before, "after": after}
