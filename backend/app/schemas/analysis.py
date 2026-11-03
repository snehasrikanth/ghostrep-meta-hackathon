from typing import Any, Literal

from pydantic import BaseModel, Field

ProcessingStatus = Literal[
    "UPLOADED",
    "VALIDATING",
    "PREPROCESSING",
    "ESTIMATING_POSE",
    "SEGMENTING",
    "DETECTING_REPS",
    "COMPUTING_METRICS",
    "GENERATING_COACHING",
    "COMPLETED",
    "FAILED",
]


class Landmark(BaseModel):
    name: str
    x: float
    y: float
    visibility: float


class FramePose(BaseModel):
    timestamp: float
    width: int
    height: int
    tracking_confidence: float
    landmarks: list[Landmark]


class RepOut(BaseModel):
    rep_id: int
    start_seconds: float
    bottom_seconds: float
    end_seconds: float
    descent_seconds: float
    ascent_seconds: float
    is_complete: bool
    is_reference: bool
    confidence: float
    metrics: dict[str, float]


class QualityIssue(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warn", "block"]


class QualityResult(BaseModel):
    usable: bool
    score: float
    issues: list[QualityIssue]
    side: Literal["left", "right"]
    notes: list[str] = Field(default_factory=list)


class DriftPoint(BaseModel):
    rep_id: int
    similarity: float
    torso_lean_difference_deg: float
    depth_difference_percent: float
    ascent_duration_difference_percent: float
    descent_duration_difference_percent: float
    knee_angle_rmse_deg: float
    hip_rmse: float
    onset: bool


class OverlayFrame(BaseModel):
    t: float
    active_rep: int | None
    phase: str
    phase_progress: float
    current: list[Landmark]
    reference: list[Landmark] | None


class OverlayPayload(BaseModel):
    analysis_id: str
    video_url: str | None
    reference_rep: int | None
    skeleton_edges: list[tuple[str, str]]
    frames: list[OverlayFrame]
    sam_available: bool
    sam_status: str
    color_reference: str = "#2EE6D6"
    color_current: str = "#FF8A3D"


class AnalysisOut(BaseModel):
    id: str
    set_id: str
    status: ProcessingStatus
    message: str | None = None
    exercise_id: str
    duration_seconds: float | None
    completed_reps: int | None
    reference_rep: int | None
    tracking_quality: QualityResult | None = None
    reps: list[RepOut] = Field(default_factory=list)
    drift: list[DriftPoint] = Field(default_factory=list)
    pose_available: bool = False
    sam_available: bool = False
    sam_status: str = "unavailable"
    analysis_version: str = "local-v1"
    mode: str = "real"
    extra: dict[str, Any] = Field(default_factory=dict)
