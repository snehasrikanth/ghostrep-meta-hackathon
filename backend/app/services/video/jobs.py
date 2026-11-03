from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.services.recording_provenance import is_sample_set

from sqlalchemy.orm import Session

from app.config import Settings
from app.database import SessionLocal
from app.models.entities import AnalysisResult, CoachingDecision, RecordedSet, RepMetric
from app.services.coaching.local_coach import generate_local_coaching
from app.services.coaching.prescription import coach_input_targets
from app.services.coaching.compatibility import recommendation_context
from app.services.meta.errors import MetaError
from app.services.meta.gateway import MetaBlocked, MetaGateway
from app.services.meta.muse import MuseProvider
from app.services.meta.request_approval import muse_request, sam_request_approval
from app.services.meta.pricing import estimate_sam_video_cost
from app.services.meta.providers import resolve_segmentation_provider
from app.services.meta.sam import SamProvider
from app.services.meta.apply_silhouettes import reapply_saved
from app.services.meta.silhouettes import (
    GeometryMissing,
    assign_athlete,
    attach_silhouettes,
    require_drawable_geometry,
    segmentation_document,
)
from app.services.movement.pipeline import analyze_pose_sequence
from app.services.movement.synthetic import synthesize_squat_set
from app.services.pose.provider import PoseExtractor
from app.services.video.version import PIPELINE_VERSION
from app.services.video.ffmpeg import MediaError, inspect_video, normalize_video, prepare_sam_video


class VideoJobRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._active: set[str] = set()

    def start(self, set_id: str, *, demo: bool = False, approval_token: str | None = None,
              sam_approval_token: str | None = None, sam_spend_limit_usd: float | None = None) -> None:
        with self._lock:
            if set_id in self._active:
                return
            self._active.add(set_id)
        thread = threading.Thread(
            target=self._run, args=(set_id, demo, approval_token, sam_approval_token, sam_spend_limit_usd), daemon=True, name=f"ghostrep-job-{set_id[:8]}"
        )
        thread.start()

    def _run(self, set_id: str, demo: bool, approval_token: str | None,
             sam_approval_token: str | None = None, sam_spend_limit_usd: float | None = None) -> None:
        db = SessionLocal()
        try:
            self._process(db, set_id, demo, approval_token, sam_approval_token, sam_spend_limit_usd)
        except Exception as exc:
            rec = db.get(RecordedSet, set_id)
            if rec:
                rec.processing_status = "FAILED"
                rec.processing_message = str(exc)[:800]
                db.commit()
        finally:
            db.close()
            with self._lock: self._active.discard(set_id)

    def _process(self, db: Session, set_id: str, demo: bool, approval_token: str | None,
                 sam_approval_token: str | None = None, sam_spend_limit_usd: float | None = None) -> None:
        rec = db.get(RecordedSet, set_id)
        if not rec:
            return
        demo = demo or is_sample_set(rec)
        if demo:
            rec.entry_source = "demo"
            rec.original_filename = "DEMO_FIXTURE"

        started=time.monotonic(); stage_clock=started; previous="UPLOADED"; timings=json.loads(rec.stage_timings_json or "{}")
        rec.processing_started_at=rec.processing_started_at or datetime.now(timezone.utc)
        def status(name: str, message: str | None = None) -> None:
            nonlocal stage_clock,previous
            now=time.monotonic();timings[previous]=round(timings.get(previous,0)+now-stage_clock,3)
            timings["total"]=round(now-started,3)
            rec.stage_timings_json=json.dumps(timings)
            rec.stage_started_at=datetime.now(timezone.utc)
            rec.processing_status = name
            rec.processing_message = message
            previous=name;stage_clock=now
            db.commit()

        frames: list[dict]
        if demo or rec.original_filename == "DEMO_FIXTURE":
            status("ESTIMATING_POSE", "Labeled demo fixture — not a live recording or Meta call.")
            frames = synthesize_squat_set(reps=6, drift=True)
            rec.duration_seconds = frames[-1]["timestamp"] if frames else 0
            rec.normalized_path = None
        else:
            if not rec.video_path:
                raise RuntimeError("No uploaded video path.")
            src = Path(rec.video_path)
            status("VALIDATING", "Inspecting media with FFprobe.")
            meta = inspect_video(src)
            if meta["duration"] <= 0 or meta["duration"] > self.settings.max_video_seconds:
                raise MediaError(
                    f"Duration {meta['duration']:.1f}s is outside the 1–{self.settings.max_video_seconds:.0f}s window."
                )
            rec.duration_seconds = meta["duration"]
            status("PREPROCESSING", "Normalizing orientation and pixel format with FFmpeg.")
            normalized = Path(self.settings.derived_dir) / f"{rec.id}.mp4"
            info = normalize_video(src, normalized)
            rec.normalized_path = str(normalized)
            rec.duration_seconds = info["duration"]
            if not rec.analysis_requested:
                if not self.settings.retain_raw_video:
                    src.unlink(missing_ok=True)
                    rec.video_path = None
                    rec.raw_deleted_at = datetime.now(timezone.utc)
                status("SAVED", "Video saved to this set. No AI analysis was requested.")
                return
            if rec.exercise_id != "barbell_squat":
                raise RuntimeError("Movement analysis is available only for barbell squats.")
            status("ESTIMATING_POSE", "Running MediaPipe Pose Landmarker.")
            frames = PoseExtractor(self.settings).extract(normalized)

        status("DETECTING_REPS", "Detecting squat phases and measuring movement.")
        result = analyze_pose_sequence(frames)
        quality = result["quality"]

        sam_info = {
            "available": False,
            "status": "skipped",
            "label": "SAM 3.1 was not called.",
            "tracks": [],
        }
        sam_settings, _ = sam_request_approval(self.settings, False)
        if sam_approval_token and not demo:
            sam_settings, _ = sam_request_approval(self.settings, True)
        segmentation = resolve_segmentation_provider(sam_settings)
        if quality["usable"] and quality.get("comparison_usable",True) and not demo and segmentation not in {"none", "local"} and rec.normalized_path:
            status("SEGMENTING", "Preparing optional movement outlines. If they take too long, your skeleton replay will remain available.")
            gateway = MetaGateway(sam_settings, db)
            sam_video = Path(rec.normalized_path)
            upload_copy = None
            try:
                if segmentation == "meta_live":
                    upload_copy = self.settings.derived_dir / f"{rec.id}-sam-upload.mp4"
                    preparation_start=time.monotonic()
                    media = prepare_sam_video(sam_video, upload_copy)
                    timings["sam_preparation"]=round(time.monotonic()-preparation_start,3)
                    sam_video = upload_copy
                else:
                    media = inspect_video(sam_video)
                fps = float(media.get("fps") or 0) or self.settings.target_analysis_fps
                est_frames = max(1, math.ceil(float(media.get("duration") or rec.duration_seconds or 1) * fps))
                if segmentation == "meta_live" and sam_spend_limit_usd is not None and estimate_sam_video_cost(est_frames) > sam_spend_limit_usd + 1e-9:
                    raise MetaBlocked("SAM estimate exceeds the approved cost limit. Pose analysis is still available.")
                sam_clock=time.monotonic()
                sam_info = SamProvider(sam_settings, gateway).segment_video(
                    sam_video,
                    est_frames,
                    approval_token=sam_approval_token,
                    fps=fps,
                    media=media,
                )
                timings["sam_upload_provider_parse_cleanup"]=round(time.monotonic()-sam_clock,3)
                timings.update({"sam_"+k:v for k,v in sam_info.get("stage_timings",{}).items()})
            except MetaBlocked as exc:
                sam_info = {"available": False, "status": "blocked", "label": str(exc), "tracks": []}
            except MetaError as exc:
                sam_info = {
                    "available": False,
                    "status": _sam_status(exc),
                    "label": str(exc),
                    "tracks": [],
                }
            except MediaError as exc:
                sam_info = {"available": False, "status": "unavailable", "label": str(exc), "tracks": []}
            finally:
                if upload_copy is not None:
                    upload_copy.unlink(missing_ok=True)
            if sam_info.get("available"):
                alignment_clock=time.monotonic()
                assign_athlete(sam_info, result["overlay"].get("frames") or [])
                try:
                    require_drawable_geometry(sam_info)
                    result["overlay"] = attach_silhouettes(result["overlay"], sam_info, result.get("reference_rep"))
                except GeometryMissing as exc:
                    sam_info["available"] = False
                    sam_info["status"] = "geometry_missing"
                    sam_info["label"] = str(exc)
                timings["outline_alignment"]=round(time.monotonic()-alignment_clock,3)
        elif rec.analysis is not None:
            result["overlay"], saved = reapply_saved(rec.analysis, result["overlay"])
            if saved:
                sam_info = saved

        status("COMPUTING_METRICS", "Selecting a personal reference repetition and measuring drift.")
        reps = result["reps"]
        rec.completed_reps = len([r for r in reps if r.is_complete])

        analysis = rec.analysis or AnalysisResult(set_id=rec.id)
        analysis.reference_rep = result["reference_rep"]
        analysis.quality_json = json.dumps(quality)
        analysis.drift_json = json.dumps(result["drift"])
        analysis.overlay_json = json.dumps(result["overlay"])
        if result["overlay"].get("silhouette_source") in {"sam", "fixture"}:
            analysis.segmentation_json = json.dumps(
                segmentation_document(
                    sam_info,
                    set_id=rec.id,
                    analysis_id=analysis.id,
                    session_id=rec.session_id,
                )
            )
        analysis.pose_available = bool(frames) and bool(frames[0].get("landmarks"))
        source = result["overlay"].get("silhouette_source")
        analysis.sam_available = source in {"sam", "fixture"}
        analysis.sam_status = (
            "live" if source == "sam" else source if analysis.sam_available else str(sam_info.get("status") or "unavailable")
        )
        analysis.analysis_version = PIPELINE_VERSION
        if rec.analysis is None:
            db.add(analysis)

        db.query(RepMetric).filter(RepMetric.set_id == rec.id).delete()
        for rep in reps:
            db.add(
                RepMetric(
                    set_id=rec.id,
                    rep_index=rep.rep_id,
                    start_seconds=rep.start_seconds,
                    bottom_seconds=rep.bottom_seconds,
                    end_seconds=rep.end_seconds,
                    descent_seconds=rep.descent_seconds,
                    ascent_seconds=rep.ascent_seconds,
                    is_complete=rep.is_complete,
                    is_reference=rep.rep_id == result["reference_rep"],
                    confidence=rep.confidence,
                    metrics_json=json.dumps(rep.metrics),
                )
            )

        if rec.coaching is None:
            status("GENERATING_COACHING", "Building an evidence-grounded next-set recommendation.")
            profile = _profile_dict(db, rec.user_id)
            coach_input = {
                "quality": quality,
                "drift": result["drift"],
                "reps": [
                    {
                        "rep_id": r.rep_id,
                        "start_seconds": r.start_seconds,
                        "bottom_seconds": r.bottom_seconds,
                        "end_seconds": r.end_seconds,
                        "descent_seconds": r.descent_seconds,
                        "ascent_seconds": r.ascent_seconds,
                        "is_complete": r.is_complete,
                        "confidence": r.confidence,
                        "reliability": r.metrics.get("reliability"),
                        "comparison_eligible": r.metrics.get("comparison_eligible"),
                        "observed_range": r.metrics.get("observed_range"),
                    }
                    for r in reps
                    if r.is_complete
                ],
                "reference_rep": result["reference_rep"],
                "profile": profile,
                "reported_rpe": rec.reported_rpe,
                **coach_input_targets(rec),
            }
            try:
                coach_settings, _ = muse_request(self.settings, "coaching", bool(approval_token) and not demo)
                gateway = MetaGateway(coach_settings, db)
                coaching = MuseProvider(coach_settings, gateway).generate_coaching(coach_input, approval_token)
            except (MetaBlocked, MetaError) as exc:
                MetaGateway(self.settings, db).note(kind="coaching_fallback", reason=type(exc).__name__, message=str(exc)[:240])
                coaching = generate_local_coaching(**coach_input)
                if approval_token:
                    coaching["uncertainties"].append("Personalized coaching was unavailable. This is a basic recommendation based on measured movement.")
            decision = CoachingDecision(
                set_id=rec.id,
                source=coaching.get("source", "local"),
                proposed_action=coaching["suggested_action"],
                reason=coaching["reason"],
                summary=coaching["summary"],
                payload_json=json.dumps({**coaching, "recommendation_context": recommendation_context(rec, analysis=analysis)}),
                user_decision="pending",
            )
            db.add(decision)
        else:
            # Keep the stored recommendation. A future live Muse result belongs
            # in the preflight ledger, or a separately authorized replace path.
            status("GENERATING_COACHING", "Keeping the existing coaching recommendation.")

        if not self.settings.retain_raw_video and rec.video_path:
            raw = Path(rec.video_path)
            if raw.exists() and raw.name != "DEMO_FIXTURE":
                raw.unlink(missing_ok=True)
                rec.raw_deleted_at = datetime.now(timezone.utc)
                rec.video_path = None

        if not quality["usable"] or not rec.completed_reps:
            reasons = [issue["message"] for issue in quality.get("issues", []) if issue.get("severity") == "block"]
            reasons = reasons or [issue["message"] for issue in quality.get("issues", [])][:2]
            hint = " ".join(reasons) or "No complete squat repetitions were found."
            status("COMPLETED", f"This recording could not be assessed. {hint} Record again from the side with your whole body in frame.")
        else:
            status("COMPLETED", sam_info.get("label"))
        db.commit()

    def cleanup_expired(self, db: Session) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.settings.retention_hours)
        removed = 0
        rows = db.query(RecordedSet).filter(RecordedSet.created_at < cutoff).all()
        for rec in rows:
            # Explicitly saved replays belong to the training journal until the
            # user deletes them. Automatic retention still removes raw uploads.
            for path in (rec.video_path, rec.normalized_path if rec.analysis_requested else None):
                if path:
                    p = Path(path)
                    if p.exists():
                        p.unlink(missing_ok=True)
                        removed += 1
            rec.video_path = None
            if rec.analysis_requested:
                rec.normalized_path = None
            rec.raw_deleted_at = rec.raw_deleted_at or datetime.now(timezone.utc)
        db.commit()
        return removed


def _sam_status(exc: Exception) -> str:
    return {
        "MetaRateLimited": "rate_limited",
        "MetaTimeout": "timeout",
        "MetaRejected": "rejected",
        "MetaUnavailable": "unavailable",
    }.get(type(exc).__name__, "unavailable")


def _profile_dict(db: Session, user_id: str) -> dict:
    from app.models.entities import Profile

    profile = db.query(Profile).filter(Profile.user_id == user_id).one_or_none()
    if not profile:
        return {}
    return {
        "goal": profile.goal,
        "experience": profile.experience,
        "days_per_week": profile.days_per_week,
        "session_duration_minutes": profile.session_duration_minutes,
        "equipment": json.loads(profile.equipment_json),
        "current_squat_load_kg": profile.current_squat_load_kg,
        "limitations": json.loads(profile.limitations_json or "[]"),
        "assessment": json.loads(profile.assessment_json) if profile.assessment_json else None,
    }
