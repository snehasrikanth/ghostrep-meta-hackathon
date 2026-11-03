"""Read-only, deterministic within-workout comparisons; no inference or target writes.

Timing means need >=2 explicitly reliable complete reps. Descriptive consistency
needs >=4 in each set. 'Improved' is reserved for phase-timing CV falling by
>=5 percentage points AND >=25%, from a noticeable baseline (CV >=15%). Equal
usable/detected counts, pipeline, known load/effort and suitable tracked views
are required. These are conservative display heuristics, not statistical or
technique-accuracy thresholds. Independently selected references are never
compared, and camera calibration is unavailable: position outcomes are withheld.
Rep reliability reuses the detector's explicit eligibility and >=90% valid-frame
rule. Phase durations must match boundaries within 0.1s. Context equality allows
0.01 units for numeric roundoff. A prior timing observation must differ by >=15%
from its own reference and match the saved duration ratio within 2 percentage
points; those reference-relative ratios are not compared across sets.
"""
from __future__ import annotations

import json
import math
from datetime import timezone
from pathlib import Path
from statistics import mean, pstdev

from sqlalchemy.orm import Session

from app.models.entities import AnalysisResult, RecordedSet
from app.services.coaching.interpretation import canonical_observations, display_interpretation, record_context
from app.services.coaching.measurement_guard import recording_problem
from app.services.recording_provenance import is_sample_set

MIN_TIMING_REPS = 2
MIN_CONSISTENCY_REPS = 4
NOTICEABLE_CV = 15.0
CV_DROP_POINTS = 5.0
CV_DROP_FRACTION = .25
TIMESTAMP_TOLERANCE = .1
PHASES = {"descent_duration": "Time lowering", "ascent_duration": "Time standing up"}
VIEW_WARNINGS = {"camera_angle", "camera_motion", "crop", "full_body", "tracking_intervals"}


def _json(raw, kind):
    try:
        value = json.loads(raw or ("{}" if kind is dict else "[]"))
        return value if isinstance(value, kind) else kind()
    except (ValueError, TypeError):
        return kind()


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _number(rec):
    return rec.set_index if isinstance(rec.set_index, int) and rec.set_index > 0 else None


def _time(rec):
    return rec.created_at.replace(tzinfo=timezone.utc) if rec.created_at.tzinfo is None else rec.created_at


def _accessible(rec):
    try:
        return bool(rec.normalized_path and Path(rec.normalized_path).is_file())
    except OSError:
        return False


def _previous(db, rec):
    # Join only to establish analysis existence; load large analysis JSON only for
    # the selected predecessor. Reliability does NOT filter the candidate list.
    rows = db.query(RecordedSet).join(AnalysisResult, AnalysisResult.set_id == RecordedSet.id).filter(
        RecordedSet.user_id == rec.user_id, RecordedSet.session_id == rec.session_id,
        RecordedSet.exercise_id == rec.exercise_id, RecordedSet.analysis_requested.is_(True),
    ).all()
    rows = [r for r in rows if not is_sample_set(r) and _accessible(r)]
    if all(_number(r) is not None for r in rows):
        earlier = [r for r in rows if r.id != rec.id and _number(r) < _number(rec)]
        return max(earlier, key=lambda r: (_number(r), _time(r), r.id), default=None), "set_number", None
    # Legacy unnumbered sets use recording time, never analysis completion time.
    # Conflicting known numbers or tied timestamps make that fallback ambiguous.
    ordered = sorted(rows, key=lambda r: (_time(r), r.id))
    numbers = [_number(r) for r in ordered if _number(r) is not None]
    if numbers != sorted(set(numbers)) or len({_time(r) for r in rows}) != len(rows):
        return None, "unavailable", "The order of these older recordings is ambiguous, so no previous set was guessed."
    index = next((i for i, r in enumerate(ordered) if r.id == rec.id), 0)
    return (ordered[index - 1] if index else None), "recording_time", None


