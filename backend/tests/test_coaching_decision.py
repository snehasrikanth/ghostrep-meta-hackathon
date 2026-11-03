from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.entities import CoachingDecision, RecordedSet, WorkoutExercise
from tests.helpers import accept_if_proposed, upload_recording_fixture
from app.services.coaching.compatibility import recommendation_context


def _wait_analysis(client: TestClient, set_id: str) -> dict:
    body = None
    for _ in range(40):
        body = client.get(f"/analysis/{set_id}").json()
        if body["status"] in {"COMPLETED", "FAILED"}:
            break
        time.sleep(0.05)
    assert body is not None
    assert body["status"] == "COMPLETED"
    return body


def _start_recording_fixture(
    *,
    target_reps: int = 8,
    load_kg: float | None = 40,
    workout_reps: int | None = None,
    workout_rest: int | None = None,
    workout_load: float | None | object = ...,
) -> tuple[TestClient, str, str, str]:
    client = TestClient(app)
    client.__enter__()
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
        },
    )
    assert profile.status_code == 200
    plan = client.post("/workouts/generate", json={})
    assert plan.status_code == 200
    plan_id = accept_if_proposed(client, plan.json())["id"]
    if workout_reps is not None or workout_rest is not None or workout_load is not ...:
        _set_squat_targets(
            plan_id,
            target_reps=workout_reps,
            rest_seconds=workout_rest,
            suggested_load_kg=None if workout_load is ... else workout_load,
            replace_load=workout_load is not ...,
        )
    session = client.post("/sessions", json={"plan_id": plan_id})
    assert session.status_code == 200
    upload = upload_recording_fixture(client, session.json()["id"], target_reps=target_reps, **({"load_kg": load_kg} if load_kg is not None else {}))
    assert upload.status_code == 200
    set_id = upload.json()["id"]
    _wait_analysis(client, set_id)
    return client, plan_id, session.json()["id"], set_id


def _set_squat_targets(
    plan_id: str,
    *,
    target_reps: int | None = None,
    rest_seconds: int | None = None,
    suggested_load_kg: float | None = None,
    replace_load: bool = False,
) -> None:
    db = SessionLocal()
    try:
        exercise = (
            db.query(WorkoutExercise)
            .filter(WorkoutExercise.plan_id == plan_id, WorkoutExercise.exercise_id == "barbell_squat")
            .one()
        )
        if target_reps is not None:
            exercise.target_reps = target_reps
        if rest_seconds is not None:
            exercise.rest_seconds = rest_seconds
        if replace_load:
            exercise.suggested_load_kg = suggested_load_kg
        db.add(exercise)
        db.commit()
    finally:
        db.close()


def _set_completed_reps(set_id: str, completed: int) -> None:
    db = SessionLocal()
    try:
        rec = db.get(RecordedSet, set_id)
        assert rec is not None
        rec.completed_reps = completed
        # Build an isolated fixture with these completed values; this is not an
        # edit to a real analysis after a recommendation was reviewed.
        payload = json.loads(rec.coaching.payload_json)
        payload["recommendation_context"] = recommendation_context(rec)
        rec.coaching.payload_json = json.dumps(payload)
        db.add(rec)
        db.commit()
    finally:
        db.close()


def _force_action(set_id: str, action: str, **fields) -> None:
    db = SessionLocal()
    try:
        row = db.query(CoachingDecision).filter(CoachingDecision.set_id == set_id).one()
        payload = json.loads(row.payload_json)
        payload.update(fields)
        payload["suggested_action"] = action
        from app.services.coaching.interpretation import canonicalize,record_context
        payload = canonicalize(payload, record_context(db.get(RecordedSet,set_id)))
        row.proposed_action = payload["suggested_action"]
        row.summary = payload["summary"]
        row.reason = payload["reason"]
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


