"""Parse a SAM 3.1 Responses stream with the official meta_sam_parser package.

The wire text below follows the documented grammar
(https://dev.meta.ai/docs/sam/segmenting). Mask payloads are produced with the
package's own encoder so the decoder accepts them. This is not a live response.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

from meta_sam_parser import (
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    parse_responses_stream,
    video_segmentation_format,
)
from meta_sam_parser._errors import (
    ResponsesStreamError,
    ResponsesStreamFailedError,
    ResponsesStreamRefusalError,
)

from app.services.meta.silhouettes import MIN_DRAW_CONFIDENCE, polygon_for_mask

_MEDIA_SIZE = re.compile(r"w=(\d+);h=(\d+)")
_LANE = {"item_id": "item_sam", "output_index": 0, "content_index": 0}


def stream_events(text: str, outcome: str = "completed") -> list[dict]:
    """Documented Responses events. `outcome` is completed, incomplete, or failed."""
    events = [
        {"type": "response.output_text.delta", "delta": text, **_LANE},
        {"type": "response.output_text.done", "text": text, **_LANE},
    ]
    if outcome == "incomplete":
        events.append(
            {"type": "response.incomplete", "response": {"incomplete_details": {"reason": "max_output_tokens"}}}
        )
    elif outcome == "failed":
        events.append({"type": "response.failed", "response": {"error": {"message": "upstream failed"}}})
    else:
        events.append({"type": "response.completed", "response": {"id": "resp_offline"}})
    return events


def mask_wire(
    *,
    frame: int,
    object_id: int,
    box: tuple[int, int, int, int],
    source: tuple[int, int],
    payload: str,
    raster: tuple[int, int],
    confidence: float | None = None,
) -> str:
    """One documented video line. `box` is inclusive x1,y1,x2,y2. `raster` is height,width."""
    x1, y1, x2, y2 = box
    width, height = source
    raster_h, raster_w = raster
    confidence_field = "" if confidence is None else f";c={confidence}"
    return (
        f"<{frame}f>{object_id}"
        f"<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={width};h={height}{confidence_field}|>"
        f"<|mask;x=0;y=0{confidence_field};data={raster_h},{raster_w},{payload}|>"
    )


def parse_video_events(events: list[dict]):
    async def _events() -> AsyncIterator[dict]:
        for event in events:
            yield event

    async def _run():
        parsed = parse_responses_stream(_events(), video_segmentation_format())
        return await parsed.final_result()

    return asyncio.run(_run())


def concept_track(result, concept: str, fps: float) -> dict:
    """Boxes, decoded outlines, and video timestamps for one concept."""
    boxes: dict[tuple[str, int], SegmentationBoxRecord] = {}
    masks: dict[tuple[str, int], SegmentationMaskRecord] = {}
    for record in result.records:
        if not isinstance(record, (SegmentationBoxRecord, SegmentationMaskRecord)):
            continue
        frame_index = record.frame.frame_index if record.frame is not None else 0
        key = (record.object_id, frame_index)
        if isinstance(record, SegmentationBoxRecord):
            boxes[key] = record
        elif isinstance(record, SegmentationMaskRecord):
            masks[key] = record
    size = _media_size(result.raw_output)
    grouped: dict[str, list[dict]] = {}
    for key, box in boxes.items():
        object_id, frame_index = key
        mask = masks.get(key)
        confidence = mask.confidence if mask is not None and mask.confidence is not None else box.confidence
        polygon = None
        if mask is not None and size and (confidence is None or confidence >= MIN_DRAW_CONFIDENCE):
            polygon = polygon_for_mask(mask, size[0], size[1]) or None
        grouped.setdefault(object_id, []).append(
            {
                "frame_index": frame_index,
                "t": round(frame_index / fps, 4) if fps > 0 else None,
                "box": {
                    "left": box.left,
                    "top": box.top,
                    "right": box.right,
                    "bottom": box.bottom,
                },
                "confidence": confidence,
                "polygon": polygon,
            }
        )
    athlete = _largest_object(grouped)
    tracks = []
    for object_id, frames in grouped.items():
        frames.sort(key=lambda item: item["frame_index"])
        tracks.append(
            {
                "concept": concept,
                "object_id": object_id,
                "athlete": object_id == athlete,
                "frames": frames,
            }
        )
    return {
        "concept": concept,
        "outcome": result.outcome.status,
        "media_width": size[0] if size else None,
        "media_height": size[1] if size else None,
        "tracks": tracks,
        "diagnostics": [
            {"severity": item.severity, "code": item.code, "message": item.message}
            for item in result.diagnostics
            if item.severity == "error"
        ],
    }


def document_from_events(events: list[dict], *, concept: str, fps: float) -> dict:
    try:
        result = parse_video_events(events)
    except ResponsesStreamFailedError as exc:
        return _failed(concept, "failed", str(exc))
    except ResponsesStreamRefusalError as exc:
        return _failed(concept, "refused", str(exc))
    except ResponsesStreamError as exc:
        return _failed(concept, "unavailable", str(exc))
    parsed = concept_track(result, concept, fps)
    polygons = [
        frame
        for track in parsed["tracks"]
        if track.get("athlete")
        for frame in track["frames"]
        if frame.get("polygon")
    ]
    if polygons:
        status = "parsed" if parsed["outcome"] == "completed" else parsed["outcome"]
    elif parsed["diagnostics"]:
        status = "unavailable"
    elif parsed["outcome"] == "completed":
        status = "empty"
    else:
        status = parsed["outcome"]
    return {**parsed, "status": status, "available": bool(polygons)}


def _failed(concept: str, status: str, message: str) -> dict:
    return {
        "concept": concept,
        "status": status,
        "available": False,
        "outcome": status,
        "tracks": [],
        "diagnostics": [{"severity": "error", "code": status, "message": message[:300]}],
        "media_width": None,
        "media_height": None,
    }


def _media_size(raw: str) -> tuple[int, int] | None:
    match = _MEDIA_SIZE.search(raw or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _largest_object(grouped: dict[str, list[dict]]) -> str | None:
    best_id = None
    best_area = -1.0
    for object_id, frames in grouped.items():
        areas = sorted(
            max(0.0, frame["box"]["right"] - frame["box"]["left"])
            * max(0.0, frame["box"]["bottom"] - frame["box"]["top"])
            for frame in frames
        )
        median = areas[len(areas) // 2] if areas else 0
        if median > best_area:
            best_area = median
            best_id = object_id
    return best_id
