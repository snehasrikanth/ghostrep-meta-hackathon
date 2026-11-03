from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.services.coaching.evidence import ground_coaching
from app.services.coaching.local_coach import generate_local_coaching
from app.services.meta.contracts import (
    accept_week,
    build_coaching_messages,
    build_coaching_model_input,
    build_workout_messages,
    coaching_response_format,
    parse_coaching_payload,
    workout_response_format,
    workout_session_count,
)
from app.services.meta.errors import MetaRejected
from app.services.meta.gateway import MetaBlocked, MetaGateway
from app.services.meta.pricing import (
    COACHING_INPUT_TOKEN_ESTIMATE,
    COACHING_OUTPUT_TOKEN_ESTIMATE,
    COACHING_REASONING_EFFORT,
    WORKOUT_INPUT_TOKEN_ESTIMATE,
    WORKOUT_OUTPUT_TOKEN_ESTIMATE,
    WORKOUT_REASONING_EFFORT,
    estimate_muse_cost,
)
from app.services.meta.providers import resolve_coaching_provider, resolve_workout_provider
from app.services.meta.transport import (
    ChatResult,
    OpenAIMetaTransport,
    call_with_retries,
    payload_digest,
    response_diagnostics,
    sanitize_error,
)
from app.services.workout.local_planner import generate_local_week

_COACH_KEYS = (
    "quality",
    "drift",
    "reps",
    "reference_rep",
    "profile",
    "current_reps",
    "current_rest",
    "current_load",
    "reported_rpe",
    "planned_set_reps",
    "planned_set_load_kg",
    "completed_reps",
    "workout_reps",
    "workout_rest_seconds",
    "workout_load_kg",
)


