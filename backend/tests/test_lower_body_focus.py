from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.meta.contracts import accept_week, build_workout_messages
from app.services.meta.errors import MetaRejected
from app.services.workout.context import squat_first_requested
from app.services.workout.local_planner import generate_local_week
from tests.test_plan_experience import profile
from tests.test_meta_offline import _four_day_week


def lower_profile(split="upper_lower", days=4):
    athlete = profile(split, days)
    athlete["assessment"]["equipment"]["available"].append("pull_up_bar")
    athlete["assessment"]["goals"]["training_focus"] = "lower_body"
    return athlete


@pytest.mark.parametrize("split,days", [("upper_lower", 4), ("full_body", 3), ("push_pull_legs", 3)])
def test_lower_body_focus_opens_each_week_with_barbell_squat(split, days):
    athlete = lower_profile(split, days)
    before = deepcopy(athlete)
    for index in [0, days]:
        week = generate_local_week(athlete, session_index=index)
        assert week["schedule"][0]["exercises"][0]["exercise_id"] == "barbell_squat"
        assert week["exercises"][0]["exercise_id"] == "barbell_squat"
    assert athlete == before


@pytest.mark.parametrize("constraint", ["no_barbell", "excluded", "unfamiliar", "limitation"])
def test_focus_never_invents_equipment_or_overrides_exclusions(constraint):
    athlete = lower_profile()
    assessment = athlete["assessment"]
    if constraint == "no_barbell":
        assessment["equipment"]["available"] = ["dumbbells", "bodyweight"]
    elif constraint == "excluded":
        assessment["considerations"]["avoided_exercises"] = ["barbell_squat"]
    elif constraint == "unfamiliar":
        assessment["experience"]["exercise_familiarity"] = {"barbell_squat": "new"}
    else:
        assessment["considerations"]["movement_restrictions"] = ["acute back pain"]
    assert not squat_first_requested(athlete)
    week = generate_local_week(athlete)
    assert week["exercises"][0]["exercise_id"] != "barbell_squat"


def test_muse_receives_the_preference_and_cannot_return_an_upper_body_opener():
    athlete = lower_profile()
    context = json.loads(build_workout_messages(athlete, None, 0)[1]["content"])
    assert context["user_preferences"]["training_focus"] == "lower_body"
    assert context["opening_exercise"] == "barbell_squat"
    raw = _four_day_week()
    before = deepcopy(raw)
    accepted = accept_week(raw, athlete, 0, "muse_spark", "live")
    assert accepted["exercises"][0]["exercise_id"] == "barbell_squat"
    assert raw == before
    raw["sessions"][0], raw["sessions"][1] = raw["sessions"][1], raw["sessions"][0]
    with pytest.raises(MetaRejected, match="lower-body"):
        accept_week(raw, athlete, 0, "muse_spark", "live")


def test_profile_preference_persists_and_generates_a_video_ready_first_session():
    with TestClient(app) as client:
        saved = client.post("/profiles", json=lower_profile())
        assert saved.status_code == 200
        assert client.get("/profiles/me").json()["assessment"]["goals"]["training_focus"] == "lower_body"
        response = client.post("/workouts/generate", json={})
        assert response.status_code == 200
        week = response.json()
        assert week["exercises"][0]["exercise_id"] == "barbell_squat"
        assert week["exercises"][0]["video_analysis"] is True
        assert week["status"] == "proposed"
        assert client.post(f"/workouts/{week['id']}/accept").status_code == 200
