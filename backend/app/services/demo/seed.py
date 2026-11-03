"""Create or remove only the isolated demo athlete. Never touches other users."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.entities import (
    AnalysisResult,
    CoachingDecision,
    ConsentRecord,
    Profile,
    RecordedSet,
    RepMetric,
    User,
    UserSession,
    WorkoutExercise,
    WorkoutPlan,
    WorkoutSession,
)
from app.services.demo.dataset import DemoDataset, build_dataset, fingerprint
from app.services.demo.identity import DEMO_DISPLAY_NAME, DEMO_USER_ID


@dataclass
class SeedResult:
    action: str
    dry_run: bool
    user_id: str
    timezone: str
    anchor: str
    message: str
    plans: int = 0
    sessions: int = 0
    completed: int = 0
    abandoned: int = 0
    paused: int = 0
    sets: int = 0
    missed: int = 0
    preserved_other_users: int | None = None
    details: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            f"{self.action}{' (dry run)' if self.dry_run else ''}: {self.message}",
            f"demo user: {self.user_id}",
            f"anchor: {self.anchor}  timezone: {self.timezone}",
            f"plans={self.plans} sessions={self.sessions} completed={self.completed} "
            f"ended-early={self.abandoned} paused={self.paused} sets={self.sets} missed-days={self.missed}",
        ]
        lines.extend(f"  {line}" for line in self.details)
        return "\n".join(lines)


class DemoBusyError(RuntimeError):
    """Demo account has records that are not this seed. Requires --refresh."""


def local_zone(name: str | None) -> ZoneInfo:
    if name:
        return ZoneInfo(name)
    current = datetime.now().astimezone().tzinfo
    key = getattr(current, "key", None)
    if isinstance(key, str) and key:
        return ZoneInfo(key)
    return ZoneInfo("UTC")


def seed_demo(
    db: Session,
    *,
    anchor: date | None = None,
    timezone_name: str | None = None,
    refresh: bool = False,
    dry_run: bool = False,
) -> SeedResult:
    """Idempotent seed. Refuses to overwrite later demo edits unless refresh=True."""
    tz = local_zone(timezone_name)
    today = anchor or datetime.now(tz).date()
    dataset = build_dataset(today, tz)
    existing = db.get(User, DEMO_USER_ID)
    others = db.query(User).filter(User.id != DEMO_USER_ID).count()
    if existing is None:
        result = _summary("create", dataset, dry_run, "Would create the demo athlete." if dry_run else "Created the demo athlete.")
        result.preserved_other_users = others
        if not dry_run:
            _insert(db, dataset)
            db.commit()
        return result

    current = _existing_fingerprint(db)
    expected = fingerprint(dataset)
    if current == expected and not refresh:
        result = _summary("reuse", dataset, dry_run, "Demo dataset already matches. Nothing to write.")
        result.preserved_other_users = others
        return result
    if not refresh:
        raise DemoBusyError(
            "The demo account has records that are not this seed "
            "(later edits, a different anchor, or a previous version). "
            "Re-run with --refresh to replace only the demo athlete. "
            "Other users are not changed."
        )
    result = _summary(
        "refresh",
        dataset,
        dry_run,
        "Would delete and recreate only the demo athlete." if dry_run else "Replaced the demo athlete.",
    )
    result.preserved_other_users = others
    if not dry_run:
        _delete_demo_user(db)
        db.commit()
        _insert(db, dataset)
        db.commit()
    return result


def cleanup_demo(db: Session, *, dry_run: bool = False) -> SeedResult:
    user = db.get(User, DEMO_USER_ID)
    others = db.query(User).filter(User.id != DEMO_USER_ID).count()
    if user is None:
        return SeedResult(
            action="cleanup",
            dry_run=dry_run,
            user_id=DEMO_USER_ID,
            timezone="",
            anchor="",
            message="No demo athlete to remove.",
            preserved_other_users=others,
        )
    plans = db.query(WorkoutPlan).filter(WorkoutPlan.user_id == DEMO_USER_ID).count()
    sessions = db.query(WorkoutSession).filter(WorkoutSession.user_id == DEMO_USER_ID).all()
    sets = db.query(RecordedSet).filter(RecordedSet.user_id == DEMO_USER_ID).count()
    result = SeedResult(
        action="cleanup",
        dry_run=dry_run,
        user_id=DEMO_USER_ID,
        timezone="",
        anchor="",
        message="Would remove only the demo athlete." if dry_run else "Removed only the demo athlete.",
        plans=plans,
        sessions=len(sessions),
        completed=sum(1 for row in sessions if row.status == "completed"),
        abandoned=sum(1 for row in sessions if row.status == "abandoned"),
        paused=sum(1 for row in sessions if row.status in {"active", "paused"}),
        sets=sets,
        preserved_other_users=others,
    )
    if not dry_run:
        _delete_demo_user(db)
        db.commit()
    return result


def _insert(db: Session, dataset: DemoDataset) -> None:
    user = User(
        id=dataset.user_id,
        display_name=DEMO_DISPLAY_NAME,
        created_at=dataset.sessions[0].plan_created_at - timedelta(days=21),
    )
    db.add(user)
    db.add(
        Profile(
            id=dataset.profile_id,
            user_id=dataset.user_id,
            goal=dataset.profile_flat["goal"],
            experience=dataset.profile_flat["experience"],
            days_per_week=dataset.profile_flat["days_per_week"],
            session_duration_minutes=dataset.profile_flat["session_duration_minutes"],
            equipment_json=json.dumps(dataset.profile_flat["equipment"]),
            current_squat_load_kg=dataset.profile_flat["current_squat_load_kg"],
            optional_height_cm=None,
            optional_weight_kg=None,
            limitations_json="[]",
            assessment_json=json.dumps(dataset.assessment),
            submitted=True,
            age_range=dataset.profile_flat["age_range"],
            created_at=user.created_at,
            updated_at=dataset.sessions[-1].started_at,
        )
    )
    for spec in dataset.sessions:
        db.add(
            WorkoutPlan(
                id=spec.plan_id,
                user_id=dataset.user_id,
                name=spec.name,
                status="active" if spec.status in {"active", "paused", "abandoned"} else "completed",
                source="local",
                duration_minutes=spec.duration_minutes,
                estimated_minutes=spec.estimated_minutes,
                session_type=spec.focus,
                notes=spec.notes,
                created_at=spec.plan_created_at,
            )
        )
        db.flush()
        for item in spec.exercises:
            db.add(
                WorkoutExercise(
                    id=demo_exercise_id(spec.key, item["exercise_id"]),
                    plan_id=spec.plan_id,
                    exercise_id=item["exercise_id"],
                    position=item["position"],
                    sets=item["sets"],
                    target_reps=item["target_reps"],
                    rest_seconds=item["rest_seconds"],
                    suggested_load_kg=item["suggested_load_kg"],
                    notes=item.get("notes"),
                )
            )
        db.add(
            WorkoutSession(
                id=spec.id,
                user_id=dataset.user_id,
                plan_id=spec.plan_id,
                status=spec.status,
                started_at=spec.started_at,
                paused_at=spec.paused_at,
                completed_at=spec.completed_at,
            )
        )
        for item in spec.sets:
            db.add(
                RecordedSet(
                    id=item.id,
                    session_id=spec.id,
                    user_id=dataset.user_id,
                    exercise_id=item.exercise_id,
                    entry_source="manual",
                    set_index=item.set_index,
                    load_kg=item.load_kg,
                    target_reps=item.target_reps,
                    completed_reps=item.completed_reps,
                    reported_rpe=item.reported_rpe,
                    processing_status="LOGGED",
                    created_at=item.created_at,
                )
            )


def _delete_demo_user(db: Session) -> None:
    user = db.get(User, DEMO_USER_ID)
    if user is None:
        return
    set_ids = [row[0] for row in db.query(RecordedSet.id).filter(RecordedSet.user_id == DEMO_USER_ID).all()]
    if set_ids:
        db.query(CoachingDecision).filter(CoachingDecision.set_id.in_(set_ids)).delete(synchronize_session=False)
        db.query(RepMetric).filter(RepMetric.set_id.in_(set_ids)).delete(synchronize_session=False)
        db.query(AnalysisResult).filter(AnalysisResult.set_id.in_(set_ids)).delete(synchronize_session=False)
        db.query(ConsentRecord).filter(ConsentRecord.recording_id.in_(set_ids)).delete(synchronize_session=False)
    db.query(RecordedSet).filter(RecordedSet.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    db.query(WorkoutSession).filter(WorkoutSession.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    plan_ids = [row[0] for row in db.query(WorkoutPlan.id).filter(WorkoutPlan.user_id == DEMO_USER_ID).all()]
    if plan_ids:
        db.query(WorkoutExercise).filter(WorkoutExercise.plan_id.in_(plan_ids)).delete(synchronize_session=False)
    db.query(WorkoutPlan).filter(WorkoutPlan.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    db.query(ConsentRecord).filter(ConsentRecord.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    db.query(Profile).filter(Profile.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    db.query(UserSession).filter(UserSession.user_id == DEMO_USER_ID).delete(synchronize_session=False)
    db.delete(user)


def _existing_fingerprint(db: Session) -> str:
    rows = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.user_id == DEMO_USER_ID)
        .order_by(WorkoutSession.id)
        .all()
    )
    parts = []
    for row in rows:
        count = db.query(RecordedSet).filter(RecordedSet.session_id == row.id).count()
        parts.append(f"{row.id}:{row.status}:{count}")
    return "|".join(sorted(parts))


def _summary(action: str, dataset: DemoDataset, dry_run: bool, message: str) -> SeedResult:
    sessions = dataset.sessions
    return SeedResult(
        action=action,
        dry_run=dry_run,
        user_id=dataset.user_id,
        timezone=dataset.timezone,
        anchor=dataset.anchor.isoformat(),
        message=message,
        plans=len(sessions),
        sessions=len(sessions),
        completed=sum(1 for row in sessions if row.status == "completed"),
        abandoned=sum(1 for row in sessions if row.status == "abandoned"),
        paused=sum(1 for row in sessions if row.status == "paused"),
        sets=sum(len(row.sets) for row in sessions),
        missed=len(dataset.missed),
        details=[
            f"{row.local_date.isoformat()} {row.name} ({row.status}, {len(row.sets)} sets)"
            + (f" — {row.extra_note}" if row.extra_note else "")
            for row in sessions
        ]
        + [f"{item['local_date']} missed {item['weekday']}: {item['reason']}" for item in dataset.missed],
    )


def demo_exercise_id(session_key: str, exercise_id: str) -> str:
    from app.services.demo.identity import demo_id

    return demo_id("exercise", session_key, exercise_id)
