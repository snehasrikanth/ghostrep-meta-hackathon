"""Weekly-plan clarity and lifecycle regressions; no live model requests."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.workout.catalog import CATALOG
from app.services.meta.contracts import build_workout_messages


def profile(split, days=4):
    return {
        "goal": "build_muscle", "experience": "intermediate", "days_per_week": days,
        "session_duration_minutes": 45, "equipment": ["barbell", "dumbbells", "bench", "machines", "bodyweight"],
        "current_squat_load_kg": 40, "limitations": [], "display_name": "Experience Test",
        "assessment": {
            "identity": {"adult_confirmed": True, "preferred_weight_unit": "kg"},
            "goals": {"primary": "build_muscle", "priority_muscles": ["full_body"]},
            "experience": {"level": "intermediate"},
            "schedule": {"days_per_week": days, "session_minutes": 45, "preferred_days": ["monday", "tuesday", "thursday", "saturday"][:days]},
            "preferences": {"preferred_split": split},
            "equipment": {"available": ["barbell", "dumbbells", "bench", "machines", "bodyweight"]},
            "considerations": {"avoided_exercises": [], "movement_restrictions": []},
        },
    }


@pytest.mark.parametrize("split", ["full_body", "upper_lower"])
def test_balanced_priority_keeps_the_selected_split_and_full_week(split):
    with TestClient(app) as client:
        saved = client.post("/profiles", json=profile(split)).json()
        proposal = client.post("/workouts/generate", json={}).json()
        assert len(proposal["schedule"]) == 4
        assert proposal["training_structure"]["split"] == split
        assert proposal["training_structure"]["sessions_per_week"] == 4
        for session in proposal["schedule"]:
            patterns = {CATALOG[e["exercise_id"]]["pattern"] for e in session["exercises"]}
            upper = bool(patterns & {"push", "push_vertical", "pull", "pull_vertical"})
            lower = bool(patterns & {"squat", "hinge", "lunge"})
            if split == "full_body":
                assert session["session_type"].startswith("full_body")
                assert upper and lower
            elif session["session_type"] == "upper":
                assert upper and not lower
            else:
                assert session["session_type"] == "lower"
                assert lower and not upper
        assert client.get("/profiles/me").json() == saved
        accepted = client.post(f"/workouts/{proposal['id']}/accept").json()
        assert accepted["status"] == "active"
        week = client.get("/program", params={"today": "2026-10-30"}).json()
        assert week["is_accepted"] and week["split"] == split


def test_blocked_proposal_survives_session_selection_and_resume():
    with TestClient(app) as client:
        client.post("/profiles", json=profile("upper_lower"))
        first = client.post("/workouts/generate", json={}).json()
        client.post(f"/workouts/{first['id']}/accept")
        session = client.post("/sessions", json={"plan_id": first["id"]}).json()
        ex = first["exercises"][0]
        logged = client.post(f"/sessions/{session['id']}/sets", json={"exercise_id": ex["exercise_id"], "set_index": 1, "completed_reps": 6, "load_kg": 40}).json()
        proposal = client.post("/workouts/generate", json={}).json()
        blocked = client.post(f"/workouts/{proposal['id']}/accept")
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["open_plan_id"] == first["id"]
        assert client.get(f"/workouts/{proposal['id']}").json()["status"] == "proposed"
        week = client.get("/program", params={"today": "2026-10-30"}).json()
        day = next(d for d in week["weeks"][0]["days"] if d["kind"] == "training" and d["is_preview"])
        selected = client.post("/program/prepare", json={"today": "2026-10-30", "weekday": day["weekday"]}).json()
        assert selected["training_structure"]["proposal_kind"] == "session"
        assert selected["name"] == day["workout"]["name"]
        assert client.get(f"/workouts/{proposal['id']}").json()["status"] == "proposed"
        assert client.get("/workouts/proposal").json()["plan"]["id"] == proposal["id"]
        paused = client.post(f"/sessions/{session['id']}/pause").json()
        assert paused["status"] == "paused"
        resumed = client.post(f"/sessions/{session['id']}/resume").json()
        assert resumed["status"] == "active" and resumed["sets"][0]["id"] == logged["id"]
        assert client.post(f"/sessions/{session['id']}/complete").status_code == 200
        assert client.post(f"/workouts/{proposal['id']}/accept").json()["status"] == "active"
        assert client.get(f"/sessions/{session['id']}").json()["sets"][0]["id"] == logged["id"]


def test_accepted_week_keeps_its_structure_until_new_preferences_are_accepted():
    with TestClient(app) as client:
        client.post("/profiles", json=profile("full_body"))
        first = client.post("/workouts/generate", json={}).json()
        client.post(f"/workouts/{first['id']}/accept")
        changed = client.post("/profiles", json=profile("upper_lower", days=3)).json()
        proposal = client.post("/workouts/generate", json={}).json()
        week = client.get("/program", params={"today": "2026-10-30"}).json()
        assert week["split"] == "full_body" and week["days_per_week"] == 4
        assert client.get("/profiles/me").json() == changed
        client.post(f"/workouts/{proposal['id']}/accept")
        week = client.get("/program", params={"today": "2026-10-30"}).json()
        assert week["split"] == "upper_lower" and week["days_per_week"] == 3


def test_model_prompt_distinguishes_balanced_priority_from_session_structure():
    import json
    for split in ("full_body", "upper_lower"):
        p = profile(split)
        original = deepcopy(p)
        messages = build_workout_messages(p, None, 0)
        context = json.loads(messages[1]["content"])
        assert context["requested_training_structure"] == split
        assert "balanced development across the week" in messages[0]["content"]
        assert p == original
