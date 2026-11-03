"""Owner-only training history for workout generation.

Completed, valid sets only. Previews, sample clips, failed recordings, and
unlogged rows are omitted. Timed holds are not treated as repetitions, and
unknown loads stay unknown.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.models.entities import RecordedSet, WorkoutSession
from app.services.recording_provenance import is_performed_set, is_sample_set
from app.services.workout.local_planner import TIMED

def is_personalization_set(rec: RecordedSet) -> bool:
    """A set that may inform a future proposal. Owner filtering happens at session query time."""
    return is_performed_set(rec)


def completed_training_session_count(db: Session, user_id: str) -> int:
    """Rotate once per owned, completed, plan-backed session with performed work."""
    sessions = (
        db.query(WorkoutSession)
        .options(selectinload(WorkoutSession.recorded_sets))
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.status == "completed",
            WorkoutSession.plan_id.is_not(None),
        )
        .all()
    )
    return sum(
        any(rec.user_id == user_id and is_performed_set(rec) for rec in session.recorded_sets)
        for session in sessions
    )


def recent_training_context(db: Session, user_id: str, limit: int = 4) -> list[dict]:
    """Sanitized completed sessions for the authenticated user only."""
    rows = (
        db.query(WorkoutSession)
        .filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.status == "completed",
        )
        .order_by(WorkoutSession.completed_at.desc())
        .all()
    )
    summary: list[dict] = []
    for session in rows:
        if len(summary) >= limit:
            break
        exercises = _session_exercises(session)
        if not exercises:
            continue
        summary.append(
            {
                "completed_on": session.completed_at.date().isoformat() if session.completed_at else None,
                "session_type": session.plan.session_type if session.plan else None,
                "exercises": exercises,
            }
        )
    return summary


def _session_exercises(session: WorkoutSession) -> list[dict]:
    chosen: dict[tuple, RecordedSet] = {}
    for rec in session.recorded_sets:
        if rec.user_id != session.user_id:
            continue
        if not is_personalization_set(rec):
            continue
        key = (rec.exercise_id, rec.set_index) if rec.set_index is not None else ("id", rec.id)
        previous = chosen.get(key)
        if previous is None or _prefer(rec, previous):
            chosen[key] = rec

    by_exercise: dict[str, dict] = {}
    for rec in chosen.values():
        bucket = by_exercise.setdefault(
            rec.exercise_id,
            {
                "exercise_id": rec.exercise_id,
                "sets": 0,
                "completed_reps": [],
                "timed_seconds": [],
                "target_reps": [],
            },
        )
        bucket["sets"] += 1
        target = rec.target_reps
        if rec.exercise_id in TIMED:
            if rec.completed_reps is not None:
                bucket["timed_seconds"].append(rec.completed_reps)
            if target is not None:
                bucket["target_reps"].append(target)
        else:
            if rec.completed_reps is not None:
                bucket["completed_reps"].append(rec.completed_reps)
            if target is not None:
                bucket["target_reps"].append(target)
            if rec.load_kg is not None:
                best = bucket.get("best_load_kg")
                bucket["best_load_kg"] = rec.load_kg if best is None else max(best, rec.load_kg)
    return list(by_exercise.values())


def _prefer(candidate: RecordedSet, current: RecordedSet) -> bool:
    rank = {"video": 2, "manual": 1, "demo": 0}
    return rank.get(candidate.entry_source or "", 0) >= rank.get(current.entry_source or "", 0)
