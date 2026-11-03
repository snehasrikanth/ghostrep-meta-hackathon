import assert from "node:assert/strict";
import test from "node:test";
import {
  captureHref,
  historyRecordingAction,
  canRetryRecording,
  retryRecordingHref,
  nextCaptureSet,
  recordingExercise,
  recordingHref,
  recordingMimeType,
  supportsAnalysis,
} from "./capture.ts";

test("retry is limited to failed personal sets without saved analysis", () => {
  assert.equal(canRetryRecording({processing_status: "FAILED", has_analysis: false}), true);
  for (const processing_status of ["COMPLETED", "SAVED", "SEGMENTING", "UPLOADED"]) {
    assert.equal(canRetryRecording({processing_status, has_analysis: false}), false);
  }
  assert.equal(canRetryRecording({processing_status: "FAILED", has_analysis: true}), false);
  assert.equal(canRetryRecording({processing_status: "FAILED"}), false);
  assert.equal(canRetryRecording({processing_status: "FAILED", has_analysis: false, is_sample: true}), false);
});

test("retry link retains the exact workout set and training details", () => {
  const url = new URL(retryRecordingHref({id: "failed-1", session_id: "workout-1", exercise_id: "barbell_squat",
    set_index: 1, target_reps: 8, load_kg: 20, reported_rpe: 8}, "plan-1"), "http://localhost");
  assert.equal(url.pathname, "/record");
  assert.deepEqual(Object.fromEntries(url.searchParams), {mode: "upload", plan: "plan-1", session: "workout-1",
    exercise: "barbell_squat", set: "1", reps: "8", load: "20", retry: "failed-1", effort: "8"});
});

test("camera and upload links retain workout, set, and kg context", () => {
  const href = captureHref({
    mode: "upload",
    planId: "plan/one",
    sessionId: "session 1",
    exerciseId: "dead_bug",
    setIndex: 2,
    targetReps: 6,
    loadKg: 0,
  });
  const url = new URL(href, "http://localhost:3000");
  assert.equal(url.pathname, "/record");
  assert.equal(url.searchParams.get("plan"), "plan/one");
  assert.equal(url.searchParams.get("session"), "session 1");
  assert.equal(url.searchParams.get("mode"), "upload");
  assert.equal(url.searchParams.get("load"), "0");
  assert.equal(url.searchParams.get("exercise"), "dead_bug");
  assert.equal(captureHref(), "/record?mode=camera");
});

test("saved videos open replay and squat analysis stays limited to barbell squats", () => {
  assert.equal(
    recordingHref({ id: "clip", analysis_requested: false }),
    "/recordings/clip",
  );
  assert.equal(
    recordingHref({ id: "analysis", analysis_requested: true }),
    "/analysis/analysis",
  );
  assert.equal(recordingHref({ id: "legacy" }), "/analysis/legacy");
  assert.equal(supportsAnalysis("barbell_squat"), true);
  for (const exercise of ["goblet_squat", "dead_bug", "plank", "push_up"])
    assert.equal(supportsAnalysis(exercise), false);
});

test("recording selects a supported codec including Safari MP4", () => {
  assert.equal(
    recordingMimeType((mime) => mime === "video/mp4"),
    "video/mp4",
  );
  assert.equal(
    recordingMimeType((mime) => mime.startsWith("video/webm")),
    "video/webm;codecs=vp9",
  );
  assert.equal(
    recordingMimeType(() => false),
    undefined,
  );
});

test("the workout recording action selects barbell squat and the next unused set", () => {
  const exercises = [
    { exercise_id: "bench_press" },
    { exercise_id: "barbell_squat" },
  ];
  assert.equal(recordingExercise(exercises)?.exercise_id, "barbell_squat");
  assert.equal(
    recordingExercise(exercises.slice(0, 1))?.exercise_id,
    "bench_press",
  );
  assert.equal(recordingExercise([]), undefined);
  assert.equal(nextCaptureSet("barbell_squat", []), 1);
  assert.equal(
    nextCaptureSet("barbell_squat", [
      {
        exercise_id: "barbell_squat",
        set_index: 1,
        completed_reps: 5,
        entry_source: "manual",
      },
      {
        exercise_id: "barbell_squat",
        set_index: 2,
        completed_reps: null,
        entry_source: "video",
      },
      {
        exercise_id: "bench_press",
        set_index: 3,
        completed_reps: 8,
        entry_source: "manual",
      },
    ]),
    3,
  );
});


test("history labels route completed, saved, processing and failed sets through existing identity-safe paths", () => {
 const set={id:"one",session_id:"session",exercise_id:"barbell_squat",set_index:3,target_reps:8,load_kg:40,reported_rpe:7,has_video:true,has_analysis:false,processing_status:"FAILED"};
 const failed=historyRecordingAction(set,"plan");assert.equal(failed.label,"Replace recording and retry");assert.equal(failed.href,retryRecordingHref(set,"plan"));
 assert.deepEqual(historyRecordingAction({...set,processing_status:"COMPLETED",has_analysis:true}),{href:"/analysis/one",label:"View analysis"});
 assert.deepEqual(historyRecordingAction({...set,processing_status:"SAVED",analysis_requested:false}),{href:"/recordings/one",label:"Watch video"});
 assert.equal(historyRecordingAction({...set,processing_status:"ANALYZING"}).label,"View processing status");
 for (const guard of [{is_sample:true},{entry_source:"demo"},{has_analysis:true}]) {
   assert.equal(historyRecordingAction({...set,...guard}).href,"/analysis/one");
 }
});
