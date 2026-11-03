"""Proposal lifecycle. Isolated temp DB; no Muse/SAM calls."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.meta.muse import MuseProvider
from tests.helpers import accept_if_proposed


def _profile(client: TestClient, name="Lifter"):
    saved = client.post(
        "/profiles",
        json={
            "goal": "build_strength",
            "experience": "intermediate",
            "days_per_week": 4,
            "session_duration_minutes": 50,
            "equipment": ["barbell", "dumbbells", "machines"],
            "current_squat_load_kg": 40,
            "limitations": [],
            "display_name": name,
        },
    )
    assert saved.status_code == 200, saved.text


def test_generating_does_not_replace_the_active_plan():
    with TestClient(app) as client:
        _profile(client)
        first = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        proposal = client.post("/workouts/generate", json={}).json()
        assert proposal["status"] == "proposed"
        assert proposal["id"] != first["id"]
        assert client.get(f"/workouts/{first['id']}").json()["status"] == "active"
        assert client.get("/workouts/next").json()["plan"]["id"] == first["id"]
        assert client.get("/workouts/proposal").json()["plan"]["id"] == proposal["id"]
        program = client.get("/program", params={"today": "2026-10-26"}).json()
        next_day = next(day for week in program["weeks"] for day in week["days"] if day.get("is_next"))
        assert next_day["plan_id"] == first["id"]
        assert proposal["why"]["kind"] == "inputs_used"
        assert proposal["why"]["model_explanation_present"] is False
        labels = {item["field"] for item in proposal["why"]["inputs"]}
        assert "goal" in labels
        assert "equipment" in labels
        assert client.post("/sessions", json={"plan_id": proposal["id"]}).status_code == 409


def test_accept_persists_without_another_model_call_and_is_idempotent():
    with TestClient(app) as client:
        _profile(client)
        first = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        proposal = client.post("/workouts/generate", json={}).json()
        with patch.object(MuseProvider, "generate_workout", side_effect=AssertionError("accept must not call Muse")):
            accepted = client.post(f"/workouts/{proposal['id']}/accept")
        assert accepted.status_code == 200, accepted.text
        body = accepted.json()
        assert body["id"] == proposal["id"]
        assert body["status"] == "active"
        assert body["source"] == proposal["source"]
        assert client.get(f"/workouts/{first['id']}").json()["status"] == "replaced"
        again = client.post(f"/workouts/{proposal['id']}/accept")
        assert again.status_code == 200
        assert again.json()["id"] == proposal["id"]
        listed = client.get("/workouts").json()["plans"]
        assert sum(1 for plan in listed if plan["id"] == proposal["id"]) == 1


def test_discard_preserves_the_current_workout():
    with TestClient(app) as client:
        _profile(client)
        first = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        proposal = client.post("/workouts/generate", json={}).json()
        discarded = client.post(f"/workouts/{proposal['id']}/discard")
        assert discarded.status_code == 200
        assert discarded.json()["discarded"] is True
        assert client.get("/workouts/next").json()["plan"]["id"] == first["id"]
        assert client.get(f"/workouts/{first['id']}").json()["status"] == "active"
        assert client.get("/workouts/proposal").json()["plan"] is None
        assert client.get(f"/workouts/{proposal['id']}").json()["status"] == "discarded"


def test_open_workout_blocks_accept_and_does_not_replace_the_active_plan():
    with TestClient(app) as client:
        _profile(client)
        first = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        session = client.post("/sessions", json={"plan_id": first["id"]}).json()
        client.post(
            f"/sessions/{session['id']}/sets",
            json={"exercise_id": first["exercises"][0]["exercise_id"], "set_index": 1, "completed_reps": 5},
        )
        proposal = client.post("/workouts/generate", json={}).json()
        blocked = client.post(f"/workouts/{proposal['id']}/accept")
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert detail["open_session_id"] == session["id"]
        assert detail["open_plan_id"] == first["id"]
        assert client.get(f"/workouts/{first['id']}").json()["status"] == "active"
        assert client.get(f"/workouts/{proposal['id']}").json()["status"] == "proposed"


def test_proposal_ownership_is_isolated():
    with TestClient(app) as alice:
        _profile(alice, "Alice")
        proposal = alice.post("/workouts/generate", json={}).json()
        with TestClient(app) as bob:
            _profile(bob, "Bob")
            assert bob.get(f"/workouts/{proposal['id']}").status_code == 404
            assert bob.post(f"/workouts/{proposal['id']}/accept").status_code == 404
            assert bob.post(f"/workouts/{proposal['id']}/discard").status_code == 404
            assert bob.get("/workouts/proposal").json()["plan"] is None


def test_generating_again_discards_the_previous_proposal_only():
    with TestClient(app) as client:
        _profile(client)
        first = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        older = client.post("/workouts/generate", json={}).json()
        newer = client.post("/workouts/generate", json={}).json()
        assert client.get(f"/workouts/{older['id']}").json()["status"] == "discarded"
        assert newer["status"] == "proposed"
        assert client.get("/workouts/next").json()["plan"]["id"] == first["id"]
        assert client.get("/workouts/proposal").json()["plan"]["id"] == newer["id"]


def test_local_proposal_is_not_labeled_as_live_muse():
    with TestClient(app) as client:
        _profile(client)
        proposal = client.post("/workouts/generate", json={}).json()
        assert proposal["source"] == "local"
        assert "not Muse Spark" in proposal["source_label"]
        assert "live" not in proposal["source_label"].lower()
