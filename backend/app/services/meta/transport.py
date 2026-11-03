"""HTTP boundary for the Meta Model API.

Live calls are constructed only after the gateway has authorized them.
Tests pass a fake transport and never build an OpenAI client.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings
from app.services.meta.errors import (
    MetaRateLimited,
    MetaRejected,
    MetaTimeout,
    MetaUnavailable,
    TransientMetaError,
)


@dataclass
class ChatResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    http_status: int | None = None
    finish_reason: str | None = None
    reasoning_tokens: int = 0


def response_diagnostics(
    result: ChatResult,
    *,
    schema_validation: str,
    error: str | None = None,
) -> dict[str, Any]:
    content = result.content if result.content is not None else ""
    present = bool(str(content).strip())
    return {
        "http_status": result.http_status,
        "finish_reason": result.finish_reason,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "reasoning_tokens": result.reasoning_tokens,
        "content_present": present,
        "content_length": len(content),
        "schema_validation": schema_validation,
        "error": error,
    }


def sanitize_error(message: str, secret: str = "") -> str:
    text = str(message or "")[:400]
    if secret:
        text = text.replace(secret, "[redacted]")
    return text


class MetaTransport(Protocol):
    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict],
        response_format: dict,
        timeout: float,
        max_completion_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> ChatResult: ...

    def upload_user_file(self, path: Path) -> str: ...

    def delete_file(self, file_id: str) -> None: ...

    def responses_events(self, *, body: dict, timeout: float) -> list[dict]: ...


def call_with_retries(operation, settings: Settings, on_retry):
    """Retry rate limits, timeouts, and 5xx. A 400 is permanent."""
    attempts = max(1, int(settings.meta_max_retries) + 1)
    last: TransientMetaError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except TransientMetaError as exc:
            last = exc
            on_retry(attempt, exc.kind)
            if attempt == attempts:
                break
            if settings.meta_retry_sleep:
                time.sleep(min(2 ** (attempt - 1), 4))
        except MetaRejected:
            raise
    assert last is not None
    if last.kind == "rate_limit":
        raise MetaRateLimited("Meta is rate limiting requests. Please try again shortly.") from last
    if last.kind == "timeout":
        raise MetaTimeout("Meta took too long to respond. Please try again.") from last
    if last.kind == "connection":
        raise MetaUnavailable(
            "GhostRep could not connect to Meta. Check the backend's internet access and try again."
        ) from last
    raise MetaUnavailable("Meta is temporarily unavailable. Please try again shortly.") from last


def translate_sdk_error(exc: Exception) -> Exception:
    """Map OpenAI SDK errors onto GhostRep's retry policy. A 400 is not retried."""
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    if name == "RateLimitError" or status == 429:
        return TransientMetaError("rate_limit", str(exc)[:240])
    if name == "APITimeoutError":
        return TransientMetaError("timeout", str(exc)[:240])
    if name == "APIConnectionError":
        return TransientMetaError("connection", str(exc)[:240])
    if name == "BadRequestError" or status == 400:
        return MetaRejected(str(exc)[:300])
    if isinstance(status, int) and status >= 500:
        return TransientMetaError("server", str(exc)[:240])
    return exc


class OpenAIMetaTransport:
    """Official OpenAI SDK against https://api.meta.ai/v1. Built only for an authorized live call."""

    def __init__(self, settings: Settings):
        from openai import OpenAI

        self._client = OpenAI(
            base_url=settings.meta_base_url,
            api_key=settings.model_api_key,
            timeout=settings.meta_request_timeout_seconds,
            max_retries=0,
        )
        self._settings = settings

    def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict],
        response_format: dict,
        timeout: float,
        max_completion_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> ChatResult:
        request = {
            "model": model,
            "messages": messages,
            "response_format": response_format,
            "timeout": timeout,
        }
        if max_completion_tokens is not None:
            request["max_completion_tokens"] = max_completion_tokens
        if reasoning_effort is not None:
            request["reasoning_effort"] = reasoning_effort
        try:
            completion = self._client.chat.completions.create(**request)
        except Exception as exc:
            mapped = translate_sdk_error(exc)
            setattr(mapped, "http_status", getattr(exc, "status_code", None))
            raise mapped from exc
        usage = getattr(completion, "usage", None)
        details = getattr(usage, "completion_tokens_details", None) if usage is not None else None
        choice = completion.choices[0]
        message = choice.message
        raw_content = getattr(message, "content", None)
        content = raw_content if isinstance(raw_content, str) else ""
        return ChatResult(
            content=content,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            http_status=200,
            finish_reason=getattr(choice, "finish_reason", None),
            reasoning_tokens=int(getattr(details, "reasoning_tokens", 0) or 0),
        )

    def upload_user_file(self, path: Path) -> str:
        try:
            with path.open("rb") as handle:
                uploaded = self._client.files.create(file=handle, purpose="user_data")
        except Exception as exc:
            raise translate_sdk_error(exc) from exc
        return uploaded.id

    def delete_file(self, file_id: str) -> None:
        self._client.files.delete(file_id)

    def responses_events(self, *, body: dict, timeout: float) -> list[dict]:
        try:
            stream = self._client.responses.create(timeout=timeout, **body)
            events = []
            for event in stream:
                if hasattr(event, "model_dump"):
                    events.append(event.model_dump())
                else:
                    events.append({"type": getattr(event, "type", "")})
            return events
        except Exception as exc:
            raise translate_sdk_error(exc) from exc


def payload_digest(payload: Any) -> str:
    import hashlib
    import json

    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:16]
