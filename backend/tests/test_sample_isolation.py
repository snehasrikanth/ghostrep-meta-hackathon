"""Synthetic samples are replayable but never performed training."""
import json
import time
import pytest
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models.entities import CoachingVersion, RecordedSet
from app.services.coaching.compatibility import recommendation_context
from app.services.workout.history import recent_training_context
from tests.helpers import accept_if_proposed, recording_bytes
from tests.test_lower_body_focus import lower_profile


def athlete(client):
    client.post("/profiles", json=lower_profile())
    plan = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
    exercises = [{k: ex[k] for k in ["exercise_id", "sets", "target_reps", "rest_seconds", "suggested_load_kg", "notes"]} for ex in plan["exercises"]]
    for ex in exercises:
        if ex["exercise_id"] == "barbell_squat":
            ex["target_reps"] = 10
    changed = client.patch("/workouts/" + plan["id"], json={"exercises": exercises})
    assert changed.status_code == 200
    return changed.json(), client.post("/sessions", json={"plan_id": plan["id"]}).json()


def sample(client, session_id=None, target_reps=6):
    data = {"demo": True, "consent": True, "exercise_id": "barbell_squat", "target_reps": target_reps, "load_kg": 40}
    if session_id:
        data["session_id"] = session_id
    response = client.post("/videos/upload", data=data)
    assert response.status_code == 200, response.text
    rec = response.json()
    for _ in range(200):
        analysis = client.get("/analysis/" + rec["id"]).json()
        if analysis["status"] in {"COMPLETED", "FAILED"}:
            assert analysis["status"] == "COMPLETED"
            return rec
        time.sleep(.02)
    pytest.fail("Sample did not complete")


def test_exact_sample_reproduction_cannot_touch_or_complete_open_workout():
    with TestClient(app) as client:
        plan, session = athlete(client)
        before = client.get("/workouts/" + plan["id"]).json()["exercises"]
        client.post("/sessions/" + session["id"] + "/pause")
        rec = sample(client, session["id"], target_reps=10)
        assert rec["session_id"] != session["id"]
        analysis = client.get("/analysis/" + rec["id"]).json()
        assert analysis["mode"] == "demo" and analysis["plan_id"] is None
        assert client.get("/analysis/" + rec["id"] + "/overlay").json()["frames"]
        coaching = client.get("/coaching/" + rec["id"]).json()
        assert coaching["is_sample"] and not coaching["actionable"]
        assert coaching["suggested_reps"] == 8  # The original 10 → 8 example stays simulated.
        for endpoint in ["decision", "import-saved"]:
            reply = client.post("/coaching/" + rec["id"] + "/" + endpoint, json={"decision": "accepted"})
            assert reply.status_code == 409 and "read-only" in reply.text
        current = client.get("/sessions/" + session["id"]).json()
        assert current["status"] == "paused" and current["sets"] == []
        assert current["summary"]["completed_sets"] == current["summary"]["total_reps"] == 0
        for sid in [session["id"], rec["session_id"]]:
            assert client.post("/sessions/" + sid + "/complete").status_code == 400
        assert client.get("/workouts/" + plan["id"]).json()["exercises"] == before
        with SessionLocal() as db:
            stored = db.get(RecordedSet, rec["id"])
            assert recent_training_context(db, stored.user_id) == []
            assert stored.coaching.user_decision == "pending"


@pytest.mark.parametrize("legacy", [False, True])
def test_legacy_and_mixed_samples_cannot_bypass_versions_logging_or_totals(legacy):
    with TestClient(app) as client:
        _, session = athlete(client)
        rec = sample(client)
        with SessionLocal() as db:
            row = db.get(RecordedSet, rec["id"])
            row.session_id = session["id"]  # Previously stored mixed-session shape.
            if legacy:
                row.entry_source = "video"
            db.flush()
            body = json.loads(row.coaching.payload_json)
            body["recommendation_context"] = recommendation_context(row)
            version = CoachingVersion(set_id=row.id, source="muse_spark", source_label="Mocked protocol",
                artifact_id="sample-bypass", verified=True, proposed_action=body["suggested_action"],
                summary=body["summary"], reason=body["reason"], payload_json=json.dumps(body),
                context_json=json.dumps(body["recommendation_context"]))
            db.add(version); db.commit(); version_id = version.id
        coaching = client.get("/coaching/" + rec["id"]).json()
        assert not coaching["actionable"] and not coaching["stored_versions"][0]["can_activate"]
        assert client.post("/coaching/" + rec["id"] + "/versions/" + version_id + "/activate",
            json={"recommendation_id": coaching["id"], "expected_revision": coaching["revision"]}).status_code == 409
        assert client.post("/coaching/" + rec["id"] + "/decision", json={"decision": "accepted"}).status_code == 409
        assert client.post("/sessions/" + session["id"] + "/complete").status_code == 400
        log = client.post("/sessions/" + session["id"] + "/sets",
            json={"exercise_id": "barbell_squat", "set_index": 1, "completed_reps": 5, "load_kg": 40})
        assert log.status_code == 200 and log.json()["id"] != rec["id"]
        mixed = client.get("/sessions/" + session["id"]).json()
        assert len(mixed["sets"]) == 2
        assert next(item for item in mixed["sets"] if item["id"] == rec["id"])["is_sample"]
        assert mixed["summary"]["completed_sets"] == 1 and mixed["summary"]["total_reps"] == 5
        assert mixed["summary"]["volume_kg"] == 200
        assert client.post("/sessions/" + session["id"] + "/complete").status_code == 200
        with SessionLocal() as db:
            context = recent_training_context(db, db.get(RecordedSet, rec["id"]).user_id)
            assert len(context) == 1 and context[0]["exercises"][0]["completed_reps"] == [5]


def test_sample_flag_cannot_launder_synthetic_measurements_into_video():
    with TestClient(app) as client:
        _, session = athlete(client)
        response = client.post("/videos/upload",
            data={"session_id": session["id"], "exercise_id": "barbell_squat", "consent": True, "demo": True},
            files={"file": ("color.mp4", recording_bytes(), "video/mp4")})
        assert response.status_code == 400
        assert client.get("/sessions/" + session["id"]).json()["sets"] == []
