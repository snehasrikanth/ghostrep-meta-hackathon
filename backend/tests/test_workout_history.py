"""Workout-generation history context. Isolated temp DB only."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.entities import RecordedSet
from app.services.workout.history import recent_training_context
from tests.helpers import accept_if_proposed


def _profile(client: TestClient):
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
            "display_name": "History Athlete",
        },
    )
    assert saved.status_code == 200


def _user_id(client: TestClient) -> str:
    return client.get("/profiles/me").json()["user_id"]


def test_completed_records_are_included_and_previews_samples_failed_are_excluded():
    with TestClient(app) as client:
        _profile(client)
        plan = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        squat = next(ex for ex in plan["exercises"] if ex["exercise_id"] == "barbell_squat")
        client.post(
            f"/sessions/{session['id']}/sets",
            json={
                "exercise_id": squat["exercise_id"],
                "set_index": 1,
                "completed_reps": 5,
                "load_kg": 40,
                "target_reps": squat["target_reps"],
            },
        )
        plank = next((ex for ex in plan["exercises"] if ex["exercise_id"] == "plank"), None)
        if plank:
            client.post(
                f"/sessions/{session['id']}/sets",
                json={
                    "exercise_id": "plank",
                    "set_index": 1,
                    "completed_reps": 40,
                    "target_reps": plank["target_reps"],
                },
            )
        client.post(
            f"/sessions/{session['id']}/sets",
            json={"exercise_id": squat["exercise_id"], "set_index": 2, "completed_reps": 0, "target_reps": squat["target_reps"]},
        )
        done = client.post(f"/sessions/{session['id']}/complete")
        assert done.status_code == 200, done.text

        user_id = _user_id(client)
        with SessionLocal() as db:
            db.add(
                RecordedSet(
                    session_id=session["id"],
                    user_id=user_id,
                    exercise_id="barbell_squat",
                    entry_source="demo",
                    set_index=3,
                    completed_reps=6,
                    processing_status="COMPLETED",
                    original_filename="DEMO_FIXTURE",
                )
            )
            db.add(
                RecordedSet(
                    session_id=session["id"],
                    user_id=user_id,
                    exercise_id="barbell_squat",
                    entry_source="video",
                    set_index=9,
                    completed_reps=None,
                    processing_status="FAILED",
                    original_filename="clip.mp4",
                )
            )
            db.commit()
            context = recent_training_context(db, user_id)

        assert len(context) == 1
        exercises = {item["exercise_id"]: item for item in context[0]["exercises"]}
        squat_row = exercises["barbell_squat"]
        assert squat_row["completed_reps"] == [5]
        assert squat_row["target_reps"] == [squat["target_reps"]]
        assert squat_row["best_load_kg"] == 40
        assert squat_row["sets"] == 1
        if plank:
            hold = exercises["plank"]
            assert hold["timed_seconds"] == [40]
            assert hold["completed_reps"] == []
            assert "best_load_kg" not in hold
        blob = str(context)
        assert "DEMO_FIXTURE" not in blob
        assert "clip.mp4" not in blob
        assert ".mp4" not in blob


def test_unknown_load_is_omitted_and_sets_are_not_double_counted():
    with TestClient(app) as client:
        _profile(client)
        plan = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        squat = next(ex for ex in plan["exercises"] if ex["exercise_id"] == "barbell_squat")
        client.post(
            f"/sessions/{session['id']}/sets",
            json={
                "exercise_id": squat["exercise_id"],
                "set_index": 1,
                "completed_reps": 6,
                "target_reps": 8,
            },
        )
        client.post(
            f"/sessions/{session['id']}/sets",
            json={
                "exercise_id": squat["exercise_id"],
                "set_index": 1,
                "completed_reps": 6,
                "target_reps": 8,
            },
        )
        client.post(f"/sessions/{session['id']}/complete")
        with SessionLocal() as db:
            context = recent_training_context(db, _user_id(client))
        squat_row = context[0]["exercises"][0]
        assert squat_row["sets"] == 1
        assert squat_row["completed_reps"] == [6]
        assert squat_row["target_reps"] == [8]
        assert "best_load_kg" not in squat_row


def test_abandoned_and_other_users_are_excluded():
    with TestClient(app) as alice:
        _profile(alice)
        plan = accept_if_proposed(alice, alice.post("/workouts/generate", json={}).json())
        session = alice.post("/sessions", json={"plan_id": plan["id"]}).json()
        alice.post(
            f"/sessions/{session['id']}/sets",
            json={"exercise_id": plan["exercises"][0]["exercise_id"], "set_index": 1, "completed_reps": 5, "load_kg": 50},
        )
        alice.post(f"/sessions/{session['id']}/abandon")
        alice_id = _user_id(alice)
        with SessionLocal() as db:
            assert recent_training_context(db, alice_id) == []
        with TestClient(app) as bob:
            _profile(bob)
            with SessionLocal() as db:
                assert recent_training_context(db, _user_id(bob)) == []
                assert recent_training_context(db, alice_id) == []
