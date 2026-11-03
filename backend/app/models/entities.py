from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False)
    sessions: Mapped[list[UserSession]] = relationship(back_populates="user")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    goal: Mapped[str] = mapped_column(String(40))
    experience: Mapped[str] = mapped_column(String(40))
    days_per_week: Mapped[int] = mapped_column(Integer)
    session_duration_minutes: Mapped[int] = mapped_column(Integer)
    equipment_json: Mapped[str] = mapped_column(Text)
    current_squat_load_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    optional_height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    optional_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    limitations_json: Mapped[str] = mapped_column(Text, default="[]")
    assessment_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted: Mapped[bool] = mapped_column(Boolean, default=True)
    age_range: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="profile")


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="active")
    source: Mapped[str] = mapped_column(String(24), default="local")
    duration_minutes: Mapped[int] = mapped_column(Integer)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    exercises: Mapped[list[WorkoutExercise]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="WorkoutExercise.position"
    )


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("workout_plans.id"), index=True)
    exercise_id: Mapped[str] = mapped_column(String(64), index=True)
    position: Mapped[int] = mapped_column(Integer)
    sets: Mapped[int] = mapped_column(Integer)
    target_reps: Mapped[int] = mapped_column(Integer)
    rest_seconds: Mapped[int] = mapped_column(Integer)
    suggested_load_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped[WorkoutPlan] = relationship(back_populates="exercises")


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("workout_plans.id"), nullable=True)
    # active | paused | completed | abandoned. A plan with no session is "planned".
    status: Mapped[str] = mapped_column(String(24), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[WorkoutPlan | None] = relationship()
    recorded_sets: Mapped[list[RecordedSet]] = relationship(back_populates="session", order_by="RecordedSet.created_at")


class RecordedSet(Base):
    __tablename__ = "recorded_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("workout_sessions.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    exercise_id: Mapped[str] = mapped_column(String(64), default="barbell_squat")
    # manual | video | demo
    entry_source: Mapped[str] = mapped_column(String(16), default="video")
    analysis_requested: Mapped[bool] = mapped_column(Boolean, default=True)
    set_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    load_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_rpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="UPLOADED")
    processing_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage_timings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    overlay_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    raw_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[WorkoutSession] = relationship(back_populates="recorded_sets")
    analysis: Mapped[AnalysisResult | None] = relationship(back_populates="recorded_set", uselist=False)
    reps: Mapped[list[RepMetric]] = relationship(back_populates="recorded_set")
    coaching: Mapped[CoachingDecision | None] = relationship(back_populates="recorded_set", uselist=False)


class RepMetric(Base):
    __tablename__ = "rep_metrics"
    __table_args__ = (UniqueConstraint("set_id", "rep_index", name="uq_rep_set_index"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    set_id: Mapped[str] = mapped_column(ForeignKey("recorded_sets.id"), index=True)
    rep_index: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[float] = mapped_column(Float)
    bottom_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    descent_seconds: Mapped[float] = mapped_column(Float)
    ascent_seconds: Mapped[float] = mapped_column(Float)
    is_complete: Mapped[bool] = mapped_column(default=True)
    is_reference: Mapped[bool] = mapped_column(default=False)
    confidence: Mapped[float] = mapped_column(Float)
    metrics_json: Mapped[str] = mapped_column(Text)

    recorded_set: Mapped[RecordedSet] = relationship(back_populates="reps")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    set_id: Mapped[str] = mapped_column(ForeignKey("recorded_sets.id"), unique=True, index=True)
    reference_rep: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_json: Mapped[str] = mapped_column(Text)
    drift_json: Mapped[str] = mapped_column(Text)
    overlay_json: Mapped[str] = mapped_column(Text)
    segmentation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_version: Mapped[str] = mapped_column(String(32), default="local-v1")
    pose_available: Mapped[bool] = mapped_column(default=True)
    sam_available: Mapped[bool] = mapped_column(default=False)
    sam_status: Mapped[str] = mapped_column(String(32), default="unavailable")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    recorded_set: Mapped[RecordedSet] = relationship(back_populates="analysis")


class CoachingDecision(Base):
    __tablename__ = "coaching_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    set_id: Mapped[str] = mapped_column(ForeignKey("recorded_sets.id"), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(24), default="local")
    proposed_action: Mapped[str] = mapped_column(String(48))
    reason: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text)
    user_decision: Mapped[str] = mapped_column(String(24), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    recorded_set: Mapped[RecordedSet] = relationship(back_populates="coaching")


class CoachingVersion(Base):
    """A stored coaching payload that is not the actionable pending decision."""

    __tablename__ = "coaching_versions"
    __table_args__ = (UniqueConstraint("set_id", "artifact_id", name="uq_coaching_version_artifact"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    set_id: Mapped[str] = mapped_column(ForeignKey("recorded_sets.id"), index=True)
    source: Mapped[str] = mapped_column(String(24))
    source_label: Mapped[str] = mapped_column(String(120))
    proposed_action: Mapped[str] = mapped_column(String(48))
    summary: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text)
    artifact_id: Mapped[str] = mapped_column(String(80))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_decision: Mapped[str] = mapped_column(String(24), default="pending")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recorded_sets.id"), index=True)
    consent_version: Mapped[str] = mapped_column(String(32))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MetaUsageEvent(Base):
    __tablename__ = "meta_usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    model: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(24))
    allowed: Mapped[bool] = mapped_column(default=False)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    video_frames: Mapped[int] = mapped_column(Integer, default=0)
