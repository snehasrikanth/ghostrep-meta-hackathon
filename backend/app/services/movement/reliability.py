"""Observable tracking checks, not posture correctness or clinical confidence."""
from __future__ import annotations
import numpy as np

JOINTS = ("shoulder", "hip", "knee", "ankle")
BONES = (("shoulder", "hip"), ("hip", "knee"), ("knee", "ankle"))


def geometry_frames(frames: list[dict]) -> list[dict]:
    """Keep display coordinates; carry the pixel aspect into angle calculations."""
    out = []
    for frame in frames:
        aspect = float(frame.get("width") or 1) / max(float(frame.get("height") or 1), 1)
        out.append({**frame, "landmarks": {name: {**point, "_aspect": aspect}
                    for name, point in frame.get("landmarks", {}).items()}})
    return out


def side_reliability(frames: list[dict], side: str) -> list[dict]:
    lengths = np.full((len(frames), 3), np.nan)
    points = np.full((len(frames), 4, 2), np.nan)
    visibility = np.zeros((len(frames), 4))
    for i, f in enumerate(frames):
        aspect = float(f.get("width") or 1) / max(float(f.get("height") or 1), 1)
        for j, joint in enumerate(JOINTS):
            p = f.get("landmarks", {}).get(f"{side}_{joint}")
            if p:
                points[i, j] = [float(p["x"]) * aspect, float(p["y"])]
                visibility[i, j] = float(p.get("visibility", 0))
        for j in range(3):
            lengths[i, j] = np.linalg.norm(points[i, j + 1] - points[i, j])
    usable = np.all(visibility >= .35, axis=1) & np.all(np.isfinite(points), axis=(1, 2))
    pool = lengths[usable]
    med = np.nanmedian(pool, axis=0) if len(pool) else np.array([.2, .2, .2])
    med = np.maximum(med, .025)
    result = []
    cadence = float(np.median(np.diff([f["timestamp"] for f in frames]))) if len(frames)>1 else .067
    for i, f in enumerate(frames):
        reasons = []
        if not usable[i]: reasons.append("missing_or_obstructed_landmarks")
        if usable[i]:
            ratio = lengths[i] / med
            if ratio[0] < .5 or ratio[0] > 1.8 or np.any(ratio[1:] < .25) or np.any(ratio[1:] > 2.5): reasons.append("inconsistent_segment_lengths")
            if points[i, 0, 1] >= points[i, 1, 1]: reasons.append("inverted_torso_geometry")
            if i and usable[i - 1]:
                dt = float(f["timestamp"]) - float(frames[i - 1]["timestamp"])
                jump = np.max(np.linalg.norm(points[i] - points[i - 1], axis=1))
                if dt <= 0 or dt > max(.3, cadence * 2.5): reasons.append("tracking_gap")
                elif jump > med[0] * max(.65, dt * 4): reasons.append("landmark_discontinuity")
        upper = points[i, :2]
        detection_valid = bool(np.all(np.isfinite(upper)) and np.all(visibility[i,:2] >= .35))
        if detection_valid:
            detection_valid = bool(.5 <= lengths[i,0]/med[0] <= 1.8 and upper[0,1] < upper[1,1])
        if i and detection_valid and np.all(np.isfinite(points[i-1,:2])):
            if np.max(np.linalg.norm(upper-points[i-1,:2],axis=1)) > med[0]*max(.65,cadence*4): detection_valid=False
        result.append({"valid": not reasons, "detection_valid": detection_valid, "visibility": float(np.mean(visibility[i])), "reasons": reasons})
    return result


def reliable_side(frames: list[dict]) -> tuple[str, list[dict]]:
    candidates = [(side, side_reliability(frames, side)) for side in ("right", "left")]
    return max(candidates, key=lambda item: sum(row["detection_valid"] + .01*row["visibility"] for row in item[1]))


def invalid_intervals(frames: list[dict], checks: list[dict]) -> list[dict]:
    intervals = []; start = None
    for i in range(len(frames) + 1):
        bad = i < len(frames) and not checks[i]["valid"]
        if bad and start is None: start = i
        if not bad and start is not None:
            end = i - 1
            intervals.append({"start_seconds": frames[start]["timestamp"], "end_seconds": frames[end]["timestamp"],
                "reason": ", ".join(sorted({r for c in checks[start:i] for r in c["reasons"]}))})
            start = None
    return intervals
