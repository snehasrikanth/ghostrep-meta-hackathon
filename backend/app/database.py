import json
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_url() -> str:
    return get_settings().database_url


def build_engine():
    url = _engine_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_profile_columns(engine)
    migrate_training_columns(engine)
    close_stale_sessions(engine)
    fail_interrupted_jobs(engine)


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}


def migrate_training_columns(target_engine=engine) -> None:
    """Add plan, session, and set-log columns in place. Existing rows keep their values."""
    additions = {
        "workout_plans": {
            "estimated_minutes": "INTEGER",
            "session_type": "TEXT",
            "schedule_json": "TEXT",
            "context_json": "TEXT",
            "warnings_json": "TEXT",
        },
        "workout_sessions": {"paused_at": "DATETIME"},
        "recorded_sets": {
            "entry_source": "TEXT NOT NULL DEFAULT 'video'", "set_index": "INTEGER",
            "analysis_requested": "BOOLEAN NOT NULL DEFAULT 1",
            "processing_started_at": "DATETIME", "stage_started_at": "DATETIME", "stage_timings_json": "TEXT",
        },
        "analysis_results": {"segmentation_json": "TEXT"},
        "coaching_decisions": {
            "revision": "INTEGER NOT NULL DEFAULT 0",
            "active_version_id": "TEXT",
        },
        "coaching_versions": {
            "verified": "BOOLEAN NOT NULL DEFAULT 0",
            "context_json": "TEXT",
            "user_decision": "TEXT NOT NULL DEFAULT 'pending'",
            "activated_at": "DATETIME",
            "decided_at": "DATETIME",
        },
    }
    with target_engine.begin() as conn:
        for table, columns in additions.items():
            names = _columns(conn, table)
            if not names:
                continue
            for name, ddl in columns.items():
                if name not in names:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        if _columns(conn, "recorded_sets"):
            conn.exec_driver_sql(
                "UPDATE recorded_sets SET entry_source = 'demo' "
                "WHERE original_filename = 'DEMO_FIXTURE' AND entry_source = 'video'"
            )


STALE_EMPTY_HOURS = 12
INTERRUPTED_PROCESSING = (
    "UPLOADED",
    "VALIDATING",
    "PREPROCESSING",
    "ESTIMATING_POSE",
    "DETECTING_REPS",
    "SEGMENTING",
    "COMPUTING_METRICS",
    "GENERATING_COACHING",
)
INTERRUPTED_JOB_MESSAGE = "Processing was interrupted when the server restarted. Upload the clip again."


def close_stale_sessions(target_engine=engine) -> int:
    """Leave at most one open session per user and close empty sessions that were never used.

    Closed sessions are marked abandoned, not deleted, and never marked completed.
    """
    with target_engine.begin() as conn:
        if not _columns(conn, "workout_sessions"):
            return 0
        rows = conn.exec_driver_sql(
            "SELECT s.id, s.user_id, s.started_at, "
            "(SELECT COUNT(*) FROM recorded_sets r WHERE r.session_id = s.id) "
            "FROM workout_sessions s WHERE s.status IN ('active', 'paused') "
            "ORDER BY s.user_id, s.started_at DESC"
        ).fetchall()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_EMPTY_HOURS)
        seen: set[str] = set()
        closed = []
        for session_id, user_id, started_at, set_count in rows:
            started = _parse_time(started_at)
            if user_id in seen or (set_count == 0 and started is not None and started < cutoff):
                closed.append(session_id)
            seen.add(user_id)
        for session_id in closed:
            conn.exec_driver_sql("UPDATE workout_sessions SET status = 'abandoned' WHERE id = ?", (session_id,))
        return len(closed)


def fail_interrupted_jobs(target_engine=engine) -> int:
    """Mark in-flight video jobs failed after a process restart. Completed rows stay completed."""
    with target_engine.begin() as conn:
        if "processing_status" not in _columns(conn, "recorded_sets"):
            return 0
        placeholders = ", ".join("?" for _ in INTERRUPTED_PROCESSING)
        result = conn.exec_driver_sql(
            f"UPDATE recorded_sets SET processing_status = 'FAILED', processing_message = ? "
            f"WHERE processing_status IN ({placeholders})",
            (INTERRUPTED_JOB_MESSAGE, *INTERRUPTED_PROCESSING),
        )
        return int(result.rowcount or 0)


def _parse_time(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def migrate_profile_columns(target_engine=engine) -> None:
    """Add profile columns in place. Existing rows keep their values."""
    with target_engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(profiles)").fetchall()
        if not rows:
            return
        names = {row[1] for row in rows}
        if "assessment_json" not in names:
            conn.exec_driver_sql("ALTER TABLE profiles ADD COLUMN assessment_json TEXT")
        if "draft_json" not in names:
            conn.exec_driver_sql("ALTER TABLE profiles ADD COLUMN draft_json TEXT")
        if "submitted" not in names:
            conn.exec_driver_sql("ALTER TABLE profiles ADD COLUMN submitted BOOLEAN NOT NULL DEFAULT 1")
        if "age_range" not in names:
            conn.exec_driver_sql("ALTER TABLE profiles ADD COLUMN age_range TEXT")
        stored = conn.exec_driver_sql("SELECT id, assessment_json, age_range FROM profiles").fetchall()
        for row in stored:
            if row[2] or not row[1]:
                continue
            try:
                age = (json.loads(row[1]).get("identity") or {}).get("age_range")
            except json.JSONDecodeError:
                continue
            if age:
                conn.exec_driver_sql("UPDATE profiles SET age_range = ? WHERE id = ?", (age, row[0]))
