"""Shared test helpers. Isolated temp DB only — never the developer database."""


def accept_if_proposed(client, plan: dict) -> dict:
    if plan.get("status") == "proposed":
        response = client.post(f"/workouts/{plan['id']}/accept")
        assert response.status_code == 200, response.text
        return response.json()
    return plan


def generate_active_plan(client, payload: dict | None = None) -> dict:
    response = client.post("/workouts/generate", json=payload or {})
    assert response.status_code == 200, response.text
    return accept_if_proposed(client, response.json())


def upload_recording_fixture(client, session_id: str, **fields):
    """Real upload/storage path with deliberately mocked pose, never accuracy evidence."""
    import time
    from unittest.mock import patch
    from app.services.movement.synthetic import synthesize_squat_set

    data = {"session_id": session_id, "exercise_id": "barbell_squat", "consent": True, **fields}
    with patch("app.services.video.jobs.PoseExtractor.extract", return_value=synthesize_squat_set(reps=6, drift=True)):
        response = client.post("/videos/upload", data=data, files={"file": ("protocol-fixture.mp4", recording_bytes(), "video/mp4")})
        assert response.status_code == 200, response.text
        for _ in range(200):
            body = client.get("/analysis/" + response.json()["id"]).json()
            if body["status"] in {"COMPLETED", "FAILED"}:
                assert body["status"] == "COMPLETED", body
                return response
            time.sleep(.02)
    raise AssertionError("Protocol recording did not finish")


from functools import lru_cache


@lru_cache(maxsize=1)
def recording_bytes():
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="ghostrep-protocol-video-") as directory:
        path = Path(directory) / "color.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=15:duration=4",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True)
        return path.read_bytes()
