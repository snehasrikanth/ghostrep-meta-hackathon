"""Repeatable squat benchmark.

Real recordings are scored only when both a video and an annotation exist.
Synthetic landmark checks are reported separately and are not a real-video result.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.movement.pipeline import analyze_pose_sequence
from app.services.movement.synthetic import synthesize_squat_set

ROOT = Path(__file__).resolve().parents[2]
VIDEO_DIR = ROOT / "fixtures" / "videos"
ANN_DIR = ROOT / "fixtures" / "annotations"


def synthetic_check() -> dict:
    frames = synthesize_squat_set(reps=6, drift=True)
    result = analyze_pose_sequence(frames)
    complete = [rep for rep in result["reps"] if rep.is_complete]
    return {
        "kind": "synthetic_landmarks",
        "expected_complete_reps": 6,
        "detected_complete_reps": len(complete),
        "reference_rep": result["reference_rep"],
        "usable": result["quality"]["usable"],
        "pass": len(complete) == 6 and result["reference_rep"] is not None,
    }


def score_reps(expected: list[dict], detected: list) -> dict:
    """Match annotated reps to detected reps in order and report boundary error in seconds."""
    pairs = list(zip(expected, detected))
    errors = {
        key: [abs(getattr(got, f"{key}_seconds") - want[f"{key}_seconds"]) for want, got in pairs]
        for key in ("start", "bottom", "end")
    }
    return {
        "matched": len(pairs),
        "mean_abs_error_s": {key: round(sum(vals) / len(vals), 3) if vals else None for key, vals in errors.items()},
        "max_abs_error_s": {key: round(max(vals), 3) if vals else None for key, vals in errors.items()},
    }


def landmark_check(ann: dict) -> dict:
    path = ROOT / ann["landmarks"]
    if not path.exists():
        return {"id": ann["id"], "status": "missing_landmarks", "path": str(path)}
    raw = json.loads(path.read_text(encoding="utf-8"))
    frames = [
        {"timestamp": f["t"], "landmarks": f["landmarks"], "width": raw.get("width", 720), "height": raw.get("height", 1280)}
        for f in raw["frames"]
    ]
    result = analyze_pose_sequence(frames)
    complete = [rep for rep in result["reps"] if rep.is_complete]
    expected = ann.get("reps") or []
    return {
        "id": ann["id"],
        "kind": "real_landmarks",
        "status": "scored",
        "expected_complete_reps": ann["expected_complete_reps"],
        "detected_complete_reps": len(complete),
        "count_correct": len(complete) == ann["expected_complete_reps"],
        "boundaries": score_reps(expected, complete),
        "reference_rep": result["reference_rep"],
        "usable": result["quality"]["usable"],
    }


def real_checks() -> list[dict]:
    rows = []
    if not ANN_DIR.exists():
        return rows
    for path in sorted(ANN_DIR.glob("*.json")):
        ann = json.loads(path.read_text(encoding="utf-8"))
        if ann.get("kind") == "real_landmarks":
            rows.append(landmark_check(ann))
            continue
        if ann.get("kind") != "real_video":
            continue
        video = VIDEO_DIR / ann["video"]
        if not video.exists():
            rows.append({"id": ann.get("id", path.stem), "status": "missing_video", "video": str(video)})
            continue
        rows.append({"id": ann.get("id", path.stem), "status": "not_run_in_this_command", "note": "Invoke with --run-real after a consented file is present."})
    return rows


def main() -> None:
    synthetic = synthetic_check()
    real = real_checks()
    scored = [row for row in real if row.get("status") == "scored"]
    report = {
        "synthetic": synthetic,
        "real_annotations": real,
        "real_recordings_scored": len(scored),
        "note": (
            f"{len(scored)} annotated real recording(s) scored from saved pose landmarks. "
            "One recording cannot show that the detector generalizes; add more annotated sets."
        ),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
