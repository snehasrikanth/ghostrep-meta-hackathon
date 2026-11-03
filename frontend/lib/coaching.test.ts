import assert from "node:assert/strict";
import test from "node:test";
import {
  appliedSummary,
  canChangeTargets,
  formatWorkoutTarget,
  keepPlanButtonLabel,
  mainFinding,
  referenceCopy,
  targetContextNote,
  explainCoachingTerms,
  observationCopy,
  nextSetAction,
  detectedRepCount,
} from "./coaching.ts";
import type { Analysis, Coaching, Rep } from "./types.ts";

test("plain-language coaching retains measurements and uncertainty without inventing a correction", () => {
  const original = "Rep 3 showed a 12° torso-angle difference. Ascent time was 0.8s; the cause is unknown.";
  const copy = explainCoachingTerms(original);
  assert.match(copy, /Rep 3.*12° upper-body angle/);
  assert.match(copy, /Time standing up was 0.8s/);
  assert.match(copy, /cause is unknown/);
  assert.doesNotMatch(copy, /wrong|unsafe|injur/i);
  assert.equal(explainCoachingTerms("No clear change detected."), "No clear change detected.");
  assert.equal(explainCoachingTerms(copy), copy);
});

function rep(partial: Partial<Rep> & { rep_id: number }): Rep {
  return {
    start_seconds: 1,
    bottom_seconds: 1.5,
    end_seconds: 2,
    descent_seconds: 0.5,
    ascent_seconds: 0.5,
    is_complete: true,
    is_reference: partial.rep_id === 2,
    confidence: 0.84,
    metrics: {},
    ...partial,
  };
}

function analysis(partial: Partial<Analysis> = {}): Analysis {
  return {
    id: "a",
    set_id: "s",
    status: "COMPLETED",
    message: null,
    exercise_id: "barbell_squat",
    duration_seconds: 16,
    completed_reps: 5,
    reference_rep: 2,
    tracking_quality: { usable: true, score: 0.9, side: "right", issues: [], notes: [] },
    reps: [rep({ rep_id: 1, start_seconds: 0.4 }), rep({ rep_id: 2, start_seconds: 3.2, is_reference: true })],
    drift: [],
    pose_available: true,
    sam_available: false,
    sam_status: "skipped_local",
    analysis_version: "local-v2",
    mode: "real",
    ...partial,
  };
}

function coaching(partial: Partial<Coaching> = {}): Coaching {
  return {
    id: "c",
    set_id: "s",
    source: "local",
    source_label: "Local deterministic coach — not Muse Spark",
    summary: "5 complete squat repetitions were measured.",
    observations: [],
    evidence_references: [],
    confidence_notes: [],
    uncertainties: [],
    suggested_action: "KEEP_PLAN",
    reason: "Later repetitions stayed close to your best observed reference repetition.",
    requires_confirmation: true,
    suggested_reps: 8,
    suggested_rest_seconds: 120,
    suggested_load_kg: 40,
    current_reps: 8,
    current_rest_seconds: 120,
    current_load_kg: 40,
    user_decision: "pending",
    ...partial,
  };
}

test("validated directional evidence leads the replay takeaway without changing the next-set decision", () => {
  const a = analysis({
    reps: [rep({rep_id:1}), rep({rep_id:2}), rep({rep_id:3,start_seconds:6,bottom_seconds:7,end_seconds:8})],
    drift: [{rep_id:3,comparison_valid:true,upper_body_comparison:{method:"phase_aligned_image_vertical_v1",
      direction:"closer_to_vertical",signed_mean_difference_deg:-28,valid_samples:17}} as Analysis["drift"][number]],
  });
  const c = coaching({suggested_action:"KEEP_PLAN",observations:[
    {metric:"descent_duration",rep_id:1,statement:"Rep 1 lowered slower.",magnitude:68,evidence_seconds:[1.5]},
    {metric:"torso_inclination",rep_id:3,statement:"Rep 3 differed across matched phases.",magnitude:29.7,evidence_seconds:[7]},
  ]});
  const before = JSON.stringify(c);
  const finding = mainFinding(a,c);
  assert.equal(finding.repId,3);
  assert.equal(finding.seconds,7);
  assert.equal(finding.what,"Rep 3's upper body looked more upright than your reference.");
  assert.equal(JSON.stringify(c),before);
  for (const direction of ["mixed","unavailable"]) {
    const uncertain = {...a,drift:[{...a.drift[0],upper_body_comparison:{...a.drift[0].upper_body_comparison!,direction}}]};
    assert.equal(mainFinding(uncertain,c).repId,1);
  }
  const contradictory = {...a,drift:[{...a.drift[0],upper_body_comparison:{...a.drift[0].upper_body_comparison!,signed_mean_difference_deg:28}}]};
  assert.equal(mainFinding(contradictory,c).repId,1);
  assert.equal(mainFinding({...a,measurement_warning:"Tracking discontinuity"},c).kind,"recording");
  assert.equal(mainFinding({...a,reps:a.reps.map(r=>r.rep_id===3?{...r,comparison_eligible:false}:r)},c).repId,1);
});

