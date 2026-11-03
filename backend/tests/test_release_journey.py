"""Isolated release journey. Temp DB only; demo fixture video; no live Muse/SAM."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.entities import CoachingDecision, WorkoutExercise
from app.services.meta.muse import MuseProvider
from tests.helpers import accept_if_proposed, upload_recording_fixture


def _wait(client: TestClient, set_id: str) -> dict:
    body = None
    for _ in range(40):
        body = client.get(f"/analysis/{set_id}").json()
        if body["status"] in {"COMPLETED", "FAILED"}:
            break
        time.sleep(0.05)
    assert body is not None
    assert body["status"] == "COMPLETED"
    return body


def _force_action(set_id: str, action: str, **fields) -> None:
    db = SessionLocal()
    try:
        row = db.query(CoachingDecision).filter(CoachingDecision.set_id == set_id).one()
        payload = json.loads(row.payload_json)
        payload.update(fields)
        payload["suggested_action"] = action
        row.proposed_action = action
        row.payload_json = json.dumps(payload)
        db.add(row)
        db.commit()
    finally:
        db.close()


def _squat_targets(plan_id: str) -> dict:
    db = SessionLocal()
    try:
        exercise = (
            db.query(WorkoutExercise)
            .filter(WorkoutExercise.plan_id == plan_id, WorkoutExercise.exercise_id == "barbell_squat")
            .one()
        )
        return {
            "target_reps": exercise.target_reps,
            "rest_seconds": exercise.rest_seconds,
            "suggested_load_kg": exercise.suggested_load_kg,
        }
    finally:
        db.close()


def test_isolated_functional_journey():
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
                "display_name": "Release Journey",
            },
        )
        assert profile.status_code == 200
        edited = client.post(
            "/profiles",
            json={
                **{
                    "goal": "build_strength",
                    "experience": "intermediate",
                    "days_per_week": 4,
                    "session_duration_minutes": 50,
                    "equipment": ["barbell", "dumbbells", "machines", "bench"],
                    "current_squat_load_kg": 42,
                    "limitations": [],
                    "display_name": "Release Journey",
                }
            },
        )
        assert edited.status_code == 200
        assert client.get("/profiles/me").json()["current_squat_load_kg"] == 42
        assert client.get("/sessions/current").json()["session"] is None

        program = client.get("/program", params={"today": "2026-10-30", "weeks": 1}).json()
        assert program["days_per_week"] == 4
        upper = next(
            day
            for week in program["weeks"]
            for day in week["days"]
            if day.get("kind") == "training" and "upper" in str(day.get("workout", {}).get("session_type") or day.get("session_type") or "")
        )
        assert upper.get("is_preview") is True or upper.get("workout", {}).get("is_preview") is True
        assert client.get("/sessions").json()["sessions"] == []

        first = accept_if_proposed(client, client.post("/workouts/generate", json={"focus": "legs"}).json())
        discarded_proposal = client.post("/workouts/generate", json={"focus": "upper"}).json()
        assert discarded_proposal["status"] == "proposed"
        assert discarded_proposal["source"] == "local"
        assert "not Muse Spark" in discarded_proposal["source_label"]
        assert discarded_proposal["exercises"]
        assert discarded_proposal["duration_minutes"]
        assert discarded_proposal["why"]["kind"] == "inputs_used"
        client.post(f"/workouts/{discarded_proposal['id']}/discard")
        assert client.get("/workouts/next").json()["plan"]["id"] == first["id"]

        proposal = client.post("/workouts/generate", json={"focus": "legs"}).json()
        with patch.object(MuseProvider, "generate_workout", side_effect=AssertionError("accept must not generate")):
            accepted = client.post(f"/workouts/{proposal['id']}/accept")
        assert accepted.status_code == 200
        plan = accepted.json()
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        exercise = plan["exercises"][0]["exercise_id"]
        client.post(
            f"/sessions/{session['id']}/sets",
            json={"exercise_id": exercise, "set_index": 1, "completed_reps": 4, "load_kg": 40, "target_reps": plan["exercises"][0]["target_reps"]},
        )
        client.post(
            f"/sessions/{session['id']}/sets",
            json={"exercise_id": exercise, "set_index": 1, "completed_reps": 6, "load_kg": 40, "target_reps": plan["exercises"][0]["target_reps"]},
        )
        sets = client.get(f"/sessions/{session['id']}").json()["sets"]
        manual = next(item for item in sets if item["entry_source"] == "manual")
        assert manual["completed_reps"] == 6

        paused = client.post(f"/sessions/{session['id']}/pause").json()
        assert paused["status"] == "paused"
        refreshed = client.get(f"/sessions/{session['id']}").json()
        assert refreshed["status"] == "paused"
        assert client.post(f"/sessions/{session['id']}/resume").json()["status"] == "active"

        upload = upload_recording_fixture(client, session["id"], target_reps=8, load_kg=40)
        assert upload.status_code == 200
        first_set = upload.json()["id"]
        analysis = _wait(client, first_set)
        overlay = client.get(f"/analysis/{first_set}/overlay").json()
        assert overlay["silhouette_label"]
        assert overlay["silhouette_source"]
        timestamps = [frame["t"] for frame in overlay["frames"][:3]]
        assert timestamps == timestamps  # same timestamp is stable for replay
        coaching = client.get(f"/coaching/{first_set}").json()
        assert coaching["user_decision"] == "pending"
        assert coaching["planned_set_reps"] == 8
        before = _squat_targets(plan["id"])
        _force_action(first_set, "REDUCE_REPS", suggested_reps=max(1, before["target_reps"] - 2))
        accepted_coach = client.post(f"/coaching/{first_set}/decision", json={"decision": "accepted"})
        assert accepted_coach.status_code == 200
        assert accepted_coach.json()["applied_change"]["applied"] is True
        assert _squat_targets(plan["id"])["target_reps"] == max(1, before["target_reps"] - 2)
        workout = client.get(f"/workouts/{plan['id']}").json()
        squat = next(ex for ex in workout["exercises"] if ex["exercise_id"] == "barbell_squat")
        assert squat["target_reps"] == max(1, before["target_reps"] - 2)

        second_upload = upload_recording_fixture(client, session["id"], target_reps=8)
        second_set = second_upload.json()["id"]
        _wait(client, second_set)
        after_accept = _squat_targets(plan["id"])
        _force_action(second_set, "REDUCE_REPS", suggested_reps=1)
        rejected = client.post(f"/coaching/{second_set}/decision", json={"decision": "rejected"})
        assert rejected.status_code == 200
        assert rejected.json()["applied_change"]["applied"] is False
        assert _squat_targets(plan["id"]) == after_accept

        done = client.post(f"/sessions/{session['id']}/complete")
        assert done.status_code == 200
        completed = [row for row in client.get("/sessions").json()["sessions"] if row["status"] == "completed"]
        assert len(completed) == 1
        assert completed[0]["summary"]["completed_sets"] == done.json()["summary"]["completed_sets"]
        assert client.get("/sessions/current").json()["session"] is None


def test_invalid_upload_and_closed_workout_failures():
    with TestClient(app) as client:
        client.post(
            "/profiles",
            json={
                "goal": "build_strength",
                "experience": "intermediate",
                "days_per_week": 4,
                "session_duration_minutes": 50,
                "equipment": ["barbell"],
                "current_squat_load_kg": 40,
                "limitations": [],
                "display_name": "Safety",
            },
        )
        plan = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        no_consent = client.post(
            "/videos/upload",
            data={"session_id": session["id"], "exercise_id": "barbell_squat", "consent": False, "demo": True},
        )
        assert no_consent.status_code == 400
        bad_file = client.post(
            "/videos/upload",
            data={"session_id": session["id"], "exercise_id": "barbell_squat", "consent": True},
            files={"file": ("notes.txt", b"not a video", "text/plain")},
        )
        assert bad_file.status_code == 400
        client.post(
            f"/sessions/{session['id']}/sets",
            json={"exercise_id": plan["exercises"][0]["exercise_id"], "set_index": 1, "completed_reps": 5},
        )
        client.post(f"/sessions/{session['id']}/complete")
        late = client.post(
            f"/sessions/{session['id']}/sets",
            json={"exercise_id": plan["exercises"][0]["exercise_id"], "set_index": 2, "completed_reps": 5},
        )
        assert late.status_code == 409
        second = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        other = client.post("/sessions", json={"plan_id": second["id"]}).json()
        client.post(
            f"/sessions/{other['id']}/sets",
            json={"exercise_id": second["exercises"][0]["exercise_id"], "set_index": 1, "completed_reps": 5},
        )
        third = client.post("/workouts/generate", json={}).json()
        blocked = client.post("/sessions", json={"plan_id": third["id"]})
        assert blocked.status_code == 409
