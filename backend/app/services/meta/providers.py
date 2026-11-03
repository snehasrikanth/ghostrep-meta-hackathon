"""Which implementation serves workouts, coaching, and segmentation.

Segmentation does not inherit AI_PROVIDER. A switch that turns on Muse Spark
must not also start paid video segmentation.
"""

from __future__ import annotations

from app.config import Settings

ProviderName = str


def resolve_workout_provider(settings: Settings) -> ProviderName:
    return _chosen(settings.workout_provider, settings.ai_provider)


def resolve_coaching_provider(settings: Settings) -> ProviderName:
    return _chosen(settings.coaching_provider, settings.ai_provider)


def resolve_segmentation_provider(settings: Settings) -> ProviderName:
    chosen = (settings.segmentation_provider or "").strip().lower()
    return chosen or "none"


def _chosen(explicit: str, legacy: str) -> ProviderName:
    value = (explicit or "").strip().lower()
    if value:
        return value
    return (legacy or "local").strip().lower() or "local"


def any_live(settings: Settings) -> bool:
    return "meta_live" in {
        resolve_workout_provider(settings),
        resolve_coaching_provider(settings),
        resolve_segmentation_provider(settings),
    }
