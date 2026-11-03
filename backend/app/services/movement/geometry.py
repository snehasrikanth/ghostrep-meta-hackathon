from __future__ import annotations

import math

import numpy as np

# MediaPipe Pose Landmarker 33-point names, in model index order.
LANDMARK_NAMES = [
    "nose",
    "left_eye_inner",
    "left_eye",
    "left_eye_outer",
    "right_eye_inner",
    "right_eye",
    "right_eye_outer",
    "left_ear",
    "right_ear",
    "mouth_left",
    "mouth_right",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_pinky",
    "right_pinky",
    "left_index",
    "right_index",
    "left_thumb",
    "right_thumb",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
]

SQUAT_LANDMARKS = [
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
]

POSE_EDGES: list[tuple[str, str]] = [
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("left_ankle", "left_heel"),
    ("left_ankle", "left_foot_index"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
    ("right_ankle", "right_heel"),
    ("right_ankle", "right_foot_index"),
]


def _as_xy(point: dict) -> np.ndarray:
    return np.array([float(point["x"]) * float(point.get("_aspect", 1)), float(point["y"])], dtype=np.float64)


def angle_at(a: dict, vertex: dict, c: dict) -> float:
    """Interior angle at `vertex` formed by points a-vertex-c, in degrees."""
    ba = _as_xy(a) - _as_xy(vertex)
    bc = _as_xy(c) - _as_xy(vertex)
    na = np.linalg.norm(ba)
    nc = np.linalg.norm(bc)
    if na < 1e-8 or nc < 1e-8:
        return float("nan")
    cosine = float(np.clip(np.dot(ba, bc) / (na * nc), -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def torso_inclination_deg(shoulder: dict, hip: dict) -> float:
    """Angle between hip→shoulder and image vertical-up (y decreases upward)."""
    vec = _as_xy(shoulder) - _as_xy(hip)
    norm = np.linalg.norm(vec)
    if norm < 1e-8:
        return float("nan")
    up = np.array([0.0, -1.0])
    cosine = float(np.clip(np.dot(vec, up) / norm, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def knee_angle(hip: dict, knee: dict, ankle: dict) -> float:
    return angle_at(hip, knee, ankle)


def relative_depth(hip_y: float, standing_hip_y: float, ankle_y: float) -> float:
    """0 ≈ standing, 1 ≈ hip level with ankle. Image y increases downward."""
    denom = ankle_y - standing_hip_y
    if denom < 1e-6:
        return float("nan")
    return float(np.clip((hip_y - standing_hip_y) / denom, 0.0, 1.4))


def visibility(point: dict | None) -> float:
    if not point:
        return 0.0
    return float(point.get("visibility", 0.0))
