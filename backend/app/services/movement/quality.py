from __future__ import annotations

import numpy as np

from app.services.movement.geometry import SQUAT_LANDMARKS
from app.services.movement.signals import choose_side, interpolate_nans, moving_average, series


def assess_camera_quality(frames: list[dict]) -> dict:
    issues: list[dict] = []
    notes: list[str] = []
    if not frames:
        return {
            "usable": False,
            "score": 0.0,
            "side": "right",
            "issues": [{"code": "empty", "message": "No frames were extracted from the recording.", "severity": "block"}],
            "notes": [],
        }

    side = choose_side(frames)
    required = [f"{side}_shoulder", f"{side}_hip", f"{side}_knee", f"{side}_ankle"]
    vis_means = {}
    for name in required + ["nose"]:
        vis = []
        for frame in frames:
            lm = frame["landmarks"].get(name)
            vis.append(lm.get("visibility", 0.0) if lm else 0.0)
        vis_means[name] = float(np.mean(vis)) if vis else 0.0

    if vis_means[required[1]] < 0.35:
        issues.append(
            {
                "code": "hip_visibility",
                "message": "Hip landmarks are not consistently visible. Step back so your hips stay in frame.",
                "severity": "block",
            }
        )
    if vis_means[required[2]] < 0.35:
        issues.append(
            {
                "code": "knee_visibility",
                "message": "Your knee landmarks are not consistently visible.",
                "severity": "block",
            }
        )
    if vis_means[required[3]] < 0.30:
        issues.append(
            {
                "code": "ankle_visibility",
                "message": "Ankles are missing from too many frames. Tilt the camera down or move it farther away.",
                "severity": "block",
            }
        )

    nose_vis = vis_means.get("nose", 0.0)
    if nose_vis < 0.25:
        issues.append(
            {
                "code": "full_body",
                "message": "Move the camera farther away so your entire body is visible.",
                "severity": "warn",
            }
        )

    shoulder_width = _mean_separation(frames, "left_shoulder", "right_shoulder")
    torso_len = _mean_separation(frames, f"{side}_shoulder", f"{side}_hip")
    side_ratio = shoulder_width / max(torso_len, 1e-3)
    if side_ratio > 0.85:
        issues.append(
            {
                "code": "camera_angle",
                "message": "Try recording from a side angle. A front view hides squat depth and torso lean.",
                "severity": "warn",
            }
        )

    ankle = interpolate_nans(series(frames, f"{side}_ankle", "x"))
    if len(ankle) > 8:
        jitter = float(np.mean(np.abs(np.diff(moving_average(ankle, 3)))))
        if jitter > 0.03:
            issues.append(
                {
                    "code": "camera_motion",
                    "message": "Keep your phone stationary during the exercise.",
                    "severity": "warn",
                }
            )

    hip_y = interpolate_nans(series(frames, f"{side}_hip", "y"))
    motion = float(np.nanmax(hip_y) - np.nanmin(hip_y)) if hip_y.size else 0.0
    if motion < 0.04:
        issues.append(
            {
                "code": "motion_incomplete",
                "message": "Not enough vertical hip travel was observed. Record a complete set of squats.",
                "severity": "block",
            }
        )

    occupancy = _full_body_occupancy(frames)
    if occupancy < 0.45:
        issues.append(
            {
                "code": "crop",
                "message": "The athlete is cropped. Keep head, hips, knees, and feet in the frame.",
                "severity": "warn",
            }
        )

    blocks = [i for i in issues if i["severity"] == "block"]
    score = max(0.0, 1.0 - 0.22 * len(issues) - 0.25 * len(blocks))
    usable = len(blocks) == 0 and score >= 0.35
    if usable:
        notes.append(
            f"Analysis uses the {side} side because those landmarks were more consistently visible."
        )
        notes.append("Camera-angle suitability is a heuristic, not a calibrated 3D reconstruction.")
    return {
        "usable": usable,
        "score": float(score),
        "side": side,
        "issues": issues,
        "notes": notes,
        "debug": {
            "visibility": vis_means,
            "side_ratio": side_ratio,
            "hip_travel": motion,
            "required_landmarks": SQUAT_LANDMARKS,
        },
    }


def _mean_separation(frames: list[dict], a: str, b: str) -> float:
    dists = []
    for frame in frames:
        pa = frame["landmarks"].get(a)
        pb = frame["landmarks"].get(b)
        if pa and pb:
            dists.append(np.hypot(pa["x"] - pb["x"], pa["y"] - pb["y"]))
    return float(np.mean(dists)) if dists else 0.0


def _full_body_occupancy(frames: list[dict]) -> float:
    hits = 0
    total = 0
    keys = ("nose", "left_hip", "right_hip", "left_ankle", "right_ankle")
    for frame in frames:
        for key in keys:
            total += 1
            lm = frame["landmarks"].get(key)
            if lm and lm.get("visibility", 0) > 0.35:
                if 0.02 < lm["x"] < 0.98 and 0.02 < lm["y"] < 0.98:
                    hits += 1
    return hits / max(total, 1)
