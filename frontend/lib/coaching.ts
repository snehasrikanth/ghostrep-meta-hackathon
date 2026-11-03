import type { Analysis, AppliedChange, Coaching, CoachingObservation, Rep } from "./types";

type WeightUnit = "kg" | "lb";
const LB_PER_KG = 1 / 0.45359237;

function formatLoad(kg: number | null | undefined, unit: WeightUnit): string {
  if (kg == null) return "Load not entered";
  const value = unit === "lb" ? kg * LB_PER_KG : kg;
  return `${Math.round(value * 10) / 10} ${unit}`;
}

const CHANGE_ACTIONS = new Set(["REDUCE_REPS", "EXTEND_REST", "REDUCE_LOAD_CONSERVATIVELY"]);

/** Explain stored and new coaching without changing its measurements or claims. */
export function explainCoachingTerms(text: string): string {
  const meanings: Record<string, string> = {
    "torso position": "upper-body position",
    "torso inclination": "upper-body angle",
    "torso-angle": "upper-body angle",
    "torso angle": "upper-body angle",
    "torso": "upper body",
    "ascent time": "time standing up",
    "ascent duration": "time standing up",
    "ascent": "standing-up phase",
    "descent time": "time lowering",
    "descent duration": "time lowering",
    "descent": "lowering phase",
    "relative depth": "measured squat depth",
    "knee trajectory": "knee movement (trajectory)",
    "RPE": "reported effort (RPE)",
  };
  return text.replace(/\b(torso position|torso inclination|torso-angle|torso angle|torso|ascent time|ascent duration|ascent|descent time|descent duration|descent|relative depth|knee trajectory|RPE)\b/gi, (term, _match, offset: number) => {
    // New output may already explain a term in parentheses; don't explain it twice.
    if (text.lastIndexOf("(", offset) > text.lastIndexOf(")", offset)) return term;
    const value = meanings[term.toLowerCase() === "rpe" ? "RPE" : term.toLowerCase()];
    return term[0] === term[0].toUpperCase() && term.toLowerCase() !== "rpe"
      ? value[0].toUpperCase() + value.slice(1)
      : value;
  });
}

export type MainFinding = {
  kind: "recording" | "difference" | "close" | "none";
  what: string;
  where: string | null;
  next: string;
  seconds: number | null;
  repId: number | null;
};

export function detectedRepCount(analysis: Pick<Analysis, "detected_reps" | "reps">): number {
  return Number.isInteger(analysis.detected_reps) && analysis.detected_reps! >= 0
    ? analysis.detected_reps!
    : analysis.reps.filter(rep => rep.is_complete).length;
}

export function mainFinding(analysis: Analysis, coaching: Coaching | null): MainFinding {
  const usable = !analysis.measurement_warning && analysis.tracking_quality?.comparison_usable !== false && analysis.tracking_quality?.usable !== false && detectedRepCount(analysis) > 0;
  if (!usable) {
    const issue = analysis.measurement_warning || analysis.tracking_quality?.issues?.[0]?.message || analysis.message;
    return {
      kind: "recording",
      what: issue || "This recording could not be assessed reliably.",
      where: null,
      next: coaching?.reason || "Record again with a clearer side view before using movement conclusions.",
      seconds: null,
      repId: null,
    };
  }

  const observations = (coaching?.observations || []).filter(o => {
    const id = repFromObservation(o, analysis);
    const rep = analysis.reps.find(r => r.rep_id === id);
    return rep && rep.is_complete && rep.comparison_eligible !== false && id !== analysis.reference_rep && analysis.drift.find(d => d.rep_id === id)?.comparison_valid !== false;
  });
  const difference = pickDifference(observations, analysis);
  if (difference) {
    const repId = repFromObservation(difference, analysis);
    const measured = analysis.reps.find(r => r.rep_id === repId && r.is_complete && r.comparison_eligible !== false);
    const seconds = difference.evidence_seconds.find(t => measured && Number.isFinite(t) && t >= measured.start_seconds && t <= measured.end_seconds) ?? null;
    return {
      kind: "difference",
      what: observationCopy(difference, analysis),
      where: whereLabel(repId, seconds),
      next: coaching?.reason || "No next-set change is proposed.",
      seconds,
      repId,
    };
  }

  const close = observations.find((item) => item.metric === "similarity");
  if (close) {
    const seconds = close.evidence_seconds[0] ?? null;
    const repId = repFromObservation(close, analysis);
    return {
      kind: "close",
      what: "No clear movement change versus your reference.",
      where: whereLabel(repId, seconds),
      next: coaching?.reason || "Keep the current workout targets.",
      seconds,
      repId,
    };
  }

  return {
    kind: "none",
    what: "No clear movement change established from this recording.",
    where: null,
      next: coaching?.reason || "Keep the current workout targets.",
    seconds: null,
    repId: analysis.reference_rep,
  };
}

