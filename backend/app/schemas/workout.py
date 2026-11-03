from pydantic import BaseModel, Field


class WorkoutExerciseIn(BaseModel):
    exercise_id: str
    sets: int = Field(ge=1, le=8)
    target_reps: int = Field(ge=1, le=30)
    rest_seconds: int = Field(ge=15, le=300)
    suggested_load_kg: float | None = Field(default=None, ge=0, le=400)
    notes: str | None = None


class WorkoutExerciseOut(WorkoutExerciseIn):
    id: str
    position: int


class WorkoutPlanOut(BaseModel):
    id: str
    name: str
    status: str
    source: str
    source_label: str
    duration_minutes: int
    notes: str | None = None
    exercises: list[WorkoutExerciseOut]


class WorkoutGenerateIn(BaseModel):
    # None follows the split rotation. A named focus forces one session type.
    focus: str | None = None
    approve_meta_spend: bool = False


class WorkoutPatchIn(BaseModel):
    name: str | None = None
    exercises: list[WorkoutExerciseIn] | None = None


class SessionOut(BaseModel):
    id: str
    plan_id: str | None
    status: str
    started_at: str
    completed_at: str | None = None
