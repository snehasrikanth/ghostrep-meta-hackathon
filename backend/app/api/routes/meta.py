from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, settings_dep
from app.config import Settings
from app.models.entities import MetaUsageEvent
from app.services.meta.gateway import approval_hint
from app.services.meta.providers import (
    resolve_coaching_provider,
    resolve_segmentation_provider,
    resolve_workout_provider,
)
from app.services.meta.pricing import (
    SAM_MIN_VIDEO_FRAMES,
    WORKOUT_INPUT_TOKEN_ESTIMATE,
    WORKOUT_OUTPUT_TOKEN_ESTIMATE,
    COACHING_INPUT_TOKEN_ESTIMATE,
    COACHING_OUTPUT_TOKEN_ESTIMATE,
    SAM_VIDEO_PER_1K_FRAMES,
    estimate_muse_cost,
    estimate_sam_video_cost,
)

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/status")
def meta_status(settings: Settings = Depends(settings_dep), db: Session = Depends(get_db)) -> dict:
    events = db.query(MetaUsageEvent).order_by(MetaUsageEvent.created_at.desc()).limit(50).all()
    live = db.query(MetaUsageEvent).filter(MetaUsageEvent.allowed.is_(True), MetaUsageEvent.provider == "meta_live").all()
    call_limit_reached = settings.meta_max_calls_per_session is not None and len(live) >= settings.meta_max_calls_per_session
    return {
        "ai_provider": settings.ai_provider,
        "workout_provider": resolve_workout_provider(settings),
        "coaching_provider": resolve_coaching_provider(settings),
        "segmentation_provider": resolve_segmentation_provider(settings),
        "enable_meta_api": settings.enable_meta_api,
        "require_explicit_approval": settings.meta_require_explicit_approval,
        "key_present": bool(settings.model_api_key),
        "workout_ready": bool(settings.enable_meta_api and settings.model_api_key and resolve_workout_provider(settings) == "meta_live"),
        "coaching_ready": bool(settings.enable_meta_api and settings.model_api_key and resolve_coaching_provider(settings) == "meta_live"),
        "sam_ready": bool(settings.enable_meta_api and settings.model_api_key and resolve_segmentation_provider(settings) == "meta_live"),
        "sam_target_fps": None,
        "sam_max_video_seconds": settings.max_video_seconds,
        "sam_min_frames": SAM_MIN_VIDEO_FRAMES,
        "max_calls": settings.meta_max_calls_per_session,
        "remaining_calls": max(0, settings.meta_max_calls_per_session - len(live)) if settings.meta_max_calls_per_session is not None else None,
        "call_limit_reached": call_limit_reached,
        "call_limit_reason": f"The development limit of {settings.meta_max_calls_per_session} paid calls has been reached. Saved results and local analysis are still available." if call_limit_reached else None,
        "spend_limit_usd": settings.meta_estimated_spend_limit_usd,
        "live_calls": len(live),
        "estimated_spend_usd": round(sum(e.estimated_cost_usd for e in live), 6),
        "approval_hint_workout": approval_hint(settings, "workout_generation")
        if settings.enable_meta_api
        else None,
        "estimates": {
            "muse_small_call_usd": round(estimate_muse_cost(WORKOUT_INPUT_TOKEN_ESTIMATE, WORKOUT_OUTPUT_TOKEN_ESTIMATE), 6),
            "muse_coaching_call_usd": round(estimate_muse_cost(COACHING_INPUT_TOKEN_ESTIMATE, COACHING_OUTPUT_TOKEN_ESTIMATE), 6),
            "sam_50_frame_min_usd": round(estimate_sam_video_cost(SAM_MIN_VIDEO_FRAMES), 6),
            "sam_video_per_1000_frames_usd": SAM_VIDEO_PER_1K_FRAMES,
        },
        "events": [
            {
                "id": e.id,
                "created_at": e.created_at.isoformat(),
                "model": e.model,
                "purpose": e.purpose,
                "provider": e.provider,
                "allowed": e.allowed,
                "blocked_reason": e.blocked_reason,
                "estimated_cost_usd": e.estimated_cost_usd,
            }
            for e in events
        ],
    }