export function referenceCopy(analysis: Analysis): { title: string; body: string } {
  const ref = analysis.reps.find((rep) => rep.is_reference || rep.rep_id === analysis.reference_rep);
  if (!ref || analysis.measurement_warning || analysis.tracking_quality?.comparison_usable === false || analysis.tracking_quality?.usable === false) {
    return {
      title: "Personal reference",
      body: "A personal reference is the best observed repetition in a usable set. This recording does not have one yet.",
    };
  }
  const confidence = Number.isFinite(ref.confidence) ? Math.round(ref.confidence * 100) : null;
  return {
    title: `Personal reference · R${ref.rep_id}`,
    body:
      `Rep ${ref.rep_id} is the best observed repetition in this set, chosen from tracking visibility, smoothness, ` +
      `and consistency with the other complete reps — not an ideal squat, and not a medical standard.` +
      (confidence != null ? ` That repetition's tracking quality was ${confidence}%.` : ""),
  };
}

export function canChangeTargets(action: string | null | undefined): boolean {
  return CHANGE_ACTIONS.has(action || "");
}

export function appliedSummary(coaching: Coaching, unit: WeightUnit = "kg"): string | null {
  if (coaching.is_sample) return null;
  const change = coaching.applied_change;
  if (coaching.user_decision === "rejected") return "Original targets were kept.";
  if (coaching.user_decision !== "accepted") return null;
  if (change?.applied && change.after) {
    return describeChange(change.action, change.before, change.after, unit);
  }
  if (change?.reason === "workout_closed") {
    return "Saved, but this workout is already finished, so remaining-set targets were not changed.";
  }
  if (change?.reason === "no_workout" || change?.reason === "no_exercise") {
    return "Saved, but there was no matching workout exercise to update.";
  }
  return "Current workout targets were kept.";
}

export function targetContextNote(coaching: Coaching): string | null {
  const planned = coaching.planned_set_reps;
  const workout = coaching.workout_reps ?? coaching.current_reps;
  if (planned != null && workout != null && planned !== workout) {
    return `This recording was planned for ${planned} reps. The current workout target is ${workout} reps.`;
  }
  return null;
}

export function formatRepLoad(
  reps: number | null | undefined,
  loadKg: number | null | undefined,
  unit: "kg" | "lb",
): string {
  const repPart = reps != null ? `${reps} reps` : "reps not set";
  return `${repPart} · ${formatLoad(loadKg, unit)}`;
}

export function formatWorkoutTarget(
  reps: number | null | undefined,
  rest: number | null | undefined,
  loadKg: number | null | undefined,
  unit: "kg" | "lb",
): string {
  const restPart = rest != null ? `${rest}s rest` : "rest not set";
  return `${formatRepLoad(reps, loadKg, unit)} · ${restPart}`;
}

export function keepPlanButtonLabel(action: string | null | undefined): string {
  if (action === "REQUEST_NEW_RECORDING" || action === "STOP_AND_SEEK_PROFESSIONAL_ADVICE") return "Got it";
  return "Keep current workout targets";
}

