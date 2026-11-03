"use client";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { ExercisePreview } from "@/components/program/ExercisePreview";
import { TrainingStructure } from "@/components/program/TrainingStructure";
import { WhyThisWorkout } from "@/components/workout/WhyThisWorkout";
import { Warmup } from "@/components/workout/Warmup";
import { buttonClass } from "@/lib/buttonStyles";
import { planStructure } from "@/lib/program";
import { sessionTypeLabel, type WeightUnit } from "@/lib/training";
import type { WorkoutPlan } from "@/lib/types";
import Link from "@/components/ui/Link";
import { useState } from "react";

export type WorkoutBlock = {
  message: string;
  planId: string | null;
  sessionId?: string | null;
};

export function ProposalReview({
  plan,
  unit,
  busy,
  pendingAction,
  error,
  blocked,
  onAccept,
  onDiscard,
}: {
  plan: WorkoutPlan;
  unit: WeightUnit;
  busy: boolean;
  pendingAction?: string | null;
  error: string | null;
  blocked: WorkoutBlock | null;
  onAccept: () => void;
  onDiscard: () => void;
}) {
  const structure = planStructure(plan);
  const [index, setIndex] = useState(structure.session_index);
  const sessions = plan.schedule?.length
    ? plan.schedule
    : [
        {
          workout_name: plan.name,
          session_type: plan.session_type,
          duration_minutes: plan.duration_minutes,
          estimated_minutes: plan.estimated_minutes,
          rationale: plan.rationale,
          warmup: plan.warmup,
          exercises: plan.exercises,
        },
      ];
  const selected = sessions[index] || sessions[0];
  const exercises = selected.exercises?.length
    ? selected.exercises
    : plan.exercises;
  const sessionProposal = structure.proposal_kind === "session";
  const continueHref = blocked?.planId
    ? `/workouts/${blocked.planId}`
    : blocked?.sessionId
      ? `/record?session=${blocked.sessionId}`
      : "/start";
  const acceptLabel = sessionProposal ? "Use this session" : "Use this plan";
  return (
    <AppShell>
      <div className={blocked ? "pb-[28rem] sm:pb-72" : "pb-44"}>
        <p className="text-sm font-medium text-teal">
          {sessionProposal
            ? "Choose your next workout"
            : "Step 2 · Review your week"}
        </p>
        <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">
          {sessionProposal
            ? "A session from your saved week."
            : "Here’s your training week."}
        </h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-white/85">
          {sessionProposal
            ? "Check the focus and exercises, then make this your next workout."
            : "Preview each session’s focus, then activate the week."}
        </p>
        <div className="mt-5">
          <TrainingStructure
            split={structure.split}
            count={structure.sessions_per_week}
          />
        </div>
        {(plan.source === "fixture" || plan.source === "local") && (
          <p className="mt-3 text-sm text-white/80">
            {plan.source === "fixture"
              ? "Saved sample plan · illustrative results."
              : "Built from your saved preferences with the basic planner."}
          </p>
        )}
        <div className="mt-7 grid min-w-0 gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
          <aside className="min-w-0">
            <h2 className="mb-3 text-base font-medium">Your sessions</h2>
            <div
              className="flex w-full min-w-0 gap-2 overflow-x-auto pb-1 sm:grid sm:grid-cols-2 lg:grid-cols-1"
              aria-label="Sessions in your week"
            >
              {sessions.map((session, i) => (
                <button
                  type="button"
                  key={i}
                  onClick={() => setIndex(i)}
                  aria-pressed={index === i}
                  className={`min-h-24 min-w-[12.5rem] shrink-0 scroll-mb-44 rounded-2xl border p-4 text-left transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal sm:min-w-0 ${index === i ? "border-teal/60 bg-teal/10" : "border-white/15 bg-card/70 hover:border-white/35"}`}
                >
                  <span className="flex items-center justify-between gap-2 text-sm text-teal">
                    <span>Session {i + 1}</span>
                    {i === structure.session_index && (
                      <span className="text-sm font-medium text-white">
                        Starts here
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block text-base font-medium">
                    {sessionTypeLabel(session.session_type) ||
                      session.workout_name}
                  </span>
                  <span className="mt-1 block text-sm text-white/80">
                    ~{session.estimated_minutes || session.duration_minutes} min
                    · {session.exercises?.length || plan.exercises.length}{" "}
                    exercises
                  </span>
                </button>
              ))}
            </div>
            <p className="mt-3 text-sm leading-6 text-white/80">
              Previewing a session doesn’t change your starting workout. First
              up:{" "}
              <span className="font-medium text-white">{plan.name}</span>.
            </p>
            <WhyThisWorkout why={plan.why} explanation={plan.notes} unit={unit} />
          </aside>
          <section aria-label="Selected session" aria-live="polite">
            <p className="text-sm font-medium text-teal">
              Session {index + 1} ·{" "}
              {sessionTypeLabel(selected.session_type) || "Training focus"}
            </p>
            <h2 className="mt-2 text-2xl font-semibold">
              {selected.workout_name}
            </h2>
            {selected.rationale && (
              <details className="mt-3 rounded-2xl border border-white/10 p-4">
                <summary className="flex min-h-11 cursor-pointer items-center text-sm font-medium text-white">
                  Why this session?
                </summary>
                <p className="mt-2 text-sm leading-7 text-white/85">
                  {selected.rationale}
                </p>
              </details>
            )}
            <Warmup
              steps={selected.warmup}
              mainLift={
                exercises[0]?.name ||
                exercises[0]?.exercise_id.replaceAll("_", " ")
              }
            />
            <div className="mt-4 space-y-3">
              {exercises.map((exercise, i) => (
                <ExercisePreview
                  key={`${i}-${exercise.exercise_id}`}
                  exercise={exercise}
                  index={i}
                  unit={unit}
                />
              ))}
            </div>
          </section>
        </div>
        {!!plan.warnings?.length && (
          <details className="mt-5 rounded-2xl border border-amber/25 p-4 text-sm">
            <summary className="flex min-h-11 cursor-pointer items-center font-medium text-amber">
              Good to know
            </summary>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-white/85">
              {plan.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </details>
        )}
        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-white/15 bg-[#07090c]/95 px-5 py-4 backdrop-blur-xl">
          <div className="mx-auto max-w-6xl">
            <div className="mb-3 space-y-2">
              {blocked && (
                <ActionFeedback kind="blocked">
                  <p className="font-medium">
                    An unfinished workout is blocking this plan.
                  </p>
                  <p>{blocked.message}</p>
                  <p className="mt-1">
                    This proposal stays saved. Finish or end the open workout,
                    then come back to activate it.
                  </p>
                  <Link
                    href={continueHref}
                    className={buttonClass("primary", "mt-3")}
                  >
                    Continue unfinished workout
                  </Link>
                </ActionFeedback>
              )}
              {error && (
                <ActionFeedback kind="error">
                  {error} Your proposal is still saved. Try again when you’re
                  ready.
                </ActionFeedback>
              )}
              {busy && (
                <ActionFeedback kind="loading">
                  {pendingAction === "discard"
                    ? "Discarding this proposal. Your active workout will stay saved."
                    : "Activating your plan. Your logged workouts stay in your history."}
                </ActionFeedback>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant={blocked ? "secondary" : "primary"}
                loading={busy && pendingAction !== "discard"}
                loadingLabel="Activating…"
                disabled={busy}
                onClick={onAccept}
              >
                {acceptLabel}
              </Button>
              <Button
                variant="ghost"
                loading={busy && pendingAction === "discard"}
                loadingLabel="Discarding…"
                disabled={busy}
                onClick={onDiscard}
              >
                Discard proposal
              </Button>
              {!blocked && (
                <p className="text-sm text-white/80">
                  {sessionProposal
                    ? "Your weekly structure stays the same."
                    : "Next: start your first workout."}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
