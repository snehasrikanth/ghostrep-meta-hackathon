"""Route-level rotation checks. Disposable history and mocked saved metadata only."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.entities import RecordedSet, User, WorkoutPlan, WorkoutSession
from app.services.meta.muse import MuseProvider
from tests.test_lower_body_focus import lower_profile
from tests.test_release_saved import _write_live_week


MANUAL = {"entry_source": "manual", "processing_status": "LOGGED", "completed_reps": 5}
VIDEO = {"entry_source": "video", "processing_status": "COMPLETED", "completed_reps": 5}
SAMPLE = {"entry_source": "demo", "processing_status": "COMPLETED", "completed_reps": 6}
LEGACY = {**VIDEO, "original_filename": "DEMO_FIXTURE"}


@pytest.mark.parametrize("route", ["generate", "import-saved"])
@pytest.mark.parametrize("status,planned,owner,sets,expected", [
    pytest.param("completed", True, True, [SAMPLE], 0, id="sample-only"),
    pytest.param("completed", True, True, [LEGACY], 0, id="legacy-sample"),
    pytest.param("completed", True, True, [], 0, id="empty"),
    pytest.param("completed", True, True, [SAMPLE, LEGACY, MANUAL, VIDEO], 1, id="mixed-counts-once"),
    pytest.param("completed", True, True, [MANUAL], 1, id="manual"),
    pytest.param("completed", True, True, [VIDEO], 1, id="analyzed-video"),
    pytest.param("completed", True, True, [{**VIDEO, "processing_status": "SAVED"}], 1, id="saved-video"),
    pytest.param("active", True, True, [MANUAL], 0, id="active"),
    pytest.param("paused", True, True, [MANUAL], 0, id="paused"),
    pytest.param("abandoned", True, True, [MANUAL], 0, id="abandoned"),
    pytest.param("completed", False, True, [MANUAL], 0, id="plan-free"),
    pytest.param("completed", True, False, [MANUAL], 0, id="another-user"),
    pytest.param("completed", True, True, [{**MANUAL, "completed_reps": 0}], 0, id="zero-reps"),
    pytest.param("completed", True, True, [{**VIDEO, "processing_status": "FAILED"}], 0, id="failed-video"),
    pytest.param("completed", True, True, [{**VIDEO, "processing_status": "UPLOADED"}], 0, id="pending-video"),
])
def test_rotation_requires_owned_completed_planned_performed_training(route, status, planned, owner, sets, expected):
    with TestClient(app) as client:
        profile = client.post("/profiles", json=lower_profile()).json()
        baseline = client.post("/workouts/generate", json={}).json()
        with SessionLocal() as db:
            assert json.loads(db.get(WorkoutPlan, baseline["id"]).context_json)["inputs"]["session_index"] == 0
            user_id = profile["user_id"]
            plan_id = baseline["id"] if planned else None
            if not owner:
                outsider = User(display_name="Fictional other owner")
                db.add(outsider); db.flush(); user_id = outsider.id
                outside_plan = WorkoutPlan(user_id=user_id, name="Other owner's plan", source="local", duration_minutes=45)
                db.add(outside_plan); db.flush(); plan_id = outside_plan.id
            session = WorkoutSession(user_id=user_id, plan_id=plan_id, status=status)
            db.add(session); db.flush(); sid = session.id
            for index, fields in enumerate(sets, 1):
                db.add(RecordedSet(session_id=sid, user_id=user_id, set_index=index,
                    exercise_id="barbell_squat", load_kg=40, **fields))
            db.commit()
        if owner and (not sets or all(item in [SAMPLE, LEGACY] for item in sets)):
            totals = client.get("/sessions/" + sid).json()["summary"]
            assert totals["completed_sets"] == totals["total_reps"] == totals["volume_kg"] == 0
        if route == "import-saved":
            _write_live_week()  # Protocol-shaped fixture, no inference.
            with patch.object(MuseProvider, "generate_workout", side_effect=AssertionError("Import must not call Muse")):
                result = client.post("/workouts/import-saved")
        else:
            result = client.post("/workouts/generate", json={})
        assert result.status_code == 200, result.text
        with SessionLocal() as db:
            proposal = db.get(WorkoutPlan, result.json()["id"])
            assert json.loads(proposal.context_json)["inputs"]["session_index"] == expected


@pytest.mark.parametrize("route", ["generate", "import-saved"])
def test_two_performed_sessions_advance_twice_not_once_per_set(route):
    with TestClient(app) as client:
        user_id = client.post("/profiles", json=lower_profile()).json()["user_id"]
        plan = client.post("/workouts/generate", json={}).json()
        with SessionLocal() as db:
            for fields in [MANUAL, VIDEO]:
                session = WorkoutSession(user_id=user_id, plan_id=plan["id"], status="completed")
                db.add(session); db.flush()
                for index in range(1, 4):
                    db.add(RecordedSet(session_id=session.id, user_id=user_id,
                        exercise_id="barbell_squat", set_index=index, **fields))
            db.commit()
        if route == "import-saved":
            _write_live_week()
        result = client.post("/workouts/" + route, json={})
        assert result.status_code == 200, result.text
        with SessionLocal() as db:
            assert json.loads(db.get(WorkoutPlan, result.json()["id"]).context_json)["inputs"]["session_index"] == 2
