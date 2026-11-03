"""Saved Muse week and versioned coaching. Isolated temp DB; no live calls."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import SessionLocal
from app.models.entities import RecordedSet
from app.services.coaching.compatibility import recommendation_context
from app.main import app
from app.services.meta.muse import MuseProvider
from app.services.meta.saved_results import SavedResultError, public_coaching, public_workout, require_live_artifact, saved_coaching_path
from tests.helpers import accept_if_proposed, upload_recording_fixture


def _profile(client: TestClient, name="Release"):
    saved = client.post(
        "/profiles",
        json={
            "goal": "build_strength",
            "experience": "intermediate",
            "days_per_week": 4,
            "session_duration_minutes": 50,
            "equipment": ["barbell", "dumbbells", "machines"],
            "current_squat_load_kg": 40,
            "limitations": [],
            "display_name": name,
        },
    )
    assert saved.status_code == 200, saved.text


def _week_result() -> dict:
    session = {
        "workout_name": "Lower Strength Builder",
        "session_type": "lower_strength",
        "duration_minutes": 50,
        "exercises": [
            {
                "exercise_id": "barbell_squat",
                "sets": 4,
                "target_reps": 8,
                "rest_seconds": 120,
                "suggested_load_kg": None,
                "notes": "Keep chest tall.",
            },
            {
                "exercise_id": "romanian_deadlift",
                "sets": 3,
                "target_reps": 10,
                "rest_seconds": 120,
                "suggested_load_kg": None,
                "notes": None,
            },
            {
                "exercise_id": "plank",
                "sets": 3,
                "target_reps": 45,
                "rest_seconds": 60,
                "suggested_load_kg": None,
                "notes": "Hold.",
            },
            {
                "exercise_id": "mystery_lift",
                "sets": 2,
                "target_reps": 8,
                "rest_seconds": 90,
                "suggested_load_kg": None,
                "notes": None,
            },
        ],
    }
    upper = {
        "workout_name": "Upper Strength Builder",
        "session_type": "upper_strength",
        "duration_minutes": 50,
        "exercises": [
            {
                "exercise_id": "bench_press",
                "sets": 4,
                "target_reps": 8,
                "rest_seconds": 120,
                "suggested_load_kg": None,
                "notes": None,
            }
        ],
    }
    return {
        "name": "Lower Strength Builder",
        "source": "muse_spark",
        "source_label": "Muse Spark 1.3 (live)",
        "duration_minutes": 50,
        "estimated_minutes": 50,
        "session_type": "lower_strength",
        "notes": "4-day strength plan. Week session 1 of 4.",
        "schedule": [session, upper, dict(session, workout_name="Lower Strength Builder 2"), dict(upper, workout_name="Upper Strength Builder 2")],
        "exercises": session["exercises"],
    }


def _write_live_week(**overrides) -> None:
    path = get_settings().data_dir / "live-tests" / "workout-attempt-002-reasoning-budget" / "workout-live.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": "Live Meta test workout. Not an offline fixture.",
        "attempt_id": "attempt-002-reasoning-budget",
        "ok": True,
        "chat_calls": 1,
        "schema_validation": "ok",
        "result": _week_result(),
    }
    payload.update(overrides)
    if "result" in overrides:
        payload["result"] = overrides["result"]
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_live_coaching(set_id: str | None, **overrides) -> None:
    # Simulated protocol metadata only, in the temp test DB. Never a live result.
    with SessionLocal() as db:
        rec = db.get(RecordedSet, set_id) if set_id else None
        context = recommendation_context(rec) if rec else {"set_id": set_id}
    path = saved_coaching_path(get_settings())
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "source": "muse_spark",
        "source_label": "Muse protocol fixture (isolated test)",
        "suggested_action": "KEEP_PLAN",
        "summary": "Keep the current prescription.",
        "reason": "The recording does not justify a change.",
        "observations": [],
        "uncertainties": [],
        "evidence_references": [],
        "confidence_notes": [],
        "requires_confirmation": True,
        "recommendation_context": context,
        "set_id": set_id,
    }
    result.update(overrides.pop("result", {}))
    payload = {
        "label": "Live Meta test coaching. Not an offline fixture.",
        "attempt_id": "coaching",
        "ok": True,
        "chat_calls": 1,
        "http_status": 200,
        "schema_validation": "ok",
        "model": "muse-spark-1.3",
        "request_schema": "ghostrep_coaching",
        "result": result,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_fixture_and_failed_ledgers_are_not_live_muse():
    with pytest.raises(SavedResultError):
        require_live_artifact({"ok": True, "chat_calls": 1, "result": {"source": "fixture", "exercises": [{}]}}, kind="workout")
    with pytest.raises(SavedResultError):
        require_live_artifact({"ok": True, "chat_calls": 1, "result": {"source": "local", "exercises": [{}]}}, kind="workout")
    with pytest.raises(SavedResultError):
        require_live_artifact({"ok": False, "chat_calls": 1, "result": {"source": "muse_spark", "exercises": [{}]}}, kind="workout")
    with pytest.raises(SavedResultError):
        require_live_artifact({"ok": True, "chat_calls": 0, "result": {"source": "muse_spark", "exercises": [{}]}}, kind="workout")


def test_saved_live_week_is_visible_without_persisting_or_calling_muse():
    _write_live_week()
    with TestClient(app) as client:
        _profile(client)
        active = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        with patch.object(MuseProvider, "generate_workout", side_effect=AssertionError("viewing must not call Muse")):
            saved = client.get("/workouts/saved-live")
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["available"] is True
        assert body["source"] == "muse_spark"
        assert "live" in body["source_label"].lower()
        assert body["name"] == "Lower Strength Builder"
        assert len(body["schedule"]) == 4
        assert body["exercises"][0]["exercise_id"] == "barbell_squat"
        assert body["exercises"][0]["name"] == "Barbell Back Squat"
        assert body["exercises"][2]["exercise_id"] == "plank"
        assert body["exercises"][2]["name"] == "Plank"
        assert body["exercises"][2]["measure"] == "seconds"
        assert body["exercises"][3]["exercise_id"] == "mystery_lift"
        assert body["exercises"][3]["name"] == "mystery lift"
        assert body["schedule"][0]["exercises"][0]["name"] == "Barbell Back Squat"
        assert client.get("/workouts/next").json()["plan"]["id"] == active["id"]
        assert client.get("/workouts/proposal").json()["plan"] is None


def test_import_saved_week_is_idempotent_and_does_not_replace_the_active_plan():
    _write_live_week()
    with TestClient(app) as client:
        _profile(client)
        active = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        with patch.object(MuseProvider, "generate_workout", side_effect=AssertionError("import must not call Muse")):
            imported = client.post("/workouts/import-saved")
        assert imported.status_code == 200, imported.text
        proposal = imported.json()
        assert proposal["status"] == "proposed"
        assert proposal["source"] == "muse_spark"
        assert proposal["id"] != active["id"]
        assert len(proposal["schedule"]) == 4
        assert client.get("/workouts/next").json()["plan"]["id"] == active["id"]
        again = client.post("/workouts/import-saved").json()
        assert again["id"] == proposal["id"]
        listed = client.get("/workouts").json()["plans"]
        assert sum(1 for plan in listed if plan["id"] == proposal["id"]) == 1
        accepted = client.post(f"/workouts/{proposal['id']}/accept")
        assert accepted.status_code == 200
        assert accepted.json()["source"] == "muse_spark"
        assert client.get(f"/workouts/{active['id']}").json()["status"] == "replaced"


def test_import_saved_rejects_a_fixture_labeled_as_live():
    _write_live_week(result={**_week_result(), "source": "fixture", "source_label": "Saved Muse Spark fixture — not a live call"})
    with TestClient(app) as client:
        _profile(client)
        missing = client.get("/workouts/saved-live").json()
        assert missing["available"] is False
        refused = client.post("/workouts/import-saved")
        assert refused.status_code == 409


def test_saved_coaching_is_review_only_and_preserves_pending():
    with TestClient(app) as client:
        _profile(client)
        plan = accept_if_proposed(client, client.post("/workouts/generate", json={}).json())
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        upload = upload_recording_fixture(client, session["id"], target_reps=8)
        set_id = upload.json()["id"]
        analysis = None
        for _ in range(40):
            analysis = client.get(f"/analysis/{set_id}").json()
            if analysis["status"] in {"COMPLETED", "FAILED"}:
                break
        assert analysis["status"] == "COMPLETED"
        pending = client.get(f"/coaching/{set_id}").json()
        assert pending["user_decision"] == "pending"
        assert pending["stored_versions"] == []
        _write_live_coaching(set_id)
        with patch.object(MuseProvider, "generate_coaching", side_effect=AssertionError("import must not call Muse")):
            imported = client.post(f"/coaching/{set_id}/import-saved")
        assert imported.status_code == 200, imported.text
        body = imported.json()
        assert body["actionable"] is False
        assert body["source"] == "muse_spark"
        assert body["pending_decision_preserved"] is True
        coaching = client.get(f"/coaching/{set_id}").json()
        assert coaching["user_decision"] == "pending"
        assert coaching["id"] == pending["id"]
        assert coaching["source"] == pending["source"]
        assert len(coaching["stored_versions"]) == 1
        assert coaching["stored_versions"][0]["actionable"] is False
        again = client.post(f"/coaching/{set_id}/import-saved").json()
        assert again["id"] == body["id"]
        _write_live_coaching("someone-else")
        mismatch = client.post(f"/coaching/{set_id}/import-saved")
        assert mismatch.status_code == 409


def test_saved_coaching_ownership_and_missing_ledger():
    with TestClient(app) as alice:
        _profile(alice, "Alice")
        plan = accept_if_proposed(alice, alice.post("/workouts/generate", json={}).json())
        session = alice.post("/sessions", json={"plan_id": plan["id"]}).json()
        upload = upload_recording_fixture(alice, session["id"], target_reps=8)
        set_id = upload.json()["id"]
        for _ in range(40):
            if alice.get(f"/analysis/{set_id}").json()["status"] in {"COMPLETED", "FAILED"}:
                break
        path = saved_coaching_path(get_settings())
        if path.exists():
            path.unlink()
        missing = alice.post(f"/coaching/{set_id}/import-saved")
        assert missing.status_code == 404
        _write_live_coaching(set_id)
        alice.post(f"/coaching/{set_id}/import-saved")
        with TestClient(app) as bob:
            _profile(bob, "Bob")
            assert bob.get(f"/coaching/{set_id}").status_code == 404
            assert bob.post(f"/coaching/{set_id}/import-saved").status_code == 404
            assert bob.get(f"/analysis/{set_id}").status_code == 404
            assert bob.get(f"/workouts/{plan['id']}").status_code == 404


_live_week = os.environ.get("GHOSTREP_TEST_SAVED_WORKOUT")
REAL_WEEK = Path(_live_week).expanduser() if _live_week else None


@pytest.mark.skipif(not REAL_WEEK or not REAL_WEEK.is_file(), reason="optional GHOSTREP_TEST_SAVED_WORKOUT is not provided")
def test_on_disk_live_week_labels_names_without_another_call():
    assert REAL_WEEK is not None
    original = REAL_WEEK.read_bytes()
    dest = get_settings().data_dir / "live-tests" / "workout-attempt-002-reasoning-budget" / "workout-live.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(REAL_WEEK.read_bytes())
    with TestClient(app) as client:
        _profile(client)
        with patch.object(MuseProvider, "generate_workout", side_effect=AssertionError("viewing must not call Muse")):
            saved = client.get("/workouts/saved-live")
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["available"] is True
        assert body["source"] == "muse_spark"
        assert "live" in body["source_label"].lower()
        squat = next(item for item in body["exercises"] if item["exercise_id"] == "barbell_squat")
        assert squat["name"] == "Barbell Back Squat"
        plank = next((item for item in body["exercises"] if item["exercise_id"] == "plank"), None)
        if plank:
            assert plank["measure"] == "seconds"
            assert plank["name"] == "Plank"
            assert plank["target_reps"] == 45
            assert "Recorded as a 45-second hold" in plank["notes"]
            assert any("explicit timed-hold normalization" in warning for warning in body["warnings"])
        imported = client.post("/workouts/import-saved")
        assert imported.status_code == 200, imported.text
        proposal = imported.json()
        assert proposal["status"] == "proposed"
        assert proposal["source"] == "muse_spark"
        named = next(item for item in proposal["exercises"] if item["exercise_id"] == "barbell_squat")
        assert named["name"] == "Barbell Back Squat"
        again = client.post("/workouts/import-saved").json()
        assert again["id"] == proposal["id"]
        assert REAL_WEEK.read_bytes() == original


@pytest.mark.parametrize("notes", ["Hold comfortably.", "Hold 30 seconds or hold 45 seconds.", "Hold for 30-45 seconds.", "Maybe hold 45 seconds."])
def test_ambiguous_hold_notes_do_not_invent_a_duration(notes):
    from app.services.workout.quality import normalize_saved_exercises
    raw = [{"exercise_id": "plank", "target_reps": 1, "notes": notes}]
    normalized, transforms = normalize_saved_exercises(raw)
    assert normalized == raw
    assert transforms == []


def test_public_helpers_keep_live_provenance():
    raw = {"ok": True, "chat_calls": 1, "attempt_id": "attempt-002-reasoning-budget", "result": _week_result()}
    public = public_workout(raw, {"days_per_week": 4, "equipment": ["barbell"], "experience": "intermediate"})
    assert public["source"] == "muse_spark"
    assert public["available"] is True
    coach = public_coaching(
        {
            "ok": True,
            "chat_calls": 1,
            "http_status": 200, "schema_validation": "ok", "model": "muse-spark-1.3", "request_schema": "ghostrep_coaching",
            "result": {"source": "muse_spark", "suggested_action": "KEEP_PLAN", "summary": "Keep", "reason": "ok", "set_id": "fixture-id", "recommendation_context": {}},
        }
    )
    assert coach["source"] == "muse_spark"
    assert coach["suggested_action"] == "KEEP_PLAN"
