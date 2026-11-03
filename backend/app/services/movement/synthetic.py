from __future__ import annotations

import math

from app.services.movement.geometry import LANDMARK_NAMES


def synthesize_squat_set(
    reps: int = 6,
    fps: float = 15.0,
    width: int = 720,
    height: int = 1280,
    drift: bool = True,
) -> list[dict]:
    """Generate a labeled side-view squat landmark sequence for tests and demo fixtures.

    Later reps optionally add torso lean, reduced depth, and slower ascent.
    This is synthetic geometry, never presented as a live Meta result.
    """
    frames: list[dict] = []
    t = 0.0
    dt = 1.0 / fps
    for rep in range(reps):
        depth_scale = 1.0 - (0.08 * max(0, rep - 2) if drift else 0.0)
        lean_extra = 6.0 * max(0, rep - 2) if drift else 0.0
        ascent_stretch = 1.0 + (0.12 * max(0, rep - 2) if drift else 0.0)
        descent_n = int(1.2 * fps)
        bottom_n = int(0.25 * fps)
        ascent_n = int(1.1 * fps * ascent_stretch)
        stand_n = int(0.35 * fps)
        phases = (
            [("descent", descent_n)]
            + [("bottom", bottom_n)]
            + [("ascent", ascent_n)]
            + [("stand", stand_n)]
        )
        step = 0
        total = descent_n + bottom_n + ascent_n + stand_n
        for phase, n in phases:
            for i in range(n):
                if phase == "descent":
                    u = i / max(n - 1, 1)
                elif phase == "bottom":
                    u = 1.0
                elif phase == "ascent":
                    u = 1.0 - i / max(n - 1, 1)
                else:
                    u = 0.0
                frames.append(
                    _pose_frame(t, width, height, u, depth_scale, lean_extra, visibility=0.92)
                )
                t += dt
                step += 1
        _ = total
    return frames


def _pose_frame(
    timestamp: float,
    width: int,
    height: int,
    squat_u: float,
    depth_scale: float,
    lean_extra_deg: float,
    visibility: float,
) -> dict:
    """2D side-view (facing +x). Right side is camera-facing / more visible."""
    u = max(0.0, min(1.0, squat_u)) * depth_scale
    hip_x = 0.52 + 0.03 * u
    hip_y = 0.42 + 0.22 * u
    lean = math.radians(8 + lean_extra_deg * u)
    torso = 0.22
    shoulder_x = hip_x + math.sin(lean) * torso
    shoulder_y = hip_y - math.cos(lean) * torso
    knee_x = 0.58 + 0.04 * u
    knee_y = 0.62 + 0.08 * u
    ankle_x = 0.56
    ankle_y = 0.84
    heel_x = ankle_x - 0.03
    heel_y = 0.86
    foot_x = ankle_x + 0.05
    foot_y = 0.87
    coords = {
        "nose": (shoulder_x + 0.01, shoulder_y - 0.08),
        "right_shoulder": (shoulder_x, shoulder_y),
        "left_shoulder": (shoulder_x - 0.03, shoulder_y + 0.01),
        "right_hip": (hip_x, hip_y),
        "left_hip": (hip_x - 0.03, hip_y + 0.005),
        "right_knee": (knee_x, knee_y),
        "left_knee": (knee_x - 0.03, knee_y + 0.01),
        "right_ankle": (ankle_x, ankle_y),
        "left_ankle": (ankle_x - 0.03, ankle_y + 0.01),
        "right_heel": (heel_x, heel_y),
        "left_heel": (heel_x - 0.03, heel_y),
        "right_foot_index": (foot_x, foot_y),
        "left_foot_index": (foot_x - 0.03, foot_y),
        "right_elbow": (shoulder_x + 0.08, shoulder_y + 0.08),
        "left_elbow": (shoulder_x + 0.05, shoulder_y + 0.09),
        "right_wrist": (shoulder_x + 0.10, shoulder_y + 0.02),
        "left_wrist": (shoulder_x + 0.07, shoulder_y + 0.03),
    }
    landmarks = {}
    for name in LANDMARK_NAMES:
        x, y = coords.get(name, (0.5, 0.5))
        vis = visibility if name in coords else 0.15
        if name.startswith("left_"):
            vis *= 0.72
        landmarks[name] = {"name": name, "x": x, "y": y, "visibility": vis}
    return {
        "timestamp": timestamp,
        "width": width,
        "height": height,
        "tracking_confidence": 0.9,
        "landmarks": landmarks,
    }
