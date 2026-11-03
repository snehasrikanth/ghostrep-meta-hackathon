import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, migrate_profile_columns
from app.main import app
from app.models.entities import Profile, User, WorkoutPlan
from app.services.workout.context import build_workout_context, validate_model_plan
from app.services.workout.local_planner import generate_local_plan
from app.services.workout.profile_model import assessment_from_legacy, project_assessment, to_kg


def _ids(plan: dict) -> list[str]:
    return [item["exercise_id"] for item in plan["exercises"]]


def test_different_profiles_produce_different_plans():
    gym = {
        "assessment": {
            "identity": {"age_range": "25_34", "preferred_weight_unit": "kg"},
            "goals": {"primary": "build_muscle", "secondary": "increase_strength", "priority_muscles": ["glutes", "quadriceps"]},
            "experience": {"level": "intermediate", "exercise_familiarity": {"barbell_squat": "confident"}, "working_sets": {"barbell_squat": {"weight_kg": 80, "reps": 8}}},
            "schedule": {"days_per_week": 4, "preferred_days": ["monday", "tuesday", "thursday", "saturday"], "session_minutes": 60},
            "preferences": {"training_style": "hypertrophy", "preferred_split": "upper_lower", "other_activities": []},
            "equipment": {"preset": "full_gym", "available": ["barbell", "squat_rack", "dumbbells", "leg_press", "leg_curl"]},
            "considerations": {"avoided_exercises": [], "movement_restrictions": []},
        }
    }
    bodyweight = {
        "assessment": {
            "identity": {"age_range": "25_34"},
            "goals": {"primary": "maintain_fitness", "priority_muscles": ["full_body"]},
            "experience": {"level": "beginner", "exercise_familiarity": {}, "working_sets": {}},
            "schedule": {"days_per_week": 3, "session_minutes": 25},
            "preferences": {"preferred_split": "full_body", "other_activities": []},
            "equipment": {"preset": "bodyweight", "available": ["bodyweight"]},
            "considerations": {"avoided_exercises": [], "movement_restrictions": []},
        }
    }
    gym_plan = generate_local_plan(gym)
    home_plan = generate_local_plan(bodyweight)
    assert _ids(gym_plan) != _ids(home_plan)
    assert "barbell_squat" in _ids(gym_plan)
    assert "barbell_squat" not in _ids(home_plan)
    assert "bodyweight_squat" in _ids(home_plan)
    assert gym_plan["name"] != home_plan["name"]
    squat = next(item for item in gym_plan["exercises"] if item["exercise_id"] == "barbell_squat")
    assert squat["suggested_load_kg"] == 80


def test_avoided_exercise_and_impact_are_left_out():
    plan = generate_local_plan(
        {
            "assessment": {
                "goals": {"primary": "build_muscle", "priority_muscles": ["glutes", "quadriceps"]},
                "experience": {"level": "intermediate", "working_sets": {}},
                "schedule": {"days_per_week": 4, "session_minutes": 50},
                "preferences": {"other_activities": [{"activity": "badminton", "sessions_per_week": 3}]},
                "equipment": {"available": ["barbell", "dumbbells", "leg_press"]},
                "considerations": {
                    "avoided_exercises": ["barbell_squat"],
                    "movement_restrictions": ["avoid_impact"],
                },
            }
        }
    )
    ids = _ids(plan)
    assert "barbell_squat" not in ids
    assert "walking_lunge" not in ids
    squat = next(item for item in plan["exercises"] if item["exercise_id"] in {"goblet_squat", "bodyweight_squat"})
    assert squat["sets"] == 2


def _strength_profile(age_range: str | None, experience: str = "advanced") -> dict:
    return {
        "assessment": {
            "identity": {"age_range": age_range},
            "goals": {"primary": "increase_strength", "priority_muscles": ["quadriceps"]},
            "experience": {"level": experience, "working_sets": {"barbell_squat": {"weight_kg": 100, "reps": 5}}},
            "schedule": {"days_per_week": 4, "session_minutes": 60},
            "preferences": {},
            "equipment": {"available": ["barbell", "dumbbells"]},
            "considerations": {"avoided_exercises": [], "movement_restrictions": []},
        }
    }


