from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.benchmark import real_checks
from app.database import Base, close_stale_sessions, migrate_training_columns
from app.main import app
from app.models.entities import RecordedSet, User, WorkoutPlan, WorkoutSession
from app.services.workout.catalog import CATALOG
from app.services.workout.local_planner import estimate_minutes, generate_local_plan, resolve_split
from tests.helpers import accept_if_proposed


def _assessment(level="intermediate", goal="increase_strength", days=4, minutes=50, equipment=None, split=None):
    return {
        "identity": {"display_name": "Lifter", "adult_confirmed": True, "preferred_weight_unit": "kg"},
        "goals": {"primary": goal, "priority_muscles": []},
        "experience": {"level": level, "working_sets": {"barbell_squat": {"weight_kg": 90, "reps": 5}}},
        "schedule": {"days_per_week": days, "session_minutes": minutes},
        "preferences": {"preferred_split": split},
        "equipment": {"available": equipment or ["barbell", "dumbbells", "machines", "pull_up_bar"]},
        "considerations": {"avoided_exercises": [], "movement_restrictions": []},
    }


def _client_with_plan(**kwargs) -> tuple[TestClient, dict]:
    client = TestClient(app)
    client.__enter__()
    assessment = _assessment(**kwargs)
    saved = client.post(
        "/profiles",
        json={
            "goal": "build_strength",
            "experience": assessment["experience"]["level"],
            "days_per_week": assessment["schedule"]["days_per_week"],
            "session_duration_minutes": assessment["schedule"]["session_minutes"],
            "equipment": ["barbell"],
            "limitations": [],
            "display_name": "Lifter",
            "assessment": assessment,
        },
    )
    assert saved.status_code == 200, saved.text
    plan = client.post("/workouts/generate", json={})
    assert plan.status_code == 200, plan.text
    return client, accept_if_proposed(client, plan.json())


@pytest.fixture
def athlete():
    client, plan = _client_with_plan()
    yield client, plan
    client.__exit__(None, None, None)


def test_start_is_idempotent_and_does_not_duplicate_sessions(athlete):
    client, plan = athlete
    first = client.post("/sessions", json={"plan_id": plan["id"]}).json()
    second = client.post("/sessions", json={"plan_id": plan["id"]}).json()
    standalone = client.post("/sessions", json={}).json()
    assert first["id"] == second["id"] == standalone["id"]
    assert client.get("/sessions/current").json()["session"]["id"] == first["id"]
    assert len(client.get("/sessions?include_empty=true").json()["sessions"]) == 1


def test_complete_requires_real_sets_and_closes_the_plan(athlete):
    client, plan = athlete
    session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
    empty = client.post(f"/sessions/{session['id']}/complete")
    assert empty.status_code == 400
    exercise = plan["exercises"][0]["exercise_id"]
    logged = client.post(
        f"/sessions/{session['id']}/sets",
        json={"exercise_id": exercise, "set_index": 1, "completed_reps": 5, "load_kg": 90, "target_reps": 5},
    )
    assert logged.status_code == 200
    assert logged.json()["entry_source"] == "manual"
    done = client.post(f"/sessions/{session['id']}/complete").json()
    assert done["status"] == "completed"
    assert done["summary"]["completed_sets"] == 1
    assert done["summary"]["volume_kg"] == 450
    assert client.post(f"/sessions/{session['id']}/complete").json()["status"] == "completed"
    assert client.get(f"/workouts/{plan['id']}").json()["status"] == "completed"
    assert client.get("/workouts/next").json()["plan"] is None
    assert client.get("/sessions/current").json()["session"] is None
    late = client.post(
        f"/sessions/{session['id']}/sets",
        json={"exercise_id": exercise, "set_index": 2, "completed_reps": 5},
    )
    assert late.status_code == 409
    assert client.post(f"/sessions/{session['id']}/abandon").status_code == 409
    assert client.post("/sessions", json={"plan_id": plan["id"]}).status_code == 409


