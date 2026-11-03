export type CaptureMode = "camera" | "upload";

export function recordingExercise<T extends { exercise_id: string }>(
  exercises: T[],
): T | undefined {
  return (
    exercises.find((item) => item.exercise_id === "barbell_squat") ||
    exercises[0]
  );
}

export function nextCaptureSet(
  exerciseId: string,
  sets: {
    exercise_id: string;
    set_index: number | null;
    completed_reps?: number | null;
    entry_source?: string;
    is_sample?: boolean;
  }[],
): number {
  const recorded = sets.filter(
    (item) =>
      item.exercise_id === exerciseId &&
      !item.is_sample && item.entry_source !== "demo" &&
      ((item.completed_reps || 0) > 0 || item.entry_source !== "manual"),
  );
  const used = new Set(recorded.map((item) => item.set_index));
  let index = 1;
  while (used.has(index) && index < 100) index += 1;
  return index;
}

export function captureHref(
  options: {
    mode?: CaptureMode;
    planId?: string | null;
    sessionId?: string | null;
    exerciseId?: string | null;
    setIndex?: number | null;
    targetReps?: number | null;
    loadKg?: number | null;
  } = {},
): string {
  const query = new URLSearchParams({ mode: options.mode || "camera" });
  if (options.planId) query.set("plan", options.planId);
  if (options.sessionId) query.set("session", options.sessionId);
  if (options.exerciseId) query.set("exercise", options.exerciseId);
  if (options.setIndex != null) query.set("set", String(options.setIndex));
  if (options.targetReps != null) query.set("reps", String(options.targetReps));
  if (options.loadKg != null) query.set("load", String(options.loadKg));
  return `/record?${query}`;
}

export function recordingHref(set: {
  id: string;
  analysis_requested?: boolean;
}): string {
  return set.analysis_requested === false
    ? `/recordings/${set.id}`
    : `/analysis/${set.id}`;
}

export function canRetryRecording(set: { processing_status: string; has_analysis?: boolean; is_sample?: boolean; entry_source?: string }): boolean {
  return set.processing_status === "FAILED" && set.has_analysis === false && !set.is_sample && set.entry_source !== "demo";
}

export function retryRecordingHref(set: {
  id: string; session_id: string; exercise_id: string; set_index: number | null;
  target_reps: number | null; load_kg: number | null; reported_rpe: number | null;
}, planId?: string | null): string {
  const href = captureHref({ mode: "upload", sessionId: set.session_id, exerciseId: set.exercise_id,
    setIndex: set.set_index, targetReps: set.target_reps, loadKg: set.load_kg, planId });
  const query = new URLSearchParams({ retry: set.id });
  if (set.reported_rpe != null) query.set("effort", String(set.reported_rpe));
  return `${href}&${query}`;
}

/** History uses the same eligibility gate and exact-set retry URL as recording. */
export function historyRecordingAction(set: Parameters<typeof retryRecordingHref>[0] & {
  processing_status: string; has_analysis?: boolean; has_video: boolean;
  analysis_requested?: boolean; is_sample?: boolean; entry_source?: string;
}, planId?: string | null): { href: string; label: string } {
  if (canRetryRecording(set)) return {href: retryRecordingHref(set, planId), label: "Replace recording and retry"};
  if (set.has_analysis && set.processing_status === "COMPLETED") return {href: `/analysis/${set.id}`, label: "View analysis"};
  if (set.analysis_requested === false) return {href: `/recordings/${set.id}`, label: set.has_video ? "Watch video" : "Video removed"};
  return {href: `/analysis/${set.id}`, label: set.processing_status === "FAILED" ? "View processing issue" : set.processing_status === "COMPLETED" ? "View analysis" : "View processing status"};
}

export function supportsAnalysis(exerciseId: string): boolean {
  return exerciseId === "barbell_squat";
}

export function recordingMimeType(
  supports: (mime: string) => boolean,
): string | undefined {
  return [
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/mp4",
    "video/webm",
  ].find(supports);
}