test("a usable set with no mechanical difference is reported as close, not a defect", () => {
  const finding = mainFinding(
    analysis(),
    coaching({
      observations: [
        {
          metric: "similarity",
          statement: "Rep 1 stayed close to your reference (74% movement similarity).",
          evidence_seconds: [0.4],
          magnitude: 74,
        },
      ],
    }),
  );
  assert.equal(finding.kind, "close");
  assert.match(finding.what, /no clear movement change/i);
  assert.equal(finding.seconds, 0.4);
  assert.equal(finding.repId, 1);
  assert.equal(finding.where, "Rep 1 at 0:00");
});

test("supported timing takes priority over a differently scaled angle measurement", () => {
  const finding = mainFinding(
    analysis({reps:[rep({rep_id:2}),rep({rep_id:5,start_seconds:11,bottom_seconds:11.5,end_seconds:12})]}),
    coaching({
      reason: "A conservative rep reduction keeps the next set closer to that reference.",
      suggested_action: "REDUCE_REPS",
      observations: [
        {
          metric: "torso_inclination",
          statement: "Rep 4 showed about 6.2° more torso-angle difference versus your reference repetition.",
          evidence_seconds: [8.1],
          magnitude: 6.2,
        },
        {
          metric: "ascent_duration",
          statement: "Rep 5 took about 22% longer to stand up than the reference repetition.",
          evidence_seconds: [11.4],
          magnitude: 22,
        },
      ],
    }),
  );
  assert.equal(finding.kind, "difference");
  assert.match(finding.what, /time standing up differed/);
  assert.equal(finding.seconds, 11.4);
  assert.equal(finding.repId, 5);
  assert.match(finding.next, /rep reduction/i);
});

test("unusable tracking suppresses movement conclusions", () => {
  const finding = mainFinding(
    analysis({
      completed_reps: 0,
      tracking_quality: {
        usable: false,
        score: 0.2,
        side: "right",
        issues: [{ code: "occlusion", message: "Too much of the athlete was occluded.", severity: "error" }],
        notes: [],
      },
    }),
    coaching({
      suggested_action: "REQUEST_NEW_RECORDING",
      observations: [
        { metric: "ascent_duration", statement: "Invented later-rep claim.", evidence_seconds: [3], magnitude: 40 },
      ],
    }),
  );
  assert.equal(finding.kind, "recording");
  assert.match(finding.what, /occluded/);
  assert.equal(finding.seconds, null);
});

test("reference copy uses the selected rep and its tracking confidence", () => {
  const copy = referenceCopy(analysis());
  assert.match(copy.title, /R2/);
  assert.match(copy.body, /best observed repetition/);
  assert.match(copy.body, /84%/);
  assert.match(copy.body, /not an ideal squat/);
});

test("KEEP_PLAN labels distinguish planned, completed, and workout targets", () => {
  const keep = coaching({
    planned_set_reps: 8,
    planned_set_load_kg: null,
    completed_reps: 5,
    workout_reps: 6,
    workout_rest_seconds: 150,
    workout_load_kg: 40,
    current_reps: 6,
    current_rest_seconds: 150,
    current_load_kg: 40,
    suggested_reps: 6,
    suggested_rest_seconds: 150,
    suggested_load_kg: 40,
  });
  assert.equal(targetContextNote(keep), "This recording was planned for 8 reps. The current workout target is 6 reps.");
  assert.equal(formatWorkoutTarget(keep.workout_reps, keep.workout_rest_seconds, keep.workout_load_kg, "kg"), "6 reps · 40 kg · 150s rest");
  assert.equal(formatWorkoutTarget(6, 150, null, "kg"), "6 reps · Load not entered · 150s rest");
  assert.equal(keepPlanButtonLabel("KEEP_PLAN"), "Keep current workout targets");
  assert.equal(appliedSummary(coaching({ user_decision: "accepted", suggested_action: "KEEP_PLAN" })), "Current workout targets were kept.");
});

