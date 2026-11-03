import type { Profile, RecordedSet, Session, WorkoutPlan } from "./types";

export type WeightUnit = "kg" | "lb";

const LB_PER_KG = 1 / 0.45359237;

export function unitFromProfile(profile: Profile | null | undefined): WeightUnit {
  return profile?.assessment?.identity?.preferred_weight_unit === "lb" ? "lb" : "kg";
}

export function displayLoad(kg: number, unit: WeightUnit): number {
  const value = unit === "lb" ? kg * LB_PER_KG : kg;
  return Math.round(value * 10) / 10;
}

export function formatLoad(kg: number | null | undefined, unit: WeightUnit): string {
  if (kg == null) return "—";
  return `${displayLoad(kg, unit)} ${unit}`;
}

export function loadToKg(value: number, unit: WeightUnit): number {
  return unit === "lb" ? Math.round(value * 0.45359237 * 100) / 100 : value;
}

export function formatVolume(kg: number, unit: WeightUnit): string {
  return `${Math.round(displayLoad(kg, unit)).toLocaleString("en-US")} ${unit}`;
}

/** Where "Start Training" should go for this athlete right now. */
export function sessionForPlan(planId: string, current: Session | null | undefined, sessions: Session[]): Session | null {
  if (current?.plan_id === planId) return current;
  const forPlan = sessions.filter((row) => row.plan_id === planId);
  return (
    forPlan.find((row) => row.status === "completed") ||
    forPlan.find((row) => row.status === "abandoned") ||
    forPlan[0] ||
    null
  );
}

export function startDestination(state: {
  hasProfile: boolean;
  current: Pick<Session, "id" | "plan_id"> | null;
  next: Pick<WorkoutPlan, "id"> | null;
}): string {
  if (!state.hasProfile) return "/onboarding";
  if (state.current?.plan_id) return `/workouts/${state.current.plan_id}`;
  if (state.current) return `/record?session=${state.current.id}`;
  if (state.next) return `/workouts/${state.next.id}`;
  return "/dashboard?plan=next";
}

export const TIMED_EXERCISES = new Set(["plank"]);

export function isTimedExercise(exerciseId: string): boolean {
  return TIMED_EXERCISES.has(exerciseId);
}

export function exerciseDisplayName(exerciseId: string, name?: string | null): string {
  const trimmed = (name || "").trim();
  if (trimmed && trimmed !== exerciseId) return trimmed;
  return exerciseId ? exerciseId.replaceAll("_", " ") : "Unknown exercise";
}

export function formatExerciseDose(
  exercise: {
    exercise_id: string;
    sets: number;
    target_reps: number;
    suggested_load_kg?: number | null;
    measure?: "reps" | "seconds" | string | null;
  },
  unit: WeightUnit,
): string {
  const timed = exercise.measure === "seconds" || isTimedExercise(exercise.exercise_id);
  const dose = timed ? `${exercise.sets} × ${exercise.target_reps}s` : `${exercise.sets} × ${exercise.target_reps}`;
  if (exercise.suggested_load_kg == null) return dose;
  return `${dose} @ ${formatLoad(exercise.suggested_load_kg, unit)}`;
}

export function isDoneSet(set: RecordedSet): boolean {
  if (isSampleSet(set)) return false;
  if ((set.completed_reps ?? 0) <= 0) return false;
  return set.entry_source === "manual" || ["COMPLETED", "SAVED"].includes(set.processing_status);
}

export type ExerciseResult = {
  exercise_id: string;
  name: string;
  sets: number;
  reps: number;
  best_load_kg: number | null;
  volume_kg: number;
  measure: "reps" | "seconds";
};

