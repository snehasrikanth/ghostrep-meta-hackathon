"""Actual FastAPI dependencies; no external cookie adapter."""
import pytest
from fastapi.testclient import TestClient
from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.services.demo.seed import seed_demo, cleanup_demo
from tests.test_lower_body_focus import lower_profile


@pytest.mark.parametrize("cookie", ["ghostrep_session", "ghostrep_repair_cookie"])
def test_identity_two_users_and_demo_return_use_configured_cookie(cookie, monkeypatch):
    monkeypatch.setattr(get_settings(), "session_cookie", cookie)
    with TestClient(app) as alice, TestClient(app) as bob:
        saved = alice.post("/profiles", json=lower_profile())
        assert saved.status_code == 200 and cookie in alice.cookies
        assert alice.get("/profiles/me").json()["id"] == saved.json()["id"]
        assert alice.get("/program", params={"today": "2026-10-31"}).status_code == 200
        assert alice.get("/demo/status").json()["active"] is False
        assert bob.get("/profiles/me").status_code == 404
        other = bob.post("/profiles", json=lower_profile()).json()
        assert other["user_id"] != saved.json()["user_id"]
        with SessionLocal() as db:
            seed_demo(db)
        try:
            assert alice.post("/demo/enter").status_code == 200
            assert alice.get("/demo/status").json()["active"] is True
            return_name = "ghostrep_return" if cookie == "ghostrep_session" else cookie + "_return"
            assert return_name in alice.cookies
            assert alice.post("/demo/exit").status_code == 200
            assert alice.get("/profiles/me").json()["user_id"] == saved.json()["user_id"]
            assert bob.get("/profiles/me").json()["user_id"] == other["user_id"]
            assert return_name not in alice.cookies
        finally:
            with SessionLocal() as db:
                cleanup_demo(db)
