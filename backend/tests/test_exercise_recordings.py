"""Real video storage/replay with no pose, coaching, or segmentation calls."""

import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db, job_runner, settings_dep
from app.config import Settings
from app.database import Base, migrate_training_columns
from app.main import app
from app.services.video.jobs import VideoJobRunner
from app.services.workout.history import is_personalization_set
from app.models.entities import RecordedSet


@pytest.fixture
def recording_client(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "data", enable_meta_api=True,
                        model_api_key="offline-only", workout_provider="meta_live",
                        coaching_provider="meta_live", segmentation_provider="meta_live")
    settings.ensure_dirs()
    engine = create_engine(f"sqlite:///{tmp_path / 'recordings.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, autoflush=False)
    monkeypatch.setattr("app.services.video.jobs.SessionLocal", sessions)

    def forbidden(*args, **kwargs):
        raise AssertionError("Recording-only videos must never enter the analysis pipeline")

    monkeypatch.setattr("app.services.video.jobs.PoseExtractor", forbidden)
    monkeypatch.setattr("app.services.video.jobs.MuseProvider", forbidden)
    monkeypatch.setattr("app.services.video.jobs.SamProvider", forbidden)

    def db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[job_runner] = lambda: VideoJobRunner(settings)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def clip(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/FFprobe is required for recording storage")
    path = tmp_path / "set.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=15:duration=4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
    return path.read_bytes()


def upload(client, session_id, clip, exercise="push_up", **extra):
    return client.post("/videos/upload", data={"session_id": session_id, "exercise_id": exercise,
                       "set_index": 1, "consent": True, **extra},
                       files={"file": ("set.mp4", clip, "video/mp4")})


def saved(client, recording_id):
    for _ in range(200):
        result = client.get(f"/recordings/{recording_id}")
        assert result.status_code == 200
        row = result.json()
        if row["processing_status"] in {"SAVED", "FAILED"}:
            assert row["processing_status"] == "SAVED", row
            return row
        time.sleep(0.02)
    pytest.fail("Video did not finish saving")


def test_failed_recording_can_be_explicitly_replaced_on_same_set(recording_client, clip):
    client = recording_client
    session_id = client.post("/sessions", json={}).json()["id"]
    failed = upload(client, session_id, b"invalid video", analyze=False, completed_reps=8,
                    target_reps=10, load_kg=20, reported_rpe=8)
    assert failed.status_code == 200
    recording_id = failed.json()["id"]
    for _ in range(200):
        row = client.get(f"/recordings/{recording_id}").json()
        if row["processing_status"] == "FAILED":
            break
        time.sleep(.02)
    assert row["processing_status"] == "FAILED"
    assert row["has_analysis"] is False
    assert upload(client, session_id, clip, analyze=False).status_code == 409
    assert upload(client, session_id, clip, analyze=False,
                  replace_failed_recording_id="another-set").status_code == 409
    replacement = upload(client, session_id, clip, analyze=False,
                         replace_failed_recording_id=recording_id)
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["id"] == recording_id
    result = saved(client, recording_id)
    assert result["target_reps"] == 10
    assert result["completed_reps"] == 8
    assert result["load_kg"] == 20
    assert result["reported_rpe"] == 8
    assert result["has_video"]
    session = client.get(f"/sessions/{session_id}").json()
    assert len(session["sets"]) == 1
    assert session["summary"]["total_reps"] == 8
    assert upload(client, session_id, clip, analyze=False,
                  replace_failed_recording_id=recording_id).status_code == 409


def test_retry_cannot_target_a_different_workout(recording_client, clip):
    client = recording_client
    first = client.post("/sessions", json={}).json()["id"]
    # No matching record exists: an arbitrary retry ID cannot bypass ownership/session guards.
    result = upload(client, first, clip, analyze=False, replace_failed_recording_id="foreign-recording")
    assert result.status_code == 409
    assert client.get(f"/sessions/{first}").json()["sets"] == []


@pytest.mark.parametrize("exercise,count", [("push_up", 12), ("goblet_squat", 8), ("plank", 60), ("barbell_squat", 5)])
def test_every_exercise_can_save_and_replay_without_ai(recording_client, clip, exercise, count):
    client = recording_client
    session = client.post("/sessions", json={}).json()
    response = upload(client, session["id"], clip, exercise, analyze=False, completed_reps=count, load_kg=10)
    assert response.status_code == 200, response.text
    recording = saved(client, response.json()["id"])
    assert recording["exercise_id"] == exercise
    assert recording["analysis_requested"] is False
    assert recording["has_analysis"] is False
    assert recording["has_video"] is True
    assert recording["completed_reps"] == count
    assert is_personalization_set(RecordedSet(entry_source="video", processing_status="SAVED", completed_reps=count))
    assert client.get(f"/media/{recording['id']}").headers["content-type"] == "video/mp4"
    assert client.get(f"/analysis/{recording['id']}").status_code == 404
    summary = client.get(f"/sessions/{session['id']}").json()["summary"]
    assert summary["completed_sets"] == 1
    assert summary["timed_seconds"] == (count if exercise == "plank" else 0)
    assert summary["total_reps"] == (0 if exercise == "plank" else count)
    assert client.post(f"/sessions/{session['id']}/complete").status_code == 200


@pytest.mark.parametrize("log_first", [True, False])
def test_attaching_video_and_logging_use_the_same_set(recording_client, clip, log_first):
    client = recording_client
    session_id = client.post("/sessions", json={}).json()["id"]
    payload = {"exercise_id": "push_up", "set_index": 1, "completed_reps": 12}
    if log_first:
        manual = client.post(f"/sessions/{session_id}/sets", json=payload).json()
    uploaded = upload(client, session_id, clip)
    assert uploaded.status_code == 200
    recording = saved(client, uploaded.json()["id"])
    if not log_first:
        assert client.get(f"/sessions/{session_id}").json()["summary"]["completed_sets"] == 0
        assert client.post(f"/sessions/{session_id}/complete").status_code == 400
        client.post("/profiles", json={"goal": "build_strength", "experience": "beginner", "days_per_week": 3, "session_duration_minutes": 30, "equipment": ["bodyweight"]})
        proposal = client.post("/workouts/generate", json={}).json()
        assert client.post(f"/workouts/{proposal['id']}/accept").status_code == 409
        manual = client.post(f"/sessions/{session_id}/sets", json=payload).json()
    assert manual["id"] == recording["id"]
    for reps in [10, 11]:
        response = client.post(f"/sessions/{session_id}/sets", json={**payload, "completed_reps": reps})
        assert response.status_code == 200
    session = client.get(f"/sessions/{session_id}").json()
    assert len(session["sets"]) == 1
    assert session["summary"]["completed_sets"] == 1
    assert session["summary"]["total_reps"] == 11
    assert client.get(f"/media/{recording['id']}").status_code == 200
    assert upload(client, session_id, clip).status_code == 409
    assert client.delete(f"/recordings/{recording['id']}").status_code == 200
    assert client.get(f"/media/{recording['id']}").status_code == 404
    after = client.get(f"/sessions/{session_id}").json()
    assert after["summary"] == session["summary"]
    assert saved(client, recording["id"])["has_video"] is False
    replacement = upload(client, session_id, clip)
    assert replacement.status_code == 200
    assert replacement.json()["id"] == recording["id"]
    saved(client, recording["id"])


def test_recording_ownership_and_unsupported_analysis(recording_client, clip):
    client = recording_client
    session = client.post("/sessions", json={}).json()
    for extra in [{"analyze": True}, {"approve_meta_spend": True}, {"approve_sam_spend": True}]:
        assert upload(client, session["id"], clip, **extra).status_code == 400
    assert upload(client, session["id"], clip, "unknown_lift").status_code == 400
    recording = saved(client, upload(client, session["id"], clip).json()["id"])
    with TestClient(app) as other:
        assert other.get(f"/recordings/{recording['id']}").status_code == 404
        assert other.get(f"/media/{recording['id']}").status_code == 404
        assert other.delete(f"/recordings/{recording['id']}").status_code == 404
        assert upload(other, session["id"], clip).status_code == 404


def test_existing_recording_schema_migrates_without_losing_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE recorded_sets (id TEXT PRIMARY KEY, original_filename TEXT, entry_source TEXT DEFAULT 'video')")
        connection.exec_driver_sql("INSERT INTO recorded_sets (id, original_filename) VALUES ('old', 'set.mp4')")
    migrate_training_columns(engine)
    migrate_training_columns(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT id, original_filename, analysis_requested FROM recorded_sets").fetchall() == [("old", "set.mp4", 1)]


def test_saved_replays_survive_raw_upload_retention(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    raw, replay = tmp_path / "original.mp4", tmp_path / "replay.mp4"
    raw.write_bytes(b"original")
    replay.write_bytes(b"replay")
    with sessionmaker(engine)() as db:
        rec = RecordedSet(user_id="test", session_id="test", entry_source="video", analysis_requested=False,
                          processing_status="SAVED", video_path=str(raw), normalized_path=str(replay),
                          created_at=datetime.now(timezone.utc) - timedelta(days=7))
        db.add(rec)
        db.commit()
        VideoJobRunner(Settings(retention_hours=24)).cleanup_expired(db)
        assert not raw.exists()
        assert replay.exists()
        assert rec.normalized_path == str(replay)
