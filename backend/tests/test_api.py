from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import accept_if_proposed


def test_health_and_catalog():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["ok"] is True
        assert body["pipeline_version"] == "local-v4"
        assert body["enable_meta_api"] is False
        assert body["ai_provider"] == "local"
        catalog = client.get("/catalog")
        assert catalog.status_code == 200
        ids = [e["id"] for e in catalog.json()["exercises"]]
        assert "barbell_squat" in ids


def test_profile_workout_demo_analysis_loop():
    with TestClient(app) as client:
        profile = client.post(
            "/profiles",
            json={
                "goal": "build_strength",
                "experience": "intermediate",
                "days_per_week": 4,
                "session_duration_minutes": 50,
                "equipment": ["barbell", "dumbbells", "machines"],
                "current_squat_load_kg": 40,
                "limitations": [],
                "display_name": "Test Athlete",
            },
        )
        assert profile.status_code == 200
        plan = client.post("/workouts/generate", json={"focus": "legs"})
        assert plan.status_code == 200
        assert plan.json()["source"] == "local"
        assert plan.json()["status"] == "proposed"
        assert any(e["exercise_id"] == "barbell_squat" for e in plan.json()["exercises"])
        accepted = accept_if_proposed(client, plan.json())

        session = client.post("/sessions", json={"plan_id": accepted["id"]})
        assert session.status_code == 200

        upload = client.post(
            "/videos/upload",
            data={
                "session_id": session.json()["id"],
                "exercise_id": "barbell_squat",
                "load_kg": 40,
                "target_reps": 8,
                "consent": True,
                "demo": True,
            },
        )
        assert upload.status_code == 200
        set_id = upload.json()["id"]

        analysis = None
        for _ in range(40):
            analysis = client.get(f"/analysis/{set_id}")
            if analysis.json()["status"] in {"COMPLETED", "FAILED"}:
                break
            import time

            time.sleep(0.05)
        assert analysis is not None
        body = analysis.json()
        assert body["status"] == "COMPLETED"
        assert body["mode"] == "demo"
        assert body["analysis_version"] == client.get("/health").json()["pipeline_version"]
        assert all("reliability" in rep and "comparison_eligible" in rep for rep in body["reps"])
        assert body["completed_reps"] == 6
        assert body["reference_rep"] is not None
        assert body["sam_available"] is False

        overlay = client.get(f"/analysis/{set_id}/overlay")
        assert overlay.status_code == 200
        assert overlay.json()["frames"]
        assert overlay.json()["sam_status"] in {"skipped_local", "skipped", "unavailable", "blocked"}

        coaching = client.get(f"/coaching/{set_id}")
        assert coaching.status_code == 200
        assert coaching.json()["source"] == "local"
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 409
        assert coaching.json()["actionable"] is False
        assert coaching.json()["is_sample"] is True

        meta = client.get("/meta/status")
        assert meta.json()["live_calls"] == 0
