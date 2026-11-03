from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from app.services.movement.geometry import visibility


def moving_average(values: np.ndarray, window: int = 5) -> np.ndarray:
    if len(values) == 0:
        return values
    window = max(1, min(window, len(values)))
    kernel = np.ones(window) / window
    pad = window // 2
    padded = np.pad(values, (pad, pad), mode="edge")
    return np.convolve(padded, kernel, mode="valid")[: len(values)]


def series(frames: list[dict], name: str, coord: str = "y") -> np.ndarray:
    out = []
    for frame in frames:
        lm = frame["landmarks"].get(name)
        out.append(float(lm[coord]) if lm else np.nan)
    return np.array(out, dtype=np.float64)


def interpolate_nans(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    x = np.arange(len(values))
    good = np.isfinite(values)
    if good.sum() == 0:
        return np.zeros_like(values)
    if good.all():
        return values
    filled = values.copy()
    filled[~good] = np.interp(x[~good], x[good], values[good])
    return filled


def choose_side(frames: Iterable[dict]) -> str:
    """Lock the more consistently visible side for the entire set."""
    left_keys = ("left_hip", "left_knee", "left_ankle", "left_shoulder")
    right_keys = ("right_hip", "right_knee", "right_ankle", "right_shoulder")
    left_scores: list[float] = []
    right_scores: list[float] = []
    for frame in frames:
        lms = frame["landmarks"]
        left_scores.append(np.mean([visibility(lms.get(k)) for k in left_keys]))
        right_scores.append(np.mean([visibility(lms.get(k)) for k in right_keys]))
    left = float(np.nanmean(left_scores) if left_scores else 0.0)
    right = float(np.nanmean(right_scores) if right_scores else 0.0)
    return "left" if left >= right else "right"


def landmark_map(frame: dict) -> dict[str, dict]:
    return frame["landmarks"]
