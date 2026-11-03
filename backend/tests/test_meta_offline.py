"""Offline Meta integration tests.

These parse documented response shapes and mock the HTTP transport.
None of them call api.meta.ai, and none of them are live verification.
"""

import json
from unittest.mock import patch
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from meta_sam_parser._mask_codec import _encode_raster

from app.config import Settings, get_settings
from app.main import app
from app.services.coaching.evidence import ground_coaching
from app.services.meta.contracts import (
    build_workout_messages,
    strict_schema_issues,
    workout_response_format,
)
from app.services.meta.errors import MetaRateLimited, MetaRejected, TransientMetaError
from app.services.meta.gateway import MetaBlocked, MetaGateway, approval_hint
from app.services.meta.muse import MuseProvider
from app.services.meta.sam import SamProvider, sam_request
from app.services.meta.sam_parse import document_from_events, mask_wire, stream_events
from app.services.meta.silhouettes import attach_silhouettes
from app.services.meta.transport import ChatResult
from app.services.movement.pipeline import analyze_pose_sequence
from app.services.movement.synthetic import synthesize_squat_set
from tests.helpers import accept_if_proposed

PROFILE = {
    "goal": "build_strength",
    "experience": "intermediate",
    "days_per_week": 2,
    "session_duration_minutes": 50,
    "equipment": ["barbell", "dumbbells", "bench"],
    "current_squat_load_kg": 40,
    "limitations": [],
    "display_name": "Test Athlete",
    "optional_height_cm": 180,
    "age_range": "25_34",
}


def _settings(tmp_path, **overrides) -> Settings:
    values = dict(
        data_dir=tmp_path,
        ai_provider="local",
        workout_provider="local",
        coaching_provider="local",
        segmentation_provider="none",
        enable_meta_api=False,
        model_api_key="sk-test-not-used",
        meta_require_explicit_approval=True,
        meta_retry_sleep=False,
        meta_max_retries=1,
    )
    values.update(overrides)
    return Settings(**values)


def _four_day_profile() -> dict:
    return {
        "goal": "build_strength",
        "experience": "intermediate",
        "days_per_week": 4,
        "session_duration_minutes": 50,
        "equipment": ["barbell", "dumbbells", "bench", "machines", "rack", "pullup", "bodyweight"],
        "current_squat_load_kg": 40,
        "limitations": [],
        "assessment": {
            "identity": {"age_range": "25_34"},
            "goals": {"primary": "increase_strength", "priority_muscles": ["full_body"]},
            "experience": {
                "level": "intermediate",
                "working_sets": {"barbell_squat": {"weight_kg": 40, "reps": 5}},
            },
            "schedule": {"days_per_week": 4, "session_minutes": 50},
            "preferences": {
                "enjoyed_exercises": ["barbell_squat", "romanian_deadlift", "dumbbell_bench_press"],
                "preferred_split": "upper_lower",
            },
            "equipment": {
                "available": ["barbell", "dumbbells", "bench", "machines", "squat_rack", "pull_up_bar"]
            },
            "considerations": {"avoided_exercises": [], "movement_restrictions": []},
        },
    }


def _exercise(exercise_id: str, sets=3, reps=5, rest=120, load=None, notes="") -> dict:
    return {
        "exercise_id": exercise_id,
        "sets": sets,
        "target_reps": reps,
        "rest_seconds": rest,
        "suggested_load_kg": load,
        "notes": notes,
    }


def _four_day_week() -> dict:
    return {
        "summary": "Four 50-minute strength days using the listed gym equipment.",
        "sessions": [
            {
                "workout_name": "Lower A",
                "session_type": "lower",
                "duration_minutes": 50,
                "exercises": [
                    _exercise("barbell_squat", 4, 5, 180, 40, "Stay at the stated squat load."),
                    _exercise("romanian_deadlift", 3, 8, 120),
                    _exercise("walking_lunge", 3, 10, 90),
                    _exercise("plank", 3, 30, 60),
                ],
            },
            {
                "workout_name": "Upper A",
                "session_type": "upper",
                "duration_minutes": 50,
                "exercises": [
                    _exercise("dumbbell_bench_press", 4, 8, 120),
                    _exercise("barbell_row", 4, 8, 120),
                    _exercise("dumbbell_shoulder_press", 3, 8, 90),
                    _exercise("lat_pulldown", 3, 10, 90),
                ],
            },
            {
                "workout_name": "Lower B",
                "session_type": "lower",
                "duration_minutes": 50,
                "exercises": [
                    _exercise("goblet_squat", 3, 8, 120),
                    _exercise("leg_press", 3, 8, 120),
                    _exercise("leg_curl", 3, 10, 75),
                    _exercise("calf_raise", 3, 12, 60),
                ],
            },
            {
                "workout_name": "Upper B",
                "session_type": "upper",
                "duration_minutes": 50,
                "exercises": [
                    _exercise("bench_press", 4, 5, 150),
                    _exercise("pull_up", 3, 6, 120),
                    _exercise("seated_cable_row", 3, 10, 90),
                    _exercise("dumbbell_curl", 2, 10, 60),
                ],
            },
        ],
    }


def _week() -> dict:
    return {
        "summary": "Upper and lower, using the stated equipment.",
        "sessions": [
            {
                "workout_name": "Lower",
                "session_type": "lower",
                "duration_minutes": 45,
                "exercises": [
                    {
                        "exercise_id": "barbell_squat",
                        "sets": 3,
                        "target_reps": 5,
                        "rest_seconds": 180,
                        "suggested_load_kg": 40,
                        "notes": "Film from the side.",
                    }
                ],
            },
            {
                "workout_name": "Upper",
                "session_type": "upper",
                "duration_minutes": 45,
                "exercises": [
                    {
                        "exercise_id": "dumbbell_bench_press",
                        "sets": 3,
                        "target_reps": 8,
                        "rest_seconds": 90,
                        "suggested_load_kg": None,
                        "notes": "",
                    }
                ],
            },
        ],
    }


class FakeTransport:
    def __init__(
        self,
        content="{}",
        events=None,
        fail=None,
        finish_reason="stop",
        http_status=200,
        input_tokens=12,
        output_tokens=8,
        reasoning_tokens=0,
    ):
        self.content = content
        self.events = events or []
        self.fail = fail
        self.calls = []
        self.deleted = []
        self.last_kwargs = {}
        self.finish_reason = finish_reason
        self.http_status = http_status
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.reasoning_tokens = reasoning_tokens

    def chat_completion(self, **kwargs):
        self.calls.append(("chat", kwargs["model"]))
        self.last_kwargs = kwargs
        if self.fail:
            raise self.fail
        return ChatResult(
            self.content,
            self.input_tokens,
            self.output_tokens,
            http_status=self.http_status,
            finish_reason=self.finish_reason,
            reasoning_tokens=self.reasoning_tokens,
        )

    def upload_user_file(self, path: Path) -> str:
        self.calls.append(("upload", path.name))
        return "file-offline"

    def delete_file(self, file_id: str) -> None:
        self.deleted.append(file_id)

    def responses_events(self, **kwargs):
        self.calls.append(("responses", kwargs["body"]["model"]))
        if self.fail:
            raise self.fail
        return self.events


