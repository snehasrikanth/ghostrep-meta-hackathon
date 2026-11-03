"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  displayLoad,
  exerciseDisplayName,
  formatExerciseDose,
  formatLoad,
  isDoneSet,
  isSampleSet,
  loadToKg,
  type WeightUnit,
} from "@/lib/training";
import type { RecordedSet, WorkoutExercise } from "@/lib/types";
import { ExerciseDemo } from "@/components/workout/ExerciseDemo";
import { Check, Video } from "lucide-react";
import Link from "@/components/ui/Link";
import { useState } from "react";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { recordingHref, canRetryRecording, retryRecordingHref } from "@/lib/capture";

const inputClass =
  "min-h-11 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-3 font-mono text-sm text-white outline-none focus:border-teal/60";

type Props = {
  index: number;
  exercise: WorkoutExercise;
  sets: RecordedSet[];
  unit: WeightUnit;
  open: boolean;
  onLog: (
    setIndex: number,
    loadKg: number | null,
    reps: number,
  ) => Promise<void>;
  onDelete: (setId: string) => Promise<void>;
};

export function ExerciseLog({
  index,
  exercise,
  sets,
  unit,
  open,
  onLog,
  onDelete,
}: Props) {
  const manual = sets.filter((set) => !isSampleSet(set));
  const videos = sets.filter(
    (set) => set.entry_source !== "manual" && set.set_index == null,
  );
  const highest = Math.max(0, ...manual.map((set) => set.set_index || 0));
  const [extra, setExtra] = useState(0);
  const rows = Math.max(exercise.sets, highest) + extra;
  const seconds = exercise.measure === "seconds";
  const done = sets.filter(isDoneSet).length;
  const nextSet = Array.from({ length: rows }, (_, i) => i + 1).find(
    (i) => !manual.some((set) => set.set_index === i && isDoneSet(set)),
  );

  return (
    <Card id={`exercise-${exercise.exercise_id}`} className="scroll-mt-24 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-sm uppercase text-white/80">
            {String(index + 1).padStart(2, "0")}
          </p>
          <div className="flex flex-wrap items-center gap-x-3">
          <h3 className="exercise-title text-xl font-medium">
            {exerciseDisplayName(exercise.exercise_id, exercise.name)}
          </h3>
          <ExerciseDemo exerciseId={exercise.exercise_id} />
          </div>
          {exercise.notes && (
            <p className="mt-1 max-w-xl text-sm leading-6 text-white/80">
              {exercise.notes}
            </p>
          )}
          {exercise.video_analysis && (
            <p className="mt-2 text-sm font-medium text-teal">
              Video coaching available
            </p>
          )}
        </div>
        <div className="text-right font-mono text-sm text-white/80">
          {formatExerciseDose(exercise, unit)}
          <div className="text-white/80">{exercise.rest_seconds}s rest</div>
          <div
            className={
              done >= exercise.sets ? "mt-1 text-teal" : "mt-1 text-white/80"
            }
          >
            {done}/{exercise.sets} sets done
          </div>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {open || manual.length > 0 ? (
          <div className="grid grid-cols-[2.75rem_minmax(0,1fr)_minmax(0,1fr)] gap-2 px-1 font-mono text-sm uppercase text-white/80 sm:grid-cols-[2.75rem_1fr_1fr_auto]">
            <span>Set</span>
            <span>Load ({unit})</span>
            <span>{seconds ? "Seconds" : "Reps"}</span>
            <span className="sr-only">Action</span>
          </div>
        ) : (
          <p className="px-1 text-sm text-white/80">No sets logged.</p>
        )}
        {Array.from({ length: rows }, (_, i) => i + 1).map((setIndex) => {
          const saved =
            manual.find((set) => set.set_index === setIndex) || null;
          const logged = saved && isDoneSet(saved) ? saved : null;
          if (!open && !saved) return null;
          const previous = manual.find((set) => set.set_index === setIndex - 1);
          return (
            <SetRow
              key={`${setIndex}-${logged?.id || "new"}-${logged?.completed_reps ?? ""}-${logged?.load_kg ?? ""}`}
              setIndex={setIndex}
              primary={setIndex === nextSet}
              logged={logged}
              defaultLoadKg={
                saved?.load_kg ??
                previous?.load_kg ??
                exercise.suggested_load_kg
              }
              defaultReps={
                !open && saved && !logged
                  ? ""
                  : (logged?.completed_reps ?? exercise.target_reps)
              }
              unit={unit}
              open={open}
              seconds={seconds}
              label={`${exercise.name || exercise.exercise_id} set ${setIndex}`}
              onLog={onLog}
              onDelete={onDelete}
              recording={
                saved &&
                saved.entry_source !== "manual" &&
                (saved.has_video ||
                  saved.analysis_requested !== false ||
                  saved.processing_status !== "SAVED")
                  ? saved
                  : null
              }
            />
          );
        })}
        {open && (
          <button
            type="button"
            className="inline-flex min-h-11 items-center px-1 text-sm font-medium text-teal hover:underline"
            onClick={() => setExtra((value) => value + 1)}
          >
            + Add a set
          </button>
        )}
      </div>

      {videos.length > 0 && (
        <div className="mt-4 rounded-2xl border border-teal/15 bg-teal/5 p-3">
          <p className="flex items-center gap-2 text-sm text-white/85">
            <Video className="h-4 w-4 text-teal" aria-hidden />
            Your set videos
          </p>
          {videos.map((set) => (
            <Link
              key={set.id}
              href={canRetryRecording(set) ? retryRecordingHref(set) : recordingHref(set)}
              className="mt-2 flex justify-between gap-3 rounded-xl bg-black/30 px-3 py-3 text-sm"
            >
              <span>
                {set.entry_source === "demo"
                  ? "Labeled sample"
                  : "Recorded set"}
                {set.set_index ? ` ${set.set_index}` : ""}
                {set.load_kg != null
                  ? ` · ${formatLoad(set.load_kg, unit)}`
                  : ""}
                {set.completed_reps != null
                  ? ` · ${set.completed_reps}${seconds ? "s" : " reps"}${set.analysis_requested !== false ? " counted" : " logged"}`
                  : ""}
              </span>
              <span className="font-mono text-sm text-teal">
                {set.analysis_requested === false &&
                set.processing_status === "SAVED"
                  ? set.has_video
                    ? "Watch video"
                    : "Video removed"
                  : set.processing_status === "COMPLETED"
                    ? "View analysis"
                    : set.processing_status.toLowerCase().replaceAll("_", " ")}
              </span>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

function SetRow({
  setIndex,
  primary,
  logged,
  defaultLoadKg,
  defaultReps,
  unit,
  open,
  seconds,
  label,
  onLog,
  onDelete,
  recording,
}: {
  setIndex: number;
  primary: boolean;
  logged: RecordedSet | null;
  defaultLoadKg: number | null | undefined;
  defaultReps: number | string;
  unit: WeightUnit;
  open: boolean;
  seconds: boolean;
  label: string;
  onLog: Props["onLog"];
  onDelete: Props["onDelete"];
  recording: RecordedSet | null;
}) {
  const [load, setLoad] = useState(
    defaultLoadKg != null ? String(displayLoad(defaultLoadKg, unit)) : "",
  );
  const [reps, setReps] = useState(String(defaultReps));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);

  async function submit() {
    const repCount = Number(reps);
    const loadValue = load.trim() === "" ? null : Number(load);
    if (!Number.isInteger(repCount) || repCount < 0 || repCount > 200) {
      setError(
        seconds
          ? "Enter a whole number of seconds."
          : "Enter a whole number of reps.",
      );
      return;
    }
    if (loadValue != null && (!Number.isFinite(loadValue) || loadValue < 0)) {
      setError("Enter a valid load, or leave it blank for bodyweight.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await onLog(
        setIndex,
        loadValue == null ? null : loadToKg(loadValue, unit),
        repCount,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this set.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!logged) return;
    setRemoving(true);
    setError(null);
    try {
      await onDelete(logged.id);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not remove this set. Your saved entry is unchanged.",
      );
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div>
      <div className="grid grid-cols-[2.75rem_minmax(0,1fr)_minmax(0,1fr)] items-center gap-2 sm:grid-cols-[2.75rem_1fr_1fr_auto]">
        <span className="flex h-11 w-11 items-center justify-center rounded-full border border-white/10 font-mono text-sm text-white/80">
          {logged ? (
            <Check className="h-4 w-4 text-teal" aria-label="Logged" />
          ) : (
            setIndex
          )}
        </span>
        <input
          aria-label={`${label} load in ${unit}`}
          inputMode="decimal"
          className={inputClass}
          placeholder="Optional"
          value={load}
          disabled={!open || busy || removing}
          onChange={(event) => setLoad(event.target.value)}
        />
        <input
          aria-label={seconds ? `${label} seconds` : `${label} reps`}
          inputMode="numeric"
          className={inputClass}
          value={reps}
          disabled={!open || busy || removing}
          onChange={(event) => setReps(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && submit()}
        />
        {open ? (
          <div className="col-span-2 col-start-2 flex gap-2 sm:col-auto sm:col-span-1">
            <Button
              variant={!logged && primary ? "primary" : "secondary"}
              className="px-4 py-2"
              aria-label={`${logged ? "Update" : "Log"} ${label}`}
              loading={busy}
              loadingLabel="Saving…"
              disabled={busy || removing}
              onClick={submit}
            >
              {logged ? "Update" : "Log set"}
            </Button>
            {logged && !recording && (
              <Button
                variant="ghost"
                className="px-3 py-2"
                aria-label={`Remove ${label}`}
                loading={removing}
                loadingLabel="Removing…"
                disabled={busy || removing}
                onClick={remove}
              >
                ×
              </Button>
            )}
          </div>
        ) : (
          <span className="w-16" />
        )}
      </div>
      {recording && (
        <Link
          href={canRetryRecording(recording) ? retryRecordingHref(recording) : recordingHref(recording)}
          className="ml-12 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-teal"
        >
          <Video className="h-4 w-4" aria-hidden />
          {canRetryRecording(recording) ? "Replace recording and retry" : recording.processing_status === "SAVED"
            ? "Watch set video"
            : recording.processing_status === "COMPLETED"
              ? "View analysis"
              : "View recording"}
        </Link>
      )}
      {logged && !error && !busy && (
        <p role="status" className="mt-1 pl-12 text-sm text-teal">
          Set {setIndex} saved
        </p>
      )}
      {error && (
        <div className="mt-2 pl-12">
          <ActionFeedback kind="error">{error}</ActionFeedback>
        </div>
      )}
    </div>
  );
}
