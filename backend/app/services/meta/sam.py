from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.services.meta.errors import MetaError
from app.services.meta.gateway import MetaBlocked, MetaGateway
from app.services.meta.pricing import estimate_sam_video_cost
from app.services.meta.providers import resolve_segmentation_provider
from app.services.meta.sam_parse import document_from_events
from app.services.meta.transport import OpenAIMetaTransport, call_with_retries, payload_digest

SUPPORTED_CODECS = {"h264", "hevc", "h265", "mpeg4"}
SUPPORTED_SUFFIXES = {".mp4", ".mov"}


class SamProvider:
    """SAM 3.1 adapter. The default segmentation provider is none, so this does not run.

    The live path, after the gateway allows it, follows the documented flow:
    upload with POST /v1/files purpose=user_data, then one cancellable background
    POST /v1/responses per concept on model sam-3.1. Person is the athlete.
    Barbell is a second request only when SAM_INCLUDE_BARBELL is true.
    Output is parsed with meta_sam_parser. The uploaded file is deleted afterward.
    """

    def __init__(self, settings: Settings, gateway: MetaGateway, transport=None):
        self.settings = settings
        self.gateway = gateway
        self.transport = transport

    def segment_video(
        self,
        video_path: Path,
        frames: int,
        approval_token: str | None = None,
        concepts: list[str] | None = None,
        fps: float | None = None,
        media: dict | None = None,
    ) -> dict:
        provider = resolve_segmentation_provider(self.settings)
        concepts = self._concepts(concepts)
        if provider in {"none", "local"}:
            return _empty(
                concepts,
                status="skipped" if provider == "none" else "skipped_local",
                label="SAM 3.1 was not called.",
            )
        if provider == "fixture":
            return self._fixture(concepts, fps or 0)
        if provider != "meta_live":
            raise MetaBlocked(f"Unknown segmentation provider '{provider}'")
        problem = unsupported_video(video_path, media)
        if problem:
            return _empty(concepts, status="unsupported", label=problem)
        return self._live(video_path, frames, concepts, fps or 0, approval_token, media)

    def _concepts(self, concepts: list[str] | None) -> list[str]:
        if concepts:
            return concepts
        chosen = ["person"]
        if self.settings.sam_include_barbell:
            chosen.append("barbell")
        return chosen

    def _live(
        self,
        video_path: Path,
        frames: int,
        concepts: list[str],
        fps: float,
        approval_token: str | None,
        media: dict | None,
    ) -> dict:
        pending=self.settings.data_dir/'sam-cleanup-pending.json'
        if pending.exists():
            raise MetaBlocked("An earlier outline request needs operator cleanup review. No new request was sent; skeleton replay remains available.")
        supplied=self.transport
        from app.services.meta.transport import OpenAIMetaTransport as LiveTransport
        if isinstance(supplied,LiveTransport) or isinstance(getattr(supplied,"inner",None),LiveTransport):
            raise MetaBlocked("Use the bounded runtime SAM transport; this legacy validation transport cannot enforce its deadline.")
        estimate = sum(estimate_sam_video_cost(frames) for _ in concepts)
        self.gateway.authorize(
            model=self.settings.sam_model,
            purpose="sam_segmentation",
            estimated_cost_usd=estimate,
            approval_token=approval_token,
            video_frames=max(50, frames) * len(concepts),
        )
        if self.transport is None:
            # The runtime path uses cancellable background Responses with a
            # total deadline. Fake transports below retain protocol coverage.
            import asyncio, time
            from app.services.meta.bounded_sam import video_events
            from app.services.meta.parse_deadline import bounded_document
            deadline=time.monotonic()+self.settings.sam_stage_timeout_seconds
            parse_reserve=min(self.settings.sam_parse_timeout_seconds,self.settings.sam_stage_timeout_seconds*.4)
            parsed=[]; cleanup=None; measured_timings={}
            for concept in concepts:
                left=deadline-time.monotonic()
                if left <= parse_reserve+1:
                    from app.services.meta.errors import MetaTimeout
                    raise MetaTimeout("Optional outlines exceeded the total stage deadline.")
                try:
                    events, cleanup = asyncio.run(video_events(self.settings,video_path,
                        sam_request(self.settings.sam_model,"pending",concept),total_seconds=left-parse_reserve))
                except MetaError as exc:
                    self.gateway.note(kind="sam_failure",purpose="sam_segmentation",stage="provider",
                        error_type=type(exc).__name__,elapsed_seconds=round(self.settings.sam_stage_timeout_seconds-(deadline-time.monotonic()),3))
                    raise
                parse_start=time.monotonic()
                try:
                    parsed.append(bounded_document(events,concept=concept,fps=fps,
                        timeout=max(.01,min(parse_reserve,deadline-time.monotonic()))))
                except MetaError as exc:
                    self.gateway.note(kind="sam_failure",purpose="sam_segmentation",stage="parsing",
                        error_type=type(exc).__name__,elapsed_seconds=round(time.monotonic()-parse_start,3))
                    raise
                measured_timings["parsing"]=round(time.monotonic()-parse_start,3)
                measured_timings.update((cleanup or {}).get("timings",{}))
            combined=_combine(parsed,concepts,fps,"live","SAM 3.1 (live)",
                None if cleanup and cleanup["file_deleted"] else "Remote cleanup needs attention",
                bool(cleanup and cleanup["file_deleted"]),media)
            combined["stage_timings"]=measured_timings
            return combined
        transport = self.transport or OpenAIMetaTransport(self.settings)
        file_id = None
        cleanup_error = None
        parsed: list[dict] = []
        try:
            file_id = transport.upload_user_file(video_path)
            for concept in concepts:
                body = sam_request(self.settings.sam_model, file_id, concept)
                self.gateway.note(
                    kind="request",
                    purpose="sam_segmentation",
                    model=self.settings.sam_model,
                    concept=concept,
                    payload_sha256=payload_digest(body),
                )
                events = call_with_retries(
                    lambda body=body: transport.responses_events(
                        body=body, timeout=self.settings.meta_request_timeout_seconds
                    ),
                    self.settings,
                    lambda attempt, kind, concept=concept: self.gateway.note(
                        kind="retry", purpose="sam_segmentation", concept=concept, attempt=attempt, reason=kind
                    ),
                )
                parsed.append(document_from_events(events, concept=concept, fps=fps))
        except MetaError:
            raise
        finally:
            if file_id is not None:
                try:
                    transport.delete_file(file_id)
                except Exception as exc:
                    cleanup_error = f"Meta file delete failed: {type(exc).__name__}"
                    self.gateway.note(kind="cleanup", purpose="sam_segmentation", error=cleanup_error)
        return _combine(parsed, concepts, fps, "live", "SAM 3.1 (live)", cleanup_error, file_deleted=cleanup_error is None, media=media)

    def _fixture(self, concepts: list[str], fps: float) -> dict:
        path = Path(__file__).resolve().parents[4] / "fixtures" / "meta" / "sam_person.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if data.get("wire"):
            parsed = [
                document_from_events(item["events"], concept=item.get("concept", "person"), fps=fps or 10)
                for item in data["wire"]
            ]
            return _combine(
                parsed,
                concepts,
                fps,
                "fixture",
                "Saved SAM fixture — not a live call",
                None,
                file_deleted=True,
                media=None,
            )
        return {
            "available": bool(data.get("tracks")),
            "status": "fixture",
            "label": "Saved SAM fixture — not a live call",
            "concepts": concepts,
            "fps": fps,
            "tracks": data.get("tracks") or [],
            "diagnostics": [],
            "file_deleted": True,
        }


