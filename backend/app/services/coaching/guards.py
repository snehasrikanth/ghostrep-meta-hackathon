from __future__ import annotations

from app.schemas.coaching import CoachAction

ALLOWED: set[CoachAction] = {
    "KEEP_PLAN",
    "REDUCE_REPS",
    "EXTEND_REST",
    "REDUCE_LOAD_CONSERVATIVELY",
    "REQUEST_NEW_RECORDING",
    "NO_RECOMMENDATION",
    "STOP_AND_SEEK_PROFESSIONAL_ADVICE",
}


def validate_recommendation(payload: dict, profile: dict | None = None) -> dict:
    """Deterministic safety filter. Muse Spark suggestions must pass this before display."""
    action = payload.get("suggested_action")
    if action not in ALLOWED:
        payload["suggested_action"] = "NO_RECOMMENDATION"
        payload["reason"] = "The proposed action was not in the allowed set."
        payload["suggested_reps"] = payload.get("current_reps")
        payload["suggested_load_kg"] = payload.get("current_load_kg")

    limitations = [str(x).lower() for x in (profile or {}).get("limitations", [])]
    if any("pain" in item for item in limitations):
        payload["suggested_action"] = "STOP_AND_SEEK_PROFESSIONAL_ADVICE"
        payload["reason"] = (
            "A pain-related limitation was declared. GhostRep will not recommend continuing the set."
        )

    current_load = payload.get("current_load_kg")
    suggested_load = payload.get("suggested_load_kg")
    if (
        current_load is not None
        and suggested_load is not None
        and suggested_load > current_load + 1e-6
    ):
        payload["suggested_load_kg"] = current_load
        payload["suggested_action"] = "KEEP_PLAN" if payload["suggested_action"] not in ALLOWED else payload["suggested_action"]
        if payload["suggested_action"] not in {
            "REDUCE_REPS",
            "EXTEND_REST",
            "REDUCE_LOAD_CONSERVATIVELY",
            "REQUEST_NEW_RECORDING",
            "STOP_AND_SEEK_PROFESSIONAL_ADVICE",
            "NO_RECOMMENDATION",
        }:
            payload["suggested_action"] = "KEEP_PLAN"
        payload.setdefault("uncertainties", []).append("Load increases are never applied automatically.")

    if payload["suggested_action"] == "REDUCE_LOAD_CONSERVATIVELY" and current_load:
        payload["suggested_load_kg"] = round(max(0.0, current_load * 0.9), 1)

    current_reps = payload.get("current_reps")
    suggested_reps = payload.get("suggested_reps")
    if current_reps is not None and suggested_reps is not None and suggested_reps > current_reps:
        payload["suggested_reps"] = current_reps
        payload.setdefault("uncertainties", []).append("Rep increases are never applied automatically.")

    current_rest = payload.get("current_rest_seconds")
    suggested_rest = payload.get("suggested_rest_seconds")
    if (
        current_rest is not None
        and suggested_rest is not None
        and suggested_rest < current_rest
        and payload["suggested_action"] != "EXTEND_REST"
    ):
        payload["suggested_rest_seconds"] = current_rest
        payload.setdefault("uncertainties", []).append("Rest is never shortened automatically.")

    if payload["suggested_action"] == "REDUCE_REPS" and current_reps:
        payload["suggested_reps"] = max(1, int(current_reps) - 2)

    if payload["suggested_action"] == "EXTEND_REST":
        rest = payload.get("current_rest_seconds")
        if rest is not None:
            payload["suggested_rest_seconds"] = min(300, int(rest + 30))

    rpe = payload.get("reported_rpe")
    if rpe is not None and rpe >= 9.5 and payload["suggested_action"] == "KEEP_PLAN":
        payload["suggested_action"] = "EXTEND_REST"
        payload["reason"] = "Reported exertion is very high, so rest is extended conservatively."
        rest = payload.get("current_rest_seconds")
        if rest is not None:
            payload["suggested_rest_seconds"] = min(300, int(rest + 30))

    if payload["suggested_action"] == "EXTEND_REST" and rpe is not None and rpe >= 9.5:
        payload["decision_basis"] = "reported_effort"
        payload["reason"] = "Add rest because you reported very high effort (RPE). This is separate from movement measurements and does not establish a technique problem."
    if payload["suggested_action"] in {
        "KEEP_PLAN",
        "NO_RECOMMENDATION",
        "REQUEST_NEW_RECORDING",
        "STOP_AND_SEEK_PROFESSIONAL_ADVICE",
    }:
        payload["suggested_reps"] = payload.get("current_reps")
        payload["suggested_rest_seconds"] = payload.get("current_rest_seconds")
        payload["suggested_load_kg"] = payload.get("current_load_kg")

    payload["requires_confirmation"] = True
    return payload