def test_accepting_reduce_reps_updates_the_open_workout_and_cannot_apply_twice():
    client, plan_id, _session_id, set_id = _start_recording_fixture()
    try:
        before = _squat_targets(plan_id)
        _force_action(set_id, "REDUCE_REPS", suggested_reps=max(1, before["target_reps"] - 2))
        analysis = client.get(f"/analysis/{set_id}").json()
        assert analysis["plan_id"] == plan_id
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 200
        body = decision.json()
        assert body["user_decision"] == "accepted"
        assert body["applied_change"]["applied"] is True
        assert body["applied_change"]["after"]["target_reps"] == max(1, before["target_reps"] - 2)
        assert _squat_targets(plan_id)["target_reps"] == body["applied_change"]["after"]["target_reps"]
        again = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert again.status_code == 409
        assert _squat_targets(plan_id)["target_reps"] == body["applied_change"]["after"]["target_reps"]
        workout = client.get(f"/workouts/{plan_id}").json()
        squat = next(ex for ex in workout["exercises"] if ex["exercise_id"] == "barbell_squat")
        assert squat["target_reps"] == body["applied_change"]["after"]["target_reps"]
    finally:
        client.__exit__(None, None, None)


def test_rejecting_keeps_original_targets():
    client, plan_id, _session_id, set_id = _start_recording_fixture()
    try:
        before = _squat_targets(plan_id)
        _force_action(set_id, "REDUCE_REPS", suggested_reps=1)
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "rejected"})
        assert decision.status_code == 200
        assert decision.json()["user_decision"] == "rejected"
        assert decision.json()["applied_change"]["applied"] is False
        assert _squat_targets(plan_id) == before
    finally:
        client.__exit__(None, None, None)


def test_accepting_on_a_completed_workout_does_not_rewrite_targets():
    client, plan_id, session_id, set_id = _start_recording_fixture()
    try:
        before = _squat_targets(plan_id)
        done = client.post(f"/sessions/{session_id}/complete")
        assert done.status_code == 200
        _force_action(set_id, "REDUCE_REPS", suggested_reps=1)
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 200
        assert decision.json()["user_decision"] == "accepted"
        assert decision.json()["applied_change"]["applied"] is False
        assert decision.json()["applied_change"]["reason"] == "workout_closed"
        assert _squat_targets(plan_id) == before
    finally:
        client.__exit__(None, None, None)


def test_keep_plan_accept_does_not_change_targets():
    client, plan_id, _session_id, set_id = _start_recording_fixture()
    try:
        before = _squat_targets(plan_id)
        _force_action(set_id, "KEEP_PLAN", suggested_reps=before["target_reps"] + 2)
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 200
        assert decision.json()["applied_change"]["applied"] is False
        assert decision.json()["applied_change"]["reason"] == "no_target_change"
        assert _squat_targets(plan_id) == before
    finally:
        client.__exit__(None, None, None)


def test_keep_plan_planned_six_completed_eight_preserves_six():
    client, plan_id, _session_id, set_id = _start_recording_fixture(
        target_reps=6,
        load_kg=40,
        workout_reps=6,
        workout_rest=150,
        workout_load=40,
    )
    try:
        _set_completed_reps(set_id, 8)
        _force_action(set_id, "KEEP_PLAN", suggested_reps=8, current_reps=8)
        coaching = client.get(f"/coaching/{set_id}").json()
        assert coaching["planned_set_reps"] == 6
        assert coaching["completed_reps"] == 8
        assert coaching["workout_reps"] == 6
        assert coaching["suggested_action"] == "KEEP_PLAN"
        assert coaching["suggested_reps"] == 6
        assert coaching["current_reps"] == 6
        assert coaching["suggested_rest_seconds"] == 150
        assert coaching["workout_rest_seconds"] == 150
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 200
        assert decision.json()["applied_change"]["reason"] == "no_target_change"
        assert _squat_targets(plan_id)["target_reps"] == 6
        assert _squat_targets(plan_id)["rest_seconds"] == 150
        workout = client.get(f"/workouts/{plan_id}").json()
        squat = next(ex for ex in workout["exercises"] if ex["exercise_id"] == "barbell_squat")
        assert squat["target_reps"] == 6
    finally:
        client.__exit__(None, None, None)


