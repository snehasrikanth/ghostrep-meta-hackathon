"""Regression for Muse Attempt 002 quality review. No Meta calls."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.meta.contracts import accept_week, build_workout_messages, parse_week
from app.services.workout.local_planner import TIMED
from app.services.workout.quality import review_week, session_work_minutes

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "meta" / "muse_attempt_002_week.json"

PROFILE = {
    "goal": "build_strength",
    "experience": "intermediate",
    "days_per_week": 4,
    "session_duration_minutes": 50,
    "equipment": ["barbell", "dumbbells", "bench", "machines", "rack", "pullup", "bodyweight"],
    "current_squat_load_kg": None,
    "limitations": [],
    "assessment": {
        "identity": {"age_range": "25_34"},
        "goals": {"primary": "increase_strength", "priority_muscles": ["full_body"]},
        "experience": {"level": "intermediate", "working_sets": {}},
        "schedule": {"days_per_week": 4, "session_minutes": 50},
        "preferences": {
            "enjoyed_exercises": [
                "barbell_squat",
                "goblet_squat",
                "bodyweight_squat",
                "romanian_deadlift",
                "walking_lunge",
                "leg_press",
                "leg_curl",
                "bench_press",
                "push_up",
                "dumbbell_row",
                "glute_bridge",
                "plank",
            ],
            "preferred_split": "upper_lower",
        },
        "equipment": {"preset": "full_gym", "available": ["barbell", "dumbbells", "bench", "machines", "squat_rack", "pull_up_bar"]},
        "considerations": {"avoided_exercises": [], "movement_restrictions": []},
    },
}


def _week() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {"summary": data["summary"], "sessions": data["sessions"]}


def test_attempt_002_is_accepted_with_quality_warnings_not_hard_failure():
    plan = accept_week(_week(), PROFILE, 0, "muse_spark", "Muse Spark 1.3 (live)")
    assert plan["source"] == "muse_spark"
    assert len(plan["schedule"]) == 4
    assert all(session["duration_minutes"] == 50 for session in plan["schedule"])
    assert plan["quality_warnings"]
    assert any("min against a 50-min request" in item for item in plan["quality_warnings"])
    assert any("enjoyed exercise" in item for item in plan["quality_warnings"])
    assert any("maintenance" in item.lower() or "unloaded squat" in item for item in plan["quality_warnings"])
    assert any("overhead" in item for item in plan["quality_warnings"])
    assert any("pattern" in item for item in plan["quality_warnings"])
    ids = [item["exercise_id"] for session in plan["schedule"] for item in session["exercises"]]
    assert "barbell_squat" in ids
    assert "bench_press" in ids


def test_plank_hold_is_an_explicit_seconds_transform():
    plan = accept_week(_week(), PROFILE, 0, "muse_spark", "Muse Spark 1.3 (live)")
    planks = [item for item in plan["exercises"] if item["exercise_id"] in TIMED]
    assert planks
    assert planks[0]["target_reps"] == 45
    assert any("seconds" in item for item in plan["quality_transforms"])
    assert "explicit timed-hold" in " ".join(plan["quality_transforms"])
    assert plan["exercises"][0]["exercise_id"] == "barbell_squat"


def test_invented_overhead_ban_is_stripped_from_summary_not_exercises():
    plan = accept_week(_week(), PROFILE, 0, "muse_spark", "Muse Spark 1.3 (live)")
    assert "no overhead" not in plan["notes"].lower()
    assert "barbell_squat" in [item["exercise_id"] for item in plan["exercises"]]


def test_estimated_minutes_use_work_rest_warmup_and_transitions():
    plan = accept_week(_week(), PROFILE, 0, "muse_spark", "Muse Spark 1.3 (live)")
    assert plan["estimated_minutes"] == session_work_minutes(plan["exercises"])
    assert plan["estimated_minutes"] < plan["duration_minutes"]
    assert plan["estimated_minutes"] >= 25


def test_prompt_does_not_treat_enjoyed_lifts_as_required():
    text = build_workout_messages(PROFILE, None, 0)[0]["content"]
    assert "optional preferences" in text
    assert "hold seconds" in text
    assert "maintenance or deload" in text


def test_review_does_not_replace_prescribed_lifts():
    original = [item["exercise_id"] for session in _week()["sessions"] for item in session["exercises"]]
    reviewed = review_week(parse_week(_week()), PROFILE)
    after = [item.exercise_id for session in reviewed["week"].sessions for item in session.exercises]
    assert after == original
