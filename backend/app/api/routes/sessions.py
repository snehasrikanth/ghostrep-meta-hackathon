from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.api.serialize import is_done_set, session_out, set_out
from app.models.entities import RecordedSet, User, WorkoutPlan, WorkoutSession
from app.services.workout.catalog import CATALOG
from app.services.recording_provenance import is_sample_set

router = APIRouter(prefix="/sessions", tags=["sessions"])

OPEN = ("active", "paused")


class SessionIn(BaseModel):
    plan_id: str | None = None


class SetLogIn(BaseModel):
    exercise_id: str
    set_index: int = Field(ge=1, le=100)
    completed_reps: int = Field(ge=0, le=200)
    load_kg: float | None = Field(default=None, ge=0, le=1000)
    target_reps: int | None = Field(default=None, ge=1, le=200)
    reported_rpe: float | None = Field(default=None, ge=1, le=10)


def _owned(db: Session, user: User, session_id: str) -> WorkoutSession:
    row = db.get(WorkoutSession, session_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def _open_sessions(db: Session, user: User) -> list[WorkoutSession]:
    return (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == user.id, WorkoutSession.status.in_(OPEN))
        .order_by(WorkoutSession.started_at.desc())
        .all()
    )


def _resume(row: WorkoutSession) -> None:
    if row.status == "paused":
        row.status = "active"
        row.paused_at = None


def has_results(row: WorkoutSession) -> bool:
    return any(is_done_set(item) for item in row.recorded_sets)


@router.post("")
def start_session(
    payload: SessionIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """Start or resume. Repeating the call returns the same open session."""
    if payload.plan_id:
        plan = db.get(WorkoutPlan, payload.plan_id)
        if not plan or plan.user_id != user.id:
            raise HTTPException(status_code=404, detail="Plan not found")
        if plan.status == "proposed":
            raise HTTPException(status_code=409, detail="Review and accept this workout before starting it.")
        if plan.status == "discarded":
            raise HTTPException(status_code=409, detail="This proposal was discarded.")
        if plan.status != "active":
            raise HTTPException(status_code=409, detail="This plan is already finished. Plan your next session.")
    open_rows = _open_sessions(db, user)
    for row in open_rows:
        if payload.plan_id is None or row.plan_id == payload.plan_id:
            _resume(row)
            db.commit()
            return session_out(row)
    for row in open_rows:
        if any(not is_sample_set(item) for item in row.recorded_sets):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Finish or abandon your open workout before starting another.",
                    "open_session_id": row.id,
                    "open_plan_id": row.plan_id,
                },
            )
        row.status = "abandoned"
        row.completed_at = datetime.now(timezone.utc)
    row = WorkoutSession(user_id=user.id, plan_id=payload.plan_id, status="active")
    db.add(row)
    db.commit()
    db.refresh(row)
    return session_out(row)


@router.get("")
def list_sessions(
    include_empty: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    rows = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == user.id)
        .order_by(WorkoutSession.started_at.desc())
        .all()
    )
    if not include_empty:
        rows = [row for row in rows if row.recorded_sets or row.status in OPEN]
    return {"sessions": [session_out(s) for s in rows]}


