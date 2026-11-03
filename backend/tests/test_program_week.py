from __future__ import annotations

import json
from datetime import date

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.entities import WorkoutPlan, WorkoutSession
from app.services.meta.muse import MuseProvider
from app.services.workout.local_planner import resolve_split
from tests.helpers import accept_if_proposed
from app.services.workout.week import (
    build_program,
    has_exercise_details,
    parse_today,
    place_training_days,
    select_saved_schedule,
    week_monday,
)


def _assessment(*, days=4, split="upper_lower", preferred=None, equipment=None, avoided=None):
    return {
        "identity": {"display_name": "Lifter", "adult_confirmed": True, "preferred_weight_unit": "kg"},
        "goals": {"primary": "increase_strength", "priority_muscles": []},
        "experience": {"level": "intermediate", "working_sets": {"barbell_squat": {"weight_kg": 40, "reps": 6}}},
        "schedule": {
            "days_per_week": days,
            "session_minutes": 50,
            "preferred_days": preferred or [],
        },
        "preferences": {"preferred_split": split},
        "equipment": {"available": equipment or ["barbell", "dumbbells", "machines", "bench"]},
        "considerations": {"avoided_exercises": avoided or [], "movement_restrictions": []},
    }


def _client(assessment=None, generate=True) -> tuple[TestClient, dict | None]:
    client = TestClient(app)
    client.__enter__()
    body = assessment or _assessment(preferred=["monday", "tuesday", "thursday", "saturday"])
    saved = client.post(
        "/profiles",
        json={
            "goal": "build_strength",
            "experience": "intermediate",
            "days_per_week": body["schedule"]["days_per_week"],
            "session_duration_minutes": 50,
            "equipment": body["equipment"]["available"],
            "current_squat_load_kg": 40,
            "limitations": [],
            "display_name": "Lifter",
            "assessment": body,
        },
    )
    assert saved.status_code == 200, saved.text
    plan = None
    if generate:
        created = client.post("/workouts/generate", json={})
        assert created.status_code == 200, created.text
        plan = accept_if_proposed(client, created.json())
    return client, plan


def _training(days):
    return [day for day in days if day["kind"] == "training"]


def _recovery(days):
    return [day for day in days if day["kind"] == "recovery"]


def test_place_training_days_uses_preferred_when_complete():
    days, mode = place_training_days(["monday", "tuesday", "thursday", "saturday"], 4)
    assert days == ["monday", "tuesday", "thursday", "saturday"]
    assert mode == "preferred"


def test_place_training_days_suggests_when_preferred_are_incomplete():
    days, mode = place_training_days(["monday"], 4)
    assert mode == "suggested"
    assert days[0] == "monday"
    assert len(days) == 4


def test_week_monday_and_today_parsing_stay_on_the_calendar_date():
    assert week_monday(date(2026, 10, 30)) == date(2026, 10, 26)
    assert parse_today("2026-10-30") == date(2026, 10, 30)
    try:
        parse_today("2026-10-30T04:00:00Z")
        assert False, "timestamps must be rejected"
    except ValueError:
        pass


def test_four_day_upper_lower_has_four_sessions_and_three_recovery_days():
    client, _plan = _client()
    try:
        body = client.get("/program", params={"today": "2026-10-30", "weeks": 1}).json()
        days = body["weeks"][0]["days"]
        assert body["split"] == "upper_lower"
        assert body["days_per_week"] == 4
        assert body["placement_mode"] == "preferred"
        assert [day["weekday"] for day in _training(days)] == ["monday", "tuesday", "thursday", "saturday"]
        assert len(_recovery(days)) == 3
        types = [day["workout"]["session_type"] for day in _training(days)]
        assert types[0] in {"lower", "legs"}
        assert "upper" in types
        next_day = next(day for day in days if day["is_next"])
        assert next_day["plan_id"]
        assert next_day["is_preview"] is False
        previews = [day for day in _training(days) if day["is_preview"]]
        assert previews
        assert all(day["plan_id"] is None for day in previews)
    finally:
        client.__exit__(None, None, None)


