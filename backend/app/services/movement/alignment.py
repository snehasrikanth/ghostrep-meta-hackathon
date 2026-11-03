from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.services.movement.reps import DetectedRep


@dataclass
class AlignedPair:
    progress: np.ndarray
    phase: list[str]
    current_points: list[dict[str, dict]]
    reference_points: list[dict[str, dict]]


def phase_progress(idx: int, rep: DetectedRep) -> tuple[str, float]:
    if idx <= rep.bottom_idx:
        span = max(1, rep.bottom_idx - rep.start_idx)
        return "descent", float(np.clip((idx - rep.start_idx) / span, 0.0, 1.0))
    span = max(1, rep.end_idx - rep.bottom_idx)
    return "ascent", float(np.clip((idx - rep.bottom_idx) / span, 0.0, 1.0))


def _sample_at_progress(frames: list[dict], start: int, end: int, progress: float) -> dict[str, dict]:
    if end <= start:
        return frames[start]["landmarks"]
    times = np.array([f["timestamp"] for f in frames[start:end+1]])
    target = times[0] + progress * (times[-1]-times[0])
    upper = int(np.searchsorted(times,target))
    hi = min(start+upper,end)
    lo = max(start,hi-1)
    if lo == hi:
        return frames[lo]["landmarks"]
    gap = frames[hi]["timestamp"]-frames[lo]["timestamp"]
    cadence = float(np.median(np.diff(times))) if len(times)>1 else .067
    if gap > max(.2,cadence*1.5):
        return {}
    t = (target-frames[lo]["timestamp"])/gap if gap>0 else 0
    return _lerp_landmarks(frames[lo]["landmarks"], frames[hi]["landmarks"], t)


def _lerp_landmarks(a: dict[str, dict], b: dict[str, dict], t: float) -> dict[str, dict]:
    out: dict[str, dict] = {}
    names = set(a) & set(b)
    for name in names:
        pa = a.get(name)
        pb = b.get(name)
        if not pa and not pb:
            continue
        out[name] = {
            "name": name,
            "_aspect": pa.get("_aspect",1),
            "_valid": pa.get("_valid",True) and pb.get("_valid",True),
            "x": (1 - t) * pa["x"] + t * pb["x"],
            "y": (1 - t) * pa["y"] + t * pb["y"],
            "visibility": min(pa.get("visibility", 0.0), pb.get("visibility", 0.0)),
        }
    return out


def align_rep(frames: list[dict], current: DetectedRep, reference: DetectedRep) -> AlignedPair:
    """Phase-normalize current vs reference. Tempo differences remain in the metrics."""
    n = max(2, current.end_idx - current.start_idx + 1)
    progress = []
    phases = []
    current_pts = []
    reference_pts = []
    for i in range(current.start_idx, current.end_idx + 1):
        phase, p = phase_progress(i, current)
        if phase == "descent":
            ref_lms = _sample_at_progress(frames, reference.start_idx, reference.bottom_idx, p)
        else:
            ref_lms = _sample_at_progress(frames, reference.bottom_idx, reference.end_idx, p)
        progress.append(p)
        phases.append(phase)
        current_pts.append(frames[i]["landmarks"])
        reference_pts.append(ref_lms)
    return AlignedPair(
        progress=np.array(progress, dtype=np.float64),
        phase=phases,
        current_points=current_pts,
        reference_points=reference_pts,
    )
