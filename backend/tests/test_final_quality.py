"""Final training-flow regressions. All model calls are offline."""
from unittest.mock import patch
from app.config import Settings
from app.services.meta.contracts import accept_week, build_coaching_model_input
from app.services.meta.gateway import MetaGateway, approval_hint
from tests.test_program_week import _client
from tests.test_meta_offline import PROFILE, _week


def test_no_application_usage_caps_by_default(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, enable_meta_api=True, model_api_key="offline-key", workout_provider="meta_live")
    assert settings.meta_max_calls_per_session is None
    assert settings.meta_estimated_spend_limit_usd is None
    gateway = MetaGateway(settings)
    with patch.object(gateway, "_session_calls", return_value=10000) as calls, patch.object(gateway, "_session_spend", return_value=10000) as spend:
        gateway.authorize(model=settings.muse_model, purpose="workout_generation", estimated_cost_usd=10000, approval_token=approval_hint(settings, "workout_generation"))
        calls.assert_not_called()
        spend.assert_not_called()


def test_week_preserves_personalized_warmup_and_rationale():
    payload = _week()
    payload["sessions"][0].update(rationale="Prioritize squat practice before accessories.", warmup=["Walk for three minutes.", "Practice gradual lighter squat sets."])
    plan = accept_week(payload, PROFILE, 0, "muse_spark", "live")
    assert plan["warmup"] == payload["sessions"][0]["warmup"]
    assert plan["rationale"] == plan["schedule"][0]["rationale"]


def test_coach_gets_effort_and_actual_early_to_late_trend():
    reps = [{"rep_id": i + 1, "start_seconds": i * 4, "bottom_seconds": i * 4 + 2, "end_seconds": i * 4 + 2 + ascent} for i, ascent in enumerate([1.2, 1.2, 1.0, 1.0])]
    measured = build_coaching_model_input({"reps": reps, "quality": {"usable": True}, "current_reps": 8, "completed_reps": 4, "reported_rpe": 7})
    assert measured["prescription"]["target_reps"] == 8
    assert measured["prescription"]["reported_rpe"] == 7
    assert measured["within_set_trend"]["ascent_change_percent"] < 0
    assert measured["within_set_trend"]["late_rep_ids"] == [3, 4]


def test_prepare_session_is_reviewable_owned_and_does_not_replace_current_plan():
    client, plan = _client()
    try:
        week = client.get("/program", params={"today": "2026-10-30"}).json()
        day = next(d for d in week["weeks"][0]["days"] if d["kind"] == "training" and d["is_preview"])
        with patch("app.services.meta.muse.MuseProvider.generate_workout", side_effect=AssertionError("preparing must not call a model")):
            response = client.post("/program/prepare", json={"today": "2026-10-30", "weekday": day["weekday"]})
        assert response.status_code == 200, response.text
        proposal = response.json()
        assert proposal["status"] == "proposed"
        assert [e["exercise_id"] for e in proposal["exercises"]] == [e["exercise_id"] for e in day["workout"]["exercises"]]
        assert client.get("/workouts/next").json()["plan"]["id"] == plan["id"]
        recovery = next(d for d in week["weeks"][0]["days"] if d["kind"] == "recovery")
        assert client.post("/program/prepare", json={"today": "2026-10-30", "weekday": recovery["weekday"]}).status_code == 400
        client.cookies.clear()
        assert client.get(f"/workouts/{proposal['id']}").status_code == 404
    finally:
        client.__exit__(None, None, None)
