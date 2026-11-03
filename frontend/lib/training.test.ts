import assert from "node:assert/strict";
import test from "node:test";

import type { RecordedSet, Session } from "./types.ts";
import {
  compareSquatRecordings,
  compareWithPrevious,
  exerciseDisplayName,
  exerciseResults,
  formatClock,
  formatExerciseDose,
  formatLoad,
  isDoneSet,
  latestRealSquat,
  loadToKg,
  sessionForPlan,
  sessionTypeLabel,
  startDestination,
  unitFromProfile,
} from "./training.ts";

function set(partial: Partial<RecordedSet>): RecordedSet {
  return {
    id: Math.random().toString(36),
    session_id: "s",
    exercise_id: "barbell_squat",
    entry_source: "manual",
    set_index: 1,
    load_kg: 100,
    target_reps: 5,
    completed_reps: 5,
    reported_rpe: null,
    processing_status: "LOGGED",
    processing_message: null,
    duration_seconds: null,
    created_at: null,
    raw_deleted: false,
    has_video: false,
    ...partial,
  };
}

function session(id: string, completedAt: string, sets: RecordedSet[], status: Session["status"] = "completed"): Session {
  return {
    id,
    plan_id: "p",
    plan_name: "Lower Body",
    session_type: "lower",
    status,
    started_at: completedAt,
    paused_at: null,
    completed_at: completedAt,
    summary: { completed_sets: sets.length, planned_sets: null, total_reps: 0, volume_kg: 0, exercises: [] },
    sets,
  };
}

test("loads display in the athlete's unit and convert back to kilograms", () => {
  assert.equal(formatLoad(100, "kg"), "100 kg");
  assert.equal(formatLoad(100, "lb"), "220.5 lb");
  assert.equal(formatLoad(null, "kg"), "—");
  assert.equal(formatLoad(null, "lb"), "—");
  assert.equal(loadToKg(225, "lb"), 102.06);
  assert.equal(loadToKg(80, "kg"), 80);
  assert.equal(unitFromProfile(null), "kg");
  assert.equal(
    unitFromProfile({ assessment: { identity: { preferred_weight_unit: "lb" } } } as never),
    "lb",
  );
});

test("a plan reopens its completed or abandoned session so analysis can return to logged sets", () => {
  const abandoned = session("old", "2026-10-28", [set({ entry_source: "video", processing_status: "COMPLETED", has_video: true })], "abandoned");
  abandoned.plan_id = "plan-a";
  const completed = session("done", "2026-10-29", [set({})], "completed");
  completed.plan_id = "plan-b";
  const current = session("open", "2026-10-30", [], "active");
  current.plan_id = "plan-c";
  current.completed_at = null;
  assert.equal(sessionForPlan("plan-c", current, [abandoned, completed])?.id, "open");
  assert.equal(sessionForPlan("plan-b", null, [abandoned, completed])?.status, "completed");
  assert.equal(sessionForPlan("plan-a", null, [abandoned, completed])?.status, "abandoned");
});

test("start training routes by profile, open workout, and next plan", () => {
  assert.equal(startDestination({ hasProfile: false, current: null, next: { id: "p1" } }), "/onboarding");
  assert.equal(startDestination({ hasProfile: true, current: { id: "s1", plan_id: "p2" }, next: { id: "p1" } }), "/workouts/p2");
  assert.equal(startDestination({ hasProfile: true, current: { id: "s1", plan_id: null }, next: null }), "/record?session=s1");
  assert.equal(startDestination({ hasProfile: true, current: null, next: { id: "p1" } }), "/workouts/p1");
  assert.equal(startDestination({ hasProfile: true, current: null, next: null }), "/dashboard?plan=next");
});

test("only real sets count toward results", () => {
  assert.ok(!isDoneSet(set({ entry_source: "video", processing_status: "SAVED", completed_reps: null })));
  assert.ok(isDoneSet(set({ entry_source: "video", processing_status: "SAVED", completed_reps: 8 })));
  assert.ok(isDoneSet(set({})));
  assert.ok(!isDoneSet(set({ completed_reps: 0 })));
  assert.ok(!isDoneSet(set({ entry_source: "video", processing_status: "FAILED", completed_reps: null })));
  assert.ok(!isDoneSet(set({ entry_source: "video", processing_status: "ESTIMATING_POSE", completed_reps: null })));
  const rows = exerciseResults(session("a", "2026-10-28", [set({}), set({ set_index: 2, load_kg: 105, completed_reps: 3 }), set({ completed_reps: 0 })]));
  assert.equal(rows.length, 1);
  assert.equal(rows[0].sets, 2);
  assert.equal(rows[0].best_load_kg, 105);
  assert.equal(rows[0].volume_kg, 815);
  const withPlank = exerciseResults(
    session("b", "2026-10-28", [set({}), set({ exercise_id: "plank", load_kg: null, completed_reps: 40, target_reps: 40 })]),
  );
  assert.equal(withPlank.find((row) => row.exercise_id === "plank")?.measure, "seconds");
  assert.equal(withPlank.find((row) => row.exercise_id === "plank")?.volume_kg, 0);
});

