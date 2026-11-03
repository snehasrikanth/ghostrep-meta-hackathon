from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.models.entities import MetaUsageEvent
from app.services.meta.providers import (
    resolve_coaching_provider,
    resolve_segmentation_provider,
    resolve_workout_provider,
)
from sqlalchemy.orm import Session


class MetaBlocked(RuntimeError):
    """Raised when a paid Meta call is refused. Never swallowed into fake results."""


@dataclass
class Approval:
    token: str
    purpose: str


class MetaGateway:
    """Single chokepoint for every Meta Model API request."""

    def __init__(self, settings: Settings, db: Session | None = None):
        self.settings = settings
        self.db = db
        self._log_path = settings.data_dir / "meta-usage.jsonl"

    def current_provider(self) -> str:
        return (self.settings.ai_provider or "local").lower()

    def live_enabled(self) -> bool:
        return bool(self.settings.enable_meta_api) and self.current_provider() == "meta_live"

    def authorize(
        self,
        *,
        model: str,
        purpose: str,
        estimated_cost_usd: float,
        approval_token: str | None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        video_frames: int = 0,
    ) -> None:
        reason = self._block_reason(purpose, estimated_cost_usd, approval_token)
        allowed = reason is None
        self._record(
            model=model,
            purpose=purpose,
            allowed=allowed,
            blocked_reason=reason,
            estimated_cost_usd=estimated_cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            video_frames=video_frames,
        )
        if not allowed:
            raise MetaBlocked(reason or "Meta request blocked")

    def _block_reason(self, purpose: str, estimated_cost_usd: float, approval_token: str | None) -> str | None:
        if not self.settings.enable_meta_api:
            return "ENABLE_META_API is false. Local/fixture providers only."
        provider = self._provider_for(purpose)
        if provider != "meta_live":
            return f"{purpose} uses provider {provider}, so no live Meta call is made."
        if not self.settings.model_api_key:
            return "MODEL_API_KEY is empty."
        if self.settings.meta_require_explicit_approval:
            if not approval_token or not self._valid_approval(approval_token, purpose):
                return "Explicit approval token missing or invalid."
        if self.settings.meta_max_calls_per_session is not None and self._session_calls() >= self.settings.meta_max_calls_per_session:
            return "META_MAX_CALLS_PER_SESSION exceeded."
        if self.settings.meta_estimated_spend_limit_usd is not None and self._session_spend() + estimated_cost_usd > self.settings.meta_estimated_spend_limit_usd:
            return "META_ESTIMATED_SPEND_LIMIT_USD would be exceeded."
        return None

    def _provider_for(self, purpose: str) -> str:
        if purpose == "workout_generation":
            return resolve_workout_provider(self.settings)
        if purpose in {"coaching", "coach_chat"}:
            return resolve_coaching_provider(self.settings)
        if purpose.startswith("sam"):
            return resolve_segmentation_provider(self.settings)
        return self.current_provider()

    def _valid_approval(self, token: str, purpose: str) -> bool:
        # Operator must send META_APPROVAL:<purpose>:<sha256(key)[:8]>
        expected = "META_APPROVAL:" + purpose + ":" + hashlib.sha256(self.settings.model_api_key.encode()).hexdigest()[:8]
        return token == expected

    def _session_calls(self) -> int:
        if not self.db:
            return 0
        return (
            self.db.query(MetaUsageEvent)
            .filter(MetaUsageEvent.allowed.is_(True), MetaUsageEvent.provider == "meta_live")
            .count()
        )

    def _session_spend(self) -> float:
        if not self.db:
            return 0.0
        rows = (
            self.db.query(MetaUsageEvent)
            .filter(MetaUsageEvent.allowed.is_(True), MetaUsageEvent.provider == "meta_live")
            .all()
        )
        return float(sum(r.estimated_cost_usd for r in rows))

    def _record(self, **kwargs) -> None:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "provider": "meta_live" if kwargs.get("allowed") else self.current_provider(),
            **kwargs,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        if self.db is not None and "model" in kwargs:
            self.db.add(
                MetaUsageEvent(
                    model=kwargs["model"],
                    purpose=kwargs["purpose"],
                    provider=event["provider"],
                    allowed=kwargs["allowed"],
                    blocked_reason=kwargs.get("blocked_reason"),
                    estimated_cost_usd=kwargs.get("estimated_cost_usd") or 0.0,
                    input_tokens=kwargs.get("input_tokens") or 0,
                    output_tokens=kwargs.get("output_tokens") or 0,
                    video_frames=kwargs.get("video_frames") or 0,
                )
            )
            self.db.commit()

    def note(self, **kwargs) -> None:
        """Log a request or retry without counting it as an allowed paid call."""
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kwargs.get("kind", "note"),
            "allowed": False,
            **kwargs,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")


def approval_hint(settings: Settings, purpose: str) -> str:
    if not settings.model_api_key:
        return "Set MODEL_API_KEY, then generate META_APPROVAL:<purpose>:<key-fingerprint>."
    fingerprint = hashlib.sha256(settings.model_api_key.encode()).hexdigest()[:8]
    return f"META_APPROVAL:{purpose}:{fingerprint}"


def usage_log(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