def test_age_does_not_change_strength_work_and_older_adults_keep_it():
    young = generate_local_plan(_strength_profile("18_29"))
    older = generate_local_plan(_strength_profile("75_plus"))
    unspecified = generate_local_plan(_strength_profile(None))
    young_squat = next(item for item in young["exercises"] if item["exercise_id"] == "barbell_squat")
    older_squat = next(item for item in older["exercises"] if item["exercise_id"] == "barbell_squat")
    open_squat = next(item for item in unspecified["exercises"] if item["exercise_id"] == "barbell_squat")
    assert young_squat["sets"] == older_squat["sets"] == open_squat["sets"] == 4
    assert young_squat["target_reps"] == older_squat["target_reps"] == 5
    assert young_squat["suggested_load_kg"] == older_squat["suggested_load_kg"] == 100
    assert "single_leg_balance" not in _ids(young)
    assert "single_leg_balance" in _ids(older)
    assert "single_leg_balance" not in _ids(unspecified)
    held_back = generate_local_plan(
        {
            "assessment": {
                "identity": {"age_range": "65_74"},
                "goals": {"primary": "increase_strength", "priority_muscles": ["full_body"]},
                "experience": {"level": "intermediate", "working_sets": {"barbell_squat": {"weight_kg": 100, "reps": 5}}},
                "schedule": {"days_per_week": 3, "session_minutes": 45},
                "preferences": {},
                "equipment": {"available": ["barbell"]},
                "considerations": {"avoided_exercises": ["single_leg_balance"], "movement_restrictions": []},
            }
        }
    )
    squat = next(item for item in held_back["exercises"] if item["exercise_id"] == "barbell_squat")
    assert squat["suggested_load_kg"] == 100
    assert "single_leg_balance" not in _ids(held_back)
    assert "sit_to_stand" in _ids(held_back)
    assert "barbell_squat" in _ids(held_back)


def test_beginners_and_advanced_athletes_still_differ_at_the_same_age():
    beginner = generate_local_plan(
        {
            "assessment": {
                "identity": {"age_range": "65_74"},
                "goals": {"primary": "maintain_fitness", "priority_muscles": []},
                "experience": {"level": "beginner", "working_sets": {}},
                "schedule": {"days_per_week": 3, "session_minutes": 25},
                "preferences": {},
                "equipment": {"available": ["bodyweight"]},
                "considerations": {"avoided_exercises": [], "movement_restrictions": []},
            }
        }
    )
    advanced = generate_local_plan(_strength_profile("65_74"))
    assert "bodyweight_squat" in _ids(beginner)
    assert "barbell_squat" not in _ids(beginner)
    assert "barbell_squat" in _ids(advanced)
    assert "single_leg_balance" in _ids(beginner)
    assert "single_leg_balance" in _ids(advanced)
    assert _ids(beginner) != _ids(advanced)


