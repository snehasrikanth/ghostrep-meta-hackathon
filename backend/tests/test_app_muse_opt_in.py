"""Real app endpoints, fake transport: opting in is required for every paid path."""

import json
import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.config import get_settings
from app.database import Base
from app.main import app
from app.services.meta.errors import TransientMetaError
from app.services.meta.gateway import approval_hint
from tests.helpers import accept_if_proposed
from tests.test_meta_offline import FakeTransport, _week
from tests.test_meta_offline import _rectangle
from tests.test_release_saved import _profile


@pytest.fixture
def live_app(monkeypatch, tmp_path):
    settings = get_settings()
    for field, value in {
        "enable_meta_api": True,
        "workout_provider": "meta_live",
        "coaching_provider": "meta_live",
        "model_api_key": "offline-app-test",
        "meta_max_calls_per_session": 100,
        "meta_max_retries": 2,
    }.items():
        monkeypatch.setattr(settings, field, value)
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, autoflush=False)
    monkeypatch.setattr("app.services.video.jobs.SessionLocal", sessions)

    def isolated_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    try:
        yield settings
    finally:
        app.dependency_overrides.pop(get_db)
        engine.dispose()


def test_live_enabled_app_stays_local_without_opt_in(live_app):
    with TestClient(app) as client, patch(
        "app.services.meta.muse.OpenAIMetaTransport", side_effect=AssertionError("No paid request")
    ):
        _profile(client)
        result = client.post("/workouts/generate", json={})
        assert result.status_code == 200
        assert result.json()["source"] == "local"


def test_opted_in_workout_uses_live_provider_and_keeps_key_on_server(live_app):
    transport = FakeTransport(content=json.dumps(_week()))
    with TestClient(app) as client, patch("app.services.meta.muse.OpenAIMetaTransport", return_value=transport):
        _profile(client)
        response = client.post("/workouts/generate", json={"approve_meta_spend": True})
        assert response.status_code == 200, response.text
        assert response.json()["source"] == "muse_spark"
        assert response.json()["status"] == "proposed"
        assert len(transport.calls) == 1
        assert live_app.model_api_key not in response.text
        assert approval_hint(live_app, "workout_generation") not in response.text


def test_opted_in_workout_does_not_retry_or_disguise_live_failure(live_app):
    transport = FakeTransport(fail=TransientMetaError("timeout", "offline timeout"))
    with TestClient(app) as client, patch("app.services.meta.muse.OpenAIMetaTransport", return_value=transport):
        _profile(client)
        response = client.post("/workouts/generate", json={"approve_meta_spend": True})
        assert response.status_code == 503
        assert len(transport.calls) == 1
        assert client.get("/workouts/proposal").json()["plan"] is None


def test_opt_in_refused_when_muse_is_disabled(live_app, monkeypatch):
    monkeypatch.setattr(live_app, "enable_meta_api", False)
    with TestClient(app) as client, patch(
        "app.services.meta.muse.OpenAIMetaTransport", side_effect=AssertionError("No paid request")
    ):
        _profile(client)
        response = client.post("/workouts/generate", json={"approve_meta_spend": True})
        assert response.status_code == 409
        assert client.get("/workouts/proposal").json()["plan"] is None


def test_real_upload_passes_only_coaching_approval_to_worker(live_app):
    with TestClient(app) as client, patch("app.services.video.jobs.VideoJobRunner.start") as start:
        _profile(client)
        plan = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        response = client.post("/videos/upload", data={
            "session_id": session["id"], "consent": "true", "approve_meta_spend": "true",
        }, files={"file": ("offline-upload.mp4", b"not processed by the mocked worker", "video/mp4")})
        assert response.status_code == 200, response.text
        assert start.call_args.kwargs["approval_token"] == approval_hint(live_app, "coaching")
        assert start.call_args.kwargs["approval_token"] != approval_hint(live_app, "sam_segmentation")
        assert live_app.model_api_key not in response.text


def test_sample_never_spends_even_if_muse_was_checked(live_app):
    with TestClient(app) as client, patch("app.services.video.jobs.VideoJobRunner.start") as start:
        _profile(client)
        session = client.post("/sessions", json={}).json()
        response = client.post("/videos/upload", data={
            "session_id": session["id"], "consent": "true", "demo": "true", "approve_meta_spend": "true",
        })
        assert response.status_code == 400
        start.assert_not_called()


