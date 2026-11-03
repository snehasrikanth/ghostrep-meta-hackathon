from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_mode: str = Field(default="real", description="real | demo — demo never pretends to be live Meta")
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:3000"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    database_url: str = "sqlite:///./data/ghostrep.db"
    data_dir: Path = Path("./data")
    retention_hours: int = 24
    retain_raw_video: bool = False
    max_upload_mb: int = 80
    max_video_seconds: float = 90.0
    target_analysis_fps: float = 15.0

    # Legacy switch. Workout and coaching inherit it when their own provider is unset.
    # Segmentation does not inherit it: video segmentation stays off until chosen.
    ai_provider: str = "local"
    workout_provider: str = ""
    coaching_provider: str = ""
    segmentation_provider: str = "none"
    sam_include_barbell: bool = False
    enable_meta_api: bool = False
    meta_require_explicit_approval: bool = True
    # Optional operator controls. Unset means no application-imposed usage cap.
    meta_max_calls_per_session: int | None = None
    meta_estimated_spend_limit_usd: float | None = None
    meta_request_timeout_seconds: float = 180
    coach_chat_max_completion_tokens: int = Field(default=8192, ge=2048, le=16384)
    coach_chat_timeout_seconds: float = Field(default=90, gt=0, le=90)
    sam_stage_timeout_seconds: float = Field(default=150, ge=30, le=300)
    sam_parse_timeout_seconds: float = Field(default=45, gt=0, le=90)
    meta_max_retries: int = 2
    meta_retry_sleep: bool = True
    model_api_key: str = ""
    meta_base_url: str = "https://api.meta.ai/v1"
    muse_model: str = "muse-spark-1.3"
    sam_model: str = "sam-3.1"

    session_cookie: str = "ghostrep_session"
    session_days: int = 30
    consent_version: str = "2026-10-26"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"

    @property
    def models_dir(self) -> Path:
        return Path(__file__).resolve().parents[1] / "models"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.derived_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