function describeChange(
  action: string | undefined,
  before: AppliedChange["before"],
  after: NonNullable<AppliedChange["after"]>,
  unit: WeightUnit,
): string {
  if (action === "REDUCE_REPS") return `Saved: next squat target is ${after.target_reps} reps (was ${before?.target_reps}).`;
  if (action === "EXTEND_REST") return `Saved: rest is now ${after.rest_seconds}s (was ${before?.rest_seconds}s).`;
  if (action === "REDUCE_LOAD_CONSERVATIVELY") {
    return `Saved: suggested load is now ${formatLoad(after.suggested_load_kg, unit)} (was ${formatLoad(before?.suggested_load_kg, unit)}).`;
  }
  return "Saved the supported adjustment.";
}

function supportedBodyDirection(observation: CoachingObservation, analysis: Analysis): string | null {
  if (observation.metric !== "torso_inclination") return null;
  const comparison = analysis.drift.find(d => d.rep_id === repFromObservation(observation, analysis))?.upper_body_comparison;
  if (!comparison || comparison.method !== "phase_aligned_image_vertical_v1" || comparison.valid_samples <= 0 || !Number.isFinite(comparison.signed_mean_difference_deg)) return null;
  if (comparison.direction === "closer_to_vertical" && comparison.signed_mean_difference_deg! < 0) return comparison.direction;
  if (comparison.direction === "farther_from_vertical" && comparison.signed_mean_difference_deg! > 0) return comparison.direction;
  return null;
}

function pickDifference(observations: CoachingObservation[], analysis: Analysis): CoachingObservation | null {
  // Existing local-coach / interpretation significance rules. This is display
  // priority only, never a new assessment or authorization to change targets.
  // Do not rank degrees against percentages or elevate tiny depth differences.
  // A validated directional change gives the user a concrete replay comparison.
  // This affects presentation only; next-set decisions keep their independent basis.
  const directional = observations.filter(o => o.statement && Number.isFinite(o.magnitude) && o.magnitude! >= 6 && supportedBodyDirection(o, analysis))
    .sort((a, b) => Math.abs(b.magnitude!) - Math.abs(a.magnitude!));
  if (directional[0]) return directional[0];
  for (const metric of ["ascent_duration", "descent_duration", "relative_depth", "torso_inclination"]) {
    const supported = observations.filter(o => o.statement && o.metric === metric && Number.isFinite(o.magnitude) && (
      metric === "ascent_duration" ? o.magnitude! >= 15 :
      metric === "descent_duration" ? Math.abs(o.magnitude!) >= 20 :
      metric === "relative_depth" ? o.magnitude! <= -8 : o.magnitude! >= 6
    )).sort((a,b) => Math.abs(b.magnitude!) - Math.abs(a.magnitude!));
    if (supported[0]) return supported[0];
  }
  return null;
}

function reliablePhase(rep: Rep, phase: "ascent_seconds" | "descent_seconds") {
  const duration = rep[phase];
  const boundary = phase === "ascent_seconds" ? rep.end_seconds - rep.bottom_seconds : rep.bottom_seconds - rep.start_seconds;
  return rep.is_complete && rep.comparison_eligible !== false && Number.isFinite(duration) && duration > 0 && Number.isFinite(boundary) && Math.abs(duration-boundary) <= .1;
}

/** Seconds come only from the actual measured rep and selected reference.
 * Missing legacy fields never turn a relative percentage into seconds. */
