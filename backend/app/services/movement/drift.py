from __future__ import annotations

import numpy as np

from app.services.movement.alignment import align_rep
from app.services.movement.geometry import knee_angle, torso_inclination_deg
from app.services.movement.reps import DetectedRep
from app.services.movement.upper_body import upper_body_comparison

# Documented similarity formula:
# similarity = 100 * (1 - clip(w_torso*n_torso + w_knee*n_knee + w_depth*n_depth
#                               + w_hip*n_hip + w_tempo*n_tempo, 0, 1))
# Normalizers are conservative movement tolerances, not injury thresholds.
WEIGHTS = {
    "torso": 0.22,
    "knee": 0.22,
    "depth": 0.20,
    "hip": 0.18,
    "tempo": 0.18,
}
NORM = {
    "torso": 18.0,  # degrees RMSE
    "knee": 20.0,  # degrees RMSE
    "depth": 25.0,  # percent
    "hip": 0.12,  # normalized hip path RMSE
    "tempo": 40.0,  # percent duration change
}


def compute_drift(
    frames: list[dict],
    reps: list[DetectedRep],
    reference: DetectedRep,
    side: str,
) -> list[dict]:
    points: list[dict] = []
    hip = f"{side}_hip"
    knee = f"{side}_knee"
    ankle = f"{side}_ankle"
    shoulder = f"{side}_shoulder"

    for rep in reps:
        aligned = align_rep(frames, rep, reference)
        torso_err = _rmse_feature(aligned, shoulder, hip, torso_inclination_deg)
        upper_body = upper_body_comparison(aligned, shoulder, hip, eligible=rep.is_complete and reference.is_complete and rep.metrics.get("comparison_eligible",True) is not False and reference.metrics.get("comparison_eligible",True) is not False)
        torso_err = upper_body["rms_difference_deg"] if upper_body["rms_difference_deg"] is not None else float("nan")
        knee_err = _rmse_knee(aligned, hip, knee, ankle)
        depth_ref = reference.metrics.get("relative_depth", 0.0)
        depth_cur = rep.metrics.get("relative_depth", 0.0)
        depth_diff = 100.0 * (depth_cur - depth_ref) / max(depth_ref, 0.05)
        hip_err = _hip_rmse(aligned, hip)
        ascent_diff = _pct(rep.ascent_seconds, reference.ascent_seconds)
        descent_diff = _pct(rep.descent_seconds, reference.descent_seconds)
        tempo = (abs(ascent_diff) + abs(descent_diff)) / 2.0

        blended = (
            WEIGHTS["torso"] * _norm(torso_err, NORM["torso"])
            + WEIGHTS["knee"] * _norm(knee_err, NORM["knee"])
            + WEIGHTS["depth"] * _norm(abs(depth_diff), NORM["depth"])
            + WEIGHTS["hip"] * _norm(hip_err, NORM["hip"])
            + WEIGHTS["tempo"] * _norm(tempo, NORM["tempo"])
        )
        similarity = float(np.clip(100.0 * (1.0 - blended), 0.0, 100.0))
        if rep.rep_id == reference.rep_id:
            similarity = 100.0
            torso_err = 0.0
            knee_err = 0.0
            depth_diff = 0.0
            hip_err = 0.0
            ascent_diff = 0.0
            descent_diff = 0.0

        valid = upper_body["comparison_usable"] and all(np.isfinite(v) for v in [torso_err,knee_err,hip_err,depth_diff,ascent_diff,descent_diff])
        points.append(
            {"comparison_valid":valid,
                "rep_id": rep.rep_id,
                "similarity": similarity,
                "reference_deviation": 0.0 if rep.rep_id == reference.rep_id else float(100.0 - similarity),
                "progressive_drift": 0.0,
                # Compatibility alias: RMS is nonnegative magnitude, never a signed direction.
                "torso_lean_difference_deg": torso_err,
                "torso_angle_rmse_deg": torso_err,
                "upper_body_comparison": upper_body,
                "depth_difference_percent": depth_diff,
                "ascent_duration_difference_percent": ascent_diff,
                "descent_duration_difference_percent": descent_diff,
                "knee_angle_rmse_deg": knee_err,
                "hip_rmse": hip_err,
                "onset": False,
            }
        )

    _fill_progressive_drift(frames, reps, points, side)
    _mark_onset(points)
    for point in points:
        if not point["comparison_valid"]:
            for key in ["similarity","reference_deviation","progressive_drift","torso_lean_difference_deg","torso_angle_rmse_deg","depth_difference_percent","knee_angle_rmse_deg","hip_rmse"]:
                point[key] = None
            point["onset"] = False
            point["unavailable_reason"] = "Insufficient reliable aligned landmarks."
    return points


