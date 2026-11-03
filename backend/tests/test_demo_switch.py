from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.api.deps import demo_switch_allowed
from app.database import SessionLocal, init_db
from app.main import app
from app.models.entities import User, WorkoutSession
from app.services.demo.identity import DEMO_DISPLAY_NAME, DEMO_USER_ID
from app.services.demo.seed import cleanup_demo, seed_demo


def test_demo_status_does_not_create_a_user():
    db = SessionLocal()
    before = db.query(User).count()
    db.close()
    with TestClient(app) as client:
        status = client.get("/demo/status")
        assert status.status_code == 200
        body = status.json()
        assert body["available"] is True
        assert body["active"] is False
    db = SessionLocal()
    try:
        assert db.query(User).count() == before
    finally:
        db.close()


def test_enter_and_exit_preserve_the_original_account():
    init_db()
    db = SessionLocal()
    client = TestClient(app)
    client.__enter__()
    try:
        seed_demo(db, anchor=date(2026, 10, 30), timezone_name="America/New_York")
        profile = client.post(
            "/profiles",
            json={
                "goal": "build_strength",
                "experience": "intermediate",
                "days_per_week": 4,
                "session_duration_minutes": 45,
                "equipment": ["barbell"],
                "limitations": [],
                "display_name": "Original",
            },
        )
        assert profile.status_code == 200, profile.text
        original_id = profile.json()["user_id"]
        assert original_id != DEMO_USER_ID
        entered = client.post("/demo/enter")
        assert entered.status_code == 200, entered.text
        me = client.get("/profiles/me").json()
        assert me["display_name"] == DEMO_DISPLAY_NAME
        assert me["user_id"] == DEMO_USER_ID
        assert client.get("/sessions/current").json()["session"]["status"] == "paused"
        ignored = client.post("/demo/enter", json={"user_id": original_id})
        assert ignored.status_code == 200
        assert client.get("/profiles/me").json()["user_id"] == DEMO_USER_ID
        left = client.post("/demo/exit")
        assert left.status_code == 200
        back = client.get("/profiles/me").json()
        assert back["user_id"] == original_id
        assert back["display_name"] == "Original"
        assert db.query(WorkoutSession).filter(WorkoutSession.user_id == original_id).count() == 0
        assert db.query(WorkoutSession).filter(WorkoutSession.user_id == DEMO_USER_ID).count() == 10
    finally:
        cleanup_demo(db)
        client.__exit__(None, None, None)
        db.close()


def test_enter_without_seed_and_production_are_blocked():
    init_db()
    db = SessionLocal()
    try:
        cleanup_demo(db)
    finally:
        db.close()
    with TestClient(app) as client:
        missing = client.post("/demo/enter")
        assert missing.status_code == 409
    original = demo_switch_allowed

    def production(_settings) -> bool:
        return False

    import app.api.routes.demo as demo_routes
    import app.api.deps as deps

    deps.demo_switch_allowed = production  # type: ignore[method-assign]
    demo_routes.demo_switch_allowed = production  # type: ignore[method-assign]
    try:
        with TestClient(app) as client:
            assert client.get("/demo/status").json()["available"] is False
            assert client.post("/demo/enter").status_code == 404
            assert client.post("/demo/exit").status_code == 404
            assert client.post("/demo/enter", json={"user_id": "anyone"}).status_code == 404
    finally:
        deps.demo_switch_allowed = original  # type: ignore[method-assign]
        demo_routes.demo_switch_allowed = original  # type: ignore[method-assign]