class MuseProvider:
    def __init__(self, settings: Settings, gateway: MetaGateway, transport=None):
        self.settings = settings
        self.gateway = gateway
        self.transport = transport

    def explain_set(self, context: dict, question: str, previous_questions: list[str], approval_token: str | None = None) -> dict:
        """One bounded structured-only request through the existing gateway.

        No retry wrapper, media, SAM, tool calls or stored response logging.
        Output allowance includes hidden reasoning; exhaustion is a fallback.
        """
        from app.services.coaching.chat import chat_messages, selection_schema
        from app.services.coaching.chat_context import MAX_CONTEXT_BYTES
        if resolve_coaching_provider(self.settings) != "meta_live":
            raise MetaBlocked("Question review is unavailable.")
        if len(json.dumps(context).encode()) > MAX_CONTEXT_BYTES:
            raise MetaRejected("Question context is too large.")
        messages = chat_messages(context, question, previous_questions)
        response_format = {"type": "json_schema", "json_schema": {"name": "set_question", "strict": True, "schema": selection_schema(context)}}
        # UTF-8 bytes conservatively bound input tokens, including schema and
        # questions; output cap bounds hidden reasoning plus visible selection.
        input_bound = len(json.dumps({"messages": messages, "response_format": response_format}).encode()) + 256
        output_bound = self.settings.coach_chat_max_completion_tokens
        self._authorize("coach_chat", input_bound, output_bound, approval_token)
        result = self._require_transport().chat_completion(
            model=self.settings.muse_model, messages=messages, response_format=response_format,
            timeout=min(self.settings.coach_chat_timeout_seconds, self.settings.meta_request_timeout_seconds),
            max_completion_tokens=output_bound, reasoning_effort=COACHING_REASONING_EFFORT,
        )
        self.gateway.note(kind="usage", purpose="coach_chat", model=self.settings.muse_model,
                          input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                          reasoning_tokens=result.reasoning_tokens, finish_reason=result.finish_reason, http_status=result.http_status)
        if not isinstance(result.content, str) or len(result.content.encode()) > 12000:
            raise MetaRejected("Question response exceeded the output limit.")
        return self._parse_live_json(result, "coach_chat")

    def generate_workout(
        self,
        profile: dict,
        focus: str | None = None,
        approval_token: str | None = None,
        session_index: int = 0,
    ) -> dict:
        provider = resolve_workout_provider(self.settings)
        if provider == "local":
            return generate_local_week(profile, focus, session_index)
        if provider == "fixture":
            data = self._load_fixture("workout_generation.json")
            return accept_week(
                data,
                profile,
                session_index,
                "fixture",
                "Saved Muse Spark fixture — not a live call",
            )
        if provider == "meta_live":
            return self._live_workout(profile, focus, approval_token, session_index)
        raise MetaBlocked(f"Unknown workout provider '{provider}'")

    def generate_coaching(self, context: dict, approval_token: str | None = None) -> dict:
        from app.services.coaching.measurement_guard import context_problem
        if context_problem(context):
            # Invalid measurements cannot be repaired by another model call.
            return generate_local_coaching(**{key: context[key] for key in _COACH_KEYS if key in context})
        provider = resolve_coaching_provider(self.settings)
        if provider == "local":
            return generate_local_coaching(**{key: context[key] for key in _COACH_KEYS if key in context})
        if provider == "fixture":
            data = self._load_fixture("coaching.json")
            data["source"] = "fixture"
            data["source_label"] = "Saved Muse Spark fixture — not a live call"
            return ground_coaching(data, context, context.get("profile"))
        if provider == "meta_live":
            return self._live_coaching(context, approval_token)
        raise MetaBlocked(f"Unknown coaching provider '{provider}'")

    def _live_workout(self, profile: dict, focus: str | None, approval_token: str | None, session_index: int) -> dict:
        messages = build_workout_messages(profile, focus, session_index)
        response_format = workout_response_format(session_count=workout_session_count(profile))
        self._authorize("workout_generation", WORKOUT_INPUT_TOKEN_ESTIMATE, WORKOUT_OUTPUT_TOKEN_ESTIMATE, approval_token)
        self.gateway.note(
            kind="request",
            purpose="workout_generation",
            model=self.settings.muse_model,
            reasoning_effort=WORKOUT_REASONING_EFFORT,
            max_completion_tokens=None,
            payload_sha256=payload_digest({"messages": messages, "response_format": response_format}),
        )
        result = call_with_retries(
            lambda: self._require_transport().chat_completion(
                model=self.settings.muse_model,
                messages=messages,
                response_format=response_format,
                timeout=self.settings.meta_request_timeout_seconds,
                reasoning_effort=WORKOUT_REASONING_EFFORT,
            ),
            self.settings,
            lambda attempt, kind: self.gateway.note(
                kind="retry", purpose="workout_generation", attempt=attempt, reason=kind
            ),
        )
        self.gateway.note(
            kind="usage",
            purpose="workout_generation",
            model=self.settings.muse_model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            reasoning_tokens=result.reasoning_tokens,
            finish_reason=result.finish_reason,
            http_status=result.http_status,
        )
        payload = self._parse_live_json(result, "workout_generation")
        try:
            accepted = accept_week(
                payload,
                profile,
                session_index,
                "muse_spark",
                "Muse Spark 1.3 (live)",
            )
        except MetaRejected as exc:
            self._note_diagnostics(result, "workout_generation", "rejected", exc)
            raise
        self._note_diagnostics(result, "workout_generation", "ok")
        return accepted

    def _live_coaching(self, context: dict, approval_token: str | None) -> dict:
        messages = build_coaching_messages(context)
        response_format = coaching_response_format()
        self._authorize("coaching", COACHING_INPUT_TOKEN_ESTIMATE, COACHING_OUTPUT_TOKEN_ESTIMATE, approval_token)
        self.gateway.note(
            kind="request",
            purpose="coaching",
            model=self.settings.muse_model,
            reasoning_effort=COACHING_REASONING_EFFORT,
            max_completion_tokens=None,
            payload_sha256=payload_digest({"messages": messages, "response_format": response_format}),
        )
        result = call_with_retries(
            lambda: self._require_transport().chat_completion(
                model=self.settings.muse_model,
                messages=messages,
                response_format=response_format,
                timeout=self.settings.meta_request_timeout_seconds,
                reasoning_effort=COACHING_REASONING_EFFORT,
            ),
            self.settings,
            lambda attempt, kind: self.gateway.note(kind="retry", purpose="coaching", attempt=attempt, reason=kind),
        )
        self.gateway.note(
            kind="usage",
            purpose="coaching",
            model=self.settings.muse_model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            reasoning_tokens=result.reasoning_tokens,
            finish_reason=result.finish_reason,
            http_status=result.http_status,
        )
        raw = self._parse_live_json(result, "coaching")
        measured = build_coaching_model_input(context)
        context = {**context, "metrics_present": measured["metrics_present"]}
        try:
            payload = parse_coaching_payload(raw, context)
        except MetaRejected as exc:
            self._note_diagnostics(result, "coaching", "rejected", exc)
            raise
        self._note_diagnostics(result, "coaching", "ok")
        return ground_coaching(payload, context, context.get("profile"))

    def _parse_live_json(self, result: ChatResult, purpose: str) -> dict:
        content = result.content if isinstance(result.content, str) else ""
        if not content.strip():
            self._note_diagnostics(result, purpose, "empty_content")
            raise MetaRejected(
                "Muse Spark returned empty content. Hidden reasoning tokens share "
                "max_completion_tokens with visible JSON; this is a failed response, not a plan."
            )
        if result.finish_reason == "length":
            self._note_diagnostics(result, purpose, "truncated")
            raise MetaRejected(
                "Muse Spark reached the completion token limit. The truncated response cannot be used."
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            self._note_diagnostics(result, purpose, "invalid_json", exc)
            raise MetaRejected("Muse Spark did not return JSON.") from exc
        if not isinstance(payload, dict):
            self._note_diagnostics(result, purpose, "rejected")
            raise MetaRejected("Muse Spark did not return a JSON object.")
        return payload

    def _note_diagnostics(
        self,
        result: ChatResult,
        purpose: str,
        schema_validation: str,
        exc: Exception | None = None,
    ) -> None:
        error = sanitize_error(str(exc), self.settings.model_api_key) if exc else None
        self.gateway.note(
            kind="response_diagnostics",
            purpose=purpose,
            model=self.settings.muse_model,
            **response_diagnostics(result, schema_validation=schema_validation, error=error),
        )

    def _authorize(self, purpose: str, input_tokens: int, output_tokens: int, approval_token: str | None) -> None:
        self.gateway.authorize(
            model=self.settings.muse_model,
            purpose=purpose,
            estimated_cost_usd=estimate_muse_cost(input_tokens, output_tokens),
            approval_token=approval_token,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def _require_transport(self):
        if self.transport is not None:
            return self.transport
        return OpenAIMetaTransport(self.settings)

    def _load_fixture(self, name: str) -> dict:
        path = Path(__file__).resolve().parents[4] / "fixtures" / "meta" / name
        if not path.exists():
            raise FileNotFoundError(f"Fixture missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))
