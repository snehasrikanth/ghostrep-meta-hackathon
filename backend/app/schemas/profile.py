from typing import Any, Literal

from pydantic import BaseModel, Field

Goal = Literal["build_strength", "build_muscle", "improve_conditioning", "learn_technique"]
Experience = Literal["beginner", "intermediate", "advanced"]
AgeRange = Literal[
    "18_29",
    "30_39",
    "40_49",
    "50_59",
    "60_64",
    "65_74",
    "75_plus",
    "prefer_not_to_say",
    "under_18",
    "18_24",
    "25_34",
    "35_44",
    "45_54",
    "55_plus",
]


class DraftIn(BaseModel):
    draft: dict[str, Any]


class ProfileIn(BaseModel):
    goal: Goal
    experience: Experience
    days_per_week: int = Field(ge=1, le=7)
    session_duration_minutes: int = Field(ge=20, le=120)
    equipment: list[str] = Field(min_length=1)
    current_squat_load_kg: float | None = Field(default=None, ge=0, le=400)
    optional_height_cm: float | None = Field(default=None, ge=100, le=230)
    optional_weight_kg: float | None = Field(default=None, ge=30, le=250)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    display_name: str | None = Field(default=None, max_length=80)
    age_range: AgeRange | None = None
    assessment: dict[str, Any] | None = None


class ProfileOut(ProfileIn):
    id: str
    user_id: str
