from __future__ import annotations

from app.services.movement.alignment import align_rep, phase_progress
from app.services.movement.baseline import select_reference_rep
from app.services.movement.drift import compute_drift
from app.services.movement.geometry import POSE_EDGES
from app.services.movement.quality import assess_camera_quality
from app.services.movement.reliability import geometry_frames, reliable_side, invalid_intervals
from app.services.movement.reps import detect_squat_reps


def analyze_pose_sequence(frames: list[dict]) -> dict:
    frames = geometry_frames(frames)
    quality = assess_camera_quality(frames)
    side, checks = reliable_side(frames)
    intervals = invalid_intervals(frames, checks)
    fraction = sum(row["valid"] for row in checks) / max(len(checks),1)
    quality.update(side=side, reliable_fraction=fraction, unreliable_intervals=intervals, comparison_usable=False)
    frames = [{**f, "landmarks": {name:{**point,"_valid":checks[i]["valid"]} for name,point in f["landmarks"].items()}} for i,f in enumerate(frames)]
    quality["score"] = round(min(quality["score"], .95 * fraction),3)
    if intervals:
        quality["issues"].append({"code":"tracking_intervals", "severity":"warn",
            "message":"Some intervals have missing, discontinuous or inconsistent landmarks. Those intervals cannot support movement comparisons."})
    if not quality["usable"]:
        return {
            "quality": quality,
            "reps": [],
            "reference_rep": None,
            "drift": [],
            "overlay": {"frames": [], "skeleton_edges": POSE_EDGES},
            "usable": False,
        }

    reps, side = detect_squat_reps(frames)
    complete = [rep for rep in reps if rep.is_complete and rep.metrics.get("comparison_eligible", False)]
    reference = select_reference_rep(complete) if fraction >= .85 else None
    drift = compute_drift(frames, complete, reference, side) if reference else []
    overlay_frames = _overlay_frames(frames, reps, reference)
    quality["comparison_usable"] = reference is not None
    quality["unreliable_rep_ids"] = [r.rep_id for r in reps if not r.metrics.get("comparison_eligible")]
    quality["detected_reps"] = sum(r.is_complete for r in reps)
    quality["partial_movements"] = sum(not r.is_complete for r in reps)
    if reference is None:
        quality["issues"].append({"code":"no_reliable_reference", "severity":"warn", "message":"No reliable reference available. Review the recording before changing targets."})
    return {
        "quality": quality,
        "side": side,
        "reps": reps,
        "reference_rep": reference.rep_id if reference else None,
        "drift": drift,
        "overlay": {
            "frames": overlay_frames,
            "skeleton_edges": POSE_EDGES,
            "silhouette_source": "unavailable",
        },
        "usable": True,
    }


def _overlay_frames(frames: list[dict], reps, reference) -> list[dict]:
    aligned_by_rep = {}
    if reference:
        for rep in reps:
            if not rep.metrics.get("comparison_eligible", False):
                continue
            aligned_by_rep[rep.rep_id] = align_rep(frames, rep, reference)
    out = []
    for i, frame in enumerate(frames):
        active = next((r for r in reps if r.start_idx <= i <= r.end_idx), None)
        ref_lms = None
        phase = "idle"
        progress = 0.0
        if active and reference and active.rep_id in aligned_by_rep:
            phase, progress = phase_progress(i, active)
            aligned = aligned_by_rep[active.rep_id]
            local = i - active.start_idx
            if 0 <= local < len(aligned.reference_points):
                ref_lms = _to_list(aligned.reference_points[local])
        out.append(
            {
                "t": frame["timestamp"],
                "active_rep": active.rep_id if active else None,
                "phase": phase,
                "phase_progress": progress,
                "current": _to_list(frame["landmarks"]),
                "reference": ref_lms,
                "silhouette": None,
            }
        )
    return out


def _to_list(landmarks: dict[str, dict]) -> list[dict]:
    return [
        {
            "name": name,
            "x": lm["x"],
            "y": lm["y"],
            "visibility": lm.get("visibility", 0.0),
        }
        for name, lm in landmarks.items()
    ]
