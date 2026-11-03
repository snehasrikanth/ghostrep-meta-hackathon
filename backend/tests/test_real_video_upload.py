"""Fresh consented recording through real FFmpeg + pose. Isolated temp DB; no Muse/SAM."""

from __future__ import annotations

import os
import shutil
import time
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.entities import RecordedSet
from app.services.video.ffmpeg import inspect_video
from tests.helpers import generate_active_plan

REPO_ROOT = Path(__file__).resolve().parents[2]
_clip = os.environ.get("GHOSTREP_TEST_VIDEO")
CONSENTED_CLIP = Path(_clip).expanduser() if _clip else None


def _pose_ready() -> bool:
    try:
        import mediapipe  # noqa: F401
        import cv2  # noqa: F401
    except ImportError:
        return False
    model = REPO_ROOT / "backend/models/pose_landmarker_lite.task"
    return model.exists() and model.stat().st_size > 1000


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg/FFprobe not installed")
@pytest.mark.skipif(not CONSENTED_CLIP or not CONSENTED_CLIP.is_file(), reason="optional GHOSTREP_TEST_VIDEO is not provided")
@pytest.mark.skipif(not _pose_ready(), reason="MediaPipe pose model is not available")
def test_consented_real_video_normalizes_and_poses(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Real-video validation cannot use synthetic landmarks or model transport")
    monkeypatch.setattr("app.services.video.jobs.synthesize_squat_set", forbidden)
    monkeypatch.setattr("app.services.meta.transport.OpenAIMetaTransport.__init__", forbidden)
    assert CONSENTED_CLIP is not None
    payload = CONSENTED_CLIP.read_bytes()
    assert len(payload) > 100_000
    started = time.perf_counter()
    with TestClient(app) as client:
        profile = client.post(
            "/profiles",
            json={
                "goal": "build_strength",
                "experience": "intermediate",
                "days_per_week": 4,
                "session_duration_minutes": 50,
                "equipment": ["barbell", "dumbbells", "machines", "bench"],
                "current_squat_load_kg": 40,
                "limitations": [],
                "display_name": "Isolated Real Video",
            },
        )
        assert profile.status_code == 200, profile.text
        plan = generate_active_plan(client)
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        uploaded = client.post(
            "/videos/upload",
            data={
                "session_id": session["id"],
                "exercise_id": "barbell_squat",
                "target_reps": "6",
                "load_kg": "40",
                "set_index": "1",
                "consent": "true",
                "demo": "false",
            },
            files={"file": ("isolated-consented-squat.mp4", payload, "video/mp4")},
        )
        assert uploaded.status_code == 200, uploaded.text
        rec = uploaded.json()
        assert rec["entry_source"] == "video"
        assert rec["is_sample"] is False
        body = None
        deadline = time.time() + 180
        while time.time() < deadline:
            body = client.get(f"/analysis/{rec['id']}").json()
            if body["status"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.5)
        elapsed = time.perf_counter() - started
        assert body is not None
        (tmp_path / "real-video-timing.txt").write_text(
            f"status={body['status']} elapsed_s={elapsed:.1f} message={body.get('message')}\n",
            encoding="utf-8",
        )
        assert body["status"] == "COMPLETED", body
        with SessionLocal() as db:
            stored = db.get(RecordedSet, rec["id"])
            normalized = inspect_video(Path(stored.normalized_path))
            assert normalized["codec"] == "h264"
            assert normalized["duration"] == pytest.approx(inspect_video(CONSENTED_CLIP)["duration"], abs=0.15)
            assert Path(stored.normalized_path) != CONSENTED_CLIP
        overlay = client.get(f"/analysis/{rec['id']}/overlay").json()
        assert overlay["silhouette_source"] not in {"sam"}
        coaching = client.get(f"/coaching/{rec['id']}")
        if coaching.status_code == 200:
            assert coaching.json()["source"] == "local"
            assert "not Muse" in (coaching.json().get("source_label") or "")
        else:
            assert body["status"] == "FAILED"
        if body["status"] == "COMPLETED":
            frames = overlay.get("frames") or []
            pose_frames = [frame for frame in frames if frame.get("current")]
            print(
                f"REAL_VIDEO status={body['status']} elapsed_s={elapsed:.1f} "
                f"reps={body.get('completed_reps')} duration={body.get('duration_seconds')} "
                f"pose={body.get('pose_available')} quality={body.get('tracking_quality')} "
                f"reference={body.get('reference_rep')} overlay_frames={len(frames)} "
                f"posed={len(pose_frames)} message={body.get('message')}"
            )
            assert body.get("mode") == "real"
            assert body.get("pose_available") is True or pose_frames, body
            if pose_frames:
                stamps = [frame["t"] for frame in pose_frames[:5]]
                assert stamps == sorted(stamps)
                assert pose_frames[0]["t"] == pose_frames[0]["t"]
                assert all(0 <= f["t"] <= body["duration_seconds"] for f in pose_frames)
                assert all(a["t"] <= b["t"] for a,b in zip(frames, frames[1:]))
            report = {
                "clip": CONSENTED_CLIP.stem, "status": body["status"], "processing_seconds": round(elapsed, 2),
                "duration_seconds": body["duration_seconds"], "normalized_media": normalized,
                "detected_reps": body["completed_reps"], "ground_truth_rep_count": "not supplied",
                "independent_boundary_accuracy": "not established; refined annotations used pose trajectories",
                "reference_rep": body["reference_rep"], "tracking": body["tracking_quality"],
                "overlay_frames": len(frames), "posed_frames": len(pose_frames),
                "alignment_checks": "sorted timestamps inside normalized duration; visual playback not checked here",
                "muse_calls": 0, "sam_calls": 0, "synthetic_landmarks": False,
            }
            (tmp_path / "real-video-result.json").write_text(json.dumps(report, indent=2))
        history = client.get("/sessions").json()["sessions"]
        matching = [row for sess in history for row in sess["sets"] if row["id"] == rec["id"]]
        assert matching
        assert matching[0]["entry_source"] == "video"
        print(f"REAL_VIDEO status={body['status']} elapsed_s={elapsed:.1f} reps={body.get('completed_reps')} message={body.get('message')}")
