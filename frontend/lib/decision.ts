import type { Analysis, Coaching } from "./types";
import { canChangeTargets, nextSetAction } from "./coaching.ts";

export function restDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60), remainder = seconds % 60;
  return [minutes ? `${minutes} min` : "", remainder ? `${remainder} sec` : ""].filter(Boolean).join(" ") || "0 sec";
}

export function feedbackLabel(c: Coaching, sample = false): string {
  return sample || c.is_sample || c.source === "fixture" ? "Sample demonstration" : c.source === "local" ? "Basic movement feedback" : "Saved analysis";
}

export function fallbackCoaching(a: Analysis): Coaching {
  return {id:"unavailable",set_id:a.set_id,plan_id:a.plan_id,session_status:a.session_status,source:"local",source_label:"Local presentation fallback",
    summary:"Feedback unavailable",reason:"Review your replay",observations:[],evidence_references:[],confidence_notes:[],uncertainties:[],
    suggested_action:"NO_RECOMMENDATION",requires_confirmation:true,current_reps:null,current_rest_seconds:null,current_load_kg:null,
    suggested_reps:null,suggested_rest_seconds:null,suggested_load_kg:null,user_decision:"pending",actionable:false};
}

/** Facts, bounded explanation and action stay separate. Never classify free prose. */
export function setDecision(c: Coaching, sample = false) {
  const closed = ["completed", "abandoned"].includes(c.session_status || "");
  const change = canChangeTargets(c.suggested_action);
  const quantifiable = nextSetAction(c).quantifiable;
  const state = sample || c.is_sample ? "sample" : closed ? "closed" : c.historical_interpretation_corrected ? "review" : c.user_decision === "rejected" ? "rejected" : c.user_decision === "accepted" ? c.applied_change?.applied ? "applied" : "kept" : c.actionable === false || !quantifiable ? "review" : "pending";
  const basis = c.presentation?.decision_basis;
  const effort = c.presentation?.reported_effort;
  let headline = "Review your set before changing targets";
  let explanation = "These measurements do not establish a technique correction; inspect the replay before deciding what to do next.";
  if (c.suggested_action === "KEEP_PLAN") {
    headline = "Keep your current targets";
    explanation = "No supported target change is proposed from this set.";
  } else if (change && quantifiable) {
    headline = c.suggested_action === "EXTEND_REST" ? "Take a longer break before your next set" : c.suggested_action === "REDUCE_REPS" ? "Consider fewer reps for your next set" : "Review a lighter load for your next set";
    explanation = basis === "reported_effort" && effort != null
      ? `You rated this set ${effort}/10 effort; a longer break is suggested.`
      : basis === "ascent_duration" || basis === "descent_duration"
        ? "Your reps took different amounts of time; review this change before the next set."
        : basis === "relative_depth" ? "Some reps stopped higher than your reference; review the proposed target with the replay."
          : "Review the suggested change and its evidence before applying it.";
  }
  if (state === "review") {
    headline = "Review your set before changing targets";
    explanation = c.presentation?.measurement_uncertain ? "Tracking wasn’t reliable enough for a comparison; review the clip before changing targets." : "This suggestion is review-only and cannot change your workout targets.";
  }
  if (state === "pending" && c.presentation?.explanation_key === "effort_scope" && basis === "reported_effort" && effort!=null && c.current_reps!=null && c.current_reps===c.suggested_reps) {
    explanation = `You rated this set ${effort}/10 effort; more rest is suggested while keeping your ${c.current_reps}-rep target.`;
  }
  if (state === "applied") { headline = c.suggested_action==="EXTEND_REST"?"Your rest change is saved":"Your change is saved"; explanation = basis==="reported_effort" && effort!=null ? `You approved this change after rating the set ${effort}/10 effort.` : "The approved change is now reflected in your workout targets."; }
  if (state === "rejected") { headline = "You kept your targets"; explanation = "The proposed change was declined; no change was applied by this decision."; }
  if (state === "kept") { headline = "Your choice is saved"; explanation = "This decision kept your workout targets."; }
  if (c.suggested_action === "REQUEST_NEW_RECORDING") { headline = "Record a clearer view"; explanation = "Keep your whole body visible from the side before using movement feedback."; }
  if (c.suggested_action === "STOP_AND_SEEK_PROFESSIONAL_ADVICE") { headline = "Pause and seek individual guidance"; explanation = "A declared limitation needs individual guidance before further training decisions."; }
  if (state === "sample") { headline = "Explore this example"; explanation = "This demonstration never changes your targets or counts as performed training."; }
  if (state === "closed") { headline = "Your saved set review"; explanation = c.user_decision === "accepted" && c.applied_change?.applied ? "Your approved adjustment was recorded for this workout." : c.user_decision === "rejected" ? "You declined the suggestion for this workout." : "This workout has ended; this review will not change its targets."; }
  return { state, change, headline, explanation, mayDecide: state === "pending", proposed: state === "pending" && change,
    reviewLabel: c.suggested_action === "EXTEND_REST" ? "Review rest change" : c.suggested_action === "REDUCE_REPS" ? "Review rep change" : "Review load change" };
}
