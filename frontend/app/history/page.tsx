"use client";

import { AppShell } from "@/components/layout/AppShell";
import { Card } from "@/components/ui/card";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { buttonClass } from "@/lib/buttonStyles";
import { historyRecordingAction } from "@/lib/capture";
import {
  STATUS_LABEL,
  exerciseResults,
  formatLoad,
  sessionTypeLabel,
  unitFromProfile,
  isTimedExercise,
  isSampleSet,
  type WeightUnit,
} from "@/lib/training";
import type { Session } from "@/lib/types";
import Link from "@/components/ui/Link";
import { useEffect, useState } from "react";

export default function HistoryPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [unit, setUnit] = useState<WeightUnit>("kg");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.listSessions(), api.getProfile().catch(() => null)])
      .then(([list, profile]) => {
        if (cancelled) return;
        setSessions(list.sessions);
        setUnit(unitFromProfile(profile));
        setError(null);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Could not load history.",
          );
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [retry]);

  const open = sessions.filter(
    (s) => s.status === "active" || s.status === "paused",
  );
  const past = sessions.filter(
    (s) => s.status === "completed" || s.status === "abandoned" || s.status === "sample",
  );

  return (
    <AppShell>
      <p className="text-sm font-medium text-teal">Progress</p>
      <h1 className="mt-2 text-3xl font-semibold">Training history</h1>
      <p className="mt-2 text-base leading-7 text-white/85">
        Your logged sets, saved videos, and movement analyses in one place.
      </p>
      {!loaded && (
        <p role="status" className="mt-4 text-sm text-teal">
          Loading your progress…
        </p>
      )}
      {error && (
        <div className="mt-4">
          <ActionFeedback kind="error">
            <p>{error}</p>
            <Button
              variant="secondary"
              className="mt-2"
              onClick={() => {
                setLoaded(false);
                setRetry((n) => n + 1);
              }}
            >
              Try again
            </Button>
          </ActionFeedback>
        </div>
      )}

      {open.map((session) => (
        <Card
          key={session.id}
          className="mt-6 flex flex-wrap items-center justify-between gap-3 border-amber/30 p-5"
        >
          <div>
            <p className="text-sm font-medium text-amber">Unfinished workout</p>
            <p className="mt-1 text-base font-medium">
              {session.plan_name || "Video training"}
            </p>
            <p className="mt-1 text-sm text-white/80">
              {sessionTypeLabel(session.session_type)
                ? `${sessionTypeLabel(session.session_type)} · `
                : ""}
              {STATUS_LABEL[session.status]} · {session.summary.completed_sets}{" "}
              {session.summary.completed_sets === 1 ? "set" : "sets"} saved
            </p>
          </div>
          <Link
            href={
              session.plan_id
                ? `/workouts/${session.plan_id}`
                : `/record?session=${session.id}`
            }
            className={buttonClass("primary")}
          >
            Continue workout
          </Link>
          {session.sets.some((set) => set.entry_source !== "manual") && (
            <div className="w-full space-y-2 border-t border-white/10 pt-3">
              {session.sets
                .filter((set) => set.entry_source !== "manual")
                .map((set) => (
                  <Link
                    key={set.id}
                    href={historyRecordingAction(set, session.plan_id).href}
                    className="flex min-h-11 items-center justify-between gap-3 rounded-xl bg-black/30 px-3 py-3 text-sm"
                  >
                    <span>
                      {set.exercise_name || "Exercise"}
                      {set.set_index ? ` · set ${set.set_index}` : ""}
                    </span>
                    <span className="font-medium text-teal">
                      {historyRecordingAction(set, session.plan_id).label}
                    </span>
                  </Link>
                ))}
            </div>
          )}
        </Card>
      ))}

      <div className="mt-6 space-y-3">
        {loaded && past.length === 0 && !error && (
          <p className="text-white/80">No finished workouts yet.</p>
        )}
        {past.map((session) => (
          <SessionCard key={session.id} session={session} unit={unit} />
        ))}
      </div>
    </AppShell>
  );
}

function SessionCard({
  session,
  unit,
}: {
  session: Session;
  unit: WeightUnit;
}) {
  const results = exerciseResults(session);
  const recordings = session.sets.filter(
    (set) => set.entry_source !== "manual",
  );
  return (
    <Card className="p-5">
      <div className="flex flex-wrap justify-between gap-3">
        <div>
          <p className="font-medium">{session.sample_only ? "Illustrative sample" : session.plan_name || "Video training"}</p>
          <p className="text-sm text-white/80">
            {new Date(
              session.completed_at || session.started_at || "",
            ).toLocaleString()}{" "}
            · {session.sample_only ? "Practice only · not performed training" : STATUS_LABEL[session.status]}
            {sessionTypeLabel(session.session_type)
              ? ` · ${sessionTypeLabel(session.session_type)}`
              : ""}
          </p>
        </div>
        <p className="font-mono text-sm text-white/80">
          {session.summary.completed_sets}
          {session.summary.planned_sets
            ? `/${session.summary.planned_sets}`
            : ""}{" "}
          sets · {session.summary.total_reps} reps
          {session.summary.timed_seconds
            ? ` · ${session.summary.timed_seconds}s holds`
            : ""}
        </p>
      </div>
      {results.length > 0 && (
        <ul className="mt-3 grid gap-1 text-sm text-white/80 sm:grid-cols-2">
          {results.map((row) => (
            <li key={row.exercise_id}>
              {row.name}: {row.sets} × {Math.round(row.reps / row.sets)}
              {row.measure === "seconds" ? "s" : ""}
              {row.best_load_kg != null
                ? ` · top ${formatLoad(row.best_load_kg, unit)}`
                : ""}
            </li>
          ))}
        </ul>
      )}
      {recordings.length > 0 && (
        <div className="mt-3 space-y-2">
          {recordings.map((set) => (
            <Link
              key={set.id}
              href={historyRecordingAction(set, session.plan_id).href}
              className="block min-h-11 rounded-2xl bg-black/30 p-3 text-sm"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <span>
                  {isSampleSet(set)
                    ? "Labeled sample analysis"
                    : `${set.exercise_name || "Exercise"}${set.set_index ? ` · set ${set.set_index}` : ""}`}
                </span>
                <span className="font-mono text-sm text-teal">
                  {historyRecordingAction(set, session.plan_id).label}
                </span>
              </div>
              <p className="text-white/80">
                {isSampleSet(set) ? `${set.completed_reps ?? 0} illustrative reps · excluded from training` : set.completed_reps == null
                  ? "Video saved · set not logged"
                  : `${set.completed_reps}${isTimedExercise(set.exercise_id) ? "s" : " reps"} ${set.analysis_requested === false ? "logged" : "counted"}`}
                {set.load_kg != null
                  ? ` · ${formatLoad(set.load_kg, unit)}`
                  : ""}
              </p>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}