def test_full_body_and_push_pull_legs_follow_existing_rotation():
    assert resolve_split("full_body", 3, "intermediate") == "full_body"
    assert resolve_split("push_pull_legs", 3, "advanced") == "push_pull_legs"
    full = build_program(profile={"assessment": _assessment(days=3, split="full_body")}, today=date(2026, 10, 26))
    assert [day["workout"]["session_type"] for day in _training(full["weeks"][0]["days"])] == [
        "full_body_a",
        "full_body_b",
        "full_body_a",
    ]
    ppl = build_program(profile={"assessment": _assessment(days=3, split="push_pull_legs")}, today=date(2026, 10, 26))
    assert [day["workout"]["session_type"] for day in _training(ppl["weeks"][0]["days"])] == ["legs", "push", "pull"]


def test_equipment_and_avoided_exercises_are_enforced_in_local_previews():
    profile = {"assessment": _assessment(equipment=["dumbbells"], avoided=["walking_lunge"])}
    week = build_program(profile=profile, today=date(2026, 10, 26))
    ids = [item["exercise_id"] for day in _training(week["weeks"][0]["days"]) for item in day["workout"]["exercises"]]
    assert "barbell_squat" not in ids
    assert "walking_lunge" not in ids
    assert all(not (item["video_analysis"] and item["exercise_id"] != "barbell_squat") for day in _training(week["weeks"][0]["days"]) for item in day["workout"]["exercises"])


def test_saved_week_with_details_is_reused_and_missing_details_are_labeled():
    saved = [
        {
            "workout_name": "Saved Lower",
            "session_type": "lower",
            "duration_minutes": 50,
            "exercises": [
                {"exercise_id": "barbell_squat", "sets": 3, "target_reps": 5, "rest_seconds": 150, "suggested_load_kg": 40, "notes": ""},
                {"exercise_id": "romanian_deadlift", "sets": 3, "target_reps": 8, "rest_seconds": 90, "suggested_load_kg": None, "notes": ""},
            ],
        },
        {"workout_name": "Named Upper", "session_type": "upper", "duration_minutes": 50, "exercises": []},
        {
            "workout_name": "Saved Lower 2",
            "session_type": "lower",
            "duration_minutes": 50,
            "exercises": [
                {"exercise_id": "goblet_squat", "sets": 3, "target_reps": 8, "rest_seconds": 90, "suggested_load_kg": None, "notes": ""},
            ],
        },
        {
            "workout_name": "Saved Upper 2",
            "session_type": "upper",
            "duration_minutes": 50,
            "exercises": [
                {"exercise_id": "push_up", "sets": 3, "target_reps": 10, "rest_seconds": 60, "suggested_load_kg": None, "notes": ""},
            ],
        },
    ]
    week = build_program(
        profile={"assessment": _assessment(preferred=["monday", "tuesday", "thursday", "saturday"])},
        today=date(2026, 10, 26),
        saved_schedule=saved,
        saved_source="muse_spark",
    )
    training = _training(week["weeks"][0]["days"])
    assert training[0]["workout"]["name"] == "Saved Lower"
    assert training[0]["source"] == "saved_muse"
    assert training[0]["workout"]["exercises"][0]["suggested_load_kg"] == 40
    assert training[1]["source"] == "local_preview"
    assert "did not include exercise details" in (training[1]["detail_note"] or "")
    assert training[1]["workout"]["exercises"]
    assert has_exercise_details(saved[0]) is True
    assert has_exercise_details(saved[1]) is False


def test_select_saved_schedule_ignores_unaccepted_proposals():
    proposed = {"status": "proposed", "schedule": [{"workout_name": "A"}, {"workout_name": "B"}]}
    discarded = {"status": "discarded", "schedule": [{"workout_name": "C"}, {"workout_name": "D"}]}
    active = {"status": "active", "schedule": [{"workout_name": "Saved Lower"}, {"workout_name": "Saved Upper"}]}
    plan, schedule = select_saved_schedule([proposed, discarded, active])
    assert plan is active
    assert schedule[0]["workout_name"] == "Saved Lower"