test("saved adjustment copy names the actual target change", () => {
  assert.equal(canChangeTargets("REDUCE_REPS"), true);
  assert.equal(canChangeTargets("KEEP_PLAN"), false);
  const saved = appliedSummary(
    coaching({
      user_decision: "accepted",
      suggested_action: "REDUCE_REPS",
      applied_change: {
        applied: true,
        action: "REDUCE_REPS",
        reason: "applied",
        before: { target_reps: 8, rest_seconds: 120, suggested_load_kg: 40 },
        after: { target_reps: 6, rest_seconds: 120, suggested_load_kg: 40 },
      },
    }),
  );
  assert.equal(saved, "Saved: next squat target is 6 reps (was 8).");
  assert.equal(appliedSummary(coaching({ user_decision: "rejected" })), "Original targets were kept.");
});


test("invalid comparison cannot be presented as normal variation", () => {
  const finding=mainFinding(analysis({measurement_warning:"Tracking discontinuity",tracking_quality:{usable:true,comparison_usable:false,score:.8,side:"right",issues:[],notes:[]}}),coaching());
  assert.equal(finding.kind,"recording");assert.match(finding.what,/discontinuity/);
});

test("rest headings distinguish pending adjustment from saved targets", async () => {
  const {nextSetHeading,applyTargetLabel,formatWorkoutTarget}=await import("./coaching.ts");
  const c=coaching({suggested_action:"EXTEND_REST",current_rest_seconds:120,suggested_rest_seconds:150});
  assert.equal(nextSetHeading(c),"Add 30 seconds of rest.");
  assert.equal(applyTargetLabel(c),"Apply +30s rest");
  assert.equal(nextSetHeading({...c,user_decision:"accepted",current_rest_seconds:150,applied_change:{applied:true,after:{target_reps:8,rest_seconds:150,suggested_load_kg:null}}}),"Rest saved at 150 seconds.");
  assert.match(formatWorkoutTarget(8,120,null,"kg"),/Load not entered/);
});

test("legacy angle RMS cannot display or apply a directional correction", async () => {
  const {coachingForDisplay}=await import("./coaching.ts");
  const a=analysis({drift:[{rep_id:1,torso_lean_difference_deg:29.7,similarity:40} as Analysis["drift"][number]]});
  const original=coaching({summary:"More forward lean means incorrect posture.",reason:"Lean farther forward and reduce reps.",primary_cue:"Lean farther forward.",suggested_action:"REDUCE_REPS",suggested_reps:6,
    observations:[{metric:"torso_inclination",statement:"Rep 1 had more forward lean.",magnitude:29.7,evidence_seconds:[1.5]}]});
  const snapshot=JSON.stringify(original);
  const c=coachingForDisplay(a,original);
  assert.doesNotMatch(JSON.stringify(c),/more forward|farther forward|incorrect posture/);
  assert.match(c.summary,/upper-body angle differed/);
  assert.equal(c.suggested_action,"NO_RECOMMENDATION");assert.equal(c.actionable,false);
  assert.equal(c.suggested_reps,8);assert.equal(JSON.stringify(original),snapshot);
  const finding=mainFinding(a,c);assert.equal(finding.repId,1);assert.equal(finding.seconds,1.5);
});

test("backend-validated direction and saved decision history are preserved", async () => {
  const {coachingForDisplay}=await import("./coaching.ts");
  const c=coaching({interpretation_version:"upper-body-v1",summary:"Rep 3's upper body was closer to vertical than your reference.",
    historical_interpretation_corrected:true,interpretation_notice:"Corrected interpretation; original decision preserved.",user_decision:"accepted",actionable:false,
    applied_change:{applied:true,action:"REDUCE_REPS",before:{target_reps:8,rest_seconds:120,suggested_load_kg:40},after:{target_reps:6,rest_seconds:120,suggested_load_kg:40}}});
  assert.equal(coachingForDisplay(analysis(),c),c);
  assert.match(appliedSummary(c)!,/6 reps/);
});


