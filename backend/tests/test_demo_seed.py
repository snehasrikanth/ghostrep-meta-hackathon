from __future__ import annotations

import inspect
from datetime import date, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.main import app
from app.models.entities import Profile, RecordedSet, User, WorkoutSession
from app.services.demo import dataset as demo_dataset
from app.services.demo import seed as demo_seed
from app.services.demo.dataset import build_dataset, fingerprint
from app.services.demo.identity import DEMO_DISPLAY_NAME, DEMO_USER_ID
from app.services.demo.seed import DemoBusyError, cleanup_demo, seed_demo
from app.services.meta.muse import MuseProvider
from app.services.workout.local_planner import TIMED


ANCHOR = date(2026, 10, 30)
TZ = ZoneInfo("America/New_York")


def _db() -> Session:
    init_db()
    return SessionLocal()


def _seed(db: Session, **kwargs):
    return seed_demo(db, anchor=ANCHOR, timezone_name="America/New_York", **kwargs)


def test_dataset_is_a_four_day_week_with_one_missed_day_and_one_open_workout():
    dataset = build_dataset(ANCHOR, TZ)
    assert len(dataset.sessions) == 10
    assert sum(1 for row in dataset.sessions if row.status == "completed") == 8
    assert sum(1 for row in dataset.sessions if row.status == "abandoned") == 1
    assert sum(1 for row in dataset.sessions if row.status == "paused") == 1
    assert len(dataset.missed) == 1
    dates = [row.local_date for row in dataset.sessions]
    assert date(2026, 10, 20) not in dates
    paused = next(row for row in dataset.sessions if row.status == "paused")
    assert paused.local_date == date(2026, 10, 29)
    assert paused.paused_at is not None
    assert paused.completed_at is None
    early = next(row for row in dataset.sessions if row.status == "abandoned")
    logged = {item.exercise_id for item in early.sets}
    planned = {item["exercise_id"] for item in early.exercises}
    assert logged < planned
    assert any(item.exercise_id == "barbell_squat" for item in early.sets)


def test_seed_is_idempotent_isolated_and_does_not_call_muse():
    assert "MuseProvider" not in inspect.getsource(demo_seed)
    assert "generate_workout" not in inspect.getsource(demo_seed)
    assert "generate_local_plan" in inspect.getsource(demo_dataset)
    called = {"muse": 0}

    def boom(*_args, **_kwargs):
        called["muse"] += 1
        raise AssertionError("demo seed must not call Muse")

    db = _db()
    try:
        with patch.object(MuseProvider, "generate_workout", boom):
            outsider = User(display_name="Real Athlete")
            db.add(outsider)
            db.flush()
            outsider_id = outsider.id
            db.add(
                Profile(
                    user_id=outsider_id,
                    goal="build_strength",
                    experience="intermediate",
                    days_per_week=4,
                    session_duration_minutes=45,
                    equipment_json='["barbell"]',
                    limitations_json="[]",
                    submitted=True,
                )
            )
            db.commit()
            first = _seed(db)
            assert first.action == "create"
            assert called["muse"] == 0
            second = _seed(db)
            assert second.action == "reuse"
            dry = _seed(db, dry_run=True)
            assert dry.action == "reuse"
            assert db.query(User).filter(User.id == outsider_id).count() == 1
            sessions = db.query(WorkoutSession).filter(WorkoutSession.user_id == DEMO_USER_ID).all()
            assert len(sessions) == 10
            open_rows = [row for row in sessions if row.status in {"active", "paused"}]
            assert len(open_rows) == 1
            assert open_rows[0].status == "paused"
            completed = [row for row in sessions if row.status == "completed"]
            assert len(completed) == 8
            for row in sessions:
                for item in row.recorded_sets:
                    assert _aware(row.started_at) <= _aware(item.created_at)
                    end = row.completed_at or row.paused_at
                    assert end is not None
                    assert _aware(item.created_at) <= _aware(end)
                    if item.exercise_id in TIMED:
                        assert item.load_kg is None
            squat = (
                db.query(RecordedSet)
                .filter(RecordedSet.user_id == DEMO_USER_ID, RecordedSet.exercise_id == "barbell_squat")
                .all()
            )
            assert {item.load_kg for item in squat} == {80.0, 82.5}
            assert db.get(User, outsider_id).display_name == "Real Athlete"
            cleanup = cleanup_demo(db)
            assert cleanup.action == "cleanup"
            assert db.get(User, DEMO_USER_ID) is None
            assert db.get(User, outsider_id) is not None
            assert db.query(WorkoutSession).filter(WorkoutSession.user_id == outsider_id).count() == 0
    finally:
        db.close()