def _snapshot(rec):
    complete = [r for r in rec.reps if r.is_complete]
    quality = _json(rec.analysis.quality_json, dict) if rec.analysis else {}
    out = {
        "set_id": rec.id, "label": f"Set {_number(rec)}" if _number(rec) else "Current recording",
        "set_number": _number(rec), "recorded_at": _time(rec).isoformat(),
        "detected_reps": len(complete), "usable_reps": 0,
        "planned_reps": rec.target_reps, "logged_reps": rec.completed_reps,
        "load_kg": rec.load_kg if _finite(rec.load_kg) and rec.load_kg >= 0 else None,
        "reported_effort": rec.reported_rpe if _finite(rec.reported_rpe) and 1 <= rec.reported_rpe <= 10 else None,
    }
    reason = None
    if rec.processing_status != "COMPLETED" or not rec.analysis or not rec.analysis.pose_available:
        reason = "The analysis is not complete with usable movement tracking."
    elif quality.get("usable") is not True or quality.get("comparison_usable") is not True:
        reason = "The recording does not have verified tracking for a movement comparison."
    else:
        try:
            reason = recording_problem(rec)
        except (ValueError, TypeError, KeyError):
            reason = "The stored measurements could not be verified."
    reliable = []
    if not reason:
        for r in complete:
            metrics = _json(r.metrics_json, dict)
            reliability = metrics.get("reliability") or {}
            if not isinstance(reliability, dict):
                continue
            if metrics.get("comparison_eligible") is not True or not _finite(reliability.get("valid_fraction")) or reliability["valid_fraction"] < .9:
                continue
            times = (r.start_seconds, r.bottom_seconds, r.end_seconds, r.descent_seconds, r.ascent_seconds)
            if not all(_finite(t) for t in times) or not (0 <= r.start_seconds < r.bottom_seconds < r.end_seconds):
                continue
            if min(r.descent_seconds, r.ascent_seconds) <= 0:
                continue
            if abs(r.descent_seconds - (r.bottom_seconds - r.start_seconds)) > TIMESTAMP_TOLERANCE or abs(r.ascent_seconds - (r.end_seconds - r.bottom_seconds)) > TIMESTAMP_TOLERANCE:
                continue
            if _finite(rec.duration_seconds) and r.end_seconds > rec.duration_seconds + TIMESTAMP_TOLERANCE:
                continue
            reliable.append(r)
    out["usable_reps"] = len(reliable)
    if not reason and len(reliable) < MIN_TIMING_REPS:
        reason = "At least two complete reps with explicit reliability and matching phase timestamps are needed; older or missing fields were not guessed."
    phases = {key: [getattr(r, "descent_seconds" if key == "descent_duration" else "ascent_seconds") for r in reliable] for key in PHASES}
    return {"public": out, "reason": reason, "quality": quality, "reps": reliable, "phases": phases, "record": rec}


def _consistency(values):
    return 100 * pstdev(values) / mean(values)


def _conditions(previous, current):
    a, b = previous["public"], current["public"]
    reasons = []
    if a["usable_reps"] < MIN_CONSISTENCY_REPS or b["usable_reps"] < MIN_CONSISTENCY_REPS:
        reasons.append("Consistency needs at least four usable reps in each set.")
    if a["usable_reps"] != b["usable_reps"] or any(s["public"]["usable_reps"] != s["public"]["detected_reps"] or any(not r.is_complete for r in s["record"].reps) for s in (previous, current)):
        reasons.append("The sets have different rep counts or excluded movements; only descriptive timing means are compared.")
    if any(s["public"]["logged_reps"] is not None and s["public"]["logged_reps"] != s["public"]["detected_reps"] for s in (previous, current)):
        reasons.append("The logged count differs from detection. Timings use measured reps only; a progress judgment is withheld.")
    for key, label in (("load_kg", "Recorded load"), ("reported_effort", "Reported effort")):
        if a[key] is None or b[key] is None:
            reasons.append(f"{label} was not entered for both sets; it was not treated as zero.")
        elif not math.isclose(a[key], b[key], rel_tol=0, abs_tol=.01):
            reasons.append(f"{label} changed, so a progress judgment is withheld.")
    if not previous["record"].analysis.analysis_version or previous["record"].analysis.analysis_version != current["record"].analysis.analysis_version:
        reasons.append("The measurement pipeline differs or is unknown.")
    a_view, b_view = previous["quality"], current["quality"]
    if a_view.get("side") not in {"left", "right"} or a_view.get("side") != b_view.get("side") or any(i.get("code") in VIEW_WARNINGS for q in (a_view, b_view) for i in q.get("issues") or [] if isinstance(i, dict)):
        reasons.append("Tracked views differ or have camera warnings; a consistency judgment is unavailable.")
    return reasons


