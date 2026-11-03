import time
import json
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, job_runner, settings_dep
from app.api.serialize import set_out
from app.config import Settings
from app.models.entities import ConsentRecord, RecordedSet, User, WorkoutSession
from app.services.video.jobs import VideoJobRunner
from app.services.meta.gateway import MetaBlocked
from app.services.meta.request_approval import muse_request, sam_request_approval
from app.services.workout.catalog import CATALOG
from app.services.recording_provenance import is_sample_set

router = APIRouter(tags=["videos"])
ALLOWED = {".mp4", ".mov", ".webm", ".m4v"}


@router.post("/videos/upload")
async def upload_video(
    session_id: str | None = Form(default=None),
    exercise_id: str = Form("barbell_squat"),
    load_kg: float | None = Form(default=None),
    clear_load: bool = Form(False),
    target_reps: int | None = Form(default=None, ge=1, le=200),
    completed_reps: int | None = Form(default=None, ge=0, le=200),
    reported_rpe: float | None = Form(default=None, ge=1, le=10),
    set_index: int | None = Form(default=None, ge=1, le=100),
    replace_failed_recording_id: str | None = Form(default=None),
    consent: bool = Form(...),
    analyze: bool | None = Form(default=None),
    demo: bool = Form(False),
    approve_meta_spend: bool = Form(False),
    approve_sam_spend: bool = Form(False),
    sam_spend_limit_usd: float | None = Form(None, gt=0),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(settings_dep),
    runner: VideoJobRunner = Depends(job_runner),
) -> dict:
    handling_started=time.monotonic()
    session = db.get(WorkoutSession, session_id) if session_id else None
    if session_id and (not session or session.user_id != user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    if not demo and not session:
        raise HTTPException(400, "Start a workout before uploading a recording.")
    if not demo and session.status not in {"active", "paused"}:
        raise HTTPException(status_code=409, detail=f"This workout is {session.status}. Start a new workout to record.")
    if demo and file:
        raise HTTPException(400, "The illustrative sample uses built-in data. Upload a clip without sample mode for actual video processing.")
    if load_kg is not None and not 0 <= load_kg <= 1000:
        raise HTTPException(status_code=400, detail="Load must be between 0 and 1000 kg.")
    if not consent:
        raise HTTPException(status_code=400, detail="Recording consent is required before upload.")
    if exercise_id not in CATALOG:
        raise HTTPException(400, "Choose a known exercise before recording.")
    if not demo and session.plan and exercise_id not in {ex.exercise_id for ex in session.plan.exercises}:
        raise HTTPException(400, "That exercise is not in this workout.")
    analyze = exercise_id == "barbell_squat" if analyze is None else analyze
    if (analyze or demo) and exercise_id != "barbell_squat":
        raise HTTPException(400, "AI form analysis is available only for barbell squats. Save this video without analysis.")
    if not analyze and (approve_meta_spend or approve_sam_spend):
        raise HTTPException(400, "Saving a video does not require or permit AI processing.")
    if demo and not analyze:
        raise HTTPException(400, "The sample is available only for barbell squat analysis.")

    if (approve_meta_spend or approve_sam_spend) and demo:
        raise HTTPException(400, "The sample uses illustrative results. Upload your own recording for personalized analysis.")
    approval = sam_approval = None
    if analyze:
        try:
            _, approval = muse_request(settings, "coaching", approve_meta_spend)
            _, sam_approval = sam_request_approval(settings, approve_sam_spend)
        except MetaBlocked as exc:
            raise HTTPException(409, str(exc)) from exc

    if demo:
        # A sample never starts/resumes/replaces an ordinary workout, including
        # when an older client sends its open workout's session_id.
        session = WorkoutSession(user_id=user.id, status="sample")
        db.add(session)
        db.flush()
    if set_index is None:
        set_index = max((item.set_index or 0 for item in session.recorded_sets if item.exercise_id == exercise_id and not is_sample_set(item)), default=0) + 1
    candidates = (
        db.query(RecordedSet)
        .filter(RecordedSet.session_id == session.id, RecordedSet.exercise_id == exercise_id,
                RecordedSet.set_index == set_index, RecordedSet.entry_source != "demo")
        .order_by(RecordedSet.created_at.desc()).all()
    ) if not demo else []
    existing = next((item for item in candidates if not is_sample_set(item)), None)
    replacing = replace_failed_recording_id is not None
    if replacing and (demo or not existing or existing.id != replace_failed_recording_id
                      or existing.user_id != user.id or existing.processing_status != "FAILED"
                      or existing.analysis or existing.coaching or is_sample_set(existing)):
        raise HTTPException(409, "Only this workout's failed recording without saved analysis can be replaced. Refresh its status first.")
    if existing and not replacing and (existing.video_path or existing.normalized_path or existing.analysis):
        raise HTTPException(409, "This set already has a recording. Open its replay, or choose another set.")
    if existing and existing.processing_status not in {"LOGGED", "SAVED", "FAILED"}:
        raise HTTPException(409, "This set is already being processed.")

    if session.status == "paused":
        session.status = "active"
        session.paused_at = None
    rec = existing or RecordedSet(
        session_id=session.id,
        user_id=user.id,
        exercise_id=exercise_id,
        set_index=set_index,
    )
    rec.processing_started_at=datetime.now(timezone.utc)
    rec.stage_timings_json=json.dumps({"upload_server_handling":0})
    rec.entry_source = "demo" if demo else "video"
    rec.analysis_requested = analyze
    rec.processing_status = "UPLOADED"
    rec.processing_message = None
    rec.consent_version = settings.consent_version
    if clear_load:
        rec.load_kg = None
    elif load_kg is not None:
        rec.load_kg = load_kg
    if target_reps is not None:
        rec.target_reps = target_reps
    if reported_rpe is not None:
        rec.reported_rpe = reported_rpe
    if not analyze and completed_reps is not None:
        rec.completed_reps = completed_reps

    if demo and not file:
        rec.original_filename = "DEMO_FIXTURE"
        rec.processing_message = "Explicitly labeled demo fixture"
    else:
        if not file:
            raise HTTPException(status_code=400, detail="Upload an MP4/MOV recording or use labeled demo mode.")
        suffix = Path(file.filename or "clip.mp4").suffix.lower()
        if suffix not in ALLOWED:
            raise HTTPException(status_code=400, detail="Supported uploads: MP4, MOV, M4V, WEBM.")
        dest = settings.upload_dir / f"{rec.id or 'pending'}{suffix}"
        db.add(rec)
        db.flush()
        dest = settings.upload_dir / f"{rec.id}{'-' + uuid4().hex if replacing else ''}{suffix}"
        payload = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(payload) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_upload_mb} MB.")
        dest.write_bytes(payload)
        if replacing:
            # Keep the old file intact; never overwrite an earlier recording.
            rec.normalized_path = None
            rec.overlay_path = None
            rec.duration_seconds = None
            rec.stage_started_at = None
        rec.video_path = str(dest)
        rec.raw_deleted_at = None
        rec.original_filename = file.filename

    if rec.id is None:
        db.add(rec)
        db.flush()

    db.add(
        ConsentRecord(
            user_id=user.id,
            recording_id=rec.id,
            consent_version=settings.consent_version,
        )
    )
    db.commit()
    db.refresh(rec)
    rec.stage_timings_json=json.dumps({"upload_server_handling":round(time.monotonic()-handling_started,3)})
    db.commit()
    runner.start(
        rec.id, demo=demo or rec.original_filename == "DEMO_FIXTURE",
        approval_token=approval, sam_approval_token=sam_approval,
        sam_spend_limit_usd=sam_spend_limit_usd if approve_sam_spend else None,
    )
    return set_out(rec)


@router.get("/recordings/{recording_id}")
def get_recording(
    recording_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    rec = db.get(RecordedSet, recording_id)
    if not rec or rec.user_id != user.id:
        raise HTTPException(404, "Recording not found")
    return {**set_out(rec), "plan_id": rec.session.plan_id, "session_status": rec.session.status}


@router.delete("/recordings/{recording_id}")
def delete_recording(
    recording_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    rec = db.get(RecordedSet, recording_id)
    if not rec or rec.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    if rec.processing_status not in {"SAVED", "LOGGED", "COMPLETED", "FAILED"}:
        raise HTTPException(409, "Wait for the video to finish processing before deleting it.")
    deleted = []
    for path in (rec.video_path, rec.normalized_path):
        if path:
            p = Path(path)
            if p.exists():
                p.unlink()
                deleted.append(path)
    rec.video_path = None
    rec.normalized_path = None
    rec.raw_deleted_at = rec.raw_deleted_at or rec.created_at
    rec.processing_message = "User deleted media"
    if not rec.analysis_requested:
        rec.processing_status = "SAVED"
        if rec.completed_reps is not None:
            rec.entry_source = "manual"
    db.commit()
    return {"deleted": deleted, "verified": all(not Path(p).exists() for p in deleted)}
