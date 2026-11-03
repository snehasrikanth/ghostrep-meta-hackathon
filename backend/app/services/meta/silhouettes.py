"""Turn official SAM mask records into normalized outlines the ghost player can draw.

Polygons are in the video's own 0–1 coordinates, the same space as pose landmarks.
A missing mask stays null. Nothing here is labeled as live SAM unless the source is sam.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np

# GhostRep policy, not a Meta requirement: a reported confidence under this is not drawn.
# A missing confidence is kept. The parser treats absence as unknown, not zero.
MIN_DRAW_CONFIDENCE = 0.2
DRAWABLE_SOURCES = {"sam", "fixture"}


class GeometryMissing(RuntimeError):
    """Inference claimed success but no drawable athlete outline was stored."""


_POSE_BODY = {
    "nose",
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
}


def polygon_for_mask(mask_record, source_width: int, source_height: int) -> list[dict]:
    import cv2
    from meta_sam_parser import decode_mask_to_raster

    raster = decode_mask_to_raster(mask_record.mask)
    width = int(mask_record.mask.width)
    height = int(mask_record.mask.height)
    if width <= 0 or height <= 0 or source_width <= 0 or source_height <= 0:
        return []
    image = np.frombuffer(raster, dtype=np.uint8).reshape(height, width).copy()
    contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 1:
        return []
    reduced = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
    if len(reduced) < 3:
        reduced = contour
    bounds = mask_record.bounds
    box_w = float(bounds.right - bounds.left)
    box_h = float(bounds.bottom - bounds.top)
    if box_w <= 0 or box_h <= 0:
        return []
    points = []
    for point in reduced.reshape(-1, 2)[:48]:
        px, py = float(point[0]), float(point[1])
        x = (bounds.left + (px + 0.5) / width * box_w) / source_width
        y = (bounds.top + (py + 0.5) / height * box_h) / source_height
        points.append({"x": round(min(1.0, max(0.0, x)), 4), "y": round(min(1.0, max(0.0, y)), 4)})
    return points if len(points) >= 3 else []


def attach_silhouettes(overlay: dict, segmentation: dict, reference_rep: int | None) -> dict:
    """Stamp athlete outlines onto pose frames by timestamp, then phase-align the reference."""
    frames = overlay.get("frames") or []
    assign_athlete(segmentation, frames)
    person = _person_frames(segmentation)
    tolerance = _timestamp_tolerance(frames, float(segmentation.get("fps") or 0))
    drawn = 0
    for frame in frames:
        frame["silhouette"] = None
        frame["reference_silhouette"] = None
        match = _nearest(person, float(frame.get("t") or 0))
        if not match or match.get("t") is None:
            continue
        if abs(float(match["t"]) - float(frame.get("t") or 0)) > tolerance:
            continue
        frame["silhouette"] = match.get("polygon")
        if frame["silhouette"]:
            drawn += 1
    source = silhouette_source(segmentation) if drawn else "unavailable"
    overlay["silhouette_source"] = source
    overlay["silhouette_label"] = silhouette_label(source)
    if drawn:
        _align_reference(frames, reference_rep)
    return overlay


def assign_athlete(segmentation: dict, overlay_frames: list[dict] | None) -> str | None:
    """Mark one person track as the athlete using pose overlap, not detection order."""
    tracks = [track for track in (segmentation.get("tracks") or []) if track.get("concept") == "person"]
    for track in tracks:
        track["athlete"] = False
    if not tracks:
        segmentation["athlete_object_id"] = None
        segmentation["athlete_confidence"] = "none"
        return None
    scored = _pose_scores(tracks, overlay_frames or [], segmentation)
    chosen = None
    confidence = "coverage"
    if scored and scored[0][0] > 0:
        chosen = scored[0][2]
        confidence = "high"
        if len(scored) > 1 and scored[1][0] > 0 and scored[0][0] - scored[1][0] < 0.05:
            confidence = "low"
    if chosen is None:
        chosen = _coverage_track(tracks)
        confidence = "coverage"
    if chosen is None:
        segmentation["athlete_object_id"] = None
        segmentation["athlete_confidence"] = "none"
        return None
    chosen["athlete"] = True
    segmentation["athlete_object_id"] = chosen.get("object_id")
    segmentation["athlete_confidence"] = confidence
    return chosen.get("object_id")


def drawable_athlete_frames(segmentation: dict) -> list[dict]:
    frames = []
    for track in segmentation.get("tracks") or []:
        if track.get("concept") != "person" or not track.get("athlete"):
            continue
        for frame in _track_frames(track):
            if frame.get("polygon") and frame.get("t") is not None:
                frames.append(frame)
    return frames


def require_drawable_geometry(segmentation: dict) -> int:
    """Refuse a 'success' that has no athlete outline with a timestamp."""
    count = len(drawable_athlete_frames(segmentation))
    if count < 1:
        raise GeometryMissing("SAM produced no drawable athlete polygons with timestamps.")
    return count


def silhouette_source(segmentation: dict) -> str:
    source = str(segmentation.get("source") or "")
    if source in DRAWABLE_SOURCES:
        return source
    status = str(segmentation.get("status") or "")
    label = str(segmentation.get("label") or "").lower()
    if status == "fixture" or "fixture" in label or "not a live" in label:
        return "fixture"
    if status in {"live", "parsed"}:
        return "sam"
    return "sam" if segmentation.get("available") else "unavailable"


def silhouette_label(source: str | None) -> str:
    if source == "sam":
        return "SAM 3.1 (live)"
    if source == "fixture":
        return "Offline fixture"
    return "Pose tracking"


def segmentation_document(
    segmentation: dict,
    *,
    set_id: str | None = None,
    analysis_id: str | None = None,
    session_id: str | None = None,
    media: dict | None = None,
) -> dict[str, Any]:
    """Compact lossless outlines plus tracking metadata. No remote file id, no rasters, no secrets."""
    media = media or {}
    source = silhouette_source(segmentation)
    tracks = deepcopy(segmentation.get("tracks") or [])
    return {
        "label": segmentation.get("label") or silhouette_label(source),
        "source": source,
        "status": segmentation.get("status"),
        "available": bool(segmentation.get("available")),
        "model": segmentation.get("model") or ("sam-3.1" if source == "sam" else None),
        "set_id": set_id or segmentation.get("set_id"),
        "analysis_id": analysis_id or segmentation.get("analysis_id"),
        "session_id": session_id or segmentation.get("session_id"),
        "media_width": segmentation.get("media_width") or media.get("width"),
        "media_height": segmentation.get("media_height") or media.get("height"),
        "rotation": media.get("rotate") if media.get("rotate") is not None else segmentation.get("rotation") or 0,
        "fps": segmentation.get("fps") or media.get("fps"),
        "athlete_object_id": segmentation.get("athlete_object_id"),
        "athlete_confidence": segmentation.get("athlete_confidence"),
        "tracks": tracks,
        "diagnostics": segmentation.get("diagnostics") or [],
    }


def fixture_from_overlay(overlay: dict, *, fps: float = 15.0) -> dict:
    """Synthetic person outlines from pose. Not live SAM. Object 0 is a decoy on purpose."""
    athlete_frames = []
    decoy_frames = []
    for index, frame in enumerate(overlay.get("frames") or []):
        polygon = hull_from_landmarks(frame.get("current") or [])
        if not polygon:
            continue
        t = float(frame.get("t") or 0)
        athlete_frames.append(
            {
                "frame_index": index,
                "t": t,
                "box": box_from_polygon(polygon),
                "confidence": 0.99,
                "polygon": polygon,
            }
        )
        decoy = _decoy_polygon()
        decoy_frames.append(
            {
                "frame_index": index,
                "t": t,
                "box": box_from_polygon(decoy),
                "confidence": 0.9,
                "polygon": decoy,
            }
        )
    tracks = [
        {"concept": "person", "object_id": "0", "athlete": False, "frames": decoy_frames},
        {"concept": "person", "object_id": "1", "athlete": False, "frames": athlete_frames},
    ]
    segmentation = {
        "source": "fixture",
        "status": "fixture",
        "label": "Offline fixture — not a live SAM call",
        "available": bool(athlete_frames),
        "fps": fps,
        "media_width": 1,
        "media_height": 1,
        "tracks": tracks,
        "diagnostics": [],
    }
    assign_athlete(segmentation, overlay.get("frames") or [])
    return segmentation


def hull_from_landmarks(landmarks: list[dict]) -> list[dict] | None:
    points = []
    for item in landmarks:
        if item.get("name") not in _POSE_BODY:
            continue
        if float(item.get("visibility") or 0) < 0.3:
            continue
        points.append((float(item["x"]), float(item["y"])))
    hull = _convex_hull(points)
    if len(hull) < 3:
        return None
    return [{"x": round(min(1.0, max(0.0, x)), 4), "y": round(min(1.0, max(0.0, y)), 4)} for x, y in hull]


def box_from_polygon(polygon: list[dict]) -> dict[str, float]:
    xs = [point["x"] for point in polygon]
    ys = [point["y"] for point in polygon]
    return {
        "left": min(xs),
        "top": min(ys),
        "right": max(xs),
        "bottom": max(ys),
    }


def _decoy_polygon() -> list[dict]:
    return [
        {"x": 0.02, "y": 0.18},
        {"x": 0.16, "y": 0.18},
        {"x": 0.16, "y": 0.72},
        {"x": 0.02, "y": 0.72},
    ]


def _person_frames(segmentation: dict) -> list[dict]:
    frames = drawable_athlete_frames(segmentation)
    frames.sort(key=lambda item: item["t"])
    return frames


def _timestamp_tolerance(overlay_frames: list[dict], sam_fps: float) -> float:
    pose_times = sorted(float(frame.get("t") or 0) for frame in overlay_frames)
    pose_dt = 0.0
    gaps = [later - earlier for earlier, later in zip(pose_times, pose_times[1:]) if later > earlier]
    typical = [gap for gap in gaps if gap <= 0.4]
    if typical:
        typical.sort()
        pose_dt = typical[len(typical) // 2]
    elif gaps:
        gaps.sort()
        pose_dt = gaps[0]
    sam_dt = 1.0 / sam_fps if sam_fps > 0 else 0.0
    step = max(pose_dt, sam_dt, 1.0 / 15.0)
    return step / 2.0 + 1e-6


def _nearest(frames: list[dict], timestamp: float) -> dict | None:
    if not frames:
        return None
    return min(frames, key=lambda item: abs(float(item["t"]) - timestamp))


def _align_reference(frames: list[dict], reference_rep: int | None) -> None:
    if reference_rep is None:
        return
    reference = [frame for frame in frames if frame.get("active_rep") == reference_rep and frame.get("silhouette")]
    for frame in frames:
        active = frame.get("active_rep")
        if active == reference_rep:
            frame["reference_silhouette"] = frame.get("silhouette")
            continue
        if not active or not reference:
            continue
        same_phase = [item for item in reference if item.get("phase") == frame.get("phase")]
        if not same_phase:
            continue
        progress = float(frame.get("phase_progress") or 0)
        best = min(same_phase, key=lambda item: abs(float(item.get("phase_progress") or 0) - progress))
        frame["reference_silhouette"] = best.get("silhouette")


def _pose_associated_track(tracks: list[dict], overlay_frames: list[dict], segmentation: dict) -> dict | None:
    scored = _pose_scores(tracks, overlay_frames, segmentation)
    if not scored or scored[0][0] <= 0:
        return None
    return scored[0][2]


def _pose_scores(tracks: list[dict], overlay_frames: list[dict], segmentation: dict) -> list[tuple[float, int, dict]]:
    if not overlay_frames:
        return []
    width = float(segmentation.get("media_width") or 0)
    height = float(segmentation.get("media_height") or 0)
    scored = []
    for track in tracks:
        ious = []
        frames = _track_frames(track)
        for frame in frames:
            pose = _nearest(overlay_frames, float(frame.get("t") or 0))
            pose_box = _pose_bbox(pose.get("current") if pose else None)
            sam_box = _norm_box(frame.get("box"), width, height)
            if pose_box and sam_box:
                ious.append(_iou(pose_box, sam_box))
        if not ious:
            continue
        ious.sort()
        scored.append((ious[len(ious) // 2], len(frames), track))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored


def _track_frames(track: dict) -> list[dict]:
    raw = track.get("frames") or []
    if not isinstance(raw, list):
        return []
    return [frame for frame in raw if isinstance(frame, dict)]


def _coverage_track(tracks: list[dict]) -> dict | None:
    def key(track: dict) -> tuple[int, float]:
        frames = _track_frames(track)
        polys = sum(1 for frame in frames if frame.get("polygon"))
        areas = [_box_area(frame.get("box")) for frame in frames if frame.get("box")]
        median = sorted(areas)[len(areas) // 2] if areas else 0.0
        return (polys, median)

    return max(tracks, key=key) if tracks else None


def _pose_bbox(landmarks: list[dict] | None) -> tuple[float, float, float, float] | None:
    if not landmarks:
        return None
    xs, ys = [], []
    for item in landmarks:
        if item.get("name") not in _POSE_BODY:
            continue
        if float(item.get("visibility") or 0) < 0.3:
            continue
        xs.append(float(item["x"]))
        ys.append(float(item["y"]))
    if len(xs) < 2:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _norm_box(box: dict | None, width: float, height: float) -> tuple[float, float, float, float] | None:
    if not box:
        return None
    left, top, right, bottom = float(box["left"]), float(box["top"]), float(box["right"]), float(box["bottom"])
    if right > 1.5 or bottom > 1.5:
        if width <= 0 or height <= 0:
            return None
        left, right = left / width, right / width
        top, bottom = top / height, bottom / height
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    inter = max(0.0, right - left) * max(0.0, bottom - top)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def _box_area(box: dict | None) -> float:
    if not box:
        return 0.0
    return max(0.0, float(box["right"]) - float(box["left"])) * max(0.0, float(box["bottom"]) - float(box["top"]))


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]