test("absolute phase timing uses the selected reference and relevant measured rep", () => {
  const a = analysis({reference_rep:2, reps:[rep({rep_id:2,start_seconds:3,bottom_seconds:4,end_seconds:4.8,descent_seconds:1,ascent_seconds:.8}),rep({rep_id:6,start_seconds:10,bottom_seconds:11,end_seconds:13.7,descent_seconds:1,ascent_seconds:2.7})], drift:[{rep_id:6,comparison_valid:true,ascent_duration_difference_percent:237.5} as Analysis["drift"][number]]});
  const o={metric:"ascent_duration",statement:"Rep 6 took longer.",rep_id:6,evidence_seconds:[11],magnitude:237.5};
  assert.equal(observationCopy(o,a),"Rep 6 took 2.7 seconds to stand up; your reference took 0.8 seconds.");
  assert.equal(mainFinding(a,coaching({observations:[o]})).seconds,11);
  for (const changed of [analysis({...a,reference_rep:null}),analysis({...a,measurement_warning:"Camera moved"}),analysis({...a,drift:[]}),analysis({...a,reps:a.reps.map(r=>({...r,comparison_eligible:false}))}),analysis({...a,reps:a.reps.map(r=>({...r,ascent_seconds:NaN}))}),analysis({...a,drift:[{...a.drift[0],ascent_duration_difference_percent:10}]})]) {
    assert.doesNotMatch(observationCopy(o,changed),/2.7 seconds|0.8 seconds/);
  }
  assert.doesNotMatch(observationCopy({...o,evidence_seconds:[0]},a),/2.7 seconds/);
  assert.doesNotMatch(observationCopy({...o,rep_id:2},a),/2.7 seconds/);
});

test("observations are not next-set instructions and missing target values cannot apply", () => {
  const measured="Rep 6 took longer to stand up.";
  assert.equal(nextSetAction(coaching({primary_cue:measured})).text,"Keep your current targets.");
  const review=nextSetAction(coaching({suggested_action:"NO_RECOMMENDATION",primary_cue:measured}));
  assert.doesNotMatch(review.text,/Rep 6/);assert.match(review.text,/No technique correction is justified/);
  assert.match(nextSetAction(coaching({actionable:false,suggested_action:"REDUCE_REPS",suggested_reps:6})).text,/Review the replay/);
  for (const missing of [{suggested_action:"REDUCE_REPS",suggested_reps:null},{suggested_action:"EXTEND_REST",suggested_rest_seconds:null},{suggested_action:"REDUCE_LOAD_CONSERVATIVELY",suggested_load_kg:null}]) {
    const action=nextSetAction(coaching(missing));assert.equal(action.quantifiable,false);assert.match(action.text,/cannot be applied/);
  }
});

test("tiny depth variation stays secondary and shallower does not become an instruction", () => {
  const tiny={metric:"relative_depth",statement:"Rep 1 reached 1% more relative depth.",rep_id:1,evidence_seconds:[1],magnitude:1};
  assert.equal(mainFinding(analysis(),coaching({observations:[tiny]})).kind,"none");
  assert.equal(mainFinding(analysis(),coaching({observations:[{...tiny,rep_id:999,magnitude:-20}]})).kind,"none");
  assert.equal(mainFinding(analysis({reps:[rep({rep_id:1,comparison_eligible:false})]}),coaching({observations:[{...tiny,magnitude:-20}]})).kind,"none");
  const shallow={...tiny,magnitude:-12};
  assert.equal(observationCopy(shallow,analysis()),"Rep 1 stopped higher than your reference.");
  assert.doesNotMatch(nextSetAction(coaching({primary_cue:shallow.statement})).text,/deeper|lean|bend/);
});

test("legacy detected counts come from measured repetitions, never corrected log counts", () => {
  const a=analysis({completed_reps:12,detected_reps:undefined});
  assert.equal(detectedRepCount(a),2);
  assert.equal(detectedRepCount({...a,detected_reps:0}),0);
  assert.equal(detectedRepCount({...a,reps:[]}),0);
  assert.equal(mainFinding({...a,reps:[]},coaching()).kind,"recording");
});