@router.get("/current")
def current_session(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rows = _open_sessions(db, user)
    return {"session": session_out(rows[0]) if rows else None}


@router.get("/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return session_out(_owned(db, user, session_id))


@router.post("/{session_id}/pause")
def pause_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = _owned(db, user, session_id)
    if row.status not in OPEN:
        raise HTTPException(status_code=409, detail=f"This workout is already {row.status}.")
    if row.status == "active":
        row.status = "paused"
        row.paused_at = datetime.now(timezone.utc)
        db.commit()
    return session_out(row)


@router.post("/{session_id}/resume")
def resume_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = _owned(db, user, session_id)
    if row.status not in OPEN:
        raise HTTPException(status_code=409, detail=f"This workout is already {row.status}.")
    _resume(row)
    db.commit()
    return session_out(row)


@router.post("/{session_id}/complete")
def complete_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = _owned(db, user, session_id)
    if row.status == "completed":
        return session_out(row)
    if row.status == "abandoned":
        raise HTTPException(status_code=409, detail="This workout was abandoned and cannot be completed.")
    if not has_results(row):
        raise HTTPException(status_code=400, detail="Log at least one set before completing, or abandon the workout.")
    if any(item.processing_status not in {"COMPLETED", "FAILED", "LOGGED", "SAVED"} for item in row.recorded_sets):
        raise HTTPException(status_code=409, detail="A recording is still being analyzed. Wait for it to finish.")
    row.status = "completed"
    row.paused_at = None
    row.completed_at = datetime.now(timezone.utc)
    if row.plan and row.plan.status == "active":
        row.plan.status = "completed"
    db.commit()
    return session_out(row)


@router.post("/{session_id}/abandon")
def abandon_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = _owned(db, user, session_id)
    if row.status == "abandoned":
        return session_out(row)
    if row.status == "completed":
        raise HTTPException(status_code=409, detail="This workout is already completed.")
    row.status = "abandoned"
    row.paused_at = None
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    return session_out(row)


@router.post("/{session_id}/sets")
def log_set(
    session_id: str,
    payload: SetLogIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """Record a set by hand. Logging the same set number again corrects it instead of duplicating."""
    row = _owned(db, user, session_id)
    if row.status not in OPEN:
        raise HTTPException(status_code=409, detail=f"This workout is {row.status}. Start a new one to log sets.")
    if payload.exercise_id not in CATALOG:
        raise HTTPException(status_code=400, detail=f"Unknown exercise '{payload.exercise_id}'.")
    if row.plan and payload.exercise_id not in {ex.exercise_id for ex in row.plan.exercises}:
        raise HTTPException(status_code=400, detail="That exercise is not in this workout.")
    candidates = (
        db.query(RecordedSet)
        .filter(
            RecordedSet.session_id == row.id,
            RecordedSet.exercise_id == payload.exercise_id,
            RecordedSet.set_index == payload.set_index,
            RecordedSet.entry_source != "demo",
        )
        .order_by(RecordedSet.created_at.desc())
        .all()
    )
    existing = next((item for item in candidates if not is_sample_set(item)), None)
    if existing and existing.processing_status not in {"COMPLETED", "FAILED", "LOGGED", "SAVED"}:
        raise HTTPException(409, "This video is still processing. Wait for it to finish before updating the set.")
    item = existing or RecordedSet(
        session_id=row.id,
        user_id=user.id,
        exercise_id=payload.exercise_id,
        set_index=payload.set_index,
        entry_source="manual",
        processing_status="LOGGED",
        analysis_requested=False,
    )
    item.completed_reps = payload.completed_reps
    if existing and existing.processing_status == "FAILED":
        item.processing_status = "SAVED"
        item.analysis_requested = False
    item.load_kg = payload.load_kg
    if existing is None:
        item.target_reps = payload.target_reps
    # Count/load corrections need not resubmit effort. An explicit null still clears it.
    if "reported_rpe" in payload.model_fields_set:
        item.reported_rpe = payload.reported_rpe
    if existing is None:
        db.add(item)
    _resume(row)
    db.commit()
    db.refresh(item)
    return set_out(item)


@router.delete("/{session_id}/sets/{set_id}")
def delete_set(
    session_id: str,
    set_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    row = _owned(db, user, session_id)
    if row.status not in OPEN:
        raise HTTPException(status_code=409, detail=f"This workout is {row.status}.")
    item = db.get(RecordedSet, set_id)
    if not item or item.session_id != row.id:
        raise HTTPException(status_code=404, detail="Not found")
    if item.entry_source != "manual":
        raise HTTPException(status_code=400, detail="Delete recordings from the analysis page.")
    db.delete(item)
    db.commit()
    return {"deleted": set_id}