def test_relogging_a_set_corrects_it_and_rejects_exercises_outside_the_plan(athlete):
    client, plan = athlete
    session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
    exercise = plan["exercises"][0]["exercise_id"]
    body = {"exercise_id": exercise, "set_index": 1, "completed_reps": 4, "load_kg": 80}
    client.post(f"/sessions/{session['id']}/sets", json=body)
    client.post(f"/sessions/{session['id']}/sets", json={**body, "completed_reps": 6})
    sets = client.get(f"/sessions/{session['id']}").json()["sets"]
    assert len(sets) == 1 and sets[0]["completed_reps"] == 6
    outside = next(ex for ex in CATALOG if ex not in {item["exercise_id"] for item in plan["exercises"]})
    assert client.post(
        f"/sessions/{session['id']}/sets", json={**body, "exercise_id": outside}
    ).status_code == 400
    removed = client.delete(f"/sessions/{session['id']}/sets/{sets[0]['id']}")
    assert removed.status_code == 200
    assert client.get(f"/sessions/{session['id']}").json()["sets"] == []


def test_pause_resume_and_logging_resumes_a_paused_workout(athlete):
    client, plan = athlete
    session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
    paused = client.post(f"/sessions/{session['id']}/pause").json()
    assert paused["status"] == "paused" and paused["paused_at"]
    assert client.post(f"/sessions/{session['id']}/pause").json()["status"] == "paused"
    assert client.post(f"/sessions/{session['id']}/resume").json()["status"] == "active"
    client.post(f"/sessions/{session['id']}/pause")
    client.post(
        f"/sessions/{session['id']}/sets",
        json={"exercise_id": plan["exercises"][0]["exercise_id"], "set_index": 1, "completed_reps": 5},
    )
    assert client.get(f"/sessions/{session['id']}").json()["status"] == "active"
    resumed = client.post("/sessions", json={"plan_id": plan["id"]}).json()
    assert resumed["id"] == session["id"]


def test_one_open_workout_at_a_time(athlete):
    client, plan = athlete
    empty = client.post("/sessions", json={"plan_id": plan["id"]}).json()
    nxt = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
    assert client.get(f"/workouts/{plan['id']}").json()["status"] == "active"
    started = client.post("/sessions", json={"plan_id": nxt["id"]}).json()
    assert started["id"] != empty["id"]
    assert client.get(f"/sessions/{empty['id']}").json()["status"] == "abandoned"
    client.post(
        f"/sessions/{started['id']}/sets",
        json={"exercise_id": nxt["exercises"][0]["exercise_id"], "set_index": 1, "completed_reps": 5},
    )
    third = client.post("/workouts/generate", json={}).json()
    blocked = client.post("/sessions", json={"plan_id": third["id"]})
    assert blocked.status_code == 409
    assert "accept" in blocked.json()["detail"].lower()
    accept_blocked = client.post(f"/workouts/{third['id']}/accept")
    assert accept_blocked.status_code == 409
    assert accept_blocked.json()["detail"]["open_session_id"] == started["id"]
    listed = [row["id"] for row in client.get("/sessions").json()["sessions"]]
    assert empty["id"] not in listed and started["id"] in listed


def test_regenerating_replaces_an_unstarted_plan_and_completion_rotates(athlete):
    client, first = athlete
    again = client.post("/workouts/generate", json={}).json()
    assert again["status"] == "proposed"
    assert client.get(f"/workouts/{first['id']}").json()["status"] == "active"
    assert client.get("/workouts/next").json()["plan"]["id"] == first["id"]
    accepted = accept_if_proposed(client, again)
    assert client.get(f"/workouts/{first['id']}").json()["status"] == "replaced"
    assert client.get("/workouts/next").json()["plan"]["id"] == accepted["id"]
    assert accepted["session_type"] == first["session_type"]
    session = client.post("/sessions", json={"plan_id": accepted["id"]}).json()
    client.post(
        f"/sessions/{session['id']}/sets",
        json={"exercise_id": accepted["exercises"][0]["exercise_id"], "set_index": 1, "completed_reps": 5},
    )
    client.post(f"/sessions/{session['id']}/complete")
    following = client.post("/workouts/generate", json={}).json()
    assert following["status"] == "proposed"
    assert following["session_type"] != accepted["session_type"]
    assert {following["session_type"], accepted["session_type"]} == {"lower", "upper"}


