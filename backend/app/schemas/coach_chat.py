"""Chat accepts questions, never measurements, targets, links or tool requests."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONSENT_VERSION = "coach-chat-2026-11-02"


class CoachQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    question: str = Field(min_length=1, max_length=400)
    previous_questions: list[str] = Field(default_factory=list, max_length=2)
    selected_rep: int | None = Field(default=None, ge=1, le=1000)
    consent_version: Literal["coach-chat-2026-11-02"] | None = None
    approve_question: bool = False

    @field_validator("question")
    @classmethod
    def clean_question(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Enter a question about this set.")
        return value

    @field_validator("previous_questions")
    @classmethod
    def bounded_history(cls, values):
        if any(not v.strip() or len(v) > 400 for v in values):
            raise ValueError("Previous questions must contain 1–400 characters.")
        return [v.strip() for v in values]


class ChatEvidenceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(max_length=80)
    set_id: str = Field(max_length=36)
    rep_id: int
    seconds: float


class ChatSelection(BaseModel):
    """Muse selects verified clauses; arbitrary generated prose is never displayed.

    A second model judging fluent claims cannot enforce measurement grounding.
    This deliberately bounded first version composes the selected facts itself.
    """
    model_config = ConfigDict(extra="forbid", strict=True)
    answer_ids: list[str] = Field(min_length=1, max_length=4)
    evidence: list[ChatEvidenceSelection] = Field(max_length=2)
    suggested_ui_action: Literal["none", "replay", "view_comparison", "watch_demo", "review_recommendation"]