def sam_request(model: str, file_id: str, concept: str) -> dict:
    """One concept per request, as the SAM 3.1 docs require. Confidence and one_bit masks are requested."""
    return {
        "model": model,
        "stream": True,
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_video", "file_id": file_id},
                ],
            }
        ],
    }


def unsupported_video(path: Path, media: dict | None) -> str | None:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return "SAM 3.1 accepts MP4 or MOV with H.264, H.265, or MPEG-4. This file was not uploaded."
    codec = str((media or {}).get("codec") or "")
    if codec and codec not in SUPPORTED_CODECS:
        return f"Codec {codec} is not accepted by SAM 3.1. This file was not uploaded."
    return None


def _empty(concepts: list[str], status: str, label: str) -> dict:
    return {
        "available": False,
        "status": status,
        "label": label,
        "concepts": concepts,
        "tracks": [],
        "diagnostics": [],
        "fps": None,
        "file_deleted": True,
    }


def _combine(parsed, concepts, fps, status, label, cleanup_error, file_deleted, media) -> dict:
    tracks = [track for item in parsed for track in item.get("tracks") or []]
    diagnostics = [item for parsed_item in parsed for item in parsed_item.get("diagnostics") or []]
    available = any(track.get("athlete") and any(frame.get("polygon") for frame in track.get("frames") or []) for track in tracks)
    widths = {item.get("media_width") for item in parsed if item.get("media_width")}
    heights = {item.get("media_height") for item in parsed if item.get("media_height")}
    expected = None
    if media and media.get("width") and media.get("height"):
        expected = (int(media["width"]), int(media["height"]))
    reported = (next(iter(widths)), next(iter(heights))) if len(widths) == 1 and len(heights) == 1 else None
    if expected and reported and expected != reported:
        available = False
        status = "size_mismatch"
        label = (
            f"SAM reported a {reported[0]}×{reported[1]} frame and the video is "
            f"{expected[0]}×{expected[1]}, so silhouettes were not drawn."
        )
        for track in tracks:
            for frame in track.get("frames") or []:
                frame["polygon"] = None
    elif not available:
        statuses = {item.get("status") for item in parsed}
        if "failed" in statuses or "refused" in statuses:
            status = "failed"
            label = "SAM 3.1 did not return segmentation. The skeleton is pose tracking, not a silhouette."
        elif "empty" in statuses or not parsed:
            status = "empty"
            label = "SAM 3.1 completed with no person match. The skeleton is pose tracking, not a silhouette."
        elif "incomplete" in statuses:
            status = "incomplete"
            label = "SAM 3.1 ended early and no silhouette was drawn."
        else:
            status = "unavailable"
            label = "SAM 3.1 returned nothing GhostRep could draw. The skeleton is pose tracking, not a silhouette."
    return {
        "available": available,
        "status": status,
        "label": label,
        "concepts": concepts,
        "fps": fps,
        "media_width": reported[0] if reported else None,
        "media_height": reported[1] if reported else None,
        "tracks": tracks,
        "diagnostics": diagnostics,
        "cleanup_error": cleanup_error,
        "file_deleted": file_deleted,
    }