@pytest.mark.parametrize("approved,failed", [(False, False), (True, False), (True, True)])
def test_upload_worker_persists_the_selected_coach_without_changing_targets(live_app, approved, failed):
    from app.services.movement.synthetic import synthesize_squat_set

    with TestClient(app) as client:
        _profile(client)
        plan = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        squat = next(ex for ex in plan["exercises"] if ex["exercise_id"] == "barbell_squat")
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        raw = {
            "summary": "Keep the current workout targets.", "observations": [], "uncertainties": [],
            "suggested_action": "KEEP_PLAN", "explanation": "No measured change is required.",
            "suggested_reps": squat["target_reps"], "suggested_rest_seconds": squat["rest_seconds"],
            "suggested_load_kg": squat["suggested_load_kg"],
        }
        transport = FakeTransport(content=json.dumps(raw), fail=TransientMetaError("timeout", "offline timeout") if failed else None)
        with patch("app.services.video.jobs.inspect_video", return_value={"duration": 16}), patch(
            "app.services.video.jobs.normalize_video", return_value={"duration": 16}
        ), patch("app.services.video.jobs.PoseExtractor.extract", return_value=synthesize_squat_set(reps=6)), patch(
            "app.services.meta.muse.OpenAIMetaTransport", return_value=transport
        ):
            response = client.post("/videos/upload", data={
                "session_id": session["id"], "consent": "true", "approve_meta_spend": str(approved).lower(),
            }, files={"file": ("offline-video.mp4", b"offline test; pose and ffmpeg mocked", "video/mp4")})
            assert response.status_code == 200, response.text
            set_id = response.json()["id"]
            for _ in range(100):
                analysis = client.get(f"/analysis/{set_id}").json()
                if analysis["status"] in {"COMPLETED", "FAILED"}:
                    break
                time.sleep(0.05)
            assert analysis["status"] == "COMPLETED", analysis
            coaching = client.get(f"/coaching/{set_id}").json()
            assert coaching["source"] == ("muse_spark" if approved and not failed else "local")
            if failed:
                assert any("Personalized coaching was unavailable" in text for text in coaching["uncertainties"])
            assert coaching["user_decision"] == "pending"
            assert coaching["requires_confirmation"] is True
            assert len(transport.calls) == int(approved)
            saved = client.get(f"/workouts/{plan['id']}").json()
            assert saved["exercises"] == plan["exercises"]


