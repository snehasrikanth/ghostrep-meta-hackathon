from fastapi import APIRouter, Depends

from app.api.deps import settings_dep
from app.config import Settings
from app.services.video.version import PIPELINE_VERSION
from app.services.meta.providers import (
    any_live,
    resolve_coaching_provider,
    resolve_segmentation_provider,
    resolve_workout_provider,
)

router = APIRouter(tags=["system"])


@router.get("/health")
def health(settings: Settings = Depends(settings_dep)) -> dict:
    return {
        "ok": True,
        "pipeline_version": PIPELINE_VERSION,
        "mode": settings.app_mode,
        "ai_provider": settings.ai_provider,
        "workout_provider": resolve_workout_provider(settings),
        "coaching_provider": resolve_coaching_provider(settings),
        "segmentation_provider": resolve_segmentation_provider(settings),
        "enable_meta_api": settings.enable_meta_api,
        "muse_model": settings.muse_model,
        "sam_model": settings.sam_model,
        "meta_live_possible": bool(settings.enable_meta_api and settings.model_api_key and any_live(settings)),
    }


@router.get("/catalog")
def catalog() -> dict:
    from app.services.workout.catalog import CATALOG

    return {
        "exercises": [
            {
                "id": key,
                "name": item["name"],
                "pattern": item["pattern"],
                "equipment": item["equipment"],
                "video_analysis": item["video_analysis"],
            }
            for key, item in CATALOG.items()
        ]
    }
