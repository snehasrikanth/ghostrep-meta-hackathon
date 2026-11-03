"""Isolated live Meta tests.

The default is a dry run. Nothing in this module runs at application startup.
A paid call happens only when a subcommand is given ``--execute`` and
``META_LIVE_APPROVAL`` is set for that one purpose. The process does not
change ``.env``, and ``META_MAX_RETRIES`` is forced to 0.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import Base, SessionLocal
from app.models.entities import Profile, RecordedSet, WorkoutSession
from app.api.routes.workouts import _profile_dict
from app.services.coaching.prescription import coach_input_targets
from app.services.meta.contracts import (
    build_coaching_messages,
    build_workout_messages,
    coaching_response_format,
    strict_schema_issues,
    workout_response_format,
    workout_session_count,
)
from app.services.meta.gateway import MetaGateway, approval_hint
from app.services.meta.muse import MuseProvider
from app.services.meta.saved_results import COACHING_LIVE_ATTEMPT_ID
from app.services.meta.pricing import (
    COACHING_INPUT_TOKEN_ESTIMATE,
    COACHING_OUTPUT_TOKEN_ESTIMATE,
    COACHING_REASONING_EFFORT,
    WORKOUT_INPUT_TOKEN_ESTIMATE,
    WORKOUT_OUTPUT_TOKEN_ESTIMATE,
    WORKOUT_REASONING_EFFORT,
    estimate_muse_cost,
    estimate_sam_video_cost,
)
from app.services.meta.transport import ChatResult, response_diagnostics, sanitize_error
from app.services.meta.sam import SamProvider, sam_request
from app.services.video.ffmpeg import inspect_video

WORKOUT_INPUT_TOKENS = WORKOUT_INPUT_TOKEN_ESTIMATE
WORKOUT_OUTPUT_TOKENS = WORKOUT_OUTPUT_TOKEN_ESTIMATE
COACHING_INPUT_TOKENS = COACHING_INPUT_TOKEN_ESTIMATE
COACHING_OUTPUT_TOKENS = COACHING_OUTPUT_TOKEN_ESTIMATE

# Attempt 001 billed one empty HTTP 200 at backend/data/live-tests/workout/.
# That ledger is immutable. This id is the next separately approved workout call.
WORKOUT_LIVE_ATTEMPT_ID = "attempt-002-reasoning-budget"
HISTORICAL_WORKOUT_LEDGER = "workout"
SAM_LIVE_ATTEMPT_ID = "attempt-002-persist-geometry"
HISTORICAL_SAM_LEDGER = "sam-attempt-001-person"
SAM_REQUEST_TIMEOUT_SECONDS = 120


class PreflightRefused(RuntimeError):
    """Raised before any Meta client is constructed."""


class _RecordingTransport:
    def __init__(self, inner):
        self.inner = inner
        self.chat_calls = 0
        self.response_calls = 0
        self.uploads = 0
        self.deletes: list[str] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.http_status: int | None = None
        self.finish_reason: str | None = None
        self.reasoning_tokens = 0
        self.last_content = ""
        self.last_error: str | None = None
        self.last_kwargs: dict = {}
        self.diagnostics: dict = {}

    def chat_completion(self, **kwargs):
        self.chat_calls += 1
        self.last_kwargs = dict(kwargs)
        try:
            result = self.inner.chat_completion(**kwargs)
        except Exception as exc:
            self.http_status = getattr(exc, "http_status", getattr(exc, "status_code", None))
            self.last_error = type(exc).__name__ + ": " + sanitize_error(str(exc))
            raise
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self.http_status = getattr(result, "http_status", None)
        self.finish_reason = getattr(result, "finish_reason", None)
        self.reasoning_tokens = int(getattr(result, "reasoning_tokens", 0) or 0)
        self.last_content = result.content if isinstance(result.content, str) else ""
        self.diagnostics = response_diagnostics(result, schema_validation="pending")
        return result

    def upload_user_file(self, path: Path) -> str:
        self.uploads += 1
        return self.inner.upload_user_file(path)

    def delete_file(self, file_id: str) -> None:
        self.deletes.append(file_id)
        self.inner.delete_file(file_id)

    def responses_events(self, **kwargs):
        self.response_calls += 1
        self.last_kwargs = {key: value for key, value in kwargs.items() if key != "body"}
        if isinstance(kwargs.get("body"), dict):
            self.last_kwargs["model"] = kwargs["body"].get("model")
            self.last_kwargs["stream"] = kwargs["body"].get("stream")
            content = (kwargs["body"].get("input") or [{}])[0].get("content") or []
            self.last_kwargs["concept"] = next(
                (item.get("text") for item in content if item.get("type") == "input_text"),
                None,
            )
            self.last_kwargs["has_video"] = any(item.get("type") == "input_video" for item in content)
            self.last_kwargs["mask_encoding"] = (kwargs["body"].get("metadata") or {}).get("mask_encoding")
        try:
            events = self.inner.responses_events(**kwargs)
        except Exception as exc:
            self.http_status = getattr(exc, "http_status", getattr(exc, "status_code", None))
            self.last_error = type(exc).__name__ + ": " + sanitize_error(str(exc))
            raise
        self.http_status = 200
        types: dict[str, int] = {}
        for event in events:
            name = str((event or {}).get("type") or "unknown")
            types[name] = types.get(name, 0) + 1
        self.diagnostics = {
            "http_status": 200,
            "event_count": len(events),
            "event_types": types,
            "stream_completed": "response.completed" in types,
            "content_present": bool(events),
            "content_length": len(events),
        }
        return events


def workout_brief(profile: dict, session_index: int, settings: Settings) -> dict:
    messages = build_workout_messages(profile, None, session_index)
    context = json.loads(messages[1]["content"])
    prefs = context["user_preferences"]
    days = workout_session_count(profile)
    response_format = workout_response_format(session_count=days)
    schema_issues = strict_schema_issues(response_format)
    cost = estimate_muse_cost(WORKOUT_INPUT_TOKENS, WORKOUT_OUTPUT_TOKENS)
    return {
        "test": "A",
        "attempt_id": WORKOUT_LIVE_ATTEMPT_ID,
        "model": settings.muse_model,
        "endpoint": "POST /v1/chat/completions",
        "purpose": "workout_generation",
        "response_format": response_format["json_schema"]["name"],
        "strict": True,
        "reasoning_effort": WORKOUT_REASONING_EFFORT,
        "max_completion_tokens": None,
        "estimated_input_tokens": WORKOUT_INPUT_TOKENS,
        "estimated_output_tokens": WORKOUT_OUTPUT_TOKENS,
        "max_output_tokens": None,
        "estimated_cost_usd": round(cost, 6),
        "schema_validation": "ready" if not schema_issues else "invalid_request_schema",
        "schema_issues": schema_issues,
        "expected_artifact": "ghostrep_week with one session per training day",
        "retries": 0,
        "will_call": False,
        "enable_meta_api": bool(settings.enable_meta_api),
        "key_present": bool(settings.model_api_key),
        "session_index": session_index,
        "primary_goal": prefs.get("primary_goal"),
        "experience": prefs.get("experience"),
        "days_per_week": context["hard_constraints"].get("days_per_week"),
        "session_minutes": context["hard_constraints"].get("session_minutes"),
        "equipment": context["hard_constraints"].get("equipment"),
        "avoided_exercises": context["hard_constraints"].get("avoided_exercises"),
        "priority_muscles": prefs.get("priority_muscles"),
        "enjoyed_exercises": prefs.get("enjoyed_exercises"),
        "recent_sessions": len(context["training_history"].get("recent_completed_sessions") or []),
        "omits_display_name": "display_name" not in messages[1]["content"],
        "requests_complete_json": "complete ghostrep_week JSON" in messages[0]["content"],
        "historical_ledger_untouched": True,
    }


def coaching_brief(context: dict, settings: Settings) -> dict:
    messages = build_coaching_messages(context)
    measured = json.loads(messages[1]["content"])
    cost = estimate_muse_cost(COACHING_INPUT_TOKENS, COACHING_OUTPUT_TOKENS)
    return {
        "test": "B",
        "attempt_id": COACHING_LIVE_ATTEMPT_ID,
        "model": settings.muse_model,
        "endpoint": "POST /v1/chat/completions",
        "purpose": "coaching",
        "response_format": coaching_response_format()["json_schema"]["name"],
        "strict": True,
        "reasoning_effort": COACHING_REASONING_EFFORT,
        "max_completion_tokens": None,
        "estimated_input_tokens": COACHING_INPUT_TOKENS,
        "estimated_output_tokens": COACHING_OUTPUT_TOKENS,
        "max_output_tokens": None,
        "estimated_cost_usd": round(cost, 6),
        "retries": 0,
        "call_cap": 1,
        "timeout_seconds": settings.meta_request_timeout_seconds,
        "will_call": False,
        "key_present": bool(settings.model_api_key),
        "completed_reps": measured["completed_reps"],
        "planned_set_reps": (measured.get("prescription") or {}).get("planned_set_reps"),
        "prescribed_target_reps": (measured.get("prescription") or {}).get("target_reps"),
        "prescribed_rest_seconds": (measured.get("prescription") or {}).get("rest_seconds"),
        "prescribed_load_kg": (measured.get("prescription") or {}).get("load_kg"),
        "keep_plan_uses_workout_prescription": True,
        "metrics_present": measured["metrics_present"],
        "reference_rep": measured["reference_rep"],
        "has_landmarks": "landmarks" in messages[1]["content"],
        "output_schema": coaching_response_format()["json_schema"]["name"],
        "schema_issues": strict_schema_issues(coaching_response_format()),
        "set_id": context.get("set_id"),
        "context_bound": bool(context.get("recommendation_context")),
        "has_video": False,
        "historical_coaching_untouched": True,
    }


def sam_brief(media: dict, settings: Settings) -> dict:
    frames = _frame_count(media)
    cost = estimate_sam_video_cost(frames)
    body = sam_request(settings.sam_model, "file_id_assigned_after_upload", "person")
    return {
        "test": "C",
        "model": settings.sam_model,
        "endpoint": "POST /v1/files then one POST /v1/responses",
        "purpose": "sam_segmentation",
        "concept": "person",
        "barbell": False,
        "codec": media.get("codec"),
        "duration_seconds": round(float(media.get("duration") or 0), 2),
        "fps": round(float(media.get("fps") or 0), 3),
        "width": media.get("width"),
        "height": media.get("height"),
        "frames": frames,
        "billed_frames": max(50, frames),
        "estimated_cost_usd": round(cost, 6),
        "retries": 0,
        "will_call": False,
        "enable_meta_api": bool(settings.enable_meta_api),
        "key_present": bool(settings.model_api_key),
        "attempt_id": SAM_LIVE_ATTEMPT_ID,
        "request_concept": body["input"][0]["content"][0]["text"],
        "mask_encoding": body["metadata"]["mask_encoding"],
        "stream": True,
        "timeout_seconds": SAM_REQUEST_TIMEOUT_SECONDS,
        "skeleton_fallback": "Pose tracking stays labeled as the skeleton, never as SAM.",
        "historical_muse_untouched": True,
        "rotation": media.get("rotate") or 0,
        "historical_sam_untouched": True,
        "persists_geometry": True,
    }


def live_settings(base: Settings, *, kind: str, estimate: float, ledger: Path) -> Settings:
    update = {
        "enable_meta_api": True,
        "ai_provider": "local",
        "workout_provider": "meta_live" if kind == "workout" else "local",
        "coaching_provider": "meta_live" if kind == "coaching" else "local",
        "segmentation_provider": "meta_live" if kind == "sam" else "none",
        "sam_include_barbell": False,
        "meta_max_retries": 0,
        "meta_retry_sleep": False,
        "meta_max_calls_per_session": 1,
        "meta_estimated_spend_limit_usd": estimate,
        "meta_require_explicit_approval": True,
        "data_dir": ledger,
    }
    if kind == "sam":
        update["meta_request_timeout_seconds"] = SAM_REQUEST_TIMEOUT_SECONDS
        update["sam_include_barbell"] = False
    return base.model_copy(update=update)


def run_workout(profile: dict, session_index: int, settings: Settings, *, execute: bool, approval: str | None, ledger: Path, transport=None) -> dict:
    brief = workout_brief(profile, session_index, settings)
    if not execute:
        return brief
    _require_execution(settings, approval)
    _refuse_historical_workout_ledger(ledger)
    cost = estimate_muse_cost(WORKOUT_INPUT_TOKENS, WORKOUT_OUTPUT_TOKENS)
    live = live_settings(settings, kind="workout", estimate=cost, ledger=ledger)
    gateway, db = _ledger(live, ledger)
    recorder = _open_transport(live, transport)
    try:
        try:
            plan = MuseProvider(live, gateway, recorder).generate_workout(profile, None, approval, session_index)
        except Exception as exc:
            if recorder.chat_calls:
                artifact = _save_failure(ledger, "workout", recorder, cost, exc, settings.model_api_key)
                raise PreflightRefused(
                    f"Live workout call failed after {recorder.chat_calls} chat call(s). Diagnostic: {artifact}"
                ) from exc
            raise
    finally:
        db.close()
    artifact = _save(ledger, "workout", plan, recorder, cost)
    return {
        **brief,
        "will_call": True,
        "calls": recorder.chat_calls,
        "http_status": recorder.http_status,
        "finish_reason": recorder.finish_reason,
        "reasoning_effort": recorder.last_kwargs.get("reasoning_effort"),
        "max_completion_tokens": recorder.last_kwargs.get("max_completion_tokens"),
        "artifact": str(artifact),
        "source": plan.get("source"),
        **recorder.diagnostics,
        "schema_validation": "ok",
    }


def run_coaching(context: dict, settings: Settings, *, execute: bool, approval: str | None, ledger: Path, transport=None) -> dict:
    brief = coaching_brief(context, settings)
    if not execute:
        return brief
    _require_execution(settings, approval)
    if approval != approval_hint(settings, "coaching"):
        raise PreflightRefused("Coaching approval is invalid. No request was sent.")
    if not context.get("set_id") or not context.get("recommendation_context"):
        raise PreflightRefused("Coaching needs a selected recording and saved context. No request was sent.")
    if ledger.name == "coaching" and ledger.parent.name == "live-tests":
        raise PreflightRefused("Refusing the historical coaching ledger. Attempt 001 stays immutable.")
    # Exclusive file creation makes the one-call cap hold across simultaneous
    # command processes, including a crash after a request was sent.
    ledger.mkdir(parents=True, exist_ok=True)
    if (ledger / "coaching-live.json").exists():
        raise PreflightRefused("A coaching attempt already exists. Reuse its artifact; do not retry.")
    try:
        with (ledger / "coaching-attempt.claim").open("x", encoding="utf-8") as claim:
            claim.write(json.dumps({"set_id": context["set_id"], "context": context["recommendation_context"]}))
    except FileExistsError as exc:
        raise PreflightRefused("The one coaching attempt was already claimed. No request was sent.") from exc
    cost = estimate_muse_cost(COACHING_INPUT_TOKENS, COACHING_OUTPUT_TOKENS)
    live = live_settings(settings, kind="coaching", estimate=cost, ledger=ledger)
    gateway, db = _ledger(live, ledger)
    recorder = _open_transport(live, transport)
    try:
        try:
            decision = MuseProvider(live, gateway, recorder).generate_coaching(context, approval)
        except Exception as exc:
            if recorder.chat_calls:
                artifact = _save_failure(ledger, "coaching", recorder, cost, exc, settings.model_api_key)
                raise PreflightRefused(f"Live coaching failed after one call. No retry. Diagnostic: {artifact}") from exc
            raise
    finally:
        db.close()
    decision["set_id"] = context.get("set_id")
    decision["recommendation_context"] = context.get("recommendation_context")
    artifact = _save(ledger, "coaching", decision, recorder, cost)
    return {**brief, "will_call": True, "calls": recorder.chat_calls, "artifact": str(artifact), "source": decision.get("source"), "action": decision.get("suggested_action")}


def run_sam(
    video: Path,
    media: dict,
    settings: Settings,
    *,
    execute: bool,
    approval: str | None,
    ledger: Path,
    transport=None,
    association: dict | None = None,
    overlay_frames: list | None = None,
) -> dict:
    brief = sam_brief(media, settings)
    if association:
        brief.update(
            {
                key: value
                for key, value in association.items()
                if value is not None and key != "overlay_frames"
            }
        )
    if brief["concept"] != "person" or brief["barbell"]:
        raise PreflightRefused("SAM live tests are person-only.")
    if not execute:
        return brief
    _require_execution(settings, approval)
    _refuse_historical_sam_ledger(ledger)
    frames = brief["frames"]
    cost = estimate_sam_video_cost(frames)
    live = live_settings(settings, kind="sam", estimate=cost, ledger=ledger)
    gateway, db = _ledger(live, ledger)
    recorder = _open_transport(live, transport)
    try:
        try:
            result = SamProvider(live, gateway, recorder).segment_video(
                video,
                frames,
                approval,
                concepts=["person"],
                fps=float(media.get("fps") or 0),
                media=media,
            )
        except Exception as exc:
            if recorder.uploads or recorder.response_calls:
                artifact = _save_failure(ledger, "sam", recorder, cost, exc, settings.model_api_key)
                raise PreflightRefused(
                    f"Live SAM call failed after {recorder.response_calls} response call(s). Diagnostic: {artifact}"
                ) from exc
            raise
    finally:
        db.close()
    result["source"] = result.get("source") or "sam"
    if not result.get("available"):
        artifact = _save_failure(
            ledger,
            "sam",
            recorder,
            cost,
            RuntimeError(result.get("label") or "SAM returned no person silhouette."),
            settings.model_api_key,
        )
        raise PreflightRefused(f"SAM produced no silhouette masks. Diagnostic: {artifact}")
    tracks = result.get("tracks") or []
    athlete_frames = [
        frame
        for track in tracks
        if track.get("athlete") and track.get("concept") == "person"
        for frame in (track.get("frames") if isinstance(track.get("frames"), list) else [])
        if isinstance(frame, dict)
    ]
    summary = {
        "status": result.get("status"),
        "available": result.get("available"),
        "label": result.get("label"),
        "file_deleted": result.get("file_deleted"),
        "cleanup_error": result.get("cleanup_error"),
        "silhouette_source": "sam" if result.get("available") else "unavailable",
        "media_width": result.get("media_width"),
        "media_height": result.get("media_height"),
        "fps": brief["fps"],
        "event_count": recorder.diagnostics.get("event_count"),
        "event_types": recorder.diagnostics.get("event_types"),
        "stream_completed": recorder.diagnostics.get("stream_completed"),
        "request_model": recorder.last_kwargs.get("model"),
        "request_concept": recorder.last_kwargs.get("concept"),
        "mask_encoding": recorder.last_kwargs.get("mask_encoding"),
        "has_video": recorder.last_kwargs.get("has_video"),
        "frames_returned": len(athlete_frames),
        "frames_with_polygons": sum(1 for frame in athlete_frames if frame.get("polygon")),
        "frames_with_boxes": sum(1 for frame in athlete_frames if frame.get("box")),
        "tracks": [
            {
                "concept": track.get("concept"),
                "object_id": track.get("object_id"),
                "athlete": track.get("athlete"),
                "frames": len(track.get("frames") or []),
            }
            for track in tracks
        ],
    }
    tracks_path = _save_tracks(ledger, result, {**brief, "overlay_frames": overlay_frames or []})
    from app.services.meta.silhouettes import GeometryMissing, require_drawable_geometry

    saved_tracks = json.loads(tracks_path.read_text(encoding="utf-8"))
    try:
        summary["frames_with_polygons"] = require_drawable_geometry(saved_tracks)
    except GeometryMissing as exc:
        artifact = _save_failure(ledger, "sam", recorder, cost, exc, settings.model_api_key)
        raise PreflightRefused(f"{exc} Diagnostic: {artifact}") from exc
    artifact = _save(ledger, "sam", summary, recorder, cost)
    return {**brief, "will_call": True, "calls": recorder.response_calls, "uploads": recorder.uploads, "deletes": len(recorder.deletes), "artifact": str(artifact), "tracks_artifact": str(tracks_path), "geometry_persisted": True, **summary}


def _require_execution(settings: Settings, approval: str | None) -> None:
    if not settings.model_api_key:
        raise PreflightRefused("MODEL_API_KEY is empty. No request was sent.")
    if not approval:
        raise PreflightRefused("META_LIVE_APPROVAL is missing. No request was sent.")


def _open_transport(settings: Settings, transport):
    if transport is not None:
        return _RecordingTransport(transport)
    from app.services.meta.transport import OpenAIMetaTransport

    return _RecordingTransport(OpenAIMetaTransport(settings))


def _ledger(settings: Settings, ledger: Path):
    ledger.mkdir(parents=True, exist_ok=True)
    url = "sqlite:///" + str(ledger / "usage.db")
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()
    return MetaGateway(settings, db), db


def kind_ledger(data_dir: Path, kind: str) -> Path:
    if kind == "workout":
        return data_dir / "live-tests" / f"workout-{WORKOUT_LIVE_ATTEMPT_ID}"
    if kind == "sam":
        return data_dir / "live-tests" / f"sam-{SAM_LIVE_ATTEMPT_ID}"
    if kind == "coaching":
        return data_dir / "live-tests" / COACHING_LIVE_ATTEMPT_ID
    return data_dir / "live-tests" / kind


def _refuse_historical_workout_ledger(ledger: Path) -> None:
    if ledger.name == HISTORICAL_WORKOUT_LEDGER and ledger.parent.name == "live-tests":
        raise PreflightRefused(
            "Refusing to write the original workout live-test ledger. "
            "Attempt 001 stays immutable; use workout-attempt-002-reasoning-budget."
        )


def _refuse_historical_sam_ledger(ledger: Path) -> None:
    historical = {HISTORICAL_SAM_LEDGER, "sam"}
    if ledger.name in historical and ledger.parent.name == "live-tests":
        raise PreflightRefused(
            "Refusing to write the original SAM live-test ledger. "
            "Attempt 001 stays immutable; use sam-attempt-002-persist-geometry."
        )


def _save_tracks(ledger: Path, result: dict, brief: dict) -> Path:
    """Decoded polygons, boxes, timestamps, and tracking. No remote file id, rasters, or API key."""
    from app.services.meta.silhouettes import assign_athlete, segmentation_document

    ledger.mkdir(parents=True, exist_ok=True)
    assign_athlete(result, brief.get("overlay_frames") or [])
    document = segmentation_document(
        {**result, "source": result.get("source") or "sam", "model": brief.get("model")},
        set_id=brief.get("set_id"),
        analysis_id=brief.get("analysis_id"),
        session_id=brief.get("session_id"),
        media={
            "width": brief.get("width") or result.get("media_width"),
            "height": brief.get("height") or result.get("media_height"),
            "fps": brief.get("fps"),
            "rotate": brief.get("rotation") or 0,
        },
    )
    document["attempt_id"] = SAM_LIVE_ATTEMPT_ID
    document["label"] = "Live SAM 3.1 decoded person tracks. Not an offline fixture."
    path = ledger / "sam-tracks.json"
    path.write_text(json.dumps(document, indent=2, default=str), encoding="utf-8")
    return path


def _save(ledger: Path, name: str, payload: dict, recorder: _RecordingTransport, estimate: float) -> Path:
    ledger.mkdir(parents=True, exist_ok=True)
    path = ledger / f"{name}-live.json"
    diagnostics = dict(recorder.diagnostics)
    diagnostics["schema_validation"] = "ok"
    body = {
        "label": f"Live Meta test {name}. Not an offline fixture.",
        "attempt_id": (
            WORKOUT_LIVE_ATTEMPT_ID if name == "workout" else SAM_LIVE_ATTEMPT_ID if name == "sam" else COACHING_LIVE_ATTEMPT_ID if name == "coaching" else name
        ),
        "ok": True,
        "estimated_cost_usd": round(estimate, 6),
        "input_tokens": recorder.input_tokens,
        "output_tokens": recorder.output_tokens,
        "reasoning_tokens": recorder.reasoning_tokens,
        "chat_calls": recorder.chat_calls,
        "response_calls": recorder.response_calls,
        "http_status": recorder.http_status,
        "finish_reason": recorder.finish_reason,
        "content_present": diagnostics.get("content_present"),
        "content_length": diagnostics.get("content_length"),
        "schema_validation": "ok",
        "model": recorder.last_kwargs.get("model"),
        "request_schema": ((recorder.last_kwargs.get("response_format") or {}).get("json_schema") or {}).get("name"),
        "reasoning_effort": recorder.last_kwargs.get("reasoning_effort"),
        "max_completion_tokens": recorder.last_kwargs.get("max_completion_tokens"),
        "result": payload,
    }
    path.write_text(json.dumps(body, indent=2, default=str), encoding="utf-8")
    return path


def _save_failure(
    ledger: Path,
    name: str,
    recorder: _RecordingTransport,
    estimate: float,
    exc: Exception,
    secret: str = "",
) -> Path:
    ledger.mkdir(parents=True, exist_ok=True)
    path = ledger / f"{name}-live.json"
    content = recorder.last_content if isinstance(recorder.last_content, str) else ""
    raw: dict | str | None
    schema_validation = "empty_content"
    if not content.strip():
        raw = None
        schema_validation = "empty_content"
    else:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            raw = content[:4000]
            schema_validation = "invalid_json"
        else:
            raw = parsed if parsed != {} else parsed
            schema_validation = "rejected"
    if content.strip() and recorder.finish_reason == "length":
        schema_validation = "truncated"
    diagnostics = response_diagnostics(
        ChatResult(
            content=content,
            input_tokens=recorder.input_tokens,
            output_tokens=recorder.output_tokens,
            http_status=recorder.http_status,
            finish_reason=recorder.finish_reason,
            reasoning_tokens=recorder.reasoning_tokens,
        ),
        schema_validation=schema_validation,
        error=sanitize_error(str(exc), secret),
    )
    body = {
        "label": f"Live Meta test {name} FAILED. Not an offline fixture. Do not retry automatically.",
        "attempt_id": (
            WORKOUT_LIVE_ATTEMPT_ID if name == "workout" else SAM_LIVE_ATTEMPT_ID if name == "sam" else COACHING_LIVE_ATTEMPT_ID if name == "coaching" else name
        ),
        "ok": False,
        "error_type": type(exc).__name__,
        "error": sanitize_error(str(exc), secret),
        "estimated_cost_usd": round(estimate, 6),
        "input_tokens": recorder.input_tokens,
        "output_tokens": recorder.output_tokens,
        "reasoning_tokens": recorder.reasoning_tokens,
        "chat_calls": recorder.chat_calls,
        "response_calls": recorder.response_calls,
        "http_status": recorder.http_status,
        "finish_reason": recorder.finish_reason,
        "content_present": diagnostics["content_present"],
        "content_length": diagnostics["content_length"],
        "schema_validation": schema_validation,
        "reasoning_effort": recorder.last_kwargs.get("reasoning_effort"),
        "max_completion_tokens": recorder.last_kwargs.get("max_completion_tokens"),
        "raw_result": raw,
    }
    path.write_text(json.dumps(body, indent=2, default=str), encoding="utf-8")
    return path


def _frame_count(media: dict) -> int:
    counted = media.get("nb_frames")
    if isinstance(counted, int) and counted > 0:
        return counted
    fps = float(media.get("fps") or 0)
    duration = float(media.get("duration") or 0)
    if fps and duration:
        return max(1, int(round(duration * fps)))
    return 1


def select_profile(db: Session) -> Profile:
    chosen = None
    for row in db.query(Profile).filter(Profile.submitted.is_(True), Profile.assessment_json.is_not(None)).all():
        enjoyed = ((json.loads(row.assessment_json).get("preferences") or {}).get("enjoyed_exercises")) or []
        if not enjoyed:
            continue
        if chosen is None or (row.updated_at and chosen.updated_at and row.updated_at > chosen.updated_at):
            chosen = row
    if chosen is None:
        raise PreflightRefused("No submitted profile with preferred exercises.")
    return chosen


def select_coaching_set(db: Session) -> RecordedSet:
    """Prefer a SAM-live squat with completed reps, then the newest consented video.

    Sample fixtures are excluded. This selector is read-only and does not write
    a coaching row; live results go to the preflight ledger.
    """
    ranked = []
    for rec in db.query(RecordedSet).filter(RecordedSet.entry_source == "video").all():
        if not rec.consent_version or rec.analysis is None:
            continue
        if rec.original_filename == "DEMO_FIXTURE":
            continue
        reps = sum(1 for rep in rec.reps if rep.is_complete)
        if reps <= 0:
            continue
        sam_rank = 1 if rec.analysis.sam_available else 0
        ranked.append((sam_rank, rec.created_at, reps, rec))
    if not ranked:
        raise PreflightRefused("No consented video analysis with completed reps.")
    ranked.sort(key=lambda row: (row[0], row[1] or 0, row[2]), reverse=True)
    return ranked[0][3]


def select_sam_set(db: Session) -> RecordedSet:
    chosen = None
    chosen_duration = None
    for rec in db.query(RecordedSet).filter(RecordedSet.entry_source == "video").all():
        path = Path(rec.normalized_path or "")
        if not rec.consent_version or not path.exists() or path.suffix.lower() != ".mp4":
            continue
        duration = rec.duration_seconds or 0
        if chosen is None or duration < (chosen_duration or 0):
            chosen = rec
            chosen_duration = duration
    if chosen is None:
        raise PreflightRefused("No short consented H.264 recording is on disk.")
    return chosen


def coaching_context(db: Session, rec: RecordedSet) -> dict:
    from app.services.coaching.compatibility import recommendation_context, require_ready

    require_ready(rec)
    profile = db.query(Profile).filter(Profile.user_id == rec.user_id).one()
    reps = [
        {
            "rep_id": rep.rep_index,
            "start_seconds": rep.start_seconds,
            "bottom_seconds": rep.bottom_seconds,
            "end_seconds": rep.end_seconds,
            "is_complete": rep.is_complete,
            "confidence": rep.confidence,
        }
        for rep in rec.reps
        if rep.is_complete
    ]
    return {
        "set_id": rec.id,
        "recommendation_context": recommendation_context(rec),
        "quality": json.loads(rec.analysis.quality_json),
        "drift": json.loads(rec.analysis.drift_json),
        "reps": reps,
        "reference_rep": rec.analysis.reference_rep,
        "profile": _profile_dict(db, profile),
        "reported_rpe": rec.reported_rpe,
        **coach_input_targets(rec),
    }


def session_index(db: Session, user_id: str) -> int:
    return (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == user_id, WorkoutSession.status == "completed", WorkoutSession.plan_id.is_not(None))
        .count()
    )


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"workout", "coaching", "sam"}:
        print("Usage: python -m app.services.meta.live_preflight workout|coaching|sam [--execute]", file=sys.stderr)
        return 2
    kind = args[0]
    execute = "--execute" in args
    settings = get_settings()
    approval = os.environ.get("META_LIVE_APPROVAL") if execute else None
    ledger = kind_ledger(settings.data_dir, kind)
    db = SessionLocal()
    try:
        if kind == "workout":
            profile_row = select_profile(db)
            profile = _profile_dict(db, profile_row)
            result = run_workout(
                profile,
                session_index(db, profile_row.user_id),
                settings,
                execute=execute,
                approval=approval,
                ledger=ledger,
            )
            result["profile_id"] = profile_row.id
            if execute:
                result["approval_purpose"] = "workout_generation"
            elif settings.model_api_key:
                result["approval_token"] = approval_hint(settings, "workout_generation")
        elif kind == "coaching":
            rec = select_coaching_set(db)
            result = run_coaching(
                coaching_context(db, rec),
                settings,
                execute=execute,
                approval=approval,
                ledger=ledger,
            )
            result["set_id"] = rec.id
            result["entry_source"] = rec.entry_source
            if settings.model_api_key and not execute:
                result["approval_token"] = approval_hint(settings, "coaching")
        else:
            rec = select_sam_set(db)
            video = Path(rec.normalized_path)
            media = inspect_video(video)
            overlay_frames = []
            if rec.analysis and rec.analysis.overlay_json:
                overlay_frames = json.loads(rec.analysis.overlay_json).get("frames") or []
            association = {
                "set_id": rec.id,
                "analysis_id": rec.analysis.id if rec.analysis else None,
                "session_id": rec.session_id,
                "rotation": media.get("rotate") or 0,
            }
            result = run_sam(
                video,
                media,
                settings,
                execute=execute,
                approval=approval,
                ledger=ledger,
                association=association,
                overlay_frames=overlay_frames,
            )
            result["set_id"] = rec.id
            result["analysis_id"] = rec.analysis.id if rec.analysis else None
            result["session_id"] = rec.session_id
            result["consent"] = rec.consent_version
            result["rotation"] = media.get("rotate") or 0
            if execute and result.get("available"):
                from app.services.meta.apply_silhouettes import persist_to_analysis
                from app.services.meta.silhouettes import GeometryMissing

                tracks = json.loads((ledger / "sam-tracks.json").read_text(encoding="utf-8"))
                try:
                    attached = persist_to_analysis(db, rec, tracks, media=media)
                    if rec.analysis and rec.analysis.segmentation_json:
                        (ledger / "sam-tracks.json").write_text(rec.analysis.segmentation_json, encoding="utf-8")
                    result["analysis_attached"] = attached.get("silhouette_source") == "sam"
                    result["geometry_persisted"] = True
                    result["silhouette_source"] = attached.get("silhouette_source")
                except GeometryMissing as exc:
                    result["analysis_attached"] = False
                    result["geometry_persisted"] = True
                    result["attach_error"] = str(exc)
            if settings.model_api_key and not execute:
                result["approval_token"] = approval_hint(settings, "sam_segmentation")
    except PreflightRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        db.close()
    result["env_changed"] = False
    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