def test_seed_refuses_later_demo_edits_without_refresh():
    db = _db()
    try:
        _seed(db)
        paused = (
            db.query(WorkoutSession)
            .filter(WorkoutSession.user_id == DEMO_USER_ID, WorkoutSession.status == "paused")
            .one()
        )
        db.add(
            RecordedSet(
                session_id=paused.id,
                user_id=DEMO_USER_ID,
                exercise_id="calf_raise",
                entry_source="manual",
                set_index=1,
                completed_reps=10,
                processing_status="LOGGED",
            )
        )
        db.commit()
        with pytest.raises(DemoBusyError):
            _seed(db)
        refreshed = _seed(db, refresh=True)
        assert refreshed.action == "refresh"
        assert fingerprint(build_dataset(ANCHOR, TZ)) == _current_fingerprint(db)
    finally:
        cleanup_demo(db)
        db.close()


def test_metrics_exclude_previews_unfinished_work_and_timed_holds():
    db = _db()
    client = TestClient(app)
    client.__enter__()
    try:
        _seed(db)
        enter = client.post("/demo/enter")
        assert enter.status_code == 200, enter.text
        sessions = client.get("/sessions").json()["sessions"]
        finished = [row for row in sessions if row["status"] == "completed"]
        assert len(finished) == 8
        paused = [row for row in sessions if row["status"] == "paused"]
        abandoned = [row for row in sessions if row["status"] == "abandoned"]
        assert len(paused) == 1
        assert len(abandoned) == 1
        completed_sets = sum(row["summary"]["completed_sets"] for row in finished)
        paused_sets = paused[0]["summary"]["completed_sets"]
        assert paused_sets > 0
        assert completed_sets == sum(row["summary"]["completed_sets"] for row in finished)
        for row in sessions:
            timed = row["summary"].get("timed_seconds") or 0
            if timed:
                assert row["summary"]["total_reps"] >= 0
                lifting = [item for item in row["sets"] if item["exercise_id"] not in TIMED]
                assert row["summary"]["total_reps"] == sum(item["completed_reps"] or 0 for item in lifting if (item["completed_reps"] or 0) > 0)
        program = client.get("/program", params={"today": "2026-10-30", "weeks": 4, "tz": "America/New_York"}).json()
        week = program["weeks"][0]["days"]
        monday = next(day for day in week if day["weekday"] == "monday")
        thursday = next(day for day in week if day["weekday"] == "thursday")
        saturday = next(day for day in week if day["weekday"] == "saturday")
        assert monday["is_preview"] is False
        assert monday["session_status"] == "completed"
        assert thursday["session_status"] == "paused"
        assert thursday["is_next"] is True
        assert saturday["is_preview"] is True
        assert saturday["plan_id"] is None
        assert all(not day["is_next"] for week_row in program["weeks"][1:] for day in week_row["days"])
        me = client.get("/profiles/me").json()
        assert me["display_name"] == DEMO_DISPLAY_NAME
        assert me["user_id"] == DEMO_USER_ID
        next_plan = client.get("/workouts/next").json()["plan"]
        assert next_plan["id"] == paused[0]["plan_id"]
        open_rows = [row for row in client.get("/sessions?include_empty=true").json()["sessions"] if row["status"] in {"active", "paused"}]
        assert len(open_rows) == 1
    finally:
        cleanup_demo(db)
        client.__exit__(None, None, None)
        db.close()


def _aware(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _current_fingerprint(db: Session) -> str:
    rows = db.query(WorkoutSession).filter(WorkoutSession.user_id == DEMO_USER_ID).all()
    parts = [f"{row.id}:{row.status}:{len(row.recorded_sets)}" for row in rows]
    return "|".join(sorted(parts))
