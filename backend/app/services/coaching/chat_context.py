"""Owned, bounded facts for read-only questions. No media or free stored prose.

    Counts, comparison eligibility and directional interpretation reuse their
    canonical services. Nothing in this module writes training data.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from app.api.serialize import coaching_out
from app.services.coaching.interpretation import canonical_observations, finite, record_context
from app.services.coaching.measurement_guard import recording_problem
from app.services.coaching.set_comparison import compare_with_previous
from app.services.recording_provenance import is_sample_set
from app.services.workout.catalog import CATALOG

MAX_CONTEXT_BYTES = 18000


def _json(raw, default):
    try:
        value = json.loads(raw or "null")
        return value if isinstance(value, type(default)) else default
    except (TypeError, ValueError):
        return default


def _num(value):
    return f"{value:g}" if finite(value) else "not entered"


def _rest_time(value):
    if not finite(value) or value <= 0:
        return "rest not specified"
    if value != int(value):
        return f"{value:g} seconds"
    minutes, seconds = divmod(int(value), 60)
    parts = ([f"{minutes} minute{'s' if minutes != 1 else ''}"] if minutes else [])
    if seconds:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    return " ".join(parts)


def _saved_coaching(rec):
    try:
        return coaching_out(rec.coaching, rec=rec, session=rec.session)
    except (ValueError, TypeError, KeyError, AttributeError):
        return {"historical_interpretation_corrected": True, "actionable": False, "user_decision": "pending"}


def _meaningful(metric, magnitude, direction=None):
    """Same display thresholds the analysis already uses. Not a new technique score."""
    if not finite(magnitude):
        return False
    if metric == "torso_inclination":
        return direction != "similar" and magnitude >= 6
    if metric == "relative_depth":
        return magnitude <= -8
    if metric == "ascent_duration":
        return magnitude >= 15
    if metric == "descent_duration":
        return abs(magnitude) >= 20
    return False


def _plain_observation(text):
    return (text
            .replace("was closer to vertical than your reference across matched movement phases.", "looked more upright than your reference.")
            .replace("was farther from vertical than your reference across matched movement phases.", "looked less upright than your reference."))


def _rep_evidence(rec, rep, eid):
    times = (rep.start_seconds, rep.bottom_seconds, rep.end_seconds)
    if not all(finite(t) for t in times) or not 0 <= times[0] < times[1] < times[2]:
        return None
    if not finite(rec.duration_seconds) or times[2] > rec.duration_seconds:
        return None
    return {"id": eid, "set_id": rec.id, "rep_id": rep.rep_index, "seconds": times[0],
            "start_seconds": times[0], "end_seconds": times[2],
            "label": f"Compare rep {rep.rep_index}"}


def build_context(db, rec, question, selected_rep=None):
    sample = is_sample_set(rec)
    ready = rec.processing_status == "COMPLETED" and rec.analysis is not None
    try:
        problem = recording_problem(rec) if ready else "Analysis is not complete."
        ctx = record_context(rec)
    except (ValueError, TypeError, KeyError, AttributeError):
        problem = "Stored measurements could not be verified."
        ctx = {"reps": [], "drift": [], "reference_rep": None}
    quality = _json(rec.analysis.quality_json, {}) if rec.analysis else {}
    verified = ready and not problem and quality.get("usable") is True and quality.get("comparison_usable") is True
    facts, evidence = {}, {}

    def fact(key, text, refs=()):
        facts[key] = {"text": text, "evidence_ids": list(refs)}

    name = CATALOG.get(rec.exercise_id, {}).get("name", "This exercise")
    fact("scope", "I can explain this saved set and its eligible previous-set comparison, not plan training or assess other records. You could ask “Explain this set.”")
    detected = sum(r.is_complete for r in rec.reps)
    if detected == rec.target_reps:
        counts = f"Nice work—{detected} reps detected—you matched your target."
    else:
        counts = f"{detected} reps detected against {_num(rec.target_reps)} planned."
    if rec.completed_reps != detected:
        counts += f" Your training log records {_num(rec.completed_reps)} reps; that does not change the measured count."
    fact("counts", counts)
    fact("reported", f"You recorded {_num(rec.load_kg)} kg and reported {_num(rec.reported_rpe)}/10 effort." if finite(rec.load_kg) and finite(rec.reported_rpe) else f"Recorded load: {_num(rec.load_kg)} kg. Reported effort: {_num(rec.reported_rpe)}/10; missing entries were not treated as zero.")
    fact("limits", "These measurements do not establish safe or correct technique, fatigue or injury risk. Your personal reference is an observed rep, not ideal form.")
    fact("approval", "Chat cannot apply changes. Use the existing recommendation review controls to make a choice; your workout targets stay unchanged here.")
    fact("focus", "Replay the saved evidence before deciding what to do next; differences alone are not instructions to change your movement.")
    if sample:
        fact("sample", "This is an illustrative sample, not performed training. It cannot change your workout, totals or personal comparison.")
    if not ready:
        fact("availability", "This set does not have a completed analysis.")
    elif not verified:
        fact("availability", "Tracking or legacy measurement fields do not support a reliable movement comparison here.")

    # Identity is limited to the selected owned set/session. No plan names,
    # profile, paths, filenames, notes, raw overlays or stored provider prose.
    result = {"set_id": rec.id, "session_id": rec.session_id, "exercise": name,
              "set_number": rec.set_index, "sample": sample, "analysis_complete": ready,
              "planned_reps": rec.target_reps, "detected_reps": sum(r.is_complete for r in rec.reps),
              "logged_reps": rec.completed_reps, "load_kg": rec.load_kg, "reported_effort": rec.reported_rpe,
              "comparison_eligible": bool(verified and not sample), "demo_available": rec.exercise_id == "barbell_squat",
              "facts": facts, "evidence": evidence, "rep_ids": [], "recommendation": None,
              "comparison": None, "workout_href": None}
    plan_id = getattr(rec.session, "plan_id", None) if rec.session else None
    if isinstance(plan_id, str) and re.fullmatch(r"[a-f0-9-]{36}", plan_id, re.I):
        result["workout_href"] = f"/workouts/{plan_id}"
    requested = re.findall(r"\brep(?:etition)?\s*#?\s*(\d{1,4})\b", question.lower())
    requested_id = int(requested[-1]) if requested else selected_rep
    reps = sorted(rec.reps, key=lambda r: r.rep_index)
    focus = next((r for r in reps if r.rep_index == requested_id), None)
    result["selected_rep_id"] = focus.rep_index if focus else None
    # At most 10 rep summaries; the explicitly requested rep is always included.
    chosen = ([focus] if focus else []) + [r for r in reps if r is not focus][:9]
    for rep in chosen:
        metrics = _json(rep.metrics_json, {})
        eid = f"current:r{rep.rep_index}"
        ref = _rep_evidence(rec, rep, eid)
        if ref:
            evidence[eid] = ref
        reliable = (verified and rep.is_complete and metrics.get("comparison_eligible") is True
                    and isinstance(metrics.get("reliability"), dict)
                    and finite(metrics["reliability"].get("valid_fraction")) and metrics["reliability"]["valid_fraction"] >= .9
                    and ref is not None and finite(rep.descent_seconds) and finite(rep.ascent_seconds)
                    and rep.descent_seconds > 0 and rep.ascent_seconds > 0
                    and abs(rep.descent_seconds - (rep.bottom_seconds-rep.start_seconds)) <= .1
                    and abs(rep.ascent_seconds - (rep.end_seconds-rep.bottom_seconds)) <= .1)
        result["rep_ids"].append(rep.rep_index)
        key = f"rep_{rep.rep_index}"
        fact(key, f"Rep {rep.rep_index} took {rep.descent_seconds:.1f} seconds to lower and {rep.ascent_seconds:.1f} seconds to stand up. Those measurements support a comparison with your reference." if reliable else f"Rep {rep.rep_index} is available to review, but its measurements are not verified for comparison.", [eid] if ref else [])
        if reliable:
            # Reuse canonical interpretation, never trust the saved observation's
            # statement or an unsigned upper-body magnitude as direction.
            # Insignificant and zero differences are not offered as findings.
            raw = {"observations": [{"metric": m, "rep_id": rep.rep_index, "evidence_seconds": [rep.bottom_seconds]} for m in ("ascent_duration", "descent_duration", "torso_inclination", "relative_depth")]}
            observations = canonical_observations(raw, ctx)
            point = next((d for d in ctx.get("drift", []) if d.get("rep_id") == rep.rep_index), {})
            for obs in observations:
                direction = (point.get("upper_body_comparison") or {}).get("direction") if obs["metric"] == "torso_inclination" else None
                if _meaningful(obs["metric"], obs.get("magnitude"), direction):
                    fact(f"{key}_{obs['metric']}", obs["statement"], [eid])
    if requested_id is not None and focus is None:
        fact("missing_rep", f"Rep {requested_id} is not a measured segment in this saved set. Correcting the log cannot create it.")

    if rec.coaching and ready:
        c = _saved_coaching(rec)
        p = c.get("presentation") or {}
        review = bool(sample or c.get("historical_interpretation_corrected") or p.get("measurement_uncertain") or (c.get("user_decision") == "pending" and not c.get("actionable")))
        decision = c.get("user_decision")
        action = c.get("suggested_action")
        historical = bool(c.get("historical_interpretation_corrected"))
        measurement_blocked = bool(p.get("measurement_uncertain"))
        # Action authorization stays separate from whether a descriptive
        # measurement can still be explained.
        result["recommendation"] = {"action": action, "basis": p.get("decision_basis"), "status": decision,
                                     "review_only": review, "historical": historical,
                                     "measurement_uncertain": measurement_blocked,
                                     "actionable": bool(c.get("actionable") and not review)}
        recorded_rest = (action == "EXTEND_REST" and p.get("decision_basis") == "reported_effort"
                         and finite(rec.reported_rpe) and rec.reported_rpe >= 9.5
                         and finite(c.get("suggested_rest_seconds")) and not historical
                         and not measurement_blocked and not sample)
        recorded_measurement = (action in {"EXTEND_REST", "REDUCE_REPS", "REDUCE_LOAD_CONSERVATIVELY"}
                                and p.get("decision_basis") in {"ascent_duration", "descent_duration", "relative_depth"}
                                and not historical and not measurement_blocked and not sample)
        if decision == "accepted":
            fact("recommendation", "You already accepted this recommendation.")
        elif decision == "rejected":
            fact("recommendation", "You declined this recommendation.")
        elif recorded_rest or recorded_measurement:
            fact("recommendation", "Review this suggestion before applying it.")
        elif review:
            fact("recommendation", "This saved result does not support a new target change.")
        else:
            fact("recommendation", "Review the saved recommendation.")
        if recorded_rest:
            fact("rest_reason", f"You rated this set {_num(rec.reported_rpe)}/10 effort, so your saved recommendation suggests {_rest_time(c['suggested_rest_seconds'])} of rest. That is reported effort, not measured fatigue.")
        elif recorded_measurement:
            kind = "depth" if p.get("decision_basis") == "relative_depth" else "timing"
            fact("rest_reason", f"The saved suggestion is based on a supported {kind} difference from your reference. Review that suggestion before applying it. Chat does not propose another adjustment.")
        if rec.session and rec.session.status not in {"active", "paused"}:
            fact("closed", "This workout has ended. Its recommendation is a saved decision, not a new change to this or another workout.")

    comparison = compare_with_previous(db, rec) if ready else None
    if comparison and comparison["status"] == "compared":
        follow = comparison.get("follow_up") or {}
        status = follow.get("status")
        if status == "improved":
            fact("comparison", "Your timing was more consistent this set. That does not establish better technique or that a cue worked.")
        elif status == "remains":
            fact("comparison", "Your rep timing still varied noticeably. This comparison does not confirm improvement or a technique fault.")
        else:
            fact("comparison", "Timing alone doesn’t confirm improvement in this comparison.")
        timings = [{"key": m["key"], "previous": m["previous"], "current": m["current"]} for m in comparison["metrics"] if m["unit"] == "seconds_per_rep"]
        result["comparison"] = {"status": comparison["status"], "follow_up_status": status, "timings": timings}
        for m in timings[:2]:
            label = "lowering" if m["key"] == "descent_duration" else "standing up"
            if abs(m["previous"] - m["current"]) < .05:
                fact(f"comparison_{m['key']}", f"Your average time {label} stayed at {m['current']:.1f} seconds per usable rep.")
            else:
                fact(f"comparison_{m['key']}", f"Your average time {label} went from {m['previous']:.1f} seconds to {m['current']:.1f} seconds per usable rep.")
        prev_id = (comparison.get("previous") or {}).get("set_id")
        # Only the canonical eligible predecessor, never a client-supplied ID.
        if follow.get("evidence") and prev_id:
            from app.models.entities import RecordedSet
            previous = db.get(RecordedSet, prev_id)
            if previous and previous.user_id == rec.user_id and previous.session_id == rec.session_id and previous.exercise_id == rec.exercise_id and not is_sample_set(previous):
                prior_rep = next((r for r in previous.reps if r.rep_index == follow["evidence"]["rep_id"]), None)
                ref = _rep_evidence(previous, prior_rep, "previous:observation") if prior_rep else None
                if ref:
                    ref["label"] = f"Compare previous set · rep {prior_rep.rep_index}"
                    evidence[ref["id"]] = ref
                    facts["comparison"]["evidence_ids"] = [ref["id"]]
    else:
        message = "This is the first available analyzed set in this workout; there is no earlier eligible set to compare." if comparison and comparison["status"] == "first" else "An eligible previous-set comparison is unavailable. Improvement is not established, and no older set was substituted."
        fact("comparison", message)
    if result["demo_available"]:
        fact("demo", "An optional squat demo is available. It is an example, not your personal reference or an assessment of your form.")
    _answer_guidance(result, ctx, question)
    # Keep focus observations first when the recording contains many reps.
    if len(json.dumps(result).encode()) > MAX_CONTEXT_BYTES:
        keep = {k for k in facts if not k.startswith("rep_") or (focus and k.startswith(f"rep_{focus.rep_index}"))}
        result["facts"] = {k: v for k, v in facts.items() if k in keep}
    return result


def _phase_sentence(key, measurements):
    """Absolute phase times only when saved durations match their boundaries."""
    rid = int(key.split("_")[1])
    rep = next((r for r in measurements.get("reps", []) if r["rep_id"] == rid), None)
    reference = next((r for r in measurements.get("reps", []) if r["rep_id"] == measurements.get("reference_rep")), None)
    phase = "ascent_seconds" if key.endswith("ascent_duration") else "descent_seconds" if key.endswith("descent_duration") else None
    def valid_phase(item):
        if not phase or not item or item.get("comparison_eligible") is not True or not all(finite(item.get(k)) for k in (phase, "start_seconds", "bottom_seconds", "end_seconds")):
            return False
        boundary = item["end_seconds"] - item["bottom_seconds"] if phase == "ascent_seconds" else item["bottom_seconds"] - item["start_seconds"]
        return item[phase] > 0 and abs(item[phase] - boundary) <= .1
    if not (phase and valid_phase(rep) and valid_phase(reference)):
        return None
    point = next((d for d in measurements.get("drift", []) if d.get("rep_id") == rid), None)
    if not point:
        return None
    percent = point.get("ascent_duration_difference_percent" if phase == "ascent_seconds" else "descent_duration_difference_percent")
    if not finite(percent) or abs(100 * (rep[phase] / reference[phase] - 1) - percent) > 2:
        return None
    verb = "stand up" if phase == "ascent_seconds" else "lower"
    return f"Rep {rid} took {rep[phase]:.1f} seconds to {verb}; your reference took {reference[phase]:.1f} seconds."


def _question_intent(question):
    q = question.lower()
    if re.search(r"\b(apply|activate)\b", q) or re.search(r"\b(change|increase|reduce|set)\s+(my|the)\s+(target|targets|load|reps|rest|workout)\b", q) or re.search(r"\bstart\s+(the\s+)?timer\b", q):
        return "apply"
    if re.search(r"\bwhy\b.*\brest\b|\brest\b.*\b(suggest|recommend|change|why|longer|extra)\b|\b(this rest|rest change|extra rest)\b", q):
        return "rest"
    if re.search(r"\b(wrong|safe|pain|injur\w*|perfect|form|lean|upright|deeper|depth)\b", q):
        return "form"
    if re.search(r"\brep(?:etition)?\s*#?\s*\d+\b|\b(this|selected|that) rep\b", q):
        return "rep"
    if re.search(r"\b(improve|improved|better|previous|last set|progress)\b", q):
        return "comparison"
    if re.search(r"\b(focus|next|should)\b", q):
        return "next_set"
    if re.search(r"\b(how many|counted)\b", q):
        return "counts"
    if re.search(r"\b(explain|summari[sz]e|summary|this set)\b", q):
        return "summary"
    if re.search(r"\b(demo|example)\b", q):
        return "demo"
    return "other"


def _answer_guidance(context, measurements, question):
    """Choose facts for the question. Measurement, meaning, and permission stay separate."""
    facts = context["facts"]
    candidates = []
    for key, value in facts.items():
        match = re.fullmatch(r"rep_(\d+)_(torso_inclination|relative_depth|ascent_duration|descent_duration)", key)
        if not match:
            continue
        rid, metric = int(match[1]), match[2]
        point = next((d for d in measurements.get("drift", []) if d.get("rep_id") == rid), {})
        magnitude = point.get({"torso_inclination": "torso_angle_rmse_deg", "relative_depth": "depth_difference_percent", "ascent_duration": "ascent_duration_difference_percent", "descent_duration": "descent_duration_difference_percent"}[metric])
        if metric == "torso_inclination" and not finite(magnitude):
            magnitude = point.get("torso_lean_difference_deg")
        direction = (point.get("upper_body_comparison") or {}).get("direction") if metric == "torso_inclination" else None
        if not _meaningful(metric, magnitude, direction):
            continue
        if metric == "torso_inclination" and direction in {"closer_to_vertical", "farther_from_vertical"}:
            priority = 0
        elif metric == "torso_inclination" and direction == "mixed":
            priority = 5
        else:
            priority = {"ascent_duration": 1, "descent_duration": 2, "relative_depth": 3, "torso_inclination": 4}[metric]
        text = _phase_sentence(key, measurements) or _plain_observation(value["text"])
        candidates.append((priority, -abs(magnitude), key, {"text": text, "evidence_ids": list(value["evidence_ids"])}, direction, rid))
    chosen = min(candidates, key=lambda item: item[:3]) if candidates else None
    finding = dict(chosen[3]) if chosen else None
    finding_direction = chosen[4] if chosen else None
    if finding:
        facts["main_finding"] = finding
    elif "availability" not in facts:
        facts["main_finding"] = {"text": "No clear movement difference was detected in the reliable reps. That is not a technique rating.", "evidence_ids": []}

    asked = context.get("selected_rep_id")
    if asked and f"rep_{asked}" in facts and "not verified" not in facts[f"rep_{asked}"]["text"]:
        best = min((item for item in candidates if item[5] == asked), default=None, key=lambda item: item[:3])
        if best:
            facts[f"rep_{asked}_focus"] = dict(best[3])
        elif "availability" not in facts:
            facts[f"rep_{asked}_focus"] = {"text": f"No clear movement difference was detected for rep {asked}. That is not a technique rating.", "evidence_ids": list(facts[f"rep_{asked}"]["evidence_ids"])}

    recommendation = context.get("recommendation")
    finding_refs = list(finding["evidence_ids"]) if finding else []
    finding_rep = chosen[5] if chosen else None
    if not context["analysis_complete"]:
        step, step_refs = "Your recording is saved. Use the status or same-set retry controls; chat does not restart processing.", []
    elif "availability" in facts:
        step, step_refs = "Let’s get a clearer recording. Keep your whole body visible from the side and review the count. Missing evidence is not a form fault.", []
    elif context["sample"]:
        step, step_refs = "This sample can explain the replay, but it cannot recommend a change to your training.", []
    elif not recommendation:
        step = f"Compare rep {finding_rep} with your reference." if finding_rep else "A next-set recommendation is not available for this recording. Review the replay; chat cannot infer new targets."
        step_refs = finding_refs
    elif recommendation.get("status") == "accepted":
        step, step_refs = "Your choice is already saved. Check the current targets in your workout before the next set.", []
    elif recommendation.get("status") == "rejected":
        step, step_refs = "You declined the suggestion. Check your current workout targets before the next set.", []
    elif recommendation.get("review_only"):
        compare = f"Compare rep {finding_rep} with your reference." if finding_rep else "Review the saved recording before deciding what to do next."
        step, step_refs = f"{compare} This saved result does not support a new target change.", finding_refs
    elif recommendation.get("action") == "KEEP_PLAN":
        step, step_refs = "No corrective cue is supported. The saved recommendation is to keep your current workout targets.", finding_refs
    elif recommendation.get("action") == "EXTEND_REST":
        step, step_refs = "Review the rest suggestion before your next set; it hasn’t been applied.", []
    else:
        step, step_refs = "Review the recommendation before your next set; it hasn’t been applied.", []
    facts["next_action"] = {"text": step, "evidence_ids": step_refs}
    if "rest_reason" not in facts:
        facts["no_rest"] = {"text": "There isn’t a supported rest-change recommendation in this saved result.", "evidence_ids": []}

    if not context["analysis_complete"]:
        measurement_state = "incomplete"
    elif "availability" in facts:
        measurement_state = "unavailable"
    else:
        measurement_state = "descriptive"
    if measurement_state != "descriptive":
        interpretation = "unavailable"
    elif not finding:
        interpretation = "none"
    elif finding_direction in {"closer_to_vertical", "farther_from_vertical"}:
        interpretation = "directional"
    elif finding_direction == "mixed":
        interpretation = "mixed"
    else:
        interpretation = "difference"
    if context["sample"]:
        action_state = "sample"
    elif "closed" in facts:
        action_state = "closed"
    elif not recommendation:
        action_state = "none"
    elif recommendation.get("status") == "accepted":
        action_state = "accepted"
    elif recommendation.get("status") == "rejected":
        action_state = "rejected"
    elif recommendation.get("actionable"):
        action_state = "applicable"
    else:
        action_state = "blocked"
    context["states"] = {"measurements": measurement_state, "interpretation": interpretation, "action": action_state}

    intent = _question_intent(question)
    guard = ["availability", "sample", "closed"]
    if intent == "apply":
        required = ["approval"] + (["recommendation"] if "recommendation" in facts else [])
    elif intent == "rest":
        if "rest_reason" in facts:
            required = ["rest_reason"]
            if recommendation and recommendation.get("status") in {"accepted", "rejected"}:
                required.append("recommendation")
            elif recommendation and recommendation.get("actionable"):
                required.append("recommendation")
        else:
            required = ["no_rest"]
            if "reported" in facts:
                required.append("reported")
            if "main_finding" in facts:
                required.append("main_finding")
            elif "availability" in facts:
                required.append("availability")
    elif intent == "form":
        rid = context.get("selected_rep_id")
        required = [k for k in ([f"rep_{rid}_torso_inclination"] if rid else []) + ["limits", f"rep_{rid}_relative_depth" if rid else ""] if k in facts]
        if not required:
            required = ["limits"] if "limits" in facts else ["availability"] if "availability" in facts else ["scope"]
    elif intent == "rep":
        rid = context.get("selected_rep_id")
        if "missing_rep" in facts and not rid:
            required = ["missing_rep"]
        elif rid and f"rep_{rid}" in facts:
            required = [f"rep_{rid}"]
            if f"rep_{rid}_focus" in facts:
                required.append(f"rep_{rid}_focus")
            elif "availability" in facts:
                required.append("next_action")
        else:
            required = ["missing_rep"] if "missing_rep" in facts else ["availability"] if "availability" in facts else ["counts"]
    elif intent == "comparison":
        timings = [k for k in facts if k.startswith("comparison_")]
        changed = [k for k in timings if "went from" in facts[k]["text"]]
        required = ["comparison"] + (changed[:1] or timings[:1])
    elif intent == "next_set":
        required = []
        if "rest_reason" in facts and recommendation and recommendation.get("action") != "KEEP_PLAN" and not recommendation.get("review_only"):
            required.append("rest_reason")
        required.append("next_action")
        if measurement_state == "descriptive" and "main_finding" in facts:
            required.append("main_finding")
    elif intent == "counts":
        required = ["counts"] + (["availability"] if "availability" in facts else [])
    elif intent == "summary":
        required = ["counts"]
        if "availability" in facts:
            required += ["availability", "next_action"]
        else:
            if "main_finding" in facts:
                required.append("main_finding")
            required.append("next_action")
    elif intent == "demo":
        required = ["demo"] if "demo" in facts else ["scope"]
    else:
        required = ["scope"]
    required = [i for i in required if i in facts][:3] or (["scope"] if "scope" in facts else ["counts"])
    allowed = list(dict.fromkeys(required + [i for i in guard if i in facts]))
    context["answer_policy"] = {"intent": intent if intent != "other" else "out_of_scope", "required": required, "allowed": allowed}


def evidence_link(ref):
    return f"/analysis/{ref['set_id']}?" + urlencode({"rep": ref["rep_id"], "t": ref["seconds"]})