@pytest.mark.parametrize("sam_enabled,coach_enabled,outcome", [
    (False, False, "local"), (False, True, "local"), (True, False, "ok"), (True, True, "ok"),
    (True, False, "over_budget"), (True, False, "failed"),
])
def test_sam_and_coaching_are_independent_and_silhouettes_persist(live_app, monkeypatch, sam_enabled, coach_enabled, outcome):
    from app.services.movement.synthetic import synthesize_squat_set
    from app.services.meta.sam_parse import mask_wire, stream_events
    from app.services.meta.sam import SamProvider

    monkeypatch.setattr(live_app, "segmentation_provider", "meta_live")
    # The app must force person-only even if another operator setting includes barbell.
    monkeypatch.setattr(live_app, "sam_include_barbell", True)
    poses = synthesize_squat_set(reps=6)
    duration = len(poses) / 15
    media = {"duration": duration, "fps": 60, "width": 40, "height": 30, "codec": "h264"}
    events = stream_events("\n".join(mask_wire(
        frame=i * 4, object_id=0, box=(18, 3, 26, 28), source=(40, 30),
        payload=_rectangle(), raster=(6, 8), confidence=0.99,
    ) for i in range(len(poses))) + "\n")
    sam_transport = FakeTransport(events=events, fail=TransientMetaError("timeout", "offline timeout") if outcome == "failed" else None)

    def prepared(src, dest):
        dest.write_bytes(b"offline SAM upload copy")
        return media

    with TestClient(app) as client:
        _profile(client)
        plan = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        squat = next(ex for ex in plan["exercises"] if ex["exercise_id"] == "barbell_squat")
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        coach_transport = FakeTransport(content=json.dumps({
            "summary": "Keep current targets.", "observations": [], "uncertainties": [],
            "suggested_action": "KEEP_PLAN", "explanation": "No supported change.",
            "suggested_reps": squat["target_reps"], "suggested_rest_seconds": squat["rest_seconds"],
            "suggested_load_kg": squat["suggested_load_kg"],
        }))
        with patch("app.services.video.jobs.inspect_video", return_value=media), patch(
            "app.services.video.jobs.normalize_video", return_value=media
        ), patch("app.services.video.jobs.prepare_sam_video", side_effect=prepared) as prepare, patch(
            "app.services.video.jobs.PoseExtractor.extract", return_value=poses
        ), patch("app.services.video.jobs.SamProvider", side_effect=lambda settings,gateway: SamProvider(settings,gateway,transport=sam_transport)), patch(
            "app.services.meta.muse.OpenAIMetaTransport", return_value=coach_transport
        ):
            data = {"session_id": session["id"], "consent": "true",
                    "approve_sam_spend": str(sam_enabled).lower(), "approve_meta_spend": str(coach_enabled).lower()}
            if sam_enabled:
                data["sam_spend_limit_usd"] = "0.0001" if outcome == "over_budget" else "1.0"
            response = client.post("/videos/upload", data=data, files={"file": ("offline-squat.mp4", b"offline video", "video/mp4")})
            assert response.status_code == 200, response.text
            set_id = response.json()["id"]
            for _ in range(200):
                analysis = client.get(f"/analysis/{set_id}").json()
                if analysis["status"] in {"COMPLETED", "FAILED"}:
                    break
                time.sleep(0.05)
            assert analysis["status"] == "COMPLETED", analysis
            overlay = client.get(f"/analysis/{set_id}/overlay").json()
            assert overlay["silhouette_source"] == ("sam" if outcome == "ok" else "unavailable")
            assert client.get(f"/coaching/{set_id}").json()["source"] == ("muse_spark" if coach_enabled else "local")
            assert len(coach_transport.calls) == int(coach_enabled)
            should_call = sam_enabled and outcome != "over_budget"
            assert sum(call[0] == "responses" for call in sam_transport.calls) == int(should_call)
            assert sam_transport.deleted == (["file-offline"] if should_call else [])
            assert prepare.call_count == int(sam_enabled)
            assert not (live_app.derived_dir / f"{set_id}-sam-upload.mp4").exists()
            if outcome == "ok":
                assert any(frame.get("silhouette") for frame in overlay["frames"])
                assert any(frame.get("reference_silhouette") for frame in overlay["frames"])
                with contextmanager(app.dependency_overrides[get_db])() as db:
                    from app.models.entities import RecordedSet
                    segmentation = db.get(RecordedSet, set_id).analysis.segmentation_json
                    assert json.loads(segmentation)["source"] == "sam"
                    assert json.loads(segmentation)["tracks"][0]["frames"][0]["polygon"]
                    assert "file-offline" not in segmentation
            if outcome == "over_budget":
                assert analysis["sam_status"] == "blocked"


@pytest.mark.parametrize("demo,limit", [(False, None), (True, "0.1")])
def test_sam_requires_budget_and_a_real_recording(live_app, monkeypatch, demo, limit):
    monkeypatch.setattr(live_app, "segmentation_provider", "meta_live")
    with TestClient(app) as client, patch("app.services.video.jobs.VideoJobRunner.start") as start:
        _profile(client)
        session = client.post("/sessions", json={}).json()
        data = {"session_id": session["id"], "consent": "true", "approve_sam_spend": "true", "demo": str(demo).lower()}
        if limit:
            data["sam_spend_limit_usd"] = limit
        result = client.post("/videos/upload", data=data)
        assert result.status_code == 400
        start.assert_not_called()


def test_app_status_explains_the_paid_call_limit(live_app, monkeypatch):
    monkeypatch.setattr(live_app, "meta_max_calls_per_session", 0)
    with TestClient(app) as client:
        status = client.get("/meta/status").json()
        assert status["call_limit_reached"] is True
        assert status["remaining_calls"] == 0
        assert "development limit" in status["call_limit_reason"]