def test_upload_is_rejected_on_a_finished_workout(athlete):
    client, plan = athlete
    session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
    client.post(f"/sessions/{session['id']}/abandon")
    response = client.post(
        "/videos/upload",
        data={"session_id": session["id"], "exercise_id": "barbell_squat", "consent": "true", "demo": "false"},
    )
    assert response.status_code == 409


def test_failed_or_empty_recordings_do_not_count_as_completed_sets():
    from app.api.serialize import is_done_set

    assert not is_done_set(RecordedSet(entry_source="video", processing_status="COMPLETED", completed_reps=0))
    assert not is_done_set(RecordedSet(entry_source="video", processing_status="FAILED", completed_reps=None))
    assert not is_done_set(RecordedSet(entry_source="manual", processing_status="LOGGED", completed_reps=0))
    assert is_done_set(RecordedSet(entry_source="video", processing_status="COMPLETED", completed_reps=8))
    assert is_done_set(RecordedSet(entry_source="manual", processing_status="LOGGED", completed_reps=5))


def test_stale_and_duplicate_open_sessions_are_closed_without_losing_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stale.db'}", future=True)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    user = User(display_name="A")
    db.add(user)
    db.flush()
    old = datetime.now(timezone.utc) - timedelta(days=2)
    empty_old = WorkoutSession(user_id=user.id, status="active", started_at=old)
    with_sets = WorkoutSession(user_id=user.id, status="active", started_at=old + timedelta(hours=1))
    newest = WorkoutSession(user_id=user.id, status="active", started_at=datetime.now(timezone.utc))
    db.add_all([empty_old, with_sets, newest])
    db.flush()
    db.add(RecordedSet(session_id=with_sets.id, user_id=user.id, exercise_id="barbell_squat", processing_status="COMPLETED"))
    db.commit()
    ids = (empty_old.id, with_sets.id, newest.id)
    db.close()

    assert close_stale_sessions(engine) == 2
    assert close_stale_sessions(engine) == 0
    with engine.connect() as conn:
        status = dict(conn.execute(text("SELECT id, status FROM workout_sessions")).fetchall())
        kept_sets = conn.execute(text("SELECT COUNT(*) FROM recorded_sets")).scalar()
    assert status[ids[0]] == "abandoned"
    assert status[ids[1]] == "abandoned"
    assert status[ids[2]] == "active"
    assert kept_sets == 1


