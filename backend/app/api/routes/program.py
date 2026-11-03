"""Training week and explicit preparation of a selected session. No model calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import current_user, get_db
from app.api.serialize import plan_out
from app.models.entities import Profile, User, WorkoutPlan, WorkoutSession
from app.services.workout.week import build_program, parse_today, select_saved_schedule
from app.services.workout.proposals import persist_proposal, latest_proposal
from app.services.workout.history import recent_training_context
from app.services.workout.local_planner import generate_local_week
from app.services.recording_provenance import is_performed_set

router = APIRouter(prefix="/program", tags=["program"])


class PrepareSession(BaseModel):
    today: str
    week_index: int = Field(default=0, ge=0, le=3)
    weekday: str
    tz: str | None = None


@router.post("/prepare")
def prepare_session(payload: PrepareSession, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    program = get_program(today=payload.today, weeks=payload.week_index + 1, tz=payload.tz, db=db, user=user)
    chosen = next((day for day in program["weeks"][payload.week_index]["days"] if day["weekday"] == payload.weekday), None)
    if not chosen or chosen["kind"] != "training" or not chosen.get("workout"):
        raise HTTPException(status_code=400, detail="Choose a training day from your week.")
    if chosen.get("plan_id") and not chosen["is_preview"]:
        existing = db.query(WorkoutPlan).filter(WorkoutPlan.id == chosen["plan_id"], WorkoutPlan.user_id == user.id).one_or_none()
        if existing and existing.status == "active":
            return plan_out(existing)
    row = db.query(Profile).filter(Profile.user_id == user.id).one()
    profile = _profile_payload(row)
    recent = recent_training_context(db, user.id)
    profile["recent_sessions"] = recent
    plans = db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user.id).order_by(WorkoutPlan.created_at.desc()).all()
    saved, schedule = select_saved_schedule([plan_out(plan) for plan in plans])
    workout = chosen["workout"]
    source = {"saved_muse": "muse_spark", "saved_fixture": "fixture"}.get(chosen["source"], "local")
    data = {**workout, "source": source, "schedule": schedule, "proposal_kind": "session",
            "week_session_index": program["training_days"].index(payload.weekday)}
    if saved and saved.get("training_structure"):
        data["training_structure"] = {**saved["training_structure"], "session_index": data["week_session_index"], "proposal_kind": "session"}
    if not schedule or chosen["source"] == "local_preview":
        data = generate_local_week(profile, focus=workout.get("session_type"), session_index=program["training_days"].index(payload.weekday))
    data["proposal_kind"] = "session"
    if data.get("training_structure"):
        data["training_structure"] = {**data["training_structure"], "proposal_kind": "session"}
    plan = persist_proposal(db, user, data, profile, 0, workout.get("session_type"), recent)
    return plan_out(plan)


@router.get("")
def get_program(
    today: str = Query(..., description="Athlete's local calendar date as YYYY-MM-DD."),
    weeks: int = Query(1, ge=1, le=4),
    tz: str | None = Query(default=None, description="IANA timezone for mapping session timestamps onto local dates."),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    try:
        day = parse_today(today)
        zone = _timezone(tz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    profile = db.query(Profile).filter(Profile.user_id == user.id, Profile.submitted.is_(True)).one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Create a profile before viewing your training week.")
    plans = (
        db.query(WorkoutPlan)
        .filter(WorkoutPlan.user_id == user.id)
        .order_by(WorkoutPlan.created_at.desc())
        .all()
    )
    plan_payloads = [plan_out(plan) for plan in plans]
    # Older single-session plans have no saved week slot. Their inferred display
    # structure must not move historical workouts away from their actual dates.
    for row, payload in zip(plans, plan_payloads):
        if not payload.get("schedule") and not json.loads(row.context_json or "{}").get("training_structure"):
            payload.pop("training_structure", None)
    saved_plan, saved_schedule = select_saved_schedule(plan_payloads)
    next_plan = next((plan for plan in plan_payloads if plan["status"] == "active"), None)
    open_row = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == user.id, WorkoutSession.status.in_(("active", "paused")))
        .order_by(WorkoutSession.started_at.desc())
        .first()
    )
    open_session = None
    if open_row:
        open_session = {
            "id": open_row.id,
            "plan_id": open_row.plan_id,
            "status": open_row.status,
            "date": _local_date(open_row.started_at, zone),
        }
    history = []
    owned = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == user.id)
        .order_by(WorkoutSession.started_at.asc())
        .all()
    )
    plans_by_id = {plan["id"]: plan for plan in plan_payloads}
    accepted_week_id = ((saved_plan or next_plan or {}).get("training_structure") or {}).get("week_id")
    for row in owned:
        plan = plans_by_id.get(row.plan_id) if row.plan_id else None
        if not plan:
            continue
        if accepted_week_id and (plan.get("training_structure") or {}).get("week_id") != accepted_week_id:
            continue
        if row.status not in {"completed", "abandoned", "active", "paused"}:
            continue
        if row.status in {"completed", "abandoned"} and not any(is_performed_set(item) for item in row.recorded_sets):
            continue
        history.append({"date": _local_date(row.started_at, zone), "plan": plan, "status": row.status})
    result = build_program(
        profile=_profile_payload(profile),
        today=day,
        week_count=weeks,
        saved_schedule=saved_schedule,
        saved_source=saved_plan.get("source") if saved_plan else None,
        next_plan=next_plan,
        open_session=open_session,
        history=history,
        saved_structure=(saved_plan or next_plan or {}).get("training_structure"),
    )
    proposal = latest_proposal(db, user)
    proposal_payload = plan_out(proposal) if proposal else None
    result.update({
        "is_accepted": bool(saved_plan or next_plan),
        "proposal_id": proposal.id if proposal else None,
        "proposal_kind": (proposal_payload or {}).get("training_structure", {}).get("proposal_kind"),
        "open_session": open_session,
    })
    return result


def _timezone(value: str | None) -> ZoneInfo:
    if not value:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("tz must be a valid IANA timezone name.") from exc


def _local_date(value: datetime | None, zone: ZoneInfo) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(zone).date().isoformat()


def _profile_payload(row: Profile) -> dict:
    return {
        "goal": row.goal,
        "experience": row.experience,
        "days_per_week": row.days_per_week,
        "session_duration_minutes": row.session_duration_minutes,
        "equipment": json.loads(row.equipment_json),
        "current_squat_load_kg": row.current_squat_load_kg,
        "limitations": json.loads(row.limitations_json or "[]"),
        "assessment": json.loads(row.assessment_json) if row.assessment_json else None,
    }
