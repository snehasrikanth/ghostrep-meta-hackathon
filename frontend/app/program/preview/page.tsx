"use client";

import { AppShell } from "@/components/layout/AppShell";
import { ExercisePreview } from "@/components/program/ExercisePreview";
import { Button } from "@/components/ui/button";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { Card } from "@/components/ui/card";
import { Warmup } from "@/components/workout/Warmup";
import { api } from "@/lib/api";
import { buttonClass } from "@/lib/buttonStyles";
import { findDay, localISODate } from "@/lib/program";
import {
  sessionTypeLabel,
  unitFromProfile,
  type WeightUnit,
} from "@/lib/training";
import type { Program, ProgramDay } from "@/lib/types";
import Link from "@/components/ui/Link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

function PreviewInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const weekIndex = Number(params.get("week") || 0);
  const weekday = params.get("day") || "";
  const [day, setDay] = useState<ProgramDay | null>(null);
  const [unit, setUnit] = useState<WeightUnit>("kg");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.getProgram(localISODate(), 4),
      api.getProfile().catch(() => null),
    ])
      .then(
        ([program, profile]: [
          Program,
          Awaited<ReturnType<typeof api.getProfile>> | null,
        ]) => {
          if (cancelled) return;
          setDay(findDay(program.weeks, weekIndex, weekday));
          setUnit(unitFromProfile(profile));
          setLoaded(true);
        },
      )
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load this preview.",
          );
          setLoaded(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [weekIndex, weekday]);

  async function useSession() {
    setBusy(true);
    setError(null);
    try {
      const plan = await api.prepareSession(localISODate(), weekIndex, weekday);
      router.push(`/workouts/${plan.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not prepare this session.",
      );
      setBusy(false);
    }
  }

  const workout = day?.workout;
  const focus = sessionTypeLabel(workout?.session_type);
  const inProgress =
    day?.session_status === "active" || day?.session_status === "paused";
  const saved = Boolean(day && !day.is_preview && day.plan_id);
  const primaryLabel = inProgress
    ? "Continue this workout"
    : saved
      ? "Open this workout"
      : "Review this session";

  return (
    <AppShell>
      <Link
        href="/program"
        className="mb-3 inline-flex min-h-11 items-center text-sm font-medium text-teal hover:underline"
      >
        ← Back to program
      </Link>
      {!loaded && (
        <p role="status" className="text-sm text-teal">
          Loading preview…
        </p>
      )}
      {error && !workout && (
        <div className="mt-3">
          <ActionFeedback kind="error">{error}</ActionFeedback>
        </div>
      )}
      {loaded && !day && !error && (
        <p className="text-sm text-white/80">
          That day is not in this training week.
        </p>
      )}
      {day?.kind === "recovery" && (
        <Card className="mt-4 p-6">
          <p className="text-sm font-medium text-teal">{day.weekday_label}</p>
          <h1 className="mt-2 text-3xl font-semibold">Recovery day</h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-white/85">
            {day.recovery_copy}
          </p>
        </Card>
      )}
      {workout && (
        <>
          <p className="text-sm font-medium text-teal">
            {day?.is_preview ? "Workout preview" : "Saved workout"} ·{" "}
            {day?.weekday_label}
            {focus ? ` · ${focus}` : ""}
          </p>
          <h1 className="mt-2 text-3xl font-semibold">{workout.name}</h1>
          <p className="mt-2 text-base text-white/85">
            Session focus:{" "}
            <strong className="font-medium text-white">
              {focus || "Personalized training"}
            </strong>
            {workout.estimated_minutes
              ? ` · ~${workout.estimated_minutes} of ${workout.duration_minutes} min`
              : ` · ${workout.duration_minutes} min target`}
          </p>
          <p className="mt-3 text-base leading-7 text-white/85">
            {inProgress
              ? "Logged sets are saved. Continue this workout."
              : "Review the exercises, then choose this as your next workout."}
          </p>
          {(workout.notes ||
            workout.rationale ||
            day?.detail_note ||
            day?.placement_note) && (
            <details className="mt-4 rounded-2xl border border-white/15 p-4">
              <summary className="flex min-h-11 cursor-pointer items-center text-sm font-medium">
                Why this session?
              </summary>
              <p className="mt-3 text-sm leading-7 text-white/85">
                {workout.rationale ||
                  workout.notes ||
                  day?.detail_note ||
                  day?.placement_note}
              </p>
            </details>
          )}
          <Button
            className="mt-5"
            loading={busy}
            loadingLabel="Preparing your review…"
            disabled={busy}
            onClick={useSession}
          >
            {primaryLabel}
          </Button>
          {busy && (
            <div className="mt-3">
              <ActionFeedback kind="loading">
                Preparing a saved proposal. Your active workout stays unchanged.
              </ActionFeedback>
            </div>
          )}
          {error && (
            <div className="mt-3">
              <ActionFeedback kind="error">{error}</ActionFeedback>
            </div>
          )}
          <Warmup
            steps={workout.warmup}
            mainLift={workout.exercises[0]?.name}
          />
          <div className="mt-6 space-y-3">
            {workout.exercises.map((exercise, index) => (
              <ExercisePreview
                key={exercise.id || `${exercise.exercise_id}-${index}`}
                exercise={exercise}
                index={index}
                unit={unit}
              />
            ))}
          </div>
        </>
      )}
      <div className="mt-8">
        <Link href="/program" className={buttonClass("secondary")}>
          Back to program
        </Link>
      </div>
    </AppShell>
  );
}

export default function PreviewPage() {
  return (
    <Suspense>
      <PreviewInner />
    </Suspense>
  );
}