export function exerciseResults(session: Session): ExerciseResult[] {
  const byExercise = new Map<string, ExerciseResult>();
  for (const set of session.sets.filter(isDoneSet)) {
    const row = byExercise.get(set.exercise_id) || {
      exercise_id: set.exercise_id,
      name: set.exercise_name || set.exercise_id.replaceAll("_", " "),
      sets: 0,
      reps: 0,
      best_load_kg: null,
      volume_kg: 0,
      measure: isTimedExercise(set.exercise_id) ? "seconds" : "reps",
    };
    row.sets += 1;
    row.reps += set.completed_reps ?? 0;
    if (set.load_kg != null) row.best_load_kg = Math.max(row.best_load_kg ?? 0, set.load_kg);
    if (row.measure === "reps") row.volume_kg += (set.load_kg ?? 0) * (set.completed_reps ?? 0);
    byExercise.set(set.exercise_id, row);
  }
  return [...byExercise.values()];
}

export type Comparison = {
  exercise_id: string;
  name: string;
  best_load_change_kg: number | null;
  volume_change_kg: number;
  reps_change: number;
  previous_date: string | null;
};

/** Compare the latest completed session with the last earlier one that trained the same exercise. */
export function compareWithPrevious(sessions: Session[]): Comparison[] {
  const completed = sessions
    .filter((session) => session.status === "completed" && session.sets.some(isDoneSet))
    .sort((a, b) => (b.completed_at || "").localeCompare(a.completed_at || ""));
  const [latest, ...earlier] = completed;
  if (!latest) return [];
  const results: Comparison[] = [];
  for (const current of exerciseResults(latest).filter((row) => row.measure === "reps")) {
    const previousSession = earlier.find((session) => exerciseResults(session).some((row) => row.exercise_id === current.exercise_id));
    if (!previousSession) continue;
    const previous = exerciseResults(previousSession).find((row) => row.exercise_id === current.exercise_id)!;
    results.push({
      exercise_id: current.exercise_id,
      name: current.name,
      best_load_change_kg:
        current.best_load_kg != null && previous.best_load_kg != null ? current.best_load_kg - previous.best_load_kg : null,
      volume_change_kg: current.volume_kg - previous.volume_kg,
      reps_change: current.reps - previous.reps,
      previous_date: previousSession.completed_at,
    });
  }
  return results;
}

export function formatClock(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export const STATUS_LABEL: Record<string, string> = {
  active: "In progress",
  paused: "Paused",
  completed: "Completed",
  abandoned: "Ended early",
  proposed: "Proposed workout",
  discarded: "Discarded proposal",
  replaced: "Replaced",
  sample: "Sample practice",
};

export function isSampleSet(set: RecordedSet): boolean {
  return set.is_sample === true || set.entry_source === "demo";
}

export function realSquatAnalyses(sessions: Session[]): RecordedSet[] {
  const rows: RecordedSet[] = [];
  for (const session of sessions) {
    for (const set of session.sets) {
      if (set.exercise_id !== "barbell_squat") continue;
      if (isSampleSet(set)) continue;
      if (set.entry_source !== "video") continue;
      if (set.processing_status !== "COMPLETED") continue;
      if ((set.completed_reps ?? 0) <= 0) continue;
      rows.push(set);
    }
  }
  return rows.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
}

export function latestRealSquat(sessions: Session[]): RecordedSet | null {
  return realSquatAnalyses(sessions)[0] || null;
}

export type SquatRecordingComparison = {
  current: RecordedSet;
  previous: RecordedSet;
};

/** Measured values from two real squat recordings. Does not imply a coaching cause. */
export function compareSquatRecordings(sessions: Session[]): SquatRecordingComparison | null {
  const [current, previous] = realSquatAnalyses(sessions);
  if (!current || !previous) return null;
  return { current, previous };
}

const SESSION_LABEL: Record<string, string> = {
  full_body_a: "Full body · squat focus",
  full_body_b: "Full body · hinge focus",
  lower: "Lower body",
  upper: "Upper body",
  legs: "Legs",
  push: "Push",
  pull: "Pull",
};

export function sessionTypeLabel(type: string | null | undefined): string | null {
  return type ? SESSION_LABEL[type] || type.replaceAll("_", " ") : null;
}