test("comparisons appear only when an earlier completed session trained the same exercise", () => {
  const only = [session("a", "2026-10-28T10:00:00", [set({})])];
  assert.deepEqual(compareWithPrevious(only), []);
  const abandonedEarlier = [...only, session("b", "2026-10-27T10:00:00", [set({ load_kg: 90 })], "abandoned")];
  assert.deepEqual(compareWithPrevious(abandonedEarlier), []);
  const withHistory = [
    session("new", "2026-10-28T10:00:00", [set({ load_kg: 105 }), set({ exercise_id: "plank", load_kg: null, completed_reps: 40 })]),
    session("old", "2026-10-25T10:00:00", [set({ load_kg: 100 })]),
  ];
  const result = compareWithPrevious(withHistory);
  assert.equal(result.length, 1);
  assert.equal(result[0].exercise_id, "barbell_squat");
  assert.equal(result[0].best_load_change_kg, 5);
  assert.equal(result[0].volume_change_kg, 25);
});

test("latest squat card uses real completed recordings and omits sample history", () => {
  const sample = set({
    id: "sample",
    entry_source: "demo",
    is_sample: true,
    processing_status: "COMPLETED",
    completed_reps: 6,
    created_at: "2026-10-29T12:00:00Z",
  });
  const previous = set({
    id: "prev",
    entry_source: "video",
    processing_status: "COMPLETED",
    completed_reps: 8,
    reference_rep: 3,
    created_at: "2026-10-20T12:00:00Z",
  });
  const latest = set({
    id: "live",
    entry_source: "video",
    processing_status: "COMPLETED",
    completed_reps: 5,
    reference_rep: 5,
    created_at: "2026-10-28T12:00:00Z",
  });
  const failed = set({
    id: "fail",
    entry_source: "video",
    processing_status: "FAILED",
    completed_reps: null,
    created_at: "2026-10-30T12:00:00Z",
  });
  const rows = [session("s", "2026-10-28", [sample, previous, latest, failed], "abandoned")];
  assert.equal(latestRealSquat(rows)?.id, "live");
  const compared = compareSquatRecordings(rows);
  assert.equal(compared?.current.id, "live");
  assert.equal(compared?.previous.id, "prev");
  assert.equal(compared?.current.completed_reps, 5);
  assert.equal(compared?.previous.completed_reps, 8);
});

test("exercise names and doses keep ids, seconds, and unknown loads", () => {
  assert.equal(exerciseDisplayName("barbell_squat", "Barbell Back Squat"), "Barbell Back Squat");
  assert.equal(exerciseDisplayName("barbell_squat"), "barbell squat");
  assert.equal(exerciseDisplayName("mystery_lift"), "mystery lift");
  assert.equal(exerciseDisplayName("barbell_squat", "barbell_squat"), "barbell squat");
  assert.equal(
    formatExerciseDose({ exercise_id: "barbell_squat", sets: 4, target_reps: 6, suggested_load_kg: 40 }, "kg"),
    "4 × 6 @ 40 kg",
  );
  assert.equal(
    formatExerciseDose({ exercise_id: "barbell_squat", sets: 4, target_reps: 6, suggested_load_kg: null }, "kg"),
    "4 × 6",
  );
  assert.equal(
    formatExerciseDose({ exercise_id: "plank", sets: 3, target_reps: 45, suggested_load_kg: null, measure: "seconds" }, "kg"),
    "3 × 45s",
  );
});

test("rest timer clock formats minutes and seconds", () => {
  assert.equal(formatClock(90), "1:30");
  assert.equal(formatClock(5), "0:05");
  assert.equal(formatClock(-3), "0:00");
});

test("session labels name the day's focus, not just the weekly split", () => {
  assert.equal(sessionTypeLabel("full_body_a"), "Full body · squat focus");
  assert.equal(sessionTypeLabel("full_body_b"), "Full body · hinge focus");
  assert.equal(sessionTypeLabel("upper"), "Upper body");
  assert.equal(sessionTypeLabel("lower"), "Lower body");
});

test("sample and legacy server-marked fixtures do not count or displace genuine comparisons", () => {
  const real = set({completed_reps: 5, load_kg: 40});
  const sample = set({entry_source: "demo", processing_status: "COMPLETED", completed_reps: 6});
  const legacy = set({entry_source: "video", is_sample: true, processing_status: "COMPLETED", completed_reps: 6});
  const mixed = session("mixed", "2026-10-30", [real, sample, legacy]);
  assert.equal(isDoneSet(sample), false);
  assert.equal(isDoneSet(legacy), false);
  assert.deepEqual(exerciseResults(mixed).map(row => [row.sets, row.reps, row.volume_kg]), [[1, 5, 200]]);
  const previous = session("previous", "2026-10-29", [set({completed_reps: 4, load_kg: 40})]);
  const illustration = session("illustration", "2026-10-31", [sample, legacy]);
  assert.equal(compareWithPrevious([illustration, mixed, previous])[0].reps_change, 1);
});