def _fill_progressive_drift(frames: list[dict], reps: list[DetectedRep], points: list[dict], side: str) -> None:
    """Change versus the previous rep. A stable offset from the reference is not drift."""
    hip = f"{side}_hip"
    knee = f"{side}_knee"
    ankle = f"{side}_ankle"
    shoulder = f"{side}_shoulder"
    for i in range(1, len(reps)):
        prev = reps[i - 1]
        cur = reps[i]
        aligned = align_rep(frames, cur, prev)
        torso_err = _rmse_feature(aligned, shoulder, hip, torso_inclination_deg)
        knee_err = _rmse_knee(aligned, hip, knee, ankle)
        depth_prev = prev.metrics.get("relative_depth", 0.0)
        depth_cur = cur.metrics.get("relative_depth", 0.0)
        depth_diff = 100.0 * (depth_cur - depth_prev) / max(depth_prev, 0.05)
        hip_err = _hip_rmse(aligned, hip)
        tempo = (abs(_pct(cur.ascent_seconds, prev.ascent_seconds)) + abs(_pct(cur.descent_seconds, prev.descent_seconds))) / 2.0
        blended = (
            WEIGHTS["torso"] * _norm(torso_err, NORM["torso"])
            + WEIGHTS["knee"] * _norm(knee_err, NORM["knee"])
            + WEIGHTS["depth"] * _norm(abs(depth_diff), NORM["depth"])
            + WEIGHTS["hip"] * _norm(hip_err, NORM["hip"])
            + WEIGHTS["tempo"] * _norm(tempo, NORM["tempo"])
        )
        points[i]["progressive_drift"] = float(np.clip(100.0 * blended, 0.0, 100.0))


def _norm(value: float, scale: float) -> float:
    if not np.isfinite(value):
        return 1.0
    return float(np.clip(abs(value) / scale, 0.0, 1.5))


def _pct(current: float, reference: float) -> float:
    if reference <= 1e-6:
        return 0.0
    return 100.0 * (current - reference) / reference


def _rmse_feature(aligned, a_name, b_name, fn) -> float:
    vals = []
    for cur, ref in zip(aligned.current_points, aligned.reference_points):
        if a_name in cur and b_name in cur and a_name in ref and b_name in ref and all(p.get("_valid",True) for p in [cur[a_name],cur[b_name],ref[a_name],ref[b_name]]):
            vals.append(fn(cur[a_name], cur[b_name]) - fn(ref[a_name], ref[b_name]))
    if not vals:
        return float("nan")
    arr = np.array(vals, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean(arr**2)))


def _rmse_knee(aligned, hip, knee, ankle) -> float:
    vals = []
    for cur, ref in zip(aligned.current_points, aligned.reference_points):
        if all(k in cur for k in (hip, knee, ankle)) and all(k in ref for k in (hip, knee, ankle)) and all(cur[k].get("_valid",True) and ref[k].get("_valid",True) for k in (hip,knee,ankle)):
            vals.append(
                knee_angle(cur[hip], cur[knee], cur[ankle])
                - knee_angle(ref[hip], ref[knee], ref[ankle])
            )
    if not vals:
        return float("nan")
    arr = np.array(vals, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    return float(np.sqrt(np.mean(arr**2))) if arr.size else float("nan")


def _hip_rmse(aligned, hip) -> float:
    vals = []
    for cur, ref in zip(aligned.current_points, aligned.reference_points):
        if hip in cur and hip in ref and cur[hip].get("_valid",True) and ref[hip].get("_valid",True):
            dx = cur[hip]["x"] - ref[hip]["x"]
            dy = cur[hip]["y"] - ref[hip]["y"]
            vals.append(np.hypot(dx, dy))
    if not vals:
        return float("nan")
    return float(np.sqrt(np.mean(np.square(vals))))


def _mark_onset(points: list[dict]) -> None:
    """Onset means later reps keep moving further from the reference.

    One repetition that differs, then stabilizes, is reference deviation only.
    """
    if len(points) < 4:
        return
    ref_indexes = [i for i, point in enumerate(points) if point["reference_deviation"] == 0]
    if not ref_indexes:
        return
    start = ref_indexes[0]
    for i in range(start, len(points) - 2):
        first = points[i + 1]["reference_deviation"] - points[i]["reference_deviation"]
        second = points[i + 2]["reference_deviation"] - points[i + 1]["reference_deviation"]
        if first < 8 or second < 4 or points[i + 1]["progressive_drift"] < 8:
            continue
        tail = [point["reference_deviation"] for point in points[i + 2 :]]
        # A dip that recovers is reference deviation. Drift has to still be there at the end.
        if min(tail) >= 12 and tail[-1] + 4 >= tail[0]:
            points[i + 2]["onset"] = True
            break