def test_training_columns_migrate_in_place(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE workout_plans (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, status TEXT,"
            " source TEXT, duration_minutes INTEGER, notes TEXT, created_at DATETIME)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE workout_sessions (id TEXT PRIMARY KEY, user_id TEXT, plan_id TEXT, status TEXT,"
            " started_at DATETIME, completed_at DATETIME)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE recorded_sets (id TEXT PRIMARY KEY, session_id TEXT, user_id TEXT, exercise_id TEXT,"
            " original_filename TEXT, processing_status TEXT)"
        )
        conn.exec_driver_sql("INSERT INTO workout_plans (id, name, duration_minutes) VALUES ('p1', 'Leg Day A', 50)")
        conn.exec_driver_sql("INSERT INTO recorded_sets (id, original_filename) VALUES ('r1', 'DEMO_FIXTURE')")
        conn.exec_driver_sql("INSERT INTO recorded_sets (id, original_filename) VALUES ('r2', 'set.mov')")
    migrate_training_columns(engine)
    migrate_training_columns(engine)
    with engine.connect() as conn:
        plan_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(workout_plans)"))}
        assert {"context_json", "warnings_json", "schedule_json"} <= plan_cols
        assert conn.execute(text("SELECT name, session_type FROM workout_plans")).fetchone() == ("Leg Day A", None)
        sources = dict(conn.execute(text("SELECT id, entry_source FROM recorded_sets")).fetchall())
        assert conn.execute(text("SELECT paused_at FROM workout_sessions")).fetchall() == []
    assert sources == {"r1": "demo", "r2": "video"}


def _view(level="intermediate", goal="increase_strength", days=4, minutes=50, equipment=None, split=None):
    return {"assessment": _assessment(level, goal, days, minutes, equipment, split)}


@pytest.mark.parametrize("minutes", [15, 25, 40, 50, 70, 90])
def test_plans_fit_the_requested_time(minutes):
    for index in range(3):
        plan = generate_local_plan(_view(minutes=minutes), session_index=index)
        assert plan["estimated_minutes"] == estimate_minutes(plan["exercises"])
        assert plan["estimated_minutes"] <= minutes
        if minutes <= 50:
            assert plan["estimated_minutes"] >= minutes * 0.75
    short = generate_local_plan(_view(minutes=25))
    long = generate_local_plan(_view(minutes=70))
    assert sum(e["sets"] for e in long["exercises"]) > sum(e["sets"] for e in short["exercises"])
    assert "remaining time" in generate_local_plan(_view(minutes=90))["notes"]


def test_frequency_and_split_choose_the_session_rotation():
    assert resolve_split("ghostrep_decides", 3, "intermediate") == "full_body"
    assert resolve_split(None, 4, "intermediate") == "upper_lower"
    assert resolve_split(None, 5, "advanced") == "push_pull_legs"
    assert resolve_split(None, 5, "beginner") == "upper_lower"
    assert resolve_split("push_pull_legs", 2, "advanced") == "full_body"
    assert resolve_split("upper_lower", 1, "advanced") == "full_body"
    ppl = [generate_local_plan(_view(days=6, split="push_pull_legs"), session_index=i)["session_type"] for i in range(4)]
    assert ppl == ["legs", "push", "pull", "legs"]
    fallback = generate_local_plan(_view(days=2, split="push_pull_legs"))
    assert fallback["session_type"] == "full_body_a"
    assert "full-body" in fallback["notes"]
    upper = generate_local_plan(_view(days=4), session_index=1)
    assert upper["session_type"] == "upper"
    assert not {"barbell_squat", "goblet_squat"} & {e["exercise_id"] for e in upper["exercises"]}


def test_different_profiles_do_not_get_the_same_leg_day():
    names = {
        generate_local_plan(_view(days=3, equipment=["bodyweight"], level="beginner", goal="maintain_fitness"))["name"],
        generate_local_plan(_view(days=4))["name"],
        generate_local_plan(_view(days=6, split="push_pull_legs"), session_index=1)["name"],
    }
    assert len(names) == 3
    assert "Leg Day A" not in names


@pytest.mark.parametrize("equipment,banned", [
    (["bodyweight"], {"barbell", "dumbbells", "machines", "kettlebell", "bands", "pullup"}),
    (["dumbbells", "bodyweight"], {"barbell", "machines", "pullup"}),
])
def test_every_session_in_the_rotation_respects_equipment(equipment, banned):
    for days, split in ((3, None), (4, None), (6, "push_pull_legs")):
        for index in range(3):
            plan = generate_local_plan(_view(days=days, split=split, equipment=equipment), session_index=index)
            for item in plan["exercises"]:
                needs = set(CATALOG[item["exercise_id"]]["equipment"])
                assert "bodyweight" in needs or not needs <= banned, (plan["session_type"], item["exercise_id"])


def test_annotated_recording_benchmark_matches_hand_labels():
    rows = [row for row in real_checks() if row.get("status") == "scored"]
    if not rows:
        pytest.skip("Optional private annotated recording is not included in the source snapshot")
    for row in rows:
        assert row["count_correct"]
        assert row["boundaries"]["max_abs_error_s"]["start"] <= 0.75
        assert row["boundaries"]["max_abs_error_s"]["bottom"] <= 0.55
        assert row["boundaries"]["max_abs_error_s"]["end"] <= 0.6
