import json
from pathlib import Path
from app.services.coaching.measurement_guard import recording_problem

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db
from app.api.serialize import analysis_out
from app.models.entities import AnalysisResult, RecordedSet, User
from app.services.meta.silhouettes import silhouette_label
from app.services.coaching.set_comparison import compare_with_previous

router = APIRouter(tags=["analysis"])


@router.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rec, analysis = _load(db, analysis_id, user)
    payload = analysis_out(rec, analysis)
    if analysis is not None and rec.processing_status == "COMPLETED":
        payload["previous_set_comparison"] = compare_with_previous(db, rec)
    return payload


@router.get("/analysis/{analysis_id}/reps")
def get_reps(analysis_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rec, analysis = _load(db, analysis_id, user)
    payload = analysis_out(rec, analysis)
    return {"reps": payload["reps"], "reference_rep": payload["reference_rep"]}


@router.get("/analysis/{analysis_id}/overlay")
def get_overlay(analysis_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rec, analysis = _load(db, analysis_id, user)
    overlay = json.loads(analysis.overlay_json) if analysis else {"frames": [], "skeleton_edges": []}
    invalid_reps={r.rep_index for r in rec.reps if not r.is_complete or json.loads(r.metrics_json).get("comparison_eligible") is False}
    problem=recording_problem(rec)
    overlay={**overlay,"frames":[{**f,"reference":None,"reference_silhouette":None} if problem or f.get("active_rep") in invalid_reps else f for f in overlay.get("frames",[])]}
    source = overlay.get("silhouette_source") or "unavailable"
    return {
        "analysis_id": analysis.id if analysis else rec.id,
        "video_url": f"/media/{rec.id}" if rec.normalized_path else None,
        "reference_rep": analysis.reference_rep if analysis and not problem else None,
        "skeleton_edges": overlay.get("skeleton_edges") or [],
        "frames": overlay.get("frames") or [],
        "sam_available": analysis.sam_available if analysis else False,
        "sam_status": analysis.sam_status if analysis else "unavailable",
        "silhouette_source": source,
        "silhouette_label": overlay.get("silhouette_label") or silhouette_label(source),
        "color_reference": "#2EE6D6",
        "color_current": "#FF8A3D",
    }


@router.get("/media/{set_id}")
def media(set_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    rec = db.get(RecordedSet, set_id)
    if not rec or rec.user_id != user.id or not rec.normalized_path:
        raise HTTPException(status_code=404, detail="Media not found")
    path = Path(rec.normalized_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Media deleted")
    return FileResponse(path, media_type="video/mp4")


def _load(db: Session, analysis_id: str, user: User) -> tuple[RecordedSet, AnalysisResult | None]:
    analysis = db.get(AnalysisResult, analysis_id)
    rec = None
    if analysis:
        rec = db.get(RecordedSet, analysis.set_id)
    if rec is None:
        rec = db.get(RecordedSet, analysis_id)
        analysis = rec.analysis if rec else None
    if not rec or rec.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    if rec.analysis_requested is False:
        raise HTTPException(404, "No AI analysis was requested for this recording. Open its video replay.")
    return rec, analysis