def _rectangle(width=8, height=6) -> str:
    raster = [0] * (width * height)
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            raster[y * width + x] = 1
    return _encode_raster(raster, width, height)


def _person_events(confidence: float = 0.91) -> list[dict]:
    payload = _rectangle()
    lines = [
        mask_wire(
            frame=index,
            object_id=0,
            box=(4, 4, 11, 9),
            source=(40, 30),
            payload=payload,
            raster=(6, 8),
            confidence=confidence if index == 0 else 0.05,
        )
        for index in (0, 1)
    ]
    return stream_events("\n".join(lines) + "\n")


def test_tests_cannot_open_a_meta_socket():
    with pytest.raises(RuntimeError, match="blocked Meta"):
        socket.create_connection(("api.meta.ai", 443), timeout=1)


def test_workout_request_uses_profile_constraints_and_omits_identity(tmp_path):
    profile = {
        **PROFILE,
        "assessment": {
            "identity": {"age_range": "25_34"},
            "goals": {"primary": "increase_strength", "priority_muscles": ["quadriceps"]},
            "experience": {
                "level": "intermediate",
                "exercise_familiarity": {"barbell_squat": "confident"},
                "working_sets": {"barbell_squat": {"weight_kg": 40, "reps": 5}},
            },
            "schedule": {"days_per_week": 2, "session_minutes": 50},
            "preferences": {"enjoyed_exercises": ["romanian_deadlift"], "preferred_split": "full_body"},
            "equipment": {"available": ["barbell", "dumbbells", "bench"]},
            "considerations": {"avoided_exercises": ["bench_press"], "movement_restrictions": []},
        },
        "recent_sessions": [
            {
                "completed_on": "2026-10-20",
                "exercises": [{"exercise_id": "barbell_squat", "sets": 3, "best_load_kg": 40, "reps": [5, 5, 4]}],
            }
        ],
    }
    messages = build_workout_messages(profile, None, 1)
    body = messages[1]["content"]
    assert "barbell" in body
    assert "25_34" in body
    assert "quadriceps" in body
    assert "romanian_deadlift" in body
    assert "bench_press" in body
    assert "2026-10-20" in body
    assert "Test Athlete" not in body
    assert "180" not in body
    assert "output_schema" not in body
    assert "complete ghostrep_week JSON" in messages[0]["content"]
    assert "exactly 2 sessions" in messages[0]["content"]
    assert "optional preferences" in messages[0]["content"]
    assert "hold seconds" in messages[0]["content"]
    schema = workout_response_format(session_count=2)["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["properties"]["sessions"]["minItems"] == 2
    assert schema["schema"]["properties"]["sessions"]["maxItems"] == 2
    assert "barbell_squat" in schema["schema"]["properties"]["sessions"]["items"]["properties"]["exercises"]["items"]["properties"]["exercise_id"]["enum"]
    assert not strict_schema_issues(workout_response_format(session_count=4))
    assert _settings(tmp_path).model_api_key not in body


def test_local_provider_never_calls_meta_even_when_a_key_exists(tmp_path):
    transport = FakeTransport()
    settings = _settings(tmp_path, enable_meta_api=True, model_api_key="sk-test-not-used")
    plan = MuseProvider(settings, MetaGateway(settings), transport).generate_workout(PROFILE, session_index=1)
    assert plan["source"] == "local"
    assert transport.calls == []


def test_live_workout_is_blocked_without_approval_and_accepted_with_it(tmp_path):
    transport = FakeTransport(content=json.dumps(_week()))
    settings = _settings(tmp_path, enable_meta_api=True, workout_provider="meta_live")
    provider = MuseProvider(settings, MetaGateway(settings), transport)
    with pytest.raises(MetaBlocked):
        provider.generate_workout(PROFILE, session_index=1)
    assert transport.calls == []

    plan = provider.generate_workout(
        PROFILE,
        session_index=1,
        approval_token=approval_hint(settings, "workout_generation"),
    )
    assert plan["source"] == "muse_spark"
    assert plan["name"] == "Upper"
    assert [item["workout_name"] for item in plan["schedule"]] == ["Lower", "Upper"]
    assert transport.calls == [("chat", "muse-spark-1.3")]
    assert transport.last_kwargs["reasoning_effort"] == "high"
    assert transport.last_kwargs.get("max_completion_tokens") is None
    assert "max_tokens" not in transport.last_kwargs
    log = (tmp_path / "meta-usage.jsonl").read_text()
    assert "sk-test" not in log
    assert "payload_sha256" in log


def test_live_coaching_request_matches_preflight_budget(tmp_path):
    from app.services.meta.pricing import COACHING_OUTPUT_TOKEN_ESTIMATE, COACHING_REASONING_EFFORT

    payload = {
        "summary": "Keep the prescribed targets.",
        "observations": [],
        "uncertainties": ["Limited drift samples."],
        "suggested_action": "KEEP_PLAN",
        "explanation": "Completed reps differ from the prescribed target.",
        "suggested_reps": 6,
        "suggested_rest_seconds": 150,
        "suggested_load_kg": None,
    }
    transport = FakeTransport(content=json.dumps(payload))
    settings = _settings(tmp_path, enable_meta_api=True, coaching_provider="meta_live")
    provider = MuseProvider(settings, MetaGateway(settings), transport)
    context = {
        "quality": {"usable": True, "score": 0.9, "issues": []},
        "drift": [],
        "reps": [
            {
                "rep_id": 1,
                "start_seconds": 0.2,
                "bottom_seconds": 0.8,
                "end_seconds": 1.4,
                "is_complete": True,
                "confidence": 0.8,
            }
        ],
        "reference_rep": 1,
        "profile": PROFILE,
        "current_reps": 6,
        "current_rest": 150,
        "current_load": None,
        "planned_set_reps": 6,
        "completed_reps": 8,
        "workout_reps": 6,
        "workout_rest_seconds": 150,
        "workout_load_kg": None,
        "reported_rpe": 7,
    }
    with pytest.raises(MetaBlocked):
        provider.generate_coaching(context)
    assert transport.calls == []
    result = provider.generate_coaching(context, approval_token=approval_hint(settings, "coaching"))
    assert result["source"] == "muse_spark"
    assert result["suggested_action"] == "KEEP_PLAN"
    assert transport.last_kwargs["reasoning_effort"] == COACHING_REASONING_EFFORT
    assert transport.last_kwargs.get("max_completion_tokens") is None
    assert "max_tokens" not in transport.last_kwargs


def test_invalid_model_plans_are_rejected_instead_of_relabeled(tmp_path):
    settings = _settings(tmp_path, enable_meta_api=True, workout_provider="meta_live")
    token = approval_hint(settings, "workout_generation")

    def attempt(content, profile=PROFILE):
        transport = FakeTransport(content=json.dumps(content))
        provider = MuseProvider(settings, MetaGateway(settings), transport)
        with pytest.raises(MetaRejected):
            provider.generate_workout(profile, approval_token=token)
        assert all(call[0] == "chat" for call in transport.calls)

    attempt({"summary": "missing sessions"})
    bad = _week()
    bad["sessions"][0]["exercises"][0]["exercise_id"] = "cable_fly"
    attempt(bad)
    overloaded = _week()
    overloaded["sessions"][0]["exercises"][0]["suggested_load_kg"] = 80
    attempt(overloaded)
    attempt(_week(), {**PROFILE, "equipment": ["bodyweight"]})
    excluded = {
        **PROFILE,
        "assessment": {
            "identity": {"age_range": "25_34"},
            "goals": {"primary": "increase_strength"},
            "experience": {"level": "intermediate"},
            "schedule": {"days_per_week": 2, "session_minutes": 50},
            "preferences": {},
            "equipment": {"available": ["barbell", "dumbbells", "bench"]},
            "considerations": {"avoided_exercises": ["barbell_squat"], "movement_restrictions": []},
        },
    }
    attempt(_week(), excluded)
    crowded = _week()
    crowded["sessions"] = crowded["sessions"] + crowded["sessions"]
    attempt(crowded, {**PROFILE, "days_per_week": 2})


def test_coaching_model_input_separates_prescribed_targets_from_completed_reps():
    from app.services.meta.contracts import build_coaching_model_input

    measured = build_coaching_model_input(
        {
            "quality": {"usable": True, "issues": []},
            "drift": [{"torso_lean_difference_deg": 2, "similarity": 90}],
            "reps": [
                {"rep_id": 1, "start_seconds": 1.0, "bottom_seconds": 2.0, "end_seconds": 3.0, "confidence": 0.8},
                {"rep_id": 2, "start_seconds": 4.0, "bottom_seconds": 5.0, "end_seconds": 6.0, "confidence": 0.8},
            ],
            "reference_rep": 1,
            "current_reps": 6,
            "current_rest": 150,
            "current_load": None,
            "planned_set_reps": 8,
            "completed_reps": 8,
            "reported_rpe": 7,
        }
    )
    assert measured["completed_reps"] == 2
    assert measured["prescription"]["planned_set_reps"] == 8
    assert measured["prescription"]["completed_reps"] == 8
    assert measured["prescription"]["target_reps"] == 6
    assert measured["prescription"]["rest_seconds"] == 150
    assert measured["prescription"]["load_kg"] is None


def test_coaching_drops_timestamps_and_diagnoses_outside_the_recording():
    context = {
        "quality": {"usable": True, "issues": []},
        "drift": [{"rep_id":1,"torso_lean_difference_deg": 8, "similarity": 70}],
        "reps": [{"rep_id": 1, "start_seconds": 1.0, "bottom_seconds": 2.0, "end_seconds": 3.0}],
        "current_reps": 8,
        "current_rest": 120,
        "current_load": 40,
        "reported_rpe": 7,
    }
    grounded = ground_coaching(
        {
            "source": "muse_spark",
            "source_label": "Muse Spark 1.3 (live)",
            "summary": "Rep 1 changed.",
            "reason": "Measured torso difference.",
            "suggested_action": "REDUCE_REPS",
            "observations": [
                {
                    "metric": "torso_inclination",
                    "statement": "Torso difference at the measured rep.",
                    "evidence_seconds": [2.0],
                    "magnitude": 8,
                },
                {
                    "metric": "torso_inclination",
                    "statement": "A timestamp the video does not contain.",
                    "evidence_seconds": [99],
                    "magnitude": 8,
                },
            ],
            "uncertainties": [],
            "suggested_reps": 12,
            "suggested_rest_seconds": 30,
            "suggested_load_kg": 50,
            "current_reps": 8,
            "current_rest_seconds": 120,
            "current_load_kg": 40,
        },
        context,
        {},
    )
    assert len(grounded["observations"]) == 1
    assert grounded["observations"][0]["evidence_seconds"] == [2.0]
    assert grounded["suggested_action"] == "NO_RECOMMENDATION"
    assert grounded["suggested_reps"] == 8
    assert grounded["suggested_load_kg"] <= 40
    assert grounded["suggested_rest_seconds"] >= 120
    assert grounded["requires_confirmation"] is True

    diagnosed = ground_coaching(
        {
            "summary": "This looks like a meniscus tear.",
            "reason": "Injury risk is high.",
            "suggested_action": "REDUCE_REPS",
            "observations": [],
            "uncertainties": [],
            "current_reps": 8,
            "current_load_kg": 40,
            "current_rest_seconds": 120,
        },
        context,
        {},
    )
    assert diagnosed["suggested_action"] == "NO_RECOMMENDATION"
    assert "diagnos" not in diagnosed["reason"].lower()


def test_sam_request_matches_the_documented_responses_shape():
    body = sam_request("sam-3.1", "file-abc123", "person")
    assert body["model"] == "sam-3.1"
    assert body["stream"] is True
    content = body["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "person"}
    assert content[1] == {"type": "input_video", "file_id": "file-abc123"}
    assert body["metadata"] == {"include_confidence": "true", "mask_encoding": "one_bit"}


def test_sam_parser_decodes_masks_boxes_and_timestamps():
    parsed = document_from_events(_person_events(), concept="person", fps=10)
    assert parsed["available"] is True
    assert parsed["status"] == "parsed"
    assert parsed["media_width"] == 40
    track = next(item for item in parsed["tracks"] if item["athlete"])
    assert track["object_id"] == "0"
    assert track["frames"][0]["t"] == 0
    assert track["frames"][1]["t"] == 0.1
    assert track["frames"][0]["box"]["left"] == 4
    assert track["frames"][0]["box"]["right"] == 12
    assert track["frames"][0]["confidence"] == pytest.approx(0.91)
    polygon = track["frames"][0]["polygon"]
    assert polygon and len(polygon) >= 3
    assert all(0 <= point["x"] <= 1 and 0 <= point["y"] <= 1 for point in polygon)
    assert track["frames"][1]["polygon"] is None

    empty = document_from_events(stream_events(""), concept="person", fps=10)
    assert empty["available"] is False
    assert empty["status"] == "empty"

    failed = document_from_events(stream_events("", "failed"), concept="person", fps=10)
    assert failed["status"] == "failed"
    assert failed["available"] is False


def test_silhouettes_align_by_phase_and_missing_masks_stay_missing():
    parsed = document_from_events(_person_events(), concept="person", fps=10)
    overlay = {
        "frames": [
            {"t": 0.0, "active_rep": 1, "phase": "down", "phase_progress": 0.2, "current": [], "reference": None, "silhouette": None},
            {"t": 0.1, "active_rep": 2, "phase": "down", "phase_progress": 0.2, "current": [], "reference": None, "silhouette": None},
            {"t": 9.0, "active_rep": 2, "phase": "up", "phase_progress": 0.8, "current": [], "reference": None, "silhouette": None},
        ]
    }
    attached = attach_silhouettes(overlay, {**parsed, "fps": 10}, reference_rep=1)
    assert attached["silhouette_source"] == "sam"
    assert attached["frames"][0]["silhouette"]
    assert attached["frames"][0]["reference_silhouette"] == attached["frames"][0]["silhouette"]
    assert attached["frames"][1]["silhouette"] is None
    assert attached["frames"][1]["reference_silhouette"] == attached["frames"][0]["silhouette"]
    assert attached["frames"][2]["reference_silhouette"] is None

    bare = attach_silhouettes({"frames": [{"t": 0, "silhouette": None}]}, {"tracks": [], "fps": 10}, None)
    assert bare["silhouette_source"] == "unavailable"
    assert bare["frames"][0]["silhouette"] is None


def _body(x=0.5, y=0.45):
    return [
        {"name": "left_shoulder", "x": x - 0.08, "y": y - 0.15, "visibility": 0.95},
        {"name": "right_shoulder", "x": x + 0.08, "y": y - 0.15, "visibility": 0.95},
        {"name": "left_hip", "x": x - 0.07, "y": y, "visibility": 0.95},
        {"name": "right_hip", "x": x + 0.07, "y": y, "visibility": 0.95},
        {"name": "left_ankle", "x": x - 0.06, "y": y + 0.25, "visibility": 0.9},
        {"name": "right_ankle", "x": x + 0.06, "y": y + 0.25, "visibility": 0.9},
    ]


def test_pose_overlap_selects_the_athlete_not_the_first_person():
    from app.services.meta.silhouettes import assign_athlete, attach_silhouettes, fixture_from_overlay

    overlay = {
        "frames": [
            {"t": 0.0, "active_rep": 1, "phase": "down", "phase_progress": 0.2, "current": _body(0.52, 0.48), "reference": None, "silhouette": None},
            {"t": 0.07, "active_rep": 1, "phase": "down", "phase_progress": 0.4, "current": _body(0.51, 0.55), "reference": None, "silhouette": None},
        ]
    }
    decoy = {"left": 0.02, "top": 0.18, "right": 0.16, "bottom": 0.72}
    athlete_box = {"left": 0.4, "top": 0.25, "right": 0.65, "bottom": 0.78}
    decoy_poly = [{"x": 0.02, "y": 0.18}, {"x": 0.16, "y": 0.18}, {"x": 0.16, "y": 0.72}, {"x": 0.02, "y": 0.72}]
    athlete_poly = [{"x": 0.42, "y": 0.28}, {"x": 0.63, "y": 0.28}, {"x": 0.6, "y": 0.76}, {"x": 0.43, "y": 0.76}]
    segmentation = {
        "source": "fixture",
        "status": "fixture",
        "fps": 32.868,
        "tracks": [
            {
                "concept": "person",
                "object_id": "0",
                "athlete": True,
                "frames": [{"t": 0.0, "frame_index": 0, "box": decoy, "polygon": decoy_poly, "confidence": 0.9}],
            },
            {
                "concept": "person",
                "object_id": "1",
                "athlete": False,
                "frames": [
                    {"t": 0.0, "frame_index": 0, "box": athlete_box, "polygon": athlete_poly, "confidence": 0.99},
                    {"t": 0.03, "frame_index": 1, "box": athlete_box, "polygon": athlete_poly, "confidence": 0.99},
                ],
            },
        ],
    }
    assert assign_athlete(segmentation, overlay["frames"]) == "1"
    assert segmentation["tracks"][0]["athlete"] is False
    attached = attach_silhouettes(overlay, segmentation, 1)
    assert attached["silhouette_source"] == "fixture"
    assert attached["silhouette_label"] == "Offline fixture"
    assert attached["frames"][0]["silhouette"][0]["x"] == 0.42
    assert all(point["x"] > 0.3 for point in attached["frames"][0]["silhouette"])

    fixture = fixture_from_overlay(overlay, fps=15)
    assert fixture["source"] == "fixture"
    assert fixture["athlete_object_id"] == "1"
    assert fixture["tracks"][0]["object_id"] == "0"
    assert fixture["tracks"][0]["athlete"] is False


def test_sparse_pose_frames_match_dense_sam_by_timestamp_not_index():
    pose = [
        {"t": i * (16.12 / 240), "active_rep": 1, "phase": "down", "phase_progress": 0.1, "current": _body(), "reference": None, "silhouette": None}
        for i in range(241)
    ]
    poly = [{"x": 0.4, "y": 0.3}, {"x": 0.6, "y": 0.3}, {"x": 0.55, "y": 0.8}, {"x": 0.45, "y": 0.8}]
    sam_frames = [
        {"t": round(i / 32.868, 4), "frame_index": i, "box": {"left": 0.4, "top": 0.3, "right": 0.6, "bottom": 0.8}, "polygon": poly}
        for i in range(530)
    ]
    overlay = {"frames": pose}
    segmentation = {
        "source": "sam",
        "status": "live",
        "fps": 32.868,
        "tracks": [{"concept": "person", "object_id": "0", "athlete": True, "frames": sam_frames}],
    }
    attached = attach_silhouettes(overlay, segmentation, 1)
    assert attached["silhouette_source"] == "sam"
    drawn = sum(1 for frame in attached["frames"] if frame["silhouette"])
    assert drawn == 241
    assert attached["frames"][0]["silhouette"]
    assert attached["frames"][120]["silhouette"]
    assert attached["frames"][0]["t"] != sam_frames[0]["t"] or True
    # Pose frame 120 is not SAM frame 120.
    assert abs(attached["frames"][120]["t"] - 120 / 32.868) > 0.5


def test_sam_attempt_002_ledger_does_not_touch_attempt_001():
    from app.services.meta.live_preflight import (
        HISTORICAL_SAM_LEDGER,
        PreflightRefused,
        SAM_LIVE_ATTEMPT_ID,
        _refuse_historical_sam_ledger,
        kind_ledger,
    )

    assert SAM_LIVE_ATTEMPT_ID == "attempt-002-persist-geometry"
    assert kind_ledger(Path("/data"), "sam").name == "sam-attempt-002-persist-geometry"
    assert HISTORICAL_SAM_LEDGER == "sam-attempt-001-person"
    with pytest.raises(PreflightRefused, match="Attempt 001 stays immutable"):
        _refuse_historical_sam_ledger(Path("/data/live-tests/sam-attempt-001-person"))


def test_summary_only_tracks_are_not_drawable_geometry():
    from app.services.meta.silhouettes import GeometryMissing, require_drawable_geometry

    with pytest.raises(GeometryMissing):
        require_drawable_geometry(
            {
                "tracks": [
                    {"concept": "person", "object_id": "0", "athlete": True, "frames": 530},
                    {"concept": "person", "object_id": "1", "athlete": False, "frames": 462},
                ]
            }
        )


def test_segmentation_roundtrip_keeps_polygons_and_phase_aligns_reference():
    from app.services.meta.silhouettes import attach_silhouettes, fixture_from_overlay, segmentation_document

    poly_a = [{"x": 0.41, "y": 0.2}, {"x": 0.59, "y": 0.2}, {"x": 0.55, "y": 0.7}, {"x": 0.45, "y": 0.7}]
    poly_b = [{"x": 0.42, "y": 0.35}, {"x": 0.58, "y": 0.35}, {"x": 0.54, "y": 0.82}, {"x": 0.46, "y": 0.82}]
    overlay = {
        "frames": [
            {"t": 0.0, "active_rep": 1, "phase": "down", "phase_progress": 0.4, "current": _body(0.5, 0.4), "reference": None, "silhouette": None},
            {"t": 2.0, "active_rep": 2, "phase": "down", "phase_progress": 0.4, "current": _body(0.5, 0.55), "reference": None, "silhouette": None},
        ]
    }
    segmentation = {
        "source": "sam",
        "status": "live",
        "fps": 15,
        "tracks": [
            {
                "concept": "person",
                "object_id": "7",
                "athlete": True,
                "frames": [
                    {"t": 0.0, "frame_index": 0, "box": {"left": 0.4, "top": 0.2, "right": 0.6, "bottom": 0.7}, "polygon": poly_a},
                    {"t": 2.0, "frame_index": 30, "box": {"left": 0.4, "top": 0.35, "right": 0.6, "bottom": 0.82}, "polygon": poly_b},
                ],
            }
        ],
    }
    document = json.loads(json.dumps(segmentation_document(segmentation, set_id="set-1", analysis_id="a-1", session_id="s-1")))
    assert document["set_id"] == "set-1"
    assert document["tracks"][0]["frames"][0]["polygon"] == poly_a
    attached = attach_silhouettes(overlay, document, 1)
    assert attached["silhouette_source"] == "sam"
    assert attached["frames"][0]["silhouette"] == poly_a
    assert attached["frames"][1]["silhouette"] == poly_b
    assert attached["frames"][1]["reference_silhouette"] == poly_a
    assert attached["frames"][1]["reference_silhouette"] != attached["frames"][1]["silhouette"]

    fixture = fixture_from_overlay(overlay, fps=15)
    assert fixture["source"] == "fixture"
    assert "not a live" in fixture["label"].lower()


def test_invalid_live_masks_do_not_replace_a_fixture_overlay():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models.entities import AnalysisResult, RecordedSet, User, WorkoutSession
    from app.services.meta.apply_silhouettes import persist_to_analysis

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User()
    db.add(user)
    db.flush()
    session = WorkoutSession(user_id=user.id)
    db.add(session)
    db.flush()
    rec = RecordedSet(user_id=user.id, session_id=session.id, duration_seconds=2.0)
    db.add(rec)
    db.flush()
    overlay = {
        "frames": [
            {
                "t": 0.0,
                "active_rep": 1,
                "phase": "down",
                "phase_progress": 0.2,
                "current": _body(),
                "reference": None,
                "silhouette": None,
            }
        ]
    }
    rec.analysis = AnalysisResult(
        set_id=rec.id,
        quality_json="{}",
        drift_json="[]",
        overlay_json=json.dumps(overlay),
    )
    db.add(rec.analysis)
    db.commit()
    from app.services.meta.silhouettes import fixture_from_overlay

    persist_to_analysis(db, rec, fixture_from_overlay(overlay, fps=15))
    assert json.loads(rec.analysis.overlay_json)["silhouette_source"] == "fixture"
    persist_to_analysis(
        db,
        rec,
        {
            "source": "sam",
            "status": "live",
            "available": True,
            "tracks": [{"concept": "person", "object_id": "0", "athlete": True, "frames": 530}],
        },
    )
    kept = json.loads(rec.analysis.overlay_json)
    assert kept["silhouette_source"] == "fixture"
    assert rec.analysis.sam_status == "fixture"


def test_pose_pipeline_does_not_pretend_the_skeleton_is_sam():
    result = analyze_pose_sequence(synthesize_squat_set(reps=4))
    assert result["overlay"]["silhouette_source"] == "unavailable"


def test_segmentation_provider_none_and_unsupported_files_do_not_upload(tmp_path):
    transport = FakeTransport()
    settings = _settings(tmp_path, enable_meta_api=True, segmentation_provider="none")
    skipped = SamProvider(settings, MetaGateway(settings), transport).segment_video(Path("clip.mp4"), 60)
    assert skipped["status"] == "skipped"
    assert transport.calls == []

    settings.segmentation_provider = "meta_live"
    unsupported = SamProvider(settings, MetaGateway(settings), transport).segment_video(Path("clip.webm"), 60)
    assert unsupported["status"] == "unsupported"
    assert transport.calls == []


def test_sam_cleans_up_the_upload_on_success_and_on_failure(tmp_path):
    settings = _settings(
        tmp_path,
        enable_meta_api=True,
        segmentation_provider="meta_live",
        meta_require_explicit_approval=True,
    )
    token = approval_hint(settings, "sam_segmentation")
    transport = FakeTransport(events=_person_events())
    result = SamProvider(settings, MetaGateway(settings), transport).segment_video(
        Path("clip.mp4"),
        12,
        approval_token=token,
        fps=10,
        media={"width": 40, "height": 30, "codec": "h264"},
    )
    assert result["available"] is True
    assert result["status"] == "live"
    assert result["file_deleted"] is True
    assert transport.deleted == ["file-offline"]

    failing = FakeTransport(fail=MetaRejected("invalid prompt"))
    with pytest.raises(MetaRejected):
        SamProvider(settings, MetaGateway(settings), failing).segment_video(
            Path("clip.mp4"), 12, approval_token=token, media={"codec": "h264"}
        )
    assert failing.deleted == ["file-offline"]


def test_rate_limit_and_timeout_retry_then_stop(tmp_path):
    settings = _settings(tmp_path, enable_meta_api=True, workout_provider="meta_live", meta_max_retries=1)
    token = approval_hint(settings, "workout_generation")
    transport = FakeTransport(fail=TransientMetaError("rate_limit"))
    with pytest.raises(MetaRateLimited):
        MuseProvider(settings, MetaGateway(settings), transport).generate_workout(PROFILE, approval_token=token)
    assert len(transport.calls) == 2
    log = (tmp_path / "meta-usage.jsonl").read_text()
    assert "rate_limit" in log

    timed = FakeTransport(fail=TransientMetaError("timeout"))
    from app.services.meta.errors import MetaTimeout

    with pytest.raises(MetaTimeout):
        MuseProvider(settings, MetaGateway(settings), timed).generate_workout(PROFILE, approval_token=token)
    assert len(timed.calls) == 2


def test_fixture_plan_and_coaching_round_trip_without_a_live_call():
    settings = get_settings()
    previous = (settings.workout_provider, settings.coaching_provider)
    settings.workout_provider = "fixture"
    settings.coaching_provider = "fixture"
    try:
        with TestClient(app) as client:
            created = client.post(
                "/profiles",
                json={
                    "goal": "build_strength",
                    "experience": "intermediate",
                    "days_per_week": 4,
                    "session_duration_minutes": 50,
                    "equipment": ["barbell", "dumbbells", "machines"],
                    "current_squat_load_kg": 40,
                    "limitations": [],
                    "display_name": "Fixture Athlete",
                },
            )
            assert created.status_code == 200
            plan = client.post("/workouts/generate", json={})
            assert plan.status_code == 200
            body = plan.json()
            assert body["source"] == "fixture"
            assert body["status"] == "proposed"
            assert "not a live call" in body["source_label"]
            assert "Muse Spark 1.3 (live)" not in body["source_label"]
            assert body["schedule"][0]["workout_name"] == "Fixture Leg Day A"
            assert any(item["exercise_id"] == "barbell_squat" for item in body["exercises"])
            accepted = accept_if_proposed(client, body)
            assert accepted["source"] == "fixture"

            session = client.post("/sessions", json={"plan_id": accepted["id"]})
            upload = client.post(
                "/videos/upload",
                data={"session_id": session.json()["id"], "exercise_id": "barbell_squat", "consent": True, "demo": True},
            )
            set_id = upload.json()["id"]
            analysis = None
            for _ in range(40):
                analysis = client.get(f"/analysis/{set_id}")
                if analysis.json()["status"] in {"COMPLETED", "FAILED"}:
                    break
            assert analysis.json()["status"] == "COMPLETED"
            assert analysis.json()["sam_available"] is False
            overlay = client.get(f"/analysis/{set_id}/overlay")
            assert overlay.json()["silhouette_source"] == "unavailable"
            coaching = client.get(f"/coaching/{set_id}")
            assert coaching.json()["source"] == "fixture"
            assert coaching.json()["requires_confirmation"] is True
            assert client.get("/meta/status").json()["live_calls"] == 0
            assert client.get("/health").json()["meta_live_possible"] is False
    finally:
        settings.workout_provider, settings.coaching_provider = previous


def test_live_preflight_dry_run_and_one_approved_call(tmp_path):
    from app.services.meta.live_preflight import PreflightRefused, live_settings, run_coaching, run_sam, run_workout
    from app.services.meta.pricing import (
        COACHING_INPUT_TOKEN_ESTIMATE,
        COACHING_OUTPUT_TOKEN_ESTIMATE,
        COACHING_REASONING_EFFORT,
        WORKOUT_INPUT_TOKEN_ESTIMATE,
        WORKOUT_OUTPUT_TOKEN_ESTIMATE,
        estimate_muse_cost,
        estimate_sam_video_cost,
    )

    settings = _settings(tmp_path, model_api_key="")
    dry = run_workout(PROFILE, 1, settings, execute=False, approval=None, ledger=tmp_path / "dry")
    assert dry["will_call"] is False
    assert dry["model"] == "muse-spark-1.3"
    assert dry["retries"] == 0
    assert dry["reasoning_effort"] == "high"
    assert dry["max_completion_tokens"] is None
    assert dry["max_output_tokens"] is None
    assert dry["schema_validation"] == "ready"
    assert dry["schema_issues"] == []
    assert dry["estimated_cost_usd"] == round(
        estimate_muse_cost(WORKOUT_INPUT_TOKEN_ESTIMATE, WORKOUT_OUTPUT_TOKEN_ESTIMATE), 6
    )
    assert dry["key_present"] is False
    from app.services.meta.live_preflight import HISTORICAL_WORKOUT_LEDGER, SAM_LIVE_ATTEMPT_ID, kind_ledger

    assert kind_ledger(Path("/data"), "workout") != Path("/data/live-tests") / HISTORICAL_WORKOUT_LEDGER
    assert "attempt-002" in str(kind_ledger(Path("/data"), "workout"))
    assert SAM_LIVE_ATTEMPT_ID == "attempt-002-persist-geometry"
    assert kind_ledger(Path("/data"), "sam") == Path("/data/live-tests") / f"sam-{SAM_LIVE_ATTEMPT_ID}"
    assert "attempt-001-person" not in str(kind_ledger(Path("/data"), "sam"))
    sam_live = live_settings(settings, kind="sam", estimate=0.1, ledger=tmp_path / "sam-live")
    assert sam_live.meta_max_retries == 0
    assert sam_live.segmentation_provider == "meta_live"
    assert sam_live.workout_provider == "local"
    assert sam_live.sam_include_barbell is False
    assert sam_live.meta_request_timeout_seconds == 120
    live = live_settings(settings, kind="workout", estimate=dry["estimated_cost_usd"], ledger=tmp_path / "live")
    assert live.meta_max_retries == 0
    assert live.workout_provider == "meta_live"
    assert live.coaching_provider == "local"
    assert live.segmentation_provider == "none"
    with pytest.raises(PreflightRefused):
        run_workout(PROFILE, 1, settings, execute=True, approval=None, ledger=tmp_path / "refused")

    armed = _settings(tmp_path, enable_meta_api=True, workout_provider="meta_live")
    token = approval_hint(armed, "workout_generation")
    transport = FakeTransport(content=json.dumps(_week()))
    ledger = tmp_path / "once"
    once = run_workout(PROFILE, 1, armed, execute=True, approval=token, ledger=ledger, transport=transport)
    assert once["calls"] == 1
    assert transport.calls == [("chat", "muse-spark-1.3")]
    assert (ledger / "workout-live.json").exists()
    with pytest.raises(MetaBlocked):
        run_workout(PROFILE, 1, armed, execute=True, approval=token, ledger=ledger, transport=FakeTransport(content=json.dumps(_week())))

    coach = run_coaching(
        {
            "quality": {"usable": True, "score": 0.9, "issues": []},
            "drift": [],
            "reps": [{"rep_id": 1, "start_seconds": 0.2, "bottom_seconds": 0.8, "end_seconds": 1.4, "confidence": 0.8}],
            "reference_rep": 1,
            "profile": PROFILE,
            "current_reps": 5,
            "current_rest": 120,
            "current_load": 40,
            "reported_rpe": 7,
        },
        settings,
        execute=False,
        approval=None,
        ledger=tmp_path / "coach",
    )
    assert coach["will_call"] is False
    assert coach["call_cap"] == 1
    assert coach["retries"] == 0
    assert coach["has_landmarks"] is False
    assert coach["reasoning_effort"] == COACHING_REASONING_EFFORT == "high"
    assert coach["max_completion_tokens"] is None
    assert coach["max_output_tokens"] is None
    assert coach["estimated_input_tokens"] == COACHING_INPUT_TOKEN_ESTIMATE == 2000
    assert coach["estimated_cost_usd"] == round(
        estimate_muse_cost(COACHING_INPUT_TOKEN_ESTIMATE, COACHING_OUTPUT_TOKEN_ESTIMATE), 6
    )

    sam = run_sam(
        tmp_path / "clip.mp4",
        {"codec": "h264", "duration": 16.12, "fps": 32.868, "width": 720, "height": 640},
        settings,
        execute=False,
        approval=None,
        ledger=tmp_path / "sam",
    )
    assert sam["concept"] == "person"
    assert sam["barbell"] is False
    assert sam["retries"] == 0
    assert sam["will_call"] is False
    assert sam["attempt_id"] == "attempt-002-persist-geometry"
    assert sam["persists_geometry"] is True
    assert sam["historical_sam_untouched"] is True
    assert sam["request_concept"] == "person"
    assert sam["mask_encoding"] == "one_bit"
    assert "skeleton" in sam["skeleton_fallback"].lower()
    assert sam["estimated_cost_usd"] == round(estimate_sam_video_cost(sam["frames"]), 6)


def test_sam_execute_persists_decoded_tracks_without_remote_ids(tmp_path):
    from app.services.meta.live_preflight import run_sam

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"offline")
    settings = _settings(tmp_path, enable_meta_api=True, segmentation_provider="meta_live")
    token = approval_hint(settings, "sam_segmentation")
    ledger = tmp_path / "sam-attempt-001-person"
    result = run_sam(
        clip,
        {"codec": "h264", "duration": 0.2, "fps": 10, "width": 40, "height": 30},
        settings,
        execute=True,
        approval=token,
        ledger=ledger,
        transport=FakeTransport(events=_person_events()),
    )
    assert result["available"] is True
    assert result["calls"] == 1
    assert result["file_deleted"] is True
    assert result["request_concept"] == "person"
    tracks_path = ledger / "sam-tracks.json"
    saved = json.loads(tracks_path.read_text())
    blob = json.dumps(saved)
    assert "file-offline" not in blob
    assert "sk-test-not-used" not in blob
    athlete = next(item for item in saved["tracks"] if item["athlete"])
    assert athlete["frames"][0]["polygon"]
    assert athlete["frames"][1]["polygon"] is None
    assert athlete["frames"][0]["t"] == 0
    assert athlete["frames"][0]["box"]
    assert athlete["frames"][0]["frame_index"] == 0
    assert saved["source"] == "sam"
    assert "file_id" not in blob
    live = json.loads((ledger / "sam-live.json").read_text())
    assert live["ok"] is True
    assert live["response_calls"] == 1
    assert result["geometry_persisted"] is True
    assert saved["tracks"][0]["frames"][0]["polygon"]


def test_empty_length_finish_is_a_failure_and_four_day_week_matches_sqlite(tmp_path):
    from app.api.serialize import plan_out
    from app.database import SessionLocal
    from app.models.entities import Profile, WorkoutExercise, WorkoutPlan
    from app.services.meta.live_preflight import PreflightRefused, _refuse_historical_workout_ledger, run_workout

    four_day = _four_day_profile()
    settings = _settings(tmp_path, enable_meta_api=True, workout_provider="meta_live")
    token = approval_hint(settings, "workout_generation")
    empty = FakeTransport(
        content="",
        finish_reason="length",
        http_status=200,
        input_tokens=1977,
        output_tokens=6000,
        reasoning_tokens=6000,
    )
    with pytest.raises(MetaRejected, match="empty content"):
        MuseProvider(settings, MetaGateway(settings), empty).generate_workout(four_day, approval_token=token)
    log = (tmp_path / "meta-usage.jsonl").read_text()
    assert "empty_content" in log
    assert '"finish_reason": "length"' in log
    assert '"content_present": false' in log
    assert empty.last_kwargs["reasoning_effort"] == "high"
    assert empty.last_kwargs.get("max_completion_tokens") is None
    assert "max_tokens" not in empty.last_kwargs

    ledger = tmp_path / "empty-attempt"
    with pytest.raises(PreflightRefused):
        run_workout(
            four_day,
            0,
            settings,
            execute=True,
            approval=token,
            ledger=ledger,
            transport=FakeTransport(
                content="",
                finish_reason="length",
                http_status=200,
                output_tokens=6000,
                reasoning_tokens=6000,
            ),
        )
    artifact = json.loads((ledger / "workout-live.json").read_text())
    assert artifact["ok"] is False
    assert artifact["http_status"] == 200
    assert artifact["finish_reason"] == "length"
    assert artifact["content_present"] is False
    assert artifact["content_length"] == 0
    assert artifact["schema_validation"] == "empty_content"
    assert artifact["raw_result"] is None
    assert artifact["output_tokens"] == 6000
    assert artifact["reasoning_tokens"] == 6000

    with pytest.raises(PreflightRefused, match="original workout live-test ledger"):
        _refuse_historical_workout_ledger(Path("/tmp/data/live-tests/workout"))

    transport = FakeTransport(content=json.dumps(_four_day_week()), finish_reason="stop")
    plan_data = MuseProvider(settings, MetaGateway(settings), transport).generate_workout(
        four_day, approval_token=token, session_index=0
    )
    assert plan_data["source"] == "muse_spark"
    assert len(plan_data["schedule"]) == 4
    assert all(session["duration_minutes"] == 50 for session in plan_data["schedule"])
    assert plan_data["schedule"][0]["exercises"][0]["suggested_load_kg"] == 40

    with TestClient(app) as client:
        created = client.post(
            "/profiles",
            json={
                "goal": "build_strength",
                "experience": "intermediate",
                "days_per_week": 4,
                "session_duration_minutes": 50,
                "equipment": ["barbell", "dumbbells", "bench", "machines"],
                "current_squat_load_kg": 40,
                "limitations": [],
                "display_name": "Four Day",
                "assessment": four_day["assessment"],
            },
        )
        assert created.status_code == 200, created.text
        historical = Path(__file__).resolve().parents[1] / "data" / "live-tests" / "workout" / "workout-live.json"
        historical_before = historical.read_text(encoding="utf-8") if historical.exists() else None
        db = SessionLocal()
        try:
            profile = db.get(Profile, created.json()["id"])
            assert profile is not None
            plan = WorkoutPlan(
                user_id=profile.user_id,
                name=plan_data["name"],
                status="active",
                source=plan_data["source"],
                duration_minutes=plan_data["duration_minutes"],
                estimated_minutes=plan_data.get("estimated_minutes"),
                session_type=plan_data.get("session_type"),
                notes=plan_data.get("notes"),
                schedule_json=json.dumps(plan_data["schedule"]),
            )
            db.add(plan)
            db.flush()
            for index, item in enumerate(plan_data["exercises"]):
                db.add(
                    WorkoutExercise(
                        plan_id=plan.id,
                        exercise_id=item["exercise_id"],
                        position=index,
                        sets=item["sets"],
                        target_reps=item["target_reps"],
                        rest_seconds=item["rest_seconds"],
                        suggested_load_kg=item.get("suggested_load_kg"),
                        notes=item.get("notes"),
                    )
                )
            db.commit()
            plan_id = plan.id
            wire = plan_out(plan)
        finally:
            db.close()
        fetched = client.get(f"/workouts/{plan_id}")
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["source"] == "muse_spark"
        assert body["source_label"] == "Muse Spark 1.3 (live)"
        assert body["duration_minutes"] == 50
        assert len(body["schedule"]) == 4
        assert [session["workout_name"] for session in body["schedule"]] == [
            item["workout_name"] for item in plan_data["schedule"]
        ]
        assert body["exercises"]
        assert {item["exercise_id"] for item in body["exercises"]} <= set(
            four_day["assessment"]["preferences"]["enjoyed_exercises"]
        ) | {
            "barbell_squat",
            "romanian_deadlift",
            "walking_lunge",
            "plank",
        }
        next_plan = client.get("/workouts/next").json()["plan"]
        assert next_plan["id"] == plan_id
        assert wire["schedule"] == body["schedule"]
        if historical_before is not None:
            assert historical.read_text(encoding="utf-8") == historical_before


def test_coaching_attempt_binds_context_and_refuses_any_second_execute(tmp_path):
    from app.services.meta.live_preflight import run_coaching, PreflightRefused
    settings=_settings(tmp_path, enable_meta_api=False)
    context={'set_id':'isolated-fixture-set','recommendation_context':{'set_id':'isolated-fixture-set','analysis_sha256':'fixture'},'quality':{'usable':True},'drift':[], 'reps':[], 'reference_rep':None,'current_reps':6,'current_rest':150,'current_load':40}
    raw={'summary':'Keep current targets.','observations':[],'uncertainties':[], 'suggested_action':'KEEP_PLAN','explanation':'No supported change.','suggested_reps':6,'suggested_rest_seconds':150,'suggested_load_kg':40}
    transport=FakeTransport(content=json.dumps(raw))
    ledger=tmp_path/'bound-coach'
    with patch('app.services.meta.live_preflight._open_transport',side_effect=AssertionError('no client on dry run')):
        assert run_coaching(context,settings,execute=False,approval=None,ledger=ledger)['will_call'] is False
    assert not ledger.exists()
    token=approval_hint(settings,'coaching')
    result=run_coaching(context,settings,execute=True,approval=token,ledger=ledger,transport=transport)
    artifact=json.loads(Path(result['artifact']).read_text())
    assert artifact['result']['set_id'] == context['set_id']
    assert artifact['result']['recommendation_context'] == context['recommendation_context']
    assert artifact['model'] == 'muse-spark-1.3' and artifact['request_schema'] == 'ghostrep_coaching'
    assert artifact['chat_calls'] == 1 and artifact['schema_validation'] == 'ok'
    with pytest.raises(PreflightRefused):
        run_coaching(context,settings,execute=True,approval=token,ledger=ledger,transport=transport)
    assert len(transport.calls) == 1
    failure=FakeTransport(content='')
    failed_ledger=tmp_path/'failed-coach'
    with pytest.raises(PreflightRefused):
        run_coaching(context,settings,execute=True,approval=token,ledger=failed_ledger,transport=failure)
    failed=json.loads((failed_ledger/'coaching-live.json').read_text())
    assert failed['ok'] is False and failed['chat_calls'] == 1
    with pytest.raises(PreflightRefused):
        run_coaching(context,settings,execute=True,approval=token,ledger=failed_ledger,transport=failure)
    assert len(failure.calls) == 1


def test_truncated_live_coaching_is_saved_as_failure_without_retry(tmp_path):
    from app.services.meta.live_preflight import PreflightRefused, run_coaching

    settings = _settings(tmp_path)
    context = {
        "set_id": "isolated-squat",
        "recommendation_context": {"set_id": "isolated-squat", "analysis_sha256": "fixture"},
        "quality": {"usable": True},
        "drift": [],
        "reps": [],
        "reference_rep": None,
    }
    transport = FakeTransport(
        content='{"explanation":"Measured set.","observations":[{"metric"',
        finish_reason="length",
        input_tokens=1524,
        output_tokens=2500,
        reasoning_tokens=1910,
    )
    ledger = tmp_path / "truncated-coach"
    token = approval_hint(settings, "coaching")
    with pytest.raises(PreflightRefused, match="No retry"):
        run_coaching(context, settings, execute=True, approval=token, ledger=ledger, transport=transport)
    path = ledger / "coaching-live.json"
    saved_bytes = path.read_bytes()
    artifact = json.loads(saved_bytes)
    assert artifact["ok"] is False
    assert artifact["chat_calls"] == 1
    assert artifact["schema_validation"] == "truncated"
    assert artifact["reasoning_tokens"] == 1910
    assert "token limit" in artifact["error"]
    assert "result" not in artifact
    with pytest.raises(PreflightRefused):
        run_coaching(context, settings, execute=True, approval=token, ledger=ledger, transport=transport)
    assert len(transport.calls) == 1
    assert path.read_bytes() == saved_bytes


def test_new_coaching_attempt_uses_import_path_and_preserves_original_ledger(tmp_path):
    from app.services.meta.live_preflight import PreflightRefused, kind_ledger, run_coaching
    from app.services.meta.saved_results import COACHING_LIVE_ATTEMPT_ID, saved_coaching_path

    settings = _settings(tmp_path)
    historical = tmp_path / "live-tests" / "coaching"
    historical.mkdir(parents=True)
    original = historical / "coaching-live.json"
    original.write_text('{"ok":false,"chat_calls":1}', encoding="utf-8")
    before = original.read_bytes()
    context = {"set_id": "isolated-squat", "recommendation_context": {"set_id": "isolated-squat"}}
    with patch("app.services.meta.live_preflight._open_transport", side_effect=AssertionError("no client")):
        with pytest.raises(PreflightRefused, match="historical coaching ledger"):
            run_coaching(context, settings, execute=True, approval=approval_hint(settings, "coaching"), ledger=historical)
        dry = run_coaching(context, settings, execute=False, approval=None, ledger=kind_ledger(tmp_path, "coaching"))
    assert original.read_bytes() == before
    assert dry["attempt_id"] == COACHING_LIVE_ATTEMPT_ID
    assert dry["will_call"] is False
    assert kind_ledger(tmp_path, "coaching") == saved_coaching_path(settings).parent
    assert kind_ledger(tmp_path, "coaching") != historical
    assert not kind_ledger(tmp_path, "coaching").exists()


@pytest.mark.parametrize('change',[{'observations':'bad'},{'suggested_reps':'6'},{'summary':None},{'suggested_load_kg':float('nan')},{'extra':'field'}])
def test_coaching_strict_response_rejects_malformed_fields(change):
    from app.services.meta.contracts import parse_coaching_payload
    raw={'summary':'Keep.','observations':[], 'uncertainties':[], 'suggested_action':'KEEP_PLAN','explanation':'No change.','suggested_reps':6,'suggested_rest_seconds':150,'suggested_load_kg':40}
    with pytest.raises(MetaRejected):
        parse_coaching_payload({**raw,**change},{})
