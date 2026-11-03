import json

import pytest

from app.config import Settings
from app.services.coaching.guards import validate_recommendation
from app.services.coaching.local_coach import generate_local_coaching
from app.services.meta.gateway import MetaBlocked, MetaGateway
from app.services.movement.pipeline import analyze_pose_sequence
from app.services.movement.synthetic import synthesize_squat_set
from app.services.workout.local_planner import generate_local_plan


def test_planner_uses_profile_equipment_and_includes_squat():
    plan = generate_local_plan(
        {
            "goal": "build_strength",
            "experience": "intermediate",
            "days_per_week": 4,
            "session_duration_minutes": 50,
            "equipment": ["barbell", "dumbbells"],
            "current_squat_load_kg": 40,
            "limitations": [],
        }
    )
    ids = [e["exercise_id"] for e in plan["exercises"]]
    assert "barbell_squat" in ids
    assert plan["source"] == "local"
    assert "not Muse Spark" in plan["source_label"]
    squat = next(e for e in plan["exercises"] if e["exercise_id"] == "barbell_squat")
    assert squat["suggested_load_kg"] == 40


def test_planner_skips_barbell_when_unavailable():
    plan = generate_local_plan(
        {
            "goal": "build_muscle",
            "experience": "beginner",
            "days_per_week": 3,
            "session_duration_minutes": 40,
            "equipment": ["dumbbells"],
            "limitations": [],
        }
    )
    ids = [e["exercise_id"] for e in plan["exercises"]]
    assert "barbell_squat" not in ids
    assert "goblet_squat" in ids


def test_pain_limitation_stops_session():
    payload = generate_local_coaching(
        quality={"usable": True, "issues": []},
        drift=[],
        reps=[{"rep_id": 1, "start_seconds": 1, "bottom_seconds": 2, "end_seconds": 3}],
        reference_rep=1,
        profile={"limitations": ["knee pain today"]},
        current_reps=8,
        current_rest=120,
        current_load=40,
        reported_rpe=6,
    )
    assert payload["suggested_action"] == "STOP_AND_SEEK_PROFESSIONAL_ADVICE"


def test_keep_plan_preserves_prescription_not_completed_reps():
    payload = generate_local_coaching(
        quality={"usable": True, "issues": []},
        drift=[
            {
                "rep_id": 2,
                "similarity": 94,
                "torso_lean_difference_deg": 1.0,
                "depth_difference_percent": 0.0,
                "ascent_duration_difference_percent": 1.0,
                "onset": False,
                "reference_deviation": 6,
            }
        ],
        reps=[
            {"rep_id": 1, "start_seconds": 1, "bottom_seconds": 2, "end_seconds": 3},
            {"rep_id": 2, "start_seconds": 4, "bottom_seconds": 5, "end_seconds": 6},
        ],
        reference_rep=1,
        profile={"limitations": []},
        current_reps=6,
        current_rest=150,
        current_load=None,
        reported_rpe=6,
        planned_set_reps=8,
        completed_reps=8,
        workout_reps=6,
        workout_rest_seconds=150,
        workout_load_kg=None,
    )
    assert payload["suggested_action"] == "KEEP_PLAN"
    assert payload["suggested_reps"] == 6
    assert payload["current_reps"] == 6
    assert payload["completed_reps"] == 8
    assert payload["planned_set_reps"] == 8
    assert payload["suggested_rest_seconds"] == 150
    assert payload["suggested_load_kg"] is None


def test_keep_plan_guard_does_not_substitute_completed_or_invent_load():
    guarded = validate_recommendation(
        {
            "suggested_action": "KEEP_PLAN",
            "current_reps": 6,
            "current_rest_seconds": 150,
            "current_load_kg": None,
            "suggested_reps": 8,
            "suggested_rest_seconds": 120,
            "suggested_load_kg": 40,
            "uncertainties": [],
        },
        {},
    )
    assert guarded["suggested_reps"] == 6
    assert guarded["suggested_rest_seconds"] == 150
    assert guarded["suggested_load_kg"] is None


def test_keep_plan_guard_preserves_eight_when_completed_six():
    guarded = validate_recommendation(
        {
            "suggested_action": "KEEP_PLAN",
            "current_reps": 8,
            "current_rest_seconds": 120,
            "current_load_kg": 40,
            "suggested_reps": 6,
            "suggested_rest_seconds": 120,
            "suggested_load_kg": 40,
            "uncertainties": [],
        },
        {},
    )
    assert guarded["suggested_reps"] == 8
    assert guarded["suggested_load_kg"] == 40


def test_extend_rest_leaves_unknown_rest_unknown():
    guarded = validate_recommendation(
        {
            "suggested_action": "EXTEND_REST",
            "current_reps": 6,
            "current_rest_seconds": None,
            "current_load_kg": None,
            "suggested_reps": 6,
            "suggested_rest_seconds": None,
            "suggested_load_kg": None,
            "uncertainties": [],
        },
        {},
    )
    assert guarded["suggested_rest_seconds"] is None
    assert guarded["suggested_load_kg"] is None


def test_never_increases_load():
    guarded = validate_recommendation(
        {
            "suggested_action": "KEEP_PLAN",
            "current_load_kg": 40,
            "suggested_load_kg": 50,
            "current_reps": 8,
            "uncertainties": [],
        },
        {},
    )
    assert guarded["suggested_load_kg"] == 40


def test_local_coach_recommends_from_real_drift():
    frames = synthesize_squat_set(reps=6, drift=True)
    result = analyze_pose_sequence(frames)
    payload = generate_local_coaching(
        quality=result["quality"],
        drift=result["drift"],
        reps=[
            {
                "rep_id": r.rep_id,
                "start_seconds": r.start_seconds,
                "bottom_seconds": r.bottom_seconds,
                "end_seconds": r.end_seconds,
            }
            for r in result["reps"]
        ],
        reference_rep=result["reference_rep"],
        profile={"limitations": []},
        current_reps=8,
        current_rest=120,
        current_load=40,
        reported_rpe=7,
    )
    assert payload["source"] == "local"
    assert payload["suggested_action"] in {"REDUCE_REPS", "EXTEND_REST", "KEEP_PLAN"}
    assert payload["requires_confirmation"] is True
    assert all("injury" not in o["statement"].lower() for o in payload["observations"])


def test_gateway_blocks_without_flags(tmp_path):
    settings = Settings(
        enable_meta_api=False,
        ai_provider="local",
        model_api_key="sk-test",
        data_dir=tmp_path,
    )
    gateway = MetaGateway(settings, db=None)
    with pytest.raises(MetaBlocked):
        gateway.authorize(
            model="muse-spark-1.3",
            purpose="workout_generation",
            estimated_cost_usd=0.01,
            approval_token=None,
        )
    log = (tmp_path / "meta-usage.jsonl").read_text()
    assert "ENABLE_META_API is false" in log
    assert json.loads(log.strip())["allowed"] is False