def _follow_up(previous, current):
    rec = previous["record"]
    base = {"status": "unavailable", "metric": None, "previous_observation": None,
            "explanation": "There is no previous measurable observation to follow up yet.", "evidence": None}
    if not rec.coaching:
        return base
    raw = {**_json(rec.coaching.payload_json, dict), "summary": rec.coaching.summary, "reason": rec.coaching.reason}
    saved_context = raw.get("recommendation_context")
    if isinstance(saved_context, dict) and saved_context.get("analysis_sha256"):
        from app.services.coaching.compatibility import recommendation_context
        if saved_context["analysis_sha256"] != recommendation_context(rec)["analysis_sha256"]:
            return {**base, "explanation": "The measured analysis changed after the previous note was saved. Its outcome cannot be evaluated against a different analysis."}
    try:
        context = record_context(rec)
        protected = display_interpretation(raw, context)
        supported = canonical_observations(protected, context)
    except (ValueError, TypeError, KeyError):
        return {**base, "explanation": "Previous coaching has incomplete measurement links; its outcome cannot be evaluated."}
    observation = next((o for o in supported if o["metric"] not in {"camera_quality", "similarity"}), None)
    if not observation:
        cue = protected.get("primary_cue") or next((o.get("statement") for o in protected.get("observations", []) if o.get("statement")), None)
        return {**base, "previous_observation": cue,
                "explanation": "This previous cue has no supported metric association, so its outcome cannot yet be measured." if cue else base["explanation"]}
    metric = observation["metric"]
    base.update(metric=metric, previous_observation=observation["statement"], evidence={
        "set_id": rec.id, "rep_id": observation["rep_id"], "seconds": observation["evidence_seconds"][0]})
    if metric not in PHASES:
        return {**base, "explanation": "Upper-body position, depth and movement paths are not scored across sets: each set has its own reference and camera position is not verified. This does not establish that the previous pattern was fixed."}
    conditions = _conditions(previous, current)
    if conditions:
        return {**base, "explanation": conditions[0]}
    ids = {r.rep_index for r in previous["reps"]}
    if observation["rep_id"] not in ids or rec.analysis.reference_rep not in ids:
        return {**base, "explanation": "The previous observation is not linked to reliable repetition timing."}
    field = "ascent_seconds" if metric == "ascent_duration" else "descent_seconds"
    observed = next(r for r in previous["reps"] if r.rep_index == observation["rep_id"])
    reference = next(r for r in previous["reps"] if r.rep_index == rec.analysis.reference_rep)
    measured_difference = 100 * (getattr(observed, field) / getattr(reference, field) - 1)
    if abs(measured_difference) < 15 or abs(measured_difference - observation["magnitude"]) > 2:
        return {**base, "explanation": "The previous timing observation cannot be confirmed from the saved phase durations."}
    old_cv, new_cv = (_consistency(s["phases"][metric]) for s in (previous, current))
    if old_cv < NOTICEABLE_CV - 1e-9:
        return {**base, "explanation": "The previous note used a rep-to-reference difference. Set-level timing variation was too small to support an improvement judgment about that note."}
    label = PHASES[metric].lower()
    detail = f"{PHASES[metric]} varied {old_cv:.0f}% around its average before and {new_cv:.0f}% now."
    if old_cv - new_cv >= CV_DROP_POINTS - 1e-9 and new_cv <= old_cv * (1 - CV_DROP_FRACTION) + 1e-9:
        return {**base, "status": "improved", "explanation": f"Your previous note concerned {label}. Timing variation fell from {old_cv:.0f}% to {new_cv:.0f}% across usable reps. This measures consistency, not technique correction or whether the cue worked."}
    return {**base, "status": "remains", "explanation": f"Variation in {label} remains noticeable. {detail} Review the replay; variation alone is not a technique fault."}


