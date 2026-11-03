import assert from "node:assert/strict";
import test from "node:test";
import {
  dayAction,
  dayHref,
  exercisePreview,
  localISODate,
} from "./program.ts";
import type { ProgramDay, ProgramWorkout } from "./types.ts";

function workout(partial: Partial<ProgramWorkout> = {}): ProgramWorkout {
  return {
    name: "Upper Body",
    session_type: "upper",
    duration_minutes: 50,
    estimated_minutes: 42,
    notes: null,
    has_video_analysis: false,
    is_preview: true,
    exercises: [
      {
        id: "a",
        exercise_id: "bench_press",
        name: "Bench Press",
        video_analysis: false,
        measure: "reps",
        position: 0,
        sets: 3,
        target_reps: 8,
        rest_seconds: 90,
        suggested_load_kg: null,
        notes: null,
      },
      {
        id: "b",
        exercise_id: "barbell_row",
        name: "Barbell Row",
        video_analysis: false,
        measure: "reps",
        position: 1,
        sets: 3,
        target_reps: 8,
        rest_seconds: 90,
        suggested_load_kg: null,
        notes: null,
      },
    ],
    ...partial,
  };
}

function day(partial: Partial<ProgramDay> = {}): ProgramDay {
  return {
    date: "2026-10-27",
    weekday: "tuesday",
    weekday_label: "Tuesday",
    kind: "training",
    is_today: false,
    is_next: false,
    is_preview: true,
    plan_id: null,
    session_status: null,
    source: "local_preview",
    source_label: "Local workout preview — not Muse Spark",
    placement_note: null,
    detail_note: null,
    recovery_copy: null,
    workout: workout(),
    ...partial,
  };
}

test("local calendar dates use the athlete's local year-month-day", () => {
  const late = new Date(2026, 0, 1, 23, 30, 0);
  assert.equal(localISODate(late), "2026-01-01");
});

test("real saved workouts keep their plan route; previews do not reuse a plan id", () => {
  const real = day({
    is_preview: false,
    plan_id: "plan-123",
    is_next: true,
    session_status: "active",
  });
  assert.equal(dayHref(real, 0), "/workouts/plan-123");
  assert.equal(dayAction(real), "Resume workout");
  const preview = day({ weekday: "thursday" });
  assert.equal(dayHref(preview, 0), "/program/preview?week=0&day=thursday");
  assert.equal(dayAction(preview), "Preview workout");
  assert.equal(
    dayAction(day({ kind: "recovery", workout: null })),
    "View recovery day",
  );
});

test("exercise previews list names without inventing loads", () => {
  assert.equal(exercisePreview(workout()), "Bench Press · Barbell Row");
  assert.match(
    exercisePreview(
      workout({
        exercises: [
          ...workout().exercises,
          workout().exercises[0],
          workout().exercises[1],
        ],
      }),
    ),
    /\+1$/,
  );
});

test("week structure explains full-body sessions separately from balanced weekly coverage", async () => {
  const { structureDescription, structureHeadline } = await import(
    "./program.ts"
  );
  assert.equal(
    structureHeadline("full_body", 4),
    "Full body · 4 sessions per week",
  );
  assert.equal(
    structureHeadline("upper_lower", 4),
    "Upper/lower · 4 sessions per week",
  );
  assert.match(
    structureDescription("full_body"),
    /Each session includes upper- and lower-body/,
  );
  assert.match(
    structureDescription("upper_lower"),
    /not from training the whole body in every session/,
  );
});

test("recording skips completed sessions and respects unfinished-workout protection", async () => {
  const {recordingDestination} = await import("./program.ts");
  const p = {today: "2026-10-31", is_accepted: true, weeks: [{week_index: 0, days: [
    day({plan_id: "closed", is_preview: false, session_status: "completed", workout: workout({has_video_analysis: true})}),
    day({weekday: "friday", workout: workout({has_video_analysis: true})}),
  ]}]} as import("./types.ts").Program;
  assert.equal(recordingDestination(p).href, "/program/preview?week=0&day=friday");
  assert.equal(recordingDestination(p).label, "Preview video workout");
  p.open_session = {id: "open-s", plan_id: "other-plan", status: "paused"};
  assert.equal(recordingDestination(p).href, "/workouts/other-plan");
  assert.equal(recordingDestination(p).label, "Continue unfinished workout");
  assert.equal(recordingDestination(p).canCoach, false);
});

test("recording prefers an open squat workout and gives truthful empty/proposal actions", async () => {
  const {recordingDestination} = await import("./program.ts");
  const p = {today: "2026-10-31", is_accepted: true, weeks: [{week_index: 0, days: [
    day({plan_id: "open", is_preview: false, session_status: "paused", workout: workout({has_video_analysis: true})}),
  ]}]} as import("./types.ts").Program;
  assert.equal(recordingDestination(p).label, "Continue video workout");
  p.weeks[0].days[0].session_status = "completed";
  assert.equal(recordingDestination(p).href, "/onboarding");
  assert.equal(recordingDestination(p).label, "Plan another week");
  p.proposal_id = "proposal"; p.is_accepted = false; p.proposal_kind = "session";
  assert.equal(recordingDestination(p).label, "Review your session");
});
