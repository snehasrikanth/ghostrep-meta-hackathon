from __future__ import annotations

from app.services.coaching.guards import validate_recommendation
from app.services.coaching.evidence import ground_coaching
from app.services.coaching.measurement_guard import context_problem, suppress_unreliable

SOURCE_LABEL = "Local deterministic coach — not Muse Spark"


def generate_local_coaching(
    *,
    quality: dict,
    drift: list[dict],
    reps: list[dict],
    reference_rep: int | None,
    profile: dict | None,
    current_reps: int | None,
    current_rest: int | None,
    current_load: float | None,
    reported_rpe: float | None,
    planned_set_reps: int | None = None,
    planned_set_load_kg: float | None = None,
    completed_reps: int | None = None,
    workout_reps: int | None = None,
    workout_rest_seconds: int | None = None,
    workout_load_kg: float | None = None,
    **_unused,
) -> dict:
    problem = context_problem({"quality":quality,"drift":drift,"reference_rep":reference_rep})
    if problem:
        return suppress_unreliable(_base("NO_RECOMMENDATION", problem, current_reps,current_rest,current_load,reported_rpe,
            planned_set_reps=planned_set_reps,planned_set_load_kg=planned_set_load_kg,completed_reps=completed_reps,
            workout_reps=workout_reps,workout_rest_seconds=workout_rest_seconds,workout_load_kg=workout_load_kg),problem)
    limitations = [str(x).lower() for x in (profile or {}).get("limitations", [])]
    if any("pain" in item for item in limitations):
        payload = _base(
            "STOP_AND_SEEK_PROFESSIONAL_ADVICE",
            "A pain-related limitation was declared. GhostRep does not recommend training through pain.",
            current_reps,
            current_rest,
            current_load,
            reported_rpe,
            planned_set_reps=planned_set_reps,
            planned_set_load_kg=planned_set_load_kg,
            completed_reps=completed_reps,
            workout_reps=workout_reps,
            workout_rest_seconds=workout_rest_seconds,
            workout_load_kg=workout_load_kg,
        )
        payload["uncertainties"].append("This is not a medical assessment.")
        return validate_recommendation(payload, profile)

    if not quality.get("usable"):
        evidence = []
        observations = [
            {
                "metric": "camera_quality",
                "statement": issue["message"],
                "evidence_seconds": [],
                "magnitude": None,
            }
            for issue in quality.get("issues", [])
        ]
        payload = _base(
            "REQUEST_NEW_RECORDING",
            "The recording could not be analyzed reliably, so no load or rep change is proposed.",
            current_reps,
            current_rest,
            current_load,
            reported_rpe,
            observations=observations,
            evidence=evidence,
            planned_set_reps=planned_set_reps,
            planned_set_load_kg=planned_set_load_kg,
            completed_reps=completed_reps,
            workout_reps=workout_reps,
            workout_rest_seconds=workout_rest_seconds,
            workout_load_kg=workout_load_kg,
        )
        payload["confidence_notes"].append("Camera-quality gate blocked metric coaching.")
        return validate_recommendation(payload, profile)

    if not reps or reference_rep is None:
        payload = _base(
            "NO_RECOMMENDATION",
            "Not enough complete repetitions were identified to compare against a personal reference.",
            current_reps,
            current_rest,
            current_load,
            reported_rpe,
            planned_set_reps=planned_set_reps,
            planned_set_load_kg=planned_set_load_kg,
            completed_reps=completed_reps,
            workout_reps=workout_reps,
            workout_rest_seconds=workout_rest_seconds,
            workout_load_kg=workout_load_kg,
        )
        return validate_recommendation(payload, profile)

    reps = [r for r in reps if r.get("comparison_eligible") is not False]
    late = [d for d in drift if d["rep_id"] != reference_rep]
    onset = next((d for d in late if d.get("onset")), None)
    worst = min(late, key=lambda d: d["similarity"]) if late else None
    observations = []
    evidence: list[float] = []
    for item in late:
        if abs(item["torso_lean_difference_deg"]) >= 6:
            ev = _rep_time(reps, item["rep_id"])
            observations.append(
                {
                    "metric": "torso_inclination",
                    "statement": (
                        f"Rep {item['rep_id']} showed about {item['torso_lean_difference_deg']:.1f}° "
                        "more torso-angle difference versus your reference repetition."
                    ),
                    "evidence_seconds": ev,
                    "magnitude": item["torso_lean_difference_deg"],
                }
            )
            evidence.extend(ev)
        if item["depth_difference_percent"] <= -8:
            ev = _rep_time(reps, item["rep_id"], use_bottom=True)
            observations.append(
                {
                    "metric": "relative_depth",
                    "statement": (
                        f"Rep {item['rep_id']} reached about {abs(item['depth_difference_percent']):.0f}% "
                        "less relative squat depth than the reference repetition."
                    ),
                    "evidence_seconds": ev,
                    "magnitude": item["depth_difference_percent"],
                }
            )
            evidence.extend(ev)
        if item["ascent_duration_difference_percent"] >= 15:
            ev = _rep_time(reps, item["rep_id"])
            observations.append(
                {
                    "metric": "ascent_duration",
                    "statement": (
                        f"Rep {item['rep_id']} took about {item['ascent_duration_difference_percent']:.0f}% "
                        "longer to stand up than the reference repetition."
                    ),
                    "evidence_seconds": ev,
                    "magnitude": item["ascent_duration_difference_percent"],
                }
            )
            evidence.extend(ev)

    if not observations and worst:
        observations.append(
            {
                "metric": "similarity",
                "statement": (
                    f"Rep {worst['rep_id']} stayed close to your reference "
                    f"({worst['similarity']:.0f}% movement similarity)."
                ),
                "evidence_seconds": _rep_time(reps, worst["rep_id"]),
                "magnitude": worst["similarity"],
            }
        )

    action = "KEEP_PLAN"
    reason = "Later repetitions stayed close to your best observed reference repetition."
    if worst is not None and not onset:
        deviation = worst.get("reference_deviation", max(0.0, 100 - worst["similarity"]))
        if deviation >= 12:
            reason = (
                "Some repetitions differ from your reference. That difference does not keep growing "
                "across the set, so no rep or load change is proposed."
            )
    if onset:
        if reported_rpe and reported_rpe >= 8.5:
            action = "EXTEND_REST"
            reason = (
                "Movement differences increased in later repetitions and reported exertion is high. "
                "Rest is extended; this does not establish a technique problem."
            )
        else:
            action = "REDUCE_REPS"
            reason = (
                "Later repetitions kept drifting further from your own reference. "
                "A conservative rep reduction keeps the next set closer to that reference."
            )

    summary = (
        f"{len(reps)} reliably tracked repetitions were available for comparison. "
        f"Rep {reference_rep} is the best observed reference based on tracking quality, "
        "smoothness, and consistency — not a universal ideal."
    )
    if onset:
        summary += f" Measurable drift began around repetition {onset['rep_id']}."

    payload = _base(
        action,
        reason,
        current_reps,
        current_rest,
        current_load,
        reported_rpe,
        observations=observations,
        evidence=sorted(set(round(x, 2) for x in evidence)),
        summary=summary,
        planned_set_reps=planned_set_reps,
        planned_set_load_kg=planned_set_load_kg,
        completed_reps=completed_reps if completed_reps is not None else len(reps),
        workout_reps=workout_reps,
        workout_rest_seconds=workout_rest_seconds,
        workout_load_kg=workout_load_kg,
    )
    payload["confidence_notes"].append(
        "Similarity is a weighted mix of torso angle, knee trajectory, depth, hip path, and tempo."
    )
    payload["uncertainties"].append(
        "Monocular phone video cannot prove fatigue, injury, or muscle weakness."
    )
    payload["decision_basis"] = next((o["metric"] for o in observations if o["metric"] in {"ascent_duration","relative_depth","descent_duration"}), None) if onset else None
    context={"quality":quality,"drift":drift,"reps":reps,"reference_rep":reference_rep,"reported_rpe":reported_rpe}
    return ground_coaching(payload, context, profile)