def compare_with_previous(db: Session, rec: RecordedSet) -> dict:
    """An owned read projection. No saved analyses/coaching/targets are changed."""
    out = {"version": "set-comparison-v1", "status": "unavailable", "emoji": "🌱",
           "headline": "A comparison needs more evidence.", "summary": "", "previous": None,
           "current": None, "metrics": [], "follow_up": None, "next_step": None,
           "details": ["Phase timings use complete, explicitly reliable reps and exclude setup and idle time; total recording duration is not exercise time.",
                       "Timing changes are not technique scores. Each set has its own reference; camera position is not calibrated. No workout targets change here."]}
    if is_sample_set(rec) or rec.session is None or rec.session.user_id != rec.user_id or rec.session.status == "sample":
        out["summary"] = "Illustrative or inaccessible sets do not enter your training comparison."
        return out
    if rec.analysis_requested is not True:
        out["summary"] = "This record does not have the metadata needed for an analyzed-set comparison."
        return out
    if not _accessible(rec):
        out["summary"] = "This saved recording is no longer available for comparison."
        return out
    current = _snapshot(rec)
    out["current"] = current["public"]
    previous_rec, order, order_problem = _previous(db, rec)
    out["details"].append("Set numbers establish order; recording time breaks ties. Legacy unnumbered sets use recording time only when known numbers agree. Analysis completion time is never used.")
    if order_problem:
        out["summary"] = order_problem
        return out
    if previous_rec is None:
        out.update(status="first", headline="Your starting point is saved.",
                   summary="This is your first available analyzed set for this exercise in this workout. There is no earlier set to compare.",
                   next_step="A later analyzed set in this workout can use this as its starting point.")
        return out
    previous = _snapshot(previous_rec)
    if previous["public"]["set_number"] is None:
        previous["public"]["label"] = "Earlier recording"
    out["previous"] = previous["public"]
    if previous["reason"] or current["reason"]:
        which = "previous" if previous["reason"] else "current"
        out.update(emoji="🎥", headline="Let’s make the comparison clearer.",
                   summary=f"The {which} set cannot support a reliable comparison. " + (previous["reason"] or current["reason"]),
                   next_step="For a future recording, keep the camera stable and your whole body visible.")
        out["details"].append("The immediately preceding available analyzed set was kept. An unreliable set was not skipped for an older one.")
        return out
    metrics = [{"key": "usable_reps", "label": "Usable measured reps", "unit": "reps",
                "previous": previous["public"]["usable_reps"], "current": current["public"]["usable_reps"], "change": None}]
    for key, label in PHASES.items():
        before, after = mean(previous["phases"][key]), mean(current["phases"][key])
        delta = after - before
        change = "About the same" if abs(delta) < .1 else f"{abs(delta):.1f}s {'longer' if delta > 0 else 'shorter'}"
        metrics.append({"key": key, "label": label, "unit": "seconds_per_rep", "previous": round(before, 1), "current": round(after, 1), "change": change})
    follow = _follow_up(previous, current)
    out.update(status="compared", emoji="✨", headline="Here’s how this set compares.",
               summary="Average time per usable rep. Shorter times and more reps aren’t automatically better.",
               metrics=metrics, follow_up=follow, next_step="Replay the timing evidence before changing your targets.")
    if follow["status"] == "improved":
        out.update(emoji="🙌", headline="More consistent this set!")
    elif follow["status"] == "remains":
        out.update(emoji="💪", headline="Keep taking it one set at a time.")
    out["details"] += _conditions(previous, current)
    out["details"].append("Consistency is descriptive variation around each phase's mean (population standard deviation ÷ mean). It needs four usable reps in each set, equal complete counts, matching load/effort/pipeline and no camera warnings. Noticeable means at least 15%; improvement requires a drop of at least 5 percentage points and 25% relative. These are conservative heuristics, not calibrated accuracy thresholds.")
    return out