def test_keep_plan_planned_eight_completed_six_preserves_eight():
    client, plan_id, _session_id, set_id = _start_recording_fixture(
        target_reps=8,
        load_kg=40,
        workout_reps=8,
        workout_rest=150,
        workout_load=40,
    )
    try:
        _set_completed_reps(set_id, 6)
        _force_action(set_id, "KEEP_PLAN", suggested_reps=6, current_reps=6)
        coaching = client.get(f"/coaching/{set_id}").json()
        assert coaching["planned_set_reps"] == 8
        assert coaching["completed_reps"] == 6
        assert coaching["workout_reps"] == 8
        assert coaching["suggested_reps"] == 8
        assert coaching["current_reps"] == 8
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 200
        assert _squat_targets(plan_id)["target_reps"] == 8
    finally:
        client.__exit__(None, None, None)


def test_keep_plan_unknown_load_stays_unknown():
    client, plan_id, _session_id, set_id = _start_recording_fixture(
        target_reps=6,
        load_kg=None,
        workout_reps=6,
        workout_rest=150,
        workout_load=None,
    )
    try:
        _force_action(set_id, "KEEP_PLAN", suggested_load_kg=40, current_load_kg=40)
        coaching = client.get(f"/coaching/{set_id}").json()
        assert coaching["planned_set_load_kg"] is None
        assert coaching["workout_load_kg"] is None
        assert coaching["current_load_kg"] is None
        assert coaching["suggested_load_kg"] is None
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 200
        assert _squat_targets(plan_id)["suggested_load_kg"] is None
    finally:
        client.__exit__(None, None, None)


def test_keep_plan_set_snapshot_eight_does_not_override_workout_six():
    client, plan_id, _session_id, set_id = _start_recording_fixture(
        target_reps=8,
        load_kg=None,
        workout_reps=6,
        workout_rest=150,
        workout_load=40,
    )
    try:
        db = SessionLocal()
        try:
            stored = json.loads(
                db.query(CoachingDecision).filter(CoachingDecision.set_id == set_id).one().payload_json
            )
        finally:
            db.close()
        assert stored["current_reps"] == 6
        assert stored["current_rest_seconds"] == 150
        assert stored["current_load_kg"] == 40
        assert stored.get("planned_set_reps") == 8
        _set_completed_reps(set_id, 5)
        _force_action(set_id, "KEEP_PLAN", suggested_reps=8, current_reps=8, current_rest_seconds=120, suggested_rest_seconds=120)
        coaching = client.get(f"/coaching/{set_id}").json()
        assert coaching["planned_set_reps"] == 8
        assert coaching["completed_reps"] == 5
        assert coaching["workout_reps"] == 6
        assert coaching["suggested_reps"] == 6
        assert coaching["suggested_rest_seconds"] == 150
        assert coaching["suggested_load_kg"] == 40
        assert coaching["planned_set_load_kg"] is None
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 200
        assert _squat_targets(plan_id) == {"target_reps": 6, "rest_seconds": 150, "suggested_load_kg": 40}
    finally:
        client.__exit__(None, None, None)


def test_accepting_on_an_abandoned_workout_does_not_rewrite_targets():
    client, plan_id, session_id, set_id = _start_recording_fixture()
    try:
        before = _squat_targets(plan_id)
        done = client.post(f"/sessions/{session_id}/abandon")
        assert done.status_code == 200
        _force_action(set_id, "REDUCE_REPS", suggested_reps=1)
        decision = client.post(f"/coaching/{set_id}/decision", json={"decision": "accepted"})
        assert decision.status_code == 200
        assert decision.json()["applied_change"]["applied"] is False
        assert decision.json()["applied_change"]["reason"] == "workout_closed"
        assert _squat_targets(plan_id) == before
    finally:
        client.__exit__(None, None, None)
