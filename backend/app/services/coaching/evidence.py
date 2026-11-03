"""Drop coaching claims that are not grounded in the measured recording."""

from __future__ import annotations

import re

from app.services.coaching.guards import validate_recommendation
from app.services.coaching.interpretation import canonicalize
from app.services.coaching.measurement_guard import context_problem, suppress_unreliable

_DIAGNOSIS = re.compile(
    r"\b(diagnos\w*|torn|tear|fracture|herniat\w*|injury|injured|sprain|medical condition)\b",
    re.IGNORECASE,
)
_CHANGES = {"REDUCE_REPS", "EXTEND_REST", "REDUCE_LOAD_CONSERVATIVELY"}


def ground_coaching(payload: dict, context: dict, profile: dict | None) -> dict:
    """Remove invented measurements, then apply the shared recommendation guard."""
    from app.services.meta.contracts import COACH_METRICS
    problem = context_problem(context)
    if problem:
        return suppress_unreliable(payload, problem)
    quality = context.get("quality") or {}
    present = set(context.get("metrics_present") or [])
    if not present:
        from app.services.meta.contracts import _metrics_present

        present = _metrics_present(list(context.get("drift") or []), quality)
    windows = _windows(list(context.get("reps") or []))
    kept = []
    dropped = 0
    for item in payload.get("observations") or []:
        if not isinstance(item, dict):
            dropped += 1
            continue
        metric = str(item.get("metric") or "")
        if metric not in COACH_METRICS or metric not in present:
            dropped += 1
            continue
        evidence = [float(value) for value in item.get("evidence_seconds") or [] if _inside(float(value), windows)]
        if metric != "camera_quality" and windows and not evidence:
            dropped += 1
            continue
        statement = str(item.get("statement") or "")
        if _DIAGNOSIS.search(statement):
            dropped += 1
            continue
        item = {**item, "evidence_seconds": evidence}
        kept.append(item)
    payload["observations"] = kept
    payload["evidence_references"] = sorted({round(t, 2) for item in kept for t in item["evidence_seconds"]})
    uncertainties = list(payload.get("uncertainties") or [])
    if dropped:
        uncertainties.append(
            f"{dropped} observation{'s' if dropped != 1 else ''} removed because the recording did not support them."
        )
    if not kept:
        payload["primary_cue"] = None
    text = " ".join([str(payload.get("summary") or ""), str(payload.get("reason") or ""), str(payload.get("primary_cue") or "")])
    if _DIAGNOSIS.search(text):
        payload["suggested_action"] = "NO_RECOMMENDATION"
        payload["reason"] = "The response made a medical claim, so no training change is proposed."
        uncertainties.append("GhostRep does not diagnose injuries or medical conditions.")
        payload["summary"] = payload["reason"]
        payload["primary_cue"] = None
    elif payload.get("suggested_action") in _CHANGES and not kept and quality.get("usable", True):
        payload["suggested_action"] = "NO_RECOMMENDATION"
        payload["reason"] = "No measured observation supported a change to the next set."
    payload["uncertainties"] = uncertainties
    payload["requires_confirmation"] = True
    result = canonicalize(validate_recommendation(payload, profile), context)
    # No validated technique-correction system exists. Actions are represented
    # separately; neither model prose nor a measured observation becomes a cue.
    result['primary_cue'] = None
    from app.services.coaching.presentation import validate_explanation_selection
    result['grounded_explanation'] = validate_explanation_selection(result, context)
    return result


def _windows(reps: list[dict]) -> list[tuple[float, float]]:
    windows = []
    for rep in reps:
        start = float(rep.get("start_seconds") or 0)
        end = float(rep.get("end_seconds") or start)
        windows.append((start - 0.25, max(end, start) + 0.25))
    return windows


def _inside(timestamp: float, windows: list[tuple[float, float]]) -> bool:
    if not windows:
        return False
    return any(start <= timestamp <= end for start, end in windows)
