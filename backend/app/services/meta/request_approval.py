"""Translate an explicit app choice into purpose-scoped server-side approval."""

from app.config import Settings
from app.services.meta.gateway import MetaBlocked, approval_hint
from app.services.meta.providers import resolve_coaching_provider, resolve_workout_provider, resolve_segmentation_provider


def muse_request(settings: Settings, purpose: str, approved: bool) -> tuple[Settings, str | None]:
    field, provider = (
        ("workout_provider", resolve_workout_provider(settings))
        if purpose == "workout_generation"
        else ("coaching_provider", resolve_coaching_provider(settings))
    )
    if not approved:
        # Selecting local stays local even when the server is enabled for Muse.
        return settings.model_copy(update={field: "local"}) if provider == "meta_live" else settings, None
    if not settings.enable_meta_api or not settings.model_api_key or provider != "meta_live":
        raise MetaBlocked("Personalized planning is temporarily unavailable. Please try again shortly.")
    # Each checked app action approves one request, never automatic retries.
    return settings.model_copy(update={"meta_max_retries": 0}), approval_hint(settings, purpose)


def sam_request_approval(settings: Settings, approved: bool) -> tuple[Settings, str | None]:
    provider = resolve_segmentation_provider(settings)
    if not approved:
        return settings.model_copy(update={"segmentation_provider": "none"}) if provider == "meta_live" else settings, None
    if not settings.enable_meta_api or not settings.model_api_key or provider != "meta_live":
        raise MetaBlocked("Movement outlines are temporarily unavailable. Please try again shortly.")
    return settings.model_copy(update={
        "meta_max_retries": 0,
        "sam_include_barbell": False,
        "meta_request_timeout_seconds": 180,
    }), approval_hint(settings, "sam_segmentation")
