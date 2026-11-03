"use client";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import {
  exerciseDisplayName,
  formatExerciseDose,
  sessionTypeLabel,
  unitFromProfile,
} from "@/lib/training";
import type { SavedLiveWorkout } from "@/lib/types";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function SavedLiveWorkoutPage() {
  const router = useRouter();
  const [saved, setSaved] = useState<SavedLiveWorkout | null>(null);
  const [unit, setUnit] = useState<"kg" | "lb">("kg");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([api.getSavedLiveWorkout(), api.getProfile()]).then(
      ([week, profile]) => {
        if (week.status === "fulfilled") setSaved(week.value);
        else
          setError(
            week.reason instanceof Error
              ? week.reason.message
              : "Could not load the saved week.",
          );
        if (profile.status === "fulfilled")
          setUnit(unitFromProfile(profile.value));
      },
    );
  }, []);

  async function importSaved() {
    setBusy(true);
    setError(null);
    try {
      const plan = await api.importSavedWorkout();
      router.push(`/workouts/${plan.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not import the saved week.",
      );
      setBusy(false);
    }
  }

  if (!saved) {
    return (
      <AppShell>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">
          Saved plan
        </p>
        <h1 className="mt-2 text-3xl font-semibold">
          {error ? "Could not load" : "Loading…"}
        </h1>
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      </AppShell>
    );
  }

  if (!saved.available) {
    return (
      <AppShell>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">
          Saved plan
        </p>
        <h1 className="mt-2 text-3xl font-semibold">No saved plan available</h1>
        <p className="mt-3 max-w-xl text-sm text-white/55">
          {"Build a new plan from your training profile to get started."}
        </p>
        <Link
          href="/dashboard"
          className="mt-6 inline-block text-sm text-teal hover:underline"
        >
          Back to dashboard
        </Link>
      </AppShell>
    );
  }

  const days = saved.schedule?.length
    ? saved.schedule
    : [
        {
          workout_name: saved.name || "Workout",
          session_type: saved.session_type,
          duration_minutes: saved.duration_minutes || 0,
          exercises: saved.exercises,
        },
      ];

  return (
    <AppShell>
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">
        Saved training week
      </p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold">{saved.name}</h1>
          <p className="text-sm text-white/50">
            {[`${days.length} sessions`].filter(Boolean).join(" · ")}
          </p>
        </div>
      </div>
      {saved.notes && (
        <p className="mt-3 max-w-3xl text-sm text-white/55">{saved.notes}</p>
      )}
      <p className="mt-3 text-sm text-white/45">
        This is a previously generated training week. Review it against your
        current preferences before using it.
      </p>
      {(saved.warnings || []).length > 0 && (
        <Card className="mt-5 border-amber/30 p-4 text-sm text-amber">
          <p className="font-medium">Quality notes from the saved week</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {saved.warnings?.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Card>
      )}
      <div className="mt-6 space-y-6">
        {days.map((day, index) => (
          <section key={`${day.workout_name}-${index}`}>
            <div className="flex flex-wrap items-end justify-between gap-2">
              <h2 className="text-xl font-medium">{day.workout_name}</h2>
              <p className="text-sm text-white/45">
                {[
                  sessionTypeLabel(day.session_type),
                  day.estimated_minutes
                    ? `~${day.estimated_minutes} min`
                    : day.duration_minutes
                      ? `${day.duration_minutes} min`
                      : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
            <div className="mt-3 space-y-3">
              {(day.exercises || []).map((exercise, position) => (
                <Card
                  key={`${exercise.exercise_id}-${position}`}
                  className="p-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">
                        {exerciseDisplayName(
                          exercise.exercise_id,
                          exercise.name,
                        )}
                      </p>
                      {exercise.notes && (
                        <p className="mt-1 text-sm text-white/50">
                          {exercise.notes}
                        </p>
                      )}
                    </div>
                    <p className="font-mono text-sm text-white/70">
                      {formatExerciseDose(exercise, unit)}
                      <span className="block text-white/40">
                        {exercise.rest_seconds}s rest
                      </span>
                    </p>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
      <div className="mt-8 flex flex-wrap gap-3">
        <Button disabled={busy} onClick={() => void importSaved()}>
          {busy ? "Importing…" : "Import as a reviewable proposal"}
        </Button>
        <Link
          href="/dashboard"
          className="rounded-full px-5 py-2.5 text-sm text-white/70 hover:text-white"
        >
          Keep current workout
        </Link>
      </div>
      <p className="mt-3 max-w-xl text-xs text-white/40">
        Import copies this saved week into a proposal. It does not generate a
        new plan. Accepting later still requires an explicit review and will not
        replace an open workout with logged sets.
      </p>
    </AppShell>
  );
}
