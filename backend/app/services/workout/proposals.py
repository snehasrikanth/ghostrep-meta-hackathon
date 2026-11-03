"""Proposal lifecycle. Generate stores a reviewable plan; accept persists it.

Accept and discard never call Muse, SAM, or any model transport.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import User, WorkoutExercise, WorkoutPlan, WorkoutSession
from app.services.workout.context import validate_model_plan
from app.services.workout.profile_model import planner_view
from app.services.workout.presentation import training_structure
from app.services.recording_provenance import is_performed_set, is_sample_set

PROPOSED = "proposed"
DISCARDED = "discarded"
ACTIVE = "active"
OPEN = ("active", "paused")


def inputs_snapshot(profile: dict, session_index: int, focus: str | None, recent: list[dict]) -> dict:
    view = planner_view(profile)
    working = {}
    for key, item in (view.get("working_sets") or {}).items():
        if not isinstance(item, dict):
            continue
        weight = item.get("weight_kg")
        reps = item.get("reps")
        if weight is None and reps is None:
            continue
        row = {}
        if weight is not None:
            row["weight_kg"] = weight
        if reps is not None:
            row["reps"] = reps
        working[key] = row
    return {
        "goal": view.get("primary_goal"),
        "training_focus": view.get("training_focus"),
        "experience": view.get("experience"),
        "equipment": list(view.get("equipment") or []),
        "session_minutes": view.get("session_duration_minutes"),
        "preferred_split": view.get("preferred_split"),
        "days_per_week": view.get("days_per_week"),
        "working_sets_kg": working,
        "recent_sessions": recent,
        "session_index": session_index,
        "focus": focus,
    }


def why_this_workout(plan: WorkoutPlan) -> dict | None:
    raw = getattr(plan, "context_json", None)
    if not raw:
        return None
    try:
        context = json.loads(raw)
    except json.JSONDecodeError:
        return None
    inputs = context.get("inputs") or {}
    recent = inputs.get("recent_sessions") or []
    used = []
    for field, label in (
        ("goal", "Stated goal"),
        ("training_focus", "Training focus"),
        ("experience", "Experience"),
        ("equipment", "Available equipment"),
        ("session_minutes", "Session duration"),
        ("preferred_split", "Preferred split"),
        ("days_per_week", "Days per week"),
        ("focus", "Requested focus"),
    ):
        value = inputs.get(field)
        if value in (None, "", []):
            continue
        used.append({"field": field, "label": label, "value": value})
    working = inputs.get("working_sets_kg") or {}
    if working:
        used.append({"field": "working_sets_kg", "label": "Stated working weights", "value": working})
    used.append(
        {
            "field": "recent_sessions",
            "label": "Recent completed sessions",
            "value": recent if recent else "none recorded",
        }
    )
    source = plan.source
    model_summary = context.get("model_summary")
    return {
        "kind": "inputs_used",
        "disclaimer": (
            "These are the stored inputs used to build this proposal. "
            "This list does not claim that the model used a particular input to make a specific decision."
        ),
        "inputs": used,
        "recent_sessions": recent,
        "generated_at": context.get("generated_at"),
        "model_summary": model_summary if source == "muse_spark" else None,
        "model_explanation_present": bool(model_summary) and source == "muse_spark",
    }


def imported_plan(db: Session, user: User, artifact_id: str | None) -> WorkoutPlan | None:
    if not artifact_id:
        return None
    for plan in db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id).all():
        raw = getattr(plan, "context_json", None)
        if not raw:
            continue
        try:
            context = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if context.get("artifact_id") == artifact_id:
            return plan
    return None


def persist_proposal(
    db: Session,
    user: User,
    plan_data: dict,
    profile: dict,
    session_index: int,
    focus: str | None,
    recent: list[dict],
    artifact_id: str | None = None,
) -> WorkoutPlan:
    existing = imported_plan(db, user, artifact_id)
    if existing:
        if existing.status == DISCARDED:
            for old in (
                db.query(WorkoutPlan)
                .filter(WorkoutPlan.user_id == user.id, WorkoutPlan.status == PROPOSED, WorkoutPlan.id != existing.id)
                .all()
            ):
                old.status = DISCARDED
            existing.status = PROPOSED
            db.commit()
            db.refresh(existing)
        return existing
    for old in (
        db.query(WorkoutPlan)
        .filter(WorkoutPlan.user_id == user.id, WorkoutPlan.status == PROPOSED)
        .all()
    ):
        # Selecting a saved session must not discard a separately generated week.
        if plan_data.get("proposal_kind") != "session" or _proposal_kind(old) == "session":
            old.status = DISCARDED

    warnings = [str(item) for item in (plan_data.get("quality_warnings") or []) if item]
    for issue in validate_model_plan(plan_data, profile):
        if issue not in warnings:
            warnings.append(issue)
    context = {
        "inputs": inputs_snapshot(profile, session_index, focus, recent),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": plan_data.get("source", "local"),
        "model_summary": plan_data.get("notes") if plan_data.get("source") == "muse_spark" else None,
        "artifact_id": artifact_id,
        "training_structure": plan_data.get("training_structure") or training_structure(profile, plan_data, session_index),
        "guidance": {"warmup": plan_data.get("warmup") or [], "rationale": plan_data.get("rationale") or ""},
    }
    plan = WorkoutPlan(
        user_id=user.id,
        name=plan_data["name"],
        status=PROPOSED,
        source=plan_data.get("source", "local"),
        duration_minutes=plan_data["duration_minutes"],
        estimated_minutes=plan_data.get("estimated_minutes"),
        session_type=plan_data.get("session_type"),
        notes=plan_data.get("notes"),
        schedule_json=json.dumps(plan_data["schedule"]) if plan_data.get("schedule") else None,
        context_json=json.dumps(context),
        warnings_json=json.dumps(warnings),
    )
    db.add(plan)
    db.flush()
    context["training_structure"].setdefault("week_id", plan.id)
    plan.context_json = json.dumps(context)
    for index, item in enumerate(plan_data["exercises"]):
        db.add(
            WorkoutExercise(
                plan_id=plan.id,
                exercise_id=item["exercise_id"],
                position=index,
                sets=item["sets"],
                target_reps=item["target_reps"],
                rest_seconds=item["rest_seconds"],
                suggested_load_kg=item.get("suggested_load_kg"),
                notes=item.get("notes"),
            )
        )
    db.commit()
    db.refresh(plan)
    return plan


def _proposal_kind(plan: WorkoutPlan) -> str:
    try:
        return (json.loads(plan.context_json or "{}").get("training_structure") or {}).get("proposal_kind", "week")
    except (ValueError, TypeError):
        return "week"


def latest_proposal(db: Session, user: User) -> WorkoutPlan | None:
    rows = (db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id, WorkoutPlan.status == PROPOSED)
            .order_by(WorkoutPlan.created_at.desc()).all())
    return next((row for row in rows if _proposal_kind(row) == "week"), rows[0] if rows else None)


def accept_proposal(db: Session, user: User, plan: WorkoutPlan) -> WorkoutPlan:
    if plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    if plan.status == ACTIVE:
        return plan
    if plan.status != PROPOSED:
        raise HTTPException(status_code=409, detail="This proposal is no longer available to accept.")
    open_row = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == user.id, WorkoutSession.status.in_(OPEN))
        .order_by(WorkoutSession.started_at.desc())
        .first()
    )
    if open_row:
        training = [item for item in open_row.recorded_sets if not is_sample_set(item)]
        processing = any(
            item.processing_status not in {"COMPLETED", "FAILED", "LOGGED", "SAVED"} for item in training
        )
        has_work = any(is_performed_set(item) for item in training)
        has_video = any(item.normalized_path or item.video_path for item in training)
        if processing or has_work or has_video:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Finish or end your unfinished workout before switching plans. Your logged sets and this new proposal are saved.",
                    "open_session_id": open_row.id,
                    "open_plan_id": open_row.plan_id,
                },
            )
        open_row.status = "abandoned"
        open_row.completed_at = datetime.now(timezone.utc)
    started = {
        row[0]
        for row in db.query(WorkoutSession.plan_id)
        .filter(WorkoutSession.user_id == user.id, WorkoutSession.plan_id.is_not(None))
        .all()
    }
    for old in db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id, WorkoutPlan.status == ACTIVE).all():
        if old.id != plan.id and old.id not in started:
            old.status = "replaced"
    plan.status = ACTIVE
    db.commit()
    db.refresh(plan)
    return plan


def discard_proposal(db: Session, user: User, plan: WorkoutPlan) -> WorkoutPlan:
    if plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    if plan.status == DISCARDED:
        return plan
    if plan.status != PROPOSED:
        raise HTTPException(status_code=409, detail="Only an unaccepted proposal can be discarded.")
    plan.status = DISCARDED
    db.commit()
    db.refresh(plan)
    return plan


def owned_plan(db: Session, user: User, plan_id: str) -> WorkoutPlan:
    plan = db.get(WorkoutPlan, plan_id)
    if not plan or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return plan
