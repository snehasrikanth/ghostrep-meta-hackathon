"""Cookie attributes and interrupted-job recovery. Isolated temp engines only."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import session_cookie_params
from app.config import Settings
from app.database import Base, fail_interrupted_jobs
from app.models.entities import RecordedSet, User, WorkoutSession


def test_session_cookie_secure_follows_frontend_origin_scheme():
    http = session_cookie_params(Settings(frontend_origin="http://localhost:3000"))
    https = session_cookie_params(Settings(frontend_origin="https://ghostrep.example"))
    assert http["httponly"] is True
    assert http["samesite"] == "lax"
    assert http["secure"] is False
    assert https["secure"] is True
    assert https["samesite"] == "lax"


def test_interrupted_video_jobs_fail_on_restart_without_touching_completed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}", future=True)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, future=True)()
    user = User(display_name="Jobs")
    db.add(user)
    db.flush()
    session = WorkoutSession(user_id=user.id, status="active")
    db.add(session)
    db.flush()
    pending = RecordedSet(
        session_id=session.id,
        user_id=user.id,
        exercise_id="barbell_squat",
        processing_status="ESTIMATING_POSE",
        entry_source="video",
    )
    coaching = RecordedSet(
        session_id=session.id,
        user_id=user.id,
        exercise_id="barbell_squat",
        processing_status="GENERATING_COACHING",
        entry_source="video",
    )
    done = RecordedSet(
        session_id=session.id,
        user_id=user.id,
        exercise_id="barbell_squat",
        processing_status="COMPLETED",
        completed_reps=5,
        entry_source="video",
    )
    db.add_all([pending, coaching, done])
    db.commit()
    ids = (pending.id, coaching.id, done.id)
    db.close()

    assert fail_interrupted_jobs(engine) == 2
    assert fail_interrupted_jobs(engine) == 0
    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT id, processing_status FROM recorded_sets")).fetchall())
        reps = conn.execute(text("SELECT completed_reps FROM recorded_sets WHERE id = :id"), {"id": ids[2]}).scalar()
    assert rows[ids[0]] == "FAILED"
    assert rows[ids[1]] == "FAILED"
    assert rows[ids[2]] == "COMPLETED"
    assert reps == 5
