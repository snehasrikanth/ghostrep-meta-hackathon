import os
import pytest
import copy
import json
import math
from pathlib import Path

from app.services.movement.alignment import align_rep, phase_progress
from app.services.movement.baseline import select_reference_rep
from app.services.movement.drift import compute_drift
from app.services.movement.pipeline import analyze_pose_sequence
from app.services.movement.quality import assess_camera_quality
from app.services.movement.reps import detect_squat_reps
from app.services.movement.synthetic import synthesize_squat_set


def test_detects_six_complete_squats():
    frames = synthesize_squat_set(reps=6, drift=True)
    reps, side = detect_squat_reps(frames)
    assert side == "right"
    assert len(reps) == 6
    assert all(r.is_complete for r in reps)
    assert all(r.descent_seconds > 0.3 for r in reps)
    assert all(r.ascent_seconds > 0.3 for r in reps)


def test_incomplete_motion_not_counted():
    frames = synthesize_squat_set(reps=1, drift=False)[:12]
    reps, _ = detect_squat_reps(frames)
    assert not any(rep.is_complete for rep in reps)


def test_reference_is_not_automatically_first_or_deepest():
    frames = synthesize_squat_set(reps=6, drift=True)
    result = analyze_pose_sequence(frames)
    reps = result["reps"]
    reference = next(r for r in reps if r.rep_id == result["reference_rep"])
    deepest = max(reps, key=lambda r: r.metrics["relative_depth"])
    assert reference.rep_id != 6
    assert result["reference_rep"] is not None
    # Drifted later reps are deeper/slower; selector must not chase maximum depth.
    assert reference.rep_id != deepest.rep_id or reference.rep_id <= 3
    selected = select_reference_rep(reps)
    assert selected is not None
    assert selected.rep_id == result["reference_rep"]


def test_alignment_preserves_phase_order():
    frames = synthesize_squat_set(reps=2, drift=False)
    reps, _ = detect_squat_reps(frames)
    aligned = align_rep(frames, reps[1], reps[0])
    assert aligned.phase[0] == "descent"
    assert aligned.phase[-1] == "ascent"
    mid = reps[1].bottom_idx - reps[1].start_idx
    assert aligned.phase[mid] in {"descent", "ascent"}
    phase, progress = phase_progress(reps[0].start_idx, reps[0])
    assert phase == "descent" and progress == 0.0


def test_drift_increases_on_later_reps():
    frames = synthesize_squat_set(reps=6, drift=True)
    result = analyze_pose_sequence(frames)
    drift = result["drift"]
    first = next(d for d in drift if d["rep_id"] == result["reference_rep"])
    last = drift[-1]
    assert first["similarity"] == 100
    assert last["similarity"] < first["similarity"]
    assert last["ascent_duration_difference_percent"] > 0
    assert compute_drift(frames, result["reps"], result["reps"][result["reference_rep"] - 1], "right")


def test_camera_quality_accepts_synthetic_side_view():
    frames = synthesize_squat_set(reps=3, drift=False)
    quality = assess_camera_quality(frames)
    assert quality["usable"] is True
    assert quality["side"] == "right"


def test_slow_reps_still_count_and_record_bottom_pause():
    frames = synthesize_squat_set(reps=2, drift=False)
    for frame in frames:
        frame["timestamp"] *= 8
    reps, _ = detect_squat_reps(frames)
    complete = [rep for rep in reps if rep.is_complete]
    assert len(complete) == 2
    assert complete[0].metrics["bottom_pause_seconds"] > 0.2


def test_overlay_does_not_claim_sam():
    frames = synthesize_squat_set(reps=2, drift=False)
    result = analyze_pose_sequence(frames)
    assert result["overlay"]["silhouette_source"] == "unavailable"
    assert result["overlay"]["frames"]
    assert result["overlay"]["frames"][0]["silhouette"] is None


def test_camera_quality_blocks_empty():
    quality = assess_camera_quality([])
    assert quality["usable"] is False


def test_setup_bob_before_squats_is_not_a_rep():
    squats = synthesize_squat_set(reps=3, drift=False)
    pose = copy.deepcopy(squats[-1])
    setup = []
    t = 0.0
    dt = 1 / 15
    for _ in range(int(6 / dt)):
        frame = copy.deepcopy(pose)
        frame["timestamp"] = t
        bob = 0.008 * math.sin(t * 2.5)
        for name in ("right_hip", "left_hip"):
            frame["landmarks"][name]["y"] = pose["landmarks"][name]["y"] + bob
        setup.append(frame)
        t += dt
    for frame in squats:
        frame["timestamp"] += t
    reps, _ = detect_squat_reps(setup + squats)
    complete = [rep for rep in reps if rep.is_complete]
    assert len(complete) == 3
    assert complete[0].start_seconds >= 5
    assert all(rep.metrics["duration_seconds"] < 5 for rep in complete)


_landmark_path = os.environ.get("GHOSTREP_TEST_LANDMARKS")
_annotation_path = os.environ.get("GHOSTREP_TEST_ANNOTATION")


@pytest.mark.skipif(not _landmark_path or not _annotation_path, reason="optional private landmark benchmark is not provided")
def test_private_landmark_benchmark():
    ann = json.loads(Path(_annotation_path).expanduser().read_text())
    raw = json.loads(Path(_landmark_path).expanduser().read_text())
    frames = [
        {"timestamp": frame["t"], "landmarks": frame["landmarks"], "width": 720, "height": 1280}
        for frame in raw["frames"]
    ]
    reps, _ = detect_squat_reps(frames)
    complete = [rep for rep in reps if rep.is_complete]
    assert len(complete) == ann["expected_complete_reps"] == 8
    assert complete[0].start_seconds > 8
    assert all(rep.metrics["duration_seconds"] < 4 for rep in complete)
    for expected, got in zip(ann["reps"], complete, strict=True):
        assert abs(got.start_seconds - expected["start_seconds"]) <= 0.75
        assert abs(got.bottom_seconds - expected["bottom_seconds"]) <= 0.55
        assert abs(got.end_seconds - expected["end_seconds"]) <= 0.6
    result = analyze_pose_sequence(frames)
    assert all(frame["active_rep"] is None for frame in result["overlay"]["frames"] if frame["t"] < 8)
    reference = next(point for point in result["drift"] if point["rep_id"] == result["reference_rep"])
    assert reference["reference_deviation"] == 0
    assert any(
        abs(point["progressive_drift"] - point["reference_deviation"]) > 1
        for point in result["drift"]
        if point["rep_id"] != result["reference_rep"]
    )