def test_opening_the_program_does_not_create_sessions_or_call_muse():
    client, plan = _client()
    called = {"muse": 0}

    def boom(*_args, **_kwargs):
        called["muse"] += 1
        raise AssertionError("Muse must not run for program previews")

    original = MuseProvider.generate_workout
    MuseProvider.generate_workout = boom  # type: ignore[method-assign]
    try:
        db = SessionLocal()
        try:
            plans = db.query(WorkoutPlan).count()
            sessions = db.query(WorkoutSession).count()
        finally:
            db.close()
        first = client.get("/program", params={"today": "2026-10-26", "weeks": 4})
        assert first.status_code == 200, first.text
        body = first.json()
        assert len(body["weeks"]) == 4
        assert body["weeks"][0]["is_repeat"] is False
        assert all(week["is_repeat"] for week in body["weeks"][1:])
        assert all(not day["is_next"] and day["plan_id"] is None for week in body["weeks"][1:] for day in week["days"])
        assert called["muse"] == 0
        db = SessionLocal()
        try:
            assert db.query(WorkoutPlan).count() == plans
            assert db.query(WorkoutSession).count() == sessions
        finally:
            db.close()
        history = client.get("/sessions").json()["sessions"]
        assert history == []
        second = client.get("/program", params={"today": "2026-10-26", "weeks": 4})
        assert second.status_code == 200
        assert client.get(f"/workouts/{plan['id']}").json()["id"] == plan["id"]
    finally:
        MuseProvider.generate_workout = original  # type: ignore[method-assign]
        client.__exit__(None, None, None)


def test_history_overlay_keeps_completed_days_and_does_not_invent_completions():
    week = build_program(
        profile={"assessment": _assessment(preferred=["monday", "tuesday", "thursday", "saturday"])},
        today=date(2026, 10, 30),
        next_plan={
            "id": "plan-open",
            "name": "Lower B",
            "source": "local",
            "source_label": "Saved local workout",
            "session_type": "lower",
            "duration_minutes": 50,
            "estimated_minutes": 48,
            "notes": "",
            "exercises": [{"exercise_id": "barbell_squat", "sets": 3, "target_reps": 6, "rest_seconds": 150, "suggested_load_kg": 80, "notes": ""}],
        },
        open_session={"id": "s-open", "plan_id": "plan-open", "status": "paused", "date": "2026-10-29"},
        history=[
            {
                "date": "2026-10-26",
                "status": "completed",
                "plan": {
                    "id": "plan-mon",
                    "name": "Lower A",
                    "source": "local",
                    "source_label": "Saved local workout",
                    "session_type": "lower",
                    "duration_minutes": 50,
                    "estimated_minutes": 48,
                    "notes": "",
                    "exercises": [{"exercise_id": "barbell_squat", "sets": 3, "target_reps": 6, "rest_seconds": 150, "suggested_load_kg": 80, "notes": ""}],
                },
            }
        ],
    )
    days = {day["weekday"]: day for day in week["weeks"][0]["days"]}
    assert days["monday"]["plan_id"] == "plan-mon"
    assert days["monday"]["session_status"] == "completed"
    assert days["monday"]["is_next"] is False
    assert days["thursday"]["plan_id"] == "plan-open"
    assert days["thursday"]["session_status"] == "paused"
    assert days["thursday"]["is_next"] is True
    assert days["friday"]["kind"] == "recovery"
    assert days["saturday"]["is_preview"] is True
    assert days["saturday"]["plan_id"] is None


def test_unknown_loads_stay_unknown_and_only_squat_has_video_analysis():
    week = build_program(profile={"assessment": _assessment()}, today=date(2026, 10, 26))
    for day in _training(week["weeks"][0]["days"]):
        for item in day["workout"]["exercises"]:
            if item["exercise_id"] != "barbell_squat":
                assert item["suggested_load_kg"] is None
                assert item["video_analysis"] is False
            else:
                assert item["video_analysis"] is True