def test_missing_age_does_not_block_generation_and_round_trips():
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
    assert plan["exercises"]
    context = build_workout_context({"assessment": {"goals": {"primary": "build_muscle"}, "experience": {"level": "intermediate"}, "schedule": {"days_per_week": 3, "session_minutes": 45}, "equipment": {"available": ["dumbbells"]}, "considerations": {"avoided_exercises": []}}})
    assert context["age_range"] is None
    assert any("Age is context" in rule for rule in build_workout_context(_strength_profile("75_plus"))["rules"])
    with TestClient(app) as client:
        saved = client.post(
            "/profiles",
            json={
                "goal": "build_strength",
                "experience": "advanced",
                "days_per_week": 4,
                "session_duration_minutes": 60,
                "equipment": ["barbell"],
                "limitations": [],
                "display_name": "Age Athlete",
                "age_range": "65_74",
                "assessment": {
                    "identity": {"display_name": "Age Athlete", "age_range": "65_74", "adult_confirmed": True},
                    "goals": {"primary": "increase_strength", "priority_muscles": ["quadriceps"]},
                    "experience": {"level": "advanced", "working_sets": {"barbell_squat": {"weight_kg": 100, "reps": 5}}},
                    "schedule": {"days_per_week": 4, "session_minutes": 60},
                    "equipment": {"available": ["barbell"]},
                    "considerations": {"avoided_exercises": [], "movement_restrictions": []},
                },
            },
        )
        assert saved.status_code == 200
        assert saved.json()["age_range"] == "65_74"
        again = client.get("/profiles/me")
        assert again.json()["age_range"] == "65_74"
        assert again.json()["assessment"]["identity"]["age_range"] == "65_74"
        generated = client.post("/workouts/generate", json={"focus": "legs"})
        assert generated.status_code == 200
        ids = [item["exercise_id"] for item in generated.json()["exercises"]]
        assert "barbell_squat" in ids
        assert "single_leg_balance" in ids