export function observationCopy(observation: CoachingObservation, analysis: Analysis): string {
  const id = repFromObservation(observation, analysis);
  const rep = analysis.reps.find(r => r.rep_id === id);
  const reference = analysis.reps.find(r => r.rep_id === analysis.reference_rep);
  const point = analysis.drift.find(d => d.rep_id === id);
  if (id != null && rep && rep.is_complete && rep.comparison_eligible !== false && point?.comparison_valid !== false && !analysis.measurement_warning && analysis.tracking_quality?.usable !== false && analysis.tracking_quality?.comparison_usable !== false) {
    const direction = supportedBodyDirection(observation, analysis);
    if (direction === "closer_to_vertical") return `Rep ${id}'s upper body looked more upright than your reference.`;
    if (direction === "farther_from_vertical") return `Rep ${id}'s upper body looked less upright than your reference.`;
  }
  if (observation.metric === "ascent_duration" || observation.metric === "descent_duration") {
    const phase = observation.metric === "ascent_duration" ? "ascent_seconds" : "descent_seconds";
    const verb = phase === "ascent_seconds" ? "stand up" : "lower";
    const percent = phase === "ascent_seconds" ? point?.ascent_duration_difference_percent : point?.descent_duration_difference_percent;
    if (!analysis.measurement_warning && analysis.tracking_quality?.comparison_usable !== false && analysis.tracking_quality?.usable !== false && point?.comparison_valid !== false && Number.isFinite(percent) && rep && reference && rep !== reference && reliablePhase(rep, phase) && reliablePhase(reference, phase) && observation.evidence_seconds.some(t => t >= rep.start_seconds && t <= rep.end_seconds) && Math.abs(100*(rep[phase]/reference[phase]-1)-percent!) <= 2) {
      return `Rep ${id} took ${rep[phase].toFixed(1)} seconds to ${verb}; your reference took ${reference[phase].toFixed(1)} seconds.`;
    }
    return id != null ? `Rep ${id}'s time ${phase === "ascent_seconds" ? "standing up" : "lowering"} differed from your reference.` : explainCoachingTerms(observation.statement);
  }
  if (observation.metric === "relative_depth" && observation.magnitude != null && observation.magnitude <= -8 && id != null) {
    return `Rep ${id} stopped higher than your reference.`;
  }
  return explainCoachingTerms(observation.statement);
}

/** A deterministic action, never free-form observational prose reused as a cue. */
export function nextSetAction(c: Coaching): { text: string; quantifiable: boolean } {
  const change = canChangeTargets(c.suggested_action);
  const quantifiable = !change || (c.suggested_action === "REDUCE_REPS"
    ? Number.isFinite(c.suggested_reps) && c.suggested_reps! > 0
    : c.suggested_action === "EXTEND_REST"
      ? Number.isFinite(c.suggested_rest_seconds) && c.suggested_rest_seconds! > 0 && Number.isFinite(c.current_rest_seconds)
      : Number.isFinite(c.suggested_load_kg) && c.suggested_load_kg! >= 0);
  if (c.user_decision !== "pending") return {text: "Your next-set decision is saved.", quantifiable};
  if (c.actionable === false) return {text: "Review the replay before changing targets.", quantifiable};
  if (change && !quantifiable) return {text: "This suggestion has no usable target value. Review the replay; it cannot be applied here.", quantifiable};
  if (c.suggested_action === "REQUEST_NEW_RECORDING") return {text: "Record again with a clear side view and your whole body in frame.", quantifiable};
  if (c.suggested_action === "STOP_AND_SEEK_PROFESSIONAL_ADVICE") return {text: "Pause training and seek individual professional guidance.", quantifiable};
  if (change || c.suggested_action === "KEEP_PLAN") return {text: nextSetHeading(c), quantifiable};
  return {text: "No technique correction is justified by these measurements. Review the relevant replay before changing targets.", quantifiable};
}

function repFromObservation(observation: CoachingObservation, analysis: Analysis): number | null {
  if (observation.rep_id != null) return observation.rep_id;
  const match = observation.statement.match(/Rep (\d+)/i);
  if (match) return Number(match[1]);
  const t = observation.evidence_seconds[0];
  if (t == null) return null;
  const hit = analysis.reps.find((rep) => t >= rep.start_seconds && t <= rep.end_seconds);
  return hit?.rep_id ?? null;
}

function whereLabel(repId: number | null, seconds: number | null): string | null {
  if (repId == null && seconds == null) return null;
  if (repId != null && seconds != null) return `Rep ${repId} at ${_clock(seconds)}`;
  if (repId != null) return `Rep ${repId}`;
  return _clock(seconds || 0);
}

