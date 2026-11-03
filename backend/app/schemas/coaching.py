from typing import Literal

from pydantic import BaseModel, Field

CoachAction = Literal[
    "KEEP_PLAN",
    "REDUCE_REPS",
    "EXTEND_REST",
    "REDUCE_LOAD_CONSERVATIVELY",
    "REQUEST_NEW_RECORDING",
    "NO_RECOMMENDATION",
    "STOP_AND_SEEK_PROFESSIONAL_ADVICE",
]


class Observation(BaseModel):
    metric: str
    statement: str
    evidence_seconds: list[float] = Field(default_factory=list)
    magnitude: float | None = None


class CoachingPayload(BaseModel):
    source: str
    source_label: str
    summary: str
    observations: list[Observation]
    evidence_references: list[float]
    confidence_notes: list[str]
    uncertainties: list[str]
    suggested_action: CoachAction
    reason: str
    primary_cue: str | None = None
    requires_confirmation: bool = True
    suggested_reps: int | None = None
    suggested_rest_seconds: int | None = None
    suggested_load_kg: float | None = None
    current_reps: int | None = None
    current_rest_seconds: int | None = None
    current_load_kg: float | None = None
    planned_set_reps: int | None = None
    planned_set_load_kg: float | None = None
    completed_reps: int | None = None
    workout_reps: int | None = None
    workout_rest_seconds: int | None = None
    workout_load_kg: float | None = None


class CoachingDecisionOut(CoachingPayload):
    id: str
    set_id: str
    user_decision: Literal["pending", "accepted", "rejected"]


class CoachingDecisionIn(BaseModel):
    decision: Literal["accepted", "rejected"]
    recommendation_id: str | None = None
    expected_revision: int | None = Field(default=None, ge=0)


class CoachingActivationIn(BaseModel):
    recommendation_id: str
    expected_revision: int = Field(ge=0)
