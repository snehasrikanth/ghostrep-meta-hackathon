"""Inference-free validity gates, including read-time protection for old results."""
import json
import math

WARNING = "Reliable movement comparison is unavailable. Review the recording and count before changing targets."


def context_problem(context: dict) -> str | None:
    quality = context.get("quality") or {}
    if quality.get("comparison_usable") is False:
        return WARNING
    drift = context.get("drift") or []
    if any(p.get("comparison_valid") is False for p in drift):
        return WARNING
    non_reference = [p for p in drift if p.get("rep_id") != context.get("reference_rep")]
    if len(non_reference) >= 2 and all(p.get("similarity") == 0 for p in non_reference):
        return "Comparisons saturated at zero; they cannot support precise movement conclusions. " + WARNING
    return None


def recording_problem(rec) -> str | None:
    if rec.analysis is None: return None
    analysis = rec.analysis
    for rep in rec.reps:
        metrics = json.loads(rep.metrics_json)
        torso = metrics.get("max_torso_inclination_deg")
        if torso is not None and (not math.isfinite(torso) or torso > 100):
            return "Stored landmark geometry is contradictory. " + WARNING
        if rep.is_reference and metrics.get("comparison_eligible") is False:
            return WARNING
    return context_problem({"quality":json.loads(analysis.quality_json), "drift":json.loads(analysis.drift_json), "reference_rep":analysis.reference_rep})


def suppress_unreliable(payload: dict, reason: str) -> dict:
    return {**payload, "summary":reason, "reason":reason, "observations":[], "evidence_references":[],
            "primary_cue":None, "suggested_action":"NO_RECOMMENDATION", "actionable":False,
            "state":"review_only", "action_blocked_reason":reason, "decision_basis":"unavailable_measurement",
            "uncertainties":[reason], "requires_confirmation":True}
