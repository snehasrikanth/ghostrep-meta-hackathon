"use client";

import { AppShell } from "@/components/layout/AppShell";
import { WeekGrid } from "@/components/program/WeekGrid";
import { TrainingStructure } from "@/components/program/TrainingStructure";
import { CaptureEntry } from "@/components/workout/CaptureEntry";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { buttonClass } from "@/lib/buttonStyles";
import { Card } from "@/components/ui/card";
import { localISODate, recordingDestination } from "@/lib/program";
import { sessionTypeLabel } from "@/lib/training";
import type { Program } from "@/lib/types";
import Link from "@/components/ui/Link";
import { useEffect, useState } from "react";

export default function ProgramPage() {
  const [program, setProgram] = useState<Program | null>(null);
  const [range, setRange] = useState<1 | 4>(1);
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const today = localISODate();
  useEffect(() => {
    let cancelled = false;
    api
      .getProgram(today, range)
      .then((data) => {
        if (!cancelled) {
          setProgram(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error ? err.message : "Could not load your week.",
          );
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [today, range, retry]);
  const next = program?.weeks[0]?.days.find(
    (day) => day.is_next && !day.is_preview,
  );
  const inProgress =
    next?.session_status === "active" || next?.session_status === "paused";
  const video = program ? recordingDestination(program) : null;
  const proposalNoun = program?.proposal_kind === "session" ? "session" : "week";
  const mainHref = next?.plan_id
    ? `/workouts/${next.plan_id}`
    : program?.proposal_id
      ? `/workouts/${program.proposal_id}`
      : program?.is_accepted
        ? "#sessions"
        : "/onboarding";
  return (
    <AppShell>
      <p className="text-sm font-medium text-teal">My plan</p>
      <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">
        Your week, at a glance.
      </h1>
      <p className="mt-3 text-base leading-7 text-white/85">
        This is the week. Today’s workout is the next labeled session.
      </p>
      {program && (
        <div className="mt-5">
          <TrainingStructure
            split={program.split}
            count={program.days_per_week}
            accepted={program.is_accepted}
          />
        </div>
      )}
      {program && (
        <section
          className="mt-5 rounded-3xl border border-white/15 bg-card/90 p-5 sm:p-6"
          aria-label="Next step"
        >
          <p className="text-sm font-medium text-teal">
            {inProgress
              ? "Unfinished workout"
              : next
                ? "Next workout"
                : program.proposal_id
                  ? (program.proposal_kind === "session" ? "Session awaiting review" : "Week awaiting review")
                  : program.is_accepted
                    ? "Choose your next session"
                    : "Start with your profile"}
          </p>
          <h2 className="mt-2 text-xl font-semibold">
            {next?.workout?.name ||
              (program.proposal_id
                ? ("Your proposed " + proposalNoun + " is saved.")
                : program.is_accepted
                  ? "Pick the session that fits today."
                  : "Build a week around your preferences.")}
          </h2>
          <p className="mt-2 text-sm leading-6 text-white/85">
            {inProgress
              ? "Your logged sets are saved. Continue this workout before switching plans."
              : next
                ? `Focus: ${sessionTypeLabel(next.workout?.session_type) || next.workout?.name}. Open the warm-up and working sets.`
                : program.proposal_id
                  ? ("Review the proposed " + proposalNoun + ", then activate it.")
                  : program.is_accepted
                    ? "Pick a session’s focus, then start that workout."
                    : "Complete your profile, then review a week before training."}
          </p>
          <Link href={mainHref} className={buttonClass("primary", "mt-4")}>
            {inProgress
              ? "Continue unfinished workout"
              : next
                ? "Open next workout"
                : program.proposal_id
                  ? ("Review proposed " + proposalNoun)
                  : program.is_accepted
                    ? "Choose a session"
                    : "Complete my profile"}
          </Link>
        </section>
      )}
      {program?.is_accepted && program.proposal_id && next && (
        <Card className="mt-4 flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <p className="text-sm font-medium text-teal">
              New {proposalNoun} awaiting review
            </p>
            <p className="mt-1 text-sm leading-6 text-white/80">
              Your active plan and logged sets stay saved until you accept the
              new {proposalNoun}.
            </p>
          </div>
          <Link
            href={`/workouts/${program.proposal_id}`}
            className={buttonClass("secondary")}
          >
            Review saved proposal
          </Link>
        </Card>
      )}
      {video && <CaptureEntry {...video} />}
      <div
        className="mt-8 flex flex-wrap items-center justify-between gap-3"
        id="sessions"
      >
        <h2 className="text-xl font-medium">Sessions and recovery</h2>
        <div
          className="inline-flex rounded-full border border-white/15 p-1"
          aria-label="Plan time range"
        >
          {([1, 4] as const).map((value) => (
            <button
              type="button"
              key={value}
              aria-pressed={range === value}
              disabled={!loaded}
              className={`min-h-11 rounded-full px-4 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal ${range === value ? "bg-white/15 text-white" : "text-white/80 hover:bg-white/5"}`}
              onClick={() => {
                if (value !== range) {
                  setRange(value);
                  setLoaded(false);
                }
              }}
            >
              {value === 1 ? "This week" : "4 weeks"}
            </button>
          ))}
        </div>
      </div>
      {!loaded && (
        <p role="status" className="mt-4 text-sm text-teal">
          Loading {range === 1 ? "this week" : "four weeks"}…
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
      {loaded && program && !error && (
        <div className="mt-5 space-y-8" aria-live="polite">
          {program.placement_note && (
            <details className="rounded-2xl border border-white/15 p-4">
              <summary className="flex min-h-11 cursor-pointer items-center text-sm font-medium">
                How your training days are placed
              </summary>
              <p className="mt-3 text-sm leading-6 text-white/85">
                {program.placement_note}
              </p>
            </details>
          )}
          {program.weeks.map((week) => (
            <section key={week.start}>
              <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                <h3 className="text-lg font-medium">{week.label}</h3>
                {week.is_repeat && (
                  <p className="text-sm text-white/80">
                    Repeats your accepted training structure.
                  </p>
                )}
              </div>
              <WeekGrid week={week} />
            </section>
          ))}
        </div>
      )}
    </AppShell>
  );
}