function _clock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function nextSetHeading(c: Coaching): string {
  if (c.user_decision === "rejected") return "Kept your current targets.";
  if (c.user_decision === "accepted" && c.applied_change?.applied && c.applied_change.after?.rest_seconds != null && c.suggested_action === "EXTEND_REST") return `Rest saved at ${c.applied_change.after.rest_seconds} seconds.`;
  if (c.suggested_action === "EXTEND_REST" && c.current_rest_seconds != null && c.suggested_rest_seconds != null) {
    return `Add ${Math.max(0,c.suggested_rest_seconds-c.current_rest_seconds)} seconds of rest.`;
  }
  if (c.suggested_action === "REDUCE_REPS" && c.suggested_reps != null) return `Next set: ${c.suggested_reps} reps.`;
  if (c.suggested_action === "REDUCE_LOAD_CONSERVATIVELY") return "Use the suggested lighter load next set.";
  if (c.suggested_action === "KEEP_PLAN") return "Keep your current targets.";
  return "Review the recording before changing targets.";
}
export function applyTargetLabel(c: Coaching): string {
  if (c.suggested_action === "EXTEND_REST" && c.current_rest_seconds != null && c.suggested_rest_seconds != null)
    return `Apply +${c.suggested_rest_seconds-c.current_rest_seconds}s rest`;
  if (c.suggested_action === "REDUCE_REPS") return `Apply ${c.suggested_reps}-rep target`;
  return "Apply suggested load";
}

/** Read-only fallback for old APIs/history: unsigned magnitude never supplies direction. */
export function coachingForDisplay(analysis: Analysis, coaching: Coaching): Coaching {
  if (coaching.interpretation_version === "upper-body-v1") return coaching;
  const hasAngle = analysis.drift.some(d => d.torso_lean_difference_deg != null || d.torso_angle_rmse_deg != null)
    || coaching.observations.some(o => o.metric === "torso_inclination");
  if (!hasAngle) return coaching;
  const observations = analysis.measurement_warning ? [] : analysis.drift.flatMap(d => {
    const r = analysis.reps.find(r => r.rep_id === d.rep_id);
    const magnitude = d.torso_angle_rmse_deg ?? d.torso_lean_difference_deg;
    if (!r || r.comparison_eligible === false || d.comparison_valid === false || r.rep_id === analysis.reference_rep || magnitude == null || !Number.isFinite(magnitude) || magnitude < 6) return [];
    return [{metric:"torso_inclination",statement:`Rep ${r.rep_id}'s upper-body angle differed from your reference.`,evidence_seconds:[r.bottom_seconds],magnitude}];
  });
  const notice = "Corrected measurement interpretation of stored coaching. Original text and decision history are retained; this is not a new model response.";
  return {...coaching, historical_interpretation_corrected:true,interpretation_notice:notice,
    summary:analysis.measurement_warning || observations.map(o=>o.statement).join(" ") || "Upper-body direction is unavailable from these measurements.",
    observations,primary_cue:observations[0]?.statement ?? null,
    reason:analysis.measurement_warning || "Review the replay before changing targets. An upper-body angle difference alone does not justify a rep or load reduction.",
    suggested_action:"NO_RECOMMENDATION",actionable:false,state:"review_only",action_blocked_reason:notice,
    suggested_reps:coaching.current_reps,suggested_rest_seconds:coaching.current_rest_seconds,suggested_load_kg:coaching.current_load_kg,
    confidence_notes:["Legacy RMS is an unsigned difference, not anatomical forward/backward direction or a technique score."],uncertainties:[],
    stored_versions:coaching.stored_versions?.map(v=>({...v,summary:"Stored wording requires the corrected backend interpretation.",reason:notice,primary_cue:null,observations:[],confidence_notes:[],uncertainties:[],suggested_action:"NO_RECOMMENDATION",actionable:false,can_activate:false,activation_blocked_reason:notice}))};
}
