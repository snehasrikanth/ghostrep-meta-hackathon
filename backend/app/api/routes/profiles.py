import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.api.serialize import profile_out
from app.models.entities import Profile, User
from app.schemas.profile import DraftIn, ProfileIn
from app.services.workout.profile_model import project_assessment

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("")
def upsert_profile(
    payload: ProfileIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    projected = project_assessment(payload.assessment) if payload.assessment else {}
    display_name = projected.get("display_name") or payload.display_name
    if display_name:
        user.display_name = display_name
    row = db.query(Profile).filter(Profile.user_id == user.id).one_or_none()
    data = dict(
        goal=projected.get("goal") or payload.goal,
        experience=projected.get("experience") or payload.experience,
        days_per_week=projected.get("days_per_week") or payload.days_per_week,
        session_duration_minutes=projected.get("session_duration_minutes") or payload.session_duration_minutes,
        equipment_json=json.dumps(projected.get("equipment") or payload.equipment),
        current_squat_load_kg=projected.get("current_squat_load_kg", payload.current_squat_load_kg),
        optional_height_cm=projected.get("optional_height_cm", payload.optional_height_cm),
        optional_weight_kg=projected.get("optional_weight_kg", payload.optional_weight_kg),
        limitations_json=json.dumps(projected.get("limitations") if payload.assessment else payload.limitations),
        assessment_json=json.dumps(payload.assessment) if payload.assessment else None,
        draft_json=None,
        submitted=True,
        age_range=projected.get("age_range") if payload.assessment else payload.age_range,
    )
    if row:
        for key, value in data.items():
            setattr(row, key, value)
    else:
        row = Profile(user_id=user.id, **data)
        db.add(row)
    db.commit()
    db.refresh(row)
    return profile_out(row)


@router.get("/me")
def my_profile(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.query(Profile).filter(Profile.user_id == user.id).one_or_none()
    if not row or not row.submitted:
        raise HTTPException(status_code=404, detail="No profile yet")
    return profile_out(row)


@router.get("/draft")
def get_draft(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.query(Profile).filter(Profile.user_id == user.id).one_or_none()
    if not row or not row.draft_json:
        raise HTTPException(status_code=404, detail="No draft")
    return {"draft": json.loads(row.draft_json), "submitted": bool(row.submitted)}


@router.put("/draft")
def save_draft(
    payload: DraftIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """Autosave in-progress answers. Does not change a submitted profile or any workout plan."""
    row = db.query(Profile).filter(Profile.user_id == user.id).one_or_none()
    encoded = json.dumps(payload.draft)
    if row is None:
        row = Profile(
            user_id=user.id,
            goal="learn_technique",
            experience="beginner",
            days_per_week=3,
            session_duration_minutes=45,
            equipment_json=json.dumps(["bodyweight"]),
            limitations_json="[]",
            draft_json=encoded,
            submitted=False,
        )
        db.add(row)
    else:
        row.draft_json = encoded
    db.commit()
    return {"draft": payload.draft, "submitted": bool(row.submitted)}


@router.get("/{profile_id}")
def get_profile(profile_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = db.get(Profile, profile_id)
    if not row or row.user_id != user.id or not row.submitted:
        raise HTTPException(status_code=404, detail="Not found")
    return profile_out(row)