def _rep_time(reps: list[dict], rep_id: int, use_bottom: bool = False) -> list[float]:
    match = next((r for r in reps if r.get("rep_id") == rep_id or r.get("rep_index") == rep_id), None)
    if not match:
        return []
    key = "bottom_seconds" if use_bottom else "start_seconds"
    return [float(match.get(key) or match.get("start_seconds") or 0.0)]


def _base(
    action: str,
    reason: str,
    current_reps,
    current_rest,
    current_load,
    reported_rpe,
    observations=None,
    evidence=None,
    summary: str | None = None,
    planned_set_reps=None,
    planned_set_load_kg=None,
    completed_reps=None,
    workout_reps=None,
    workout_rest_seconds=None,
    workout_load_kg=None,
) -> dict:
    return {
        "source": "local",
        "source_label": SOURCE_LABEL,
        "summary": summary or reason,
        "observations": observations or [],
        "evidence_references": evidence or [],
        "confidence_notes": [],
        "uncertainties": [],
        "suggested_action": action,
        "reason": reason,
        "requires_confirmation": True,
        "suggested_reps": current_reps,
        "suggested_rest_seconds": current_rest,
        "suggested_load_kg": current_load,
        "current_reps": current_reps,
        "current_rest_seconds": current_rest,
        "current_load_kg": current_load,
        "planned_set_reps": planned_set_reps,
        "planned_set_load_kg": planned_set_load_kg,
        "completed_reps": completed_reps,
        "workout_reps": workout_reps,
        "workout_rest_seconds": workout_rest_seconds,
        "workout_load_kg": workout_load_kg,
        "reported_rpe": reported_rpe,
    }