def test_legacy_profile_stays_readable_without_inventing_equipment():
    legacy = assessment_from_legacy(
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
    assert legacy["identity"]["training_environment"] is None
    assert legacy["goals"]["secondary"] is None
    projected = project_assessment(legacy)
    assert projected["current_squat_load_kg"] == 40
    assert "barbell" in projected["equipment"]


def test_pounds_convert_to_kilograms():
    assert to_kg(100, "lb") == 45.36
    assert to_kg(40, "kg") == 40


def test_muse_context_omits_body_size_and_marks_missing_fields():
    context = build_workout_context(
        {
            "assessment": {
                "identity": {"display_name": "Alex", "height_cm": 180, "weight_kg": 80, "age_range": None},
                "goals": {"primary": "build_muscle", "secondary": None, "priority_muscles": ["full_body"]},
                "experience": {"level": "intermediate", "working_sets": {}, "exercise_familiarity": {}},
                "schedule": {"days_per_week": 4, "preferred_days": [], "session_minutes": 50},
                "preferences": {"preferred_split": "ghostrep_decides"},
                "equipment": {"available": ["barbell", "dumbbells"]},
                "considerations": {"avoided_exercises": ["bench_press"], "movement_restrictions": []},
            }
        }
    )
    encoded = json.dumps(context)
    assert "height_cm" not in encoded
    assert "Alex" not in encoded
    assert "bench_press" not in [item["id"] for item in context["exercise_catalog"]]
    assert "secondary_goal" in context["missing_optional_fields"]
    assert context["provider"] == "unsent"
    assert context["output_schema"]["required"] == ["workout_name", "duration_minutes", "exercises"]


def test_profile_column_migration_is_idempotent():
    migrate_profile_columns()
    migrate_profile_columns()


def test_strength_athlete_differs_from_beginner_and_honors_exclusions():
    athlete = generate_local_plan(
        {
            "assessment": {
                "goals": {"primary": "increase_strength", "priority_muscles": ["quadriceps", "back"]},
                "experience": {"level": "advanced", "working_sets": {"barbell_squat": {"weight_kg": 120, "reps": 5}}},
                "schedule": {"days_per_week": 4, "session_minutes": 70},
                "preferences": {"preferred_split": "upper_lower", "other_activities": []},
                "equipment": {"preset": "full_gym", "available": ["barbell", "dumbbells", "squat_rack", "leg_press"]},
                "considerations": {"avoided_exercises": ["romanian_deadlift"], "movement_restrictions": []},
            }
        }
    )
    beginner = generate_local_plan(
        {
            "assessment": {
                "goals": {"primary": "maintain_fitness", "priority_muscles": []},
                "experience": {"level": "beginner", "working_sets": {}},
                "schedule": {"days_per_week": 3, "session_minutes": 25},
                "preferences": {"other_activities": []},
                "equipment": {"preset": "bodyweight", "available": ["bodyweight"]},
                "considerations": {"avoided_exercises": [], "movement_restrictions": []},
            }
        }
    )
    athlete_ids = _ids(athlete)
    beginner_ids = _ids(beginner)
    assert athlete_ids != beginner_ids
    assert "barbell_squat" in athlete_ids
    assert "romanian_deadlift" not in athlete_ids
    assert "bodyweight_squat" in beginner_ids
    squat = next(item for item in athlete["exercises"] if item["exercise_id"] == "barbell_squat")
    assert squat["sets"] == 4
    assert squat["target_reps"] == 5
    assert squat["suggested_load_kg"] == 120
    issues = validate_model_plan(
        {"duration_minutes": 120, "exercises": [{"exercise_id": "romanian_deadlift"}, {"exercise_id": "barbell_squat"}]},
        {"assessment": {"goals": {"primary": "increase_strength"}, "experience": {"level": "advanced"}, "schedule": {"days_per_week": 4, "session_minutes": 60}, "equipment": {"available": ["barbell"]}, "considerations": {"avoided_exercises": ["romanian_deadlift"], "movement_restrictions": []}}},
    )
    assert any("excluded" in issue for issue in issues)
    assert any("longer" in issue for issue in issues)


def test_sqlite_draft_survives_reopen_without_replacing_the_plan(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/ghostrep.db")
    Base.metadata.create_all(engine)
    migrate_profile_columns(engine)
    migrate_profile_columns(engine)
    db = sessionmaker(bind=engine)()
    user = User(display_name="Alex")
    db.add(user)
    db.flush()
    profile = Profile(
        user_id=user.id,
        goal="build_strength",
        experience="intermediate",
        days_per_week=4,
        session_duration_minutes=50,
        equipment_json='["barbell"]',
        limitations_json="[]",
        assessment_json=json.dumps({"goals": {"primary": "increase_strength"}}),
        submitted=True,
    )
    db.add(profile)
    db.add(WorkoutPlan(user_id=user.id, name="Leg Day A", status="active", source="local", duration_minutes=50))
    db.commit()
    profile.draft_json = json.dumps({"goals": {"primary": "build_muscle"}})
    db.commit()
    profile_id = profile.id
    engine.dispose()

    reopened = create_engine(f"sqlite:///{tmp_path}/ghostrep.db")
    session = sessionmaker(bind=reopened)()
    stored = session.get(Profile, profile_id)
    assert stored is not None
    assert stored.submitted is True
    assert json.loads(stored.assessment_json)["goals"]["primary"] == "increase_strength"
    assert json.loads(stored.draft_json)["goals"]["primary"] == "build_muscle"
    assert session.query(WorkoutPlan).count() == 1
    reopened.dispose()


def test_draft_does_not_replace_another_users_profile():
    with TestClient(app) as alice:
        saved = alice.post(
            "/profiles",
            json={
                "goal": "build_strength",
                "experience": "intermediate",
                "days_per_week": 4,
                "session_duration_minutes": 50,
                "equipment": ["barbell"],
                "limitations": [],
                "display_name": "Alice",
            },
        )
        assert saved.status_code == 200
        draft = alice.put("/profiles/draft", json={"draft": {"identity": {"display_name": "Draft Alice"}}})
        assert draft.status_code == 200
        me = alice.get("/profiles/me")
        assert me.status_code == 200
        assert me.json()["goal"] == "build_strength"
        assert me.json()["display_name"] == "Alice"
        plans_before = alice.get("/workouts").json()["plans"]
        assert alice.get("/profiles/draft").json()["draft"]["identity"]["display_name"] == "Draft Alice"
        assert alice.get("/workouts").json()["plans"] == plans_before
    with TestClient(app) as bob:
        assert bob.get(f"/profiles/{saved.json()['id']}").status_code == 404
        assert bob.get("/profiles/draft").status_code == 404
