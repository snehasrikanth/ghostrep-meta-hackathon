"use client";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ExerciseLog } from "@/components/workout/ExerciseLog";
import { ExerciseDemo } from "@/components/workout/ExerciseDemo";
import { CaptureEntry } from "@/components/workout/CaptureEntry";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { TrainingStructure } from "@/components/program/TrainingStructure";
import { planStructure } from "@/lib/program";
import { buttonClass } from "@/lib/buttonStyles";
import { ProposalReview } from "@/components/workout/ProposalReview";
import { Warmup } from "@/components/workout/Warmup";
import { TrainingConsent } from "@/components/workout/TrainingConsent";
import { captureHref, nextCaptureSet, recordingExercise } from "@/lib/capture";
import { RestTimer, type RestState } from "@/components/workout/RestTimer";
import { useRestTimer } from "@/lib/useRestTimer";
import { ApiError, api } from "@/lib/api";
import {
  STATUS_LABEL,
  compareWithPrevious,
  exerciseResults,
  formatClock,
  exerciseDisplayName,
  formatExerciseDose,
  formatLoad,
  formatVolume,
  isDoneSet,
  sessionForPlan,
  sessionTypeLabel,
  unitFromProfile,
  type WeightUnit,
} from "@/lib/training";
import type { Session, WorkoutPlan } from "@/lib/types";
import Link from "@/components/ui/Link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const TERMINAL = new Set(["COMPLETED", "FAILED", "LOGGED", "SAVED"]);

async function fetchWorkout(planId: string) {
  const [plan, current, sessions, profile] = await Promise.all([
    api.getWorkout(planId),
    api.currentSession(),
    api.listSessions(),
    api.getProfile().catch(() => null),
  ]);
  const session = sessionForPlan(planId, current.session, sessions.sessions);
  return {
    plan,
    session,
    history: sessions.sessions,
    unit: unitFromProfile(profile),
  };
}

function restFor(label: string, seconds: number): RestState {
  return { label, endsAt: Date.now() + seconds * 1000, total: seconds };
}

export default function WorkoutPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [plan, setPlan] = useState<WorkoutPlan | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [history, setHistory] = useState<Session[]>([]);
  const [unit, setUnit] = useState<WeightUnit>("kg");
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<{
    message: string;
    planId: string | null;
    sessionId?: string | null;
  } | null>(null);
  const [rest, setRest] = useRestTimer(session?.id, session?.status, session?.paused_at);
  const [confirm, setConfirm] = useState<"complete" | "abandon" | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [justAccepted, setJustAccepted] = useState(false);
  const [planConsent, setPlanConsent] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchWorkout(params.id)
      .then((data) => {
        if (cancelled) return;
        setError(null);
        setBlocked(null);
        setNotice(
          new URLSearchParams(window.location.search).has("recorded")
            ? "Video saved to your set. You can replay it below or continue training."
            : null,
        );
        setJustAccepted(false);
        setPlan(data.plan);
        setSession(data.session);
        setHistory(data.history);
        setUnit(data.unit);
      })
      .catch(
        (err) =>
          !cancelled &&
          setError(
            err instanceof Error ? err.message : "Could not load this workout.",
          ),
      );
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  const processing =
    session?.sets.some((set) => !TERMINAL.has(set.processing_status)) ?? false;
  useEffect(() => {
    if (!session || !processing) return;
    const timer = window.setInterval(() => {
      api
        .getSession(session.id)
        .then(setSession)
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [session, processing]);

  const open = session?.status === "active" || session?.status === "paused";

  async function run<T>(action: () => Promise<T>, actionName = "update") {
    setError(null);
    setNotice(null);
    setPendingAction(actionName);
    setBlocked(null);
    setBusy(true);
    try {
      return await action();
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.detail &&
        typeof err.detail === "object" &&
        "open_plan_id" in err.detail
      ) {
        setBlocked({
          message: err.message,
          planId: (err.detail as { open_plan_id: string | null }).open_plan_id,
          sessionId: (err.detail as { open_session_id?: string })
            .open_session_id,
        });
      } else {
        setError(err instanceof Error ? err.message : "Something went wrong.");
      }
    } finally {
      setBusy(false);
      setPendingAction(null);
    }
  }

  async function start() {
    const started = await run(() => api.startSession(params.id), "start");
    if (started) {
      setSession(started);
      setNotice("Workout started. Log your first set below.");
    }
  }

  async function capture(mode: "camera" | "upload") {
    if (!plan) return;
    const exercise = recordingExercise(plan.exercises);
    if (!exercise) return;
    const active =
      open && session
        ? session.status === "paused"
          ? await run(() => api.resumeSession(session.id), "capture")
          : session
        : await run(() => api.startSession(plan.id), "capture");
    if (!active) return;
    setSession(active);
    router.push(
      captureHref({
        mode,
        planId: plan.id,
        sessionId: active.id,
        exerciseId: exercise.exercise_id,
        setIndex: nextCaptureSet(exercise.exercise_id, active.sets),
        targetReps: exercise.target_reps,
        loadKg: exercise.suggested_load_kg,
      }),
    );
  }

  async function logSet(
    exerciseId: string,
    setIndex: number,
    loadKg: number | null,
    reps: number,
  ) {
    if (!session || !plan) return;
    const wasDone = session.sets.some(item => item.exercise_id === exerciseId && item.set_index === setIndex && isDoneSet(item));
    const exercise = plan.exercises.find(
      (item) => item.exercise_id === exerciseId,
    )!;
    await api.logSet(session.id, {
      exercise_id: exerciseId,
      set_index: setIndex,
      completed_reps: reps,
      load_kg: loadKg,
      target_reps: exercise.target_reps,
    });
    setSession(await api.getSession(session.id));
    setNotice(null);
    if (reps > 0 && !wasDone) {
      setRest(restFor(exercise.name || exerciseId, exercise.rest_seconds));
    }
  }

  async function deleteSet(setId: string) {
    if (!session) return;
    await api.deleteSet(session.id, setId);
    setSession(await api.getSession(session.id));
  }

  async function togglePause() {
    if (!session) return;
    const next = await run(
      () =>
        session.status === "paused"
          ? api.resumeSession(session.id)
          : api.pauseSession(session.id),
      "pause",
    );
    if (next) {
      setSession(next);
      setNotice(
        next.status === "paused"
          ? "Workout paused. Your logged sets are saved."
          : "Workout resumed. Continue with your next set.",
      );
    }
  }

  async function finish(kind: "complete" | "abandon") {
    if (!session) return;
    const next = await run(
      () =>
        kind === "complete"
          ? api.completeSession(session.id)
          : api.abandonSession(session.id),
      kind,
    );
    setConfirm(null);
    if (!next) return;
    setRest(null);
    if (kind === "abandon") {
      router.push("/dashboard");
      return;
    }
    setSession(next);
    const [loadedPlan, sessions] = await Promise.all([
      api.getWorkout(params.id),
      api.listSessions(),
    ]);
    setPlan(loadedPlan);
    setHistory(sessions.sessions);
  }

  async function bumpReps(index: number, delta: number) {
    if (!plan) return;
    const exercises = plan.exercises.map((ex, i) => ({
      exercise_id: ex.exercise_id,
      sets: ex.sets,
      target_reps:
        i === index ? Math.max(1, ex.target_reps + delta) : ex.target_reps,
      rest_seconds: ex.rest_seconds,
      suggested_load_kg: ex.suggested_load_kg,
      notes: ex.notes,
    }));
    const updated = await run(() => api.patchWorkout(plan.id, { exercises }));
    if (updated) {
      setPlan(updated);
      setNotice("Your target is saved.");
    }
  }

  async function planNext() {
    if (!planConsent) {
      setError("Agree to share your training details to build a new plan.");
      return;
    }
    const next = await run(() => api.generateWorkout(true));
    if (next) router.push(`/workouts/${next.id}`);
  }

  async function acceptProposal() {
    if (!plan) return;
    const accepted = await run(() => api.acceptWorkout(plan.id), "accept");
    if (accepted) {
      setPlan(accepted);
      setJustAccepted(true);
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  }

  async function discardProposal() {
    if (!plan) return;
    const result = await run(() => api.discardWorkout(plan.id), "discard");
    if (!result) return;
    if (result.plan) router.push(`/workouts/${result.plan.id}`);
    else router.push("/program");
  }

  if (error && !plan)
    return (
      <AppShell>
        <ActionFeedback kind="error">{error}</ActionFeedback>
      </AppShell>
    );
  if (!plan || plan.id !== params.id)
    return (
      <AppShell>
        <p role="status" className="text-white/85">
          Loading workout…
        </p>
      </AppShell>
    );
  if (plan.status === "proposed") {
    return (
      <ProposalReview
        plan={plan}
        unit={unit}
        busy={busy}
        pendingAction={pendingAction}
        error={error}
        blocked={blocked}
        onAccept={acceptProposal}
        onDiscard={discardProposal}
      />
    );
  }

  const plannedSets = plan.exercises.reduce((sum, ex) => sum + ex.sets, 0);
  const doneSets = session?.sets.filter(isDoneSet).length ?? 0;
  const typeLabel = sessionTypeLabel(plan.session_type);
  const videoExercise = recordingExercise(plan.exercises);

  return (
    <AppShell>
      <div className={rest ? "pb-24" : undefined}>
        <Link
          href="/program"
          className="mb-4 inline-flex min-h-11 items-center text-sm font-medium text-teal"
        >
          ← My weekly plan
        </Link>
        <TrainingStructure
          split={planStructure(plan).split}
          count={planStructure(plan).sessions_per_week}
          accepted
          compact
        />
        <p className="mt-6 text-sm font-medium text-teal">
          {session
            ? STATUS_LABEL[session.status]
            : plan.status === "active"
              ? "Your next workout"
              : "Workout history"}{" "}
          · Session {planStructure(plan).session_index + 1} of{" "}
          {planStructure(plan).sessions_per_week}
        </p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-semibold">{plan.name}</h1>
            <p className="mt-2 text-base text-white/85">
              Session focus:{" "}
              <strong className="font-medium text-white">
                {typeLabel || "Personalized training"}
              </strong>
            </p>
          </div>
          <div className="text-sm text-white/80">
            <p>
              About {plan.estimated_minutes || plan.duration_minutes} minutes
            </p>
            {session && (
              <p>
                {doneSets}/{plannedSets} sets logged
              </p>
            )}
            {session?.started_at && open && (
              <Elapsed
                since={session.started_at}
                paused={session.status === "paused"}
              />
            )}
          </div>
        </div>
        {plan.status === "active" && (!session || open) && videoExercise && (
          <CaptureEntry
            sticky
            exerciseName={
              videoExercise.name ||
              exerciseDisplayName(videoExercise.exercise_id)
            }
            canCoach={Boolean(videoExercise.video_analysis)}
            onRecord={() => void capture("camera")}
            disabled={busy || processing}
            loading={pendingAction === "capture"}
          />
        )}
        {!session && plan.status === "active" && (
          <Card className="mt-5 border-teal/30 p-5">
            <ActionFeedback kind="success">
              <p className="font-semibold">
                {justAccepted
                  ? planStructure(plan).proposal_kind === "session"
                    ? "This session is now your next workout."
                    : "Your weekly plan is now active."
                  : "Active plan · ready when you are."}
              </p>
              <p>
                Next up: {typeLabel || plan.name}. Start this workout to begin
                logging sets.
              </p>
            </ActionFeedback>
            <div className="mt-4 space-y-3">
              {error && <ActionFeedback kind="error">{error}</ActionFeedback>}
              {blocked && (
                <ActionFeedback kind="blocked">
                  <p className="font-medium">
                    An unfinished workout needs your attention.
                  </p>
                  <p>{blocked.message}</p>
                  <Link
                    href={
                      blocked.planId
                        ? `/workouts/${blocked.planId}`
                        : `/record?session=${blocked.sessionId || ""}`
                    }
                    className={buttonClass("primary", "mt-3")}
                  >
                    Continue unfinished workout
                  </Link>
                </ActionFeedback>
              )}
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <Button
                variant={blocked ? "secondary" : "primary"}
                loading={pendingAction === "start"}
                loadingLabel="Starting workout…"
                disabled={busy}
                onClick={start}
              >
                Start this workout
              </Button>
              <Link href="/program" className={buttonClass("secondary")}>
                View my week
              </Link>
            </div>
          </Card>
        )}
        {!session && plan.status !== "active" && (
          <Card className="mt-6 p-4 text-sm text-white/80">
            {plan.status === "replaced"
              ? "A newer plan replaced this one before it was started."
              : "This workout is finished."}{" "}
            <Link href="/start" className="text-teal hover:underline">
              Go to your next workout
            </Link>
          </Card>
        )}

        {open && session && (
          <Card className="mt-5 p-4 sm:p-5">
            <div className="flex flex-wrap items-center gap-3">
              {session.status === "paused" ? (
                <Button
                  loading={pendingAction === "pause"}
                  loadingLabel="Resuming…"
                  disabled={busy}
                  onClick={togglePause}
                >
                  Resume workout
                </Button>
              ) : (
                <>
                  <Button
                    variant={doneSets >= plannedSets ? "primary" : "secondary"}
                    disabled={busy || processing || doneSets === 0}
                    onClick={() => setConfirm("complete")}
                  >
                    Finish workout
                  </Button>
                  <Button
                    variant="secondary"
                    loading={pendingAction === "pause"}
                    loadingLabel="Pausing…"
                    disabled={busy}
                    onClick={togglePause}
                  >
                    Pause
                  </Button>
                </>
              )}
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => setConfirm("abandon")}
              >
                End workout early
              </Button>
            </div>
            <div className="mt-3 space-y-2">
              {session.status === "paused" && (
                <p className="text-sm text-white/85">
                  Paused · Your {doneSets} logged{" "}
                  {doneSets === 1 ? "set is" : "sets are"} saved. Resume when
                  you’re ready.
                </p>
              )}
              {notice && (
                <ActionFeedback kind="success">{notice}</ActionFeedback>
              )}
              {error && <ActionFeedback kind="error">{error}</ActionFeedback>}
              {processing && (
                <ActionFeedback kind="loading">
                  Your recording is being analyzed. You can finish the workout
                  when it’s ready.
                </ActionFeedback>
              )}
              {!processing && !notice && session.status === "active" && (
                <p className="text-sm text-white/80">
                  Log your working sets below. Use Record workout above for your
                  video check-in.
                </p>
              )}
              {doneSets === 0 && (
                <p className="text-sm text-white/80">
                  Finish workout becomes available after your first logged set.
                </p>
              )}
            </div>
          </Card>
        )}
        {(!session || open) && (
          <Warmup
            steps={plan.warmup}
            mainLift={plan.exercises[0]?.name}
            expanded
          />
        )}
        {plan.rationale && (
          <details className="mt-4 rounded-2xl border border-white/15 p-4">
            <summary className="flex min-h-11 cursor-pointer items-center text-sm font-medium">
              Why this workout?
            </summary>
            <p className="mt-3 text-sm leading-7 text-white/85">
              {plan.rationale}
            </p>
          </details>
        )}

        {confirm && session && (
          <Card className="mt-3 p-4">
            {confirm === "complete" ? (
              <>
                <p className="font-medium">
                  {doneSets === 0
                    ? "Log at least one set before completing."
                    : doneSets < plannedSets
                      ? `You logged ${doneSets} of ${plannedSets} planned sets. Complete with what you did?`
                      : `All ${plannedSets} planned sets are logged. Complete this workout?`}
                </p>
                <div className="mt-3 flex gap-2">
                  <Button
                    loading={pendingAction === "complete"}
                    loadingLabel="Finishing…"
                    disabled={busy || doneSets === 0}
                    onClick={() => finish("complete")}
                  >
                    Complete
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirm(null)}>
                    Keep training
                  </Button>
                </div>
              </>
            ) : (
              <>
                <p className="font-medium">
                  End this workout early? Logged sets stay in history, marked as
                  ended early.
                </p>
                <div className="mt-3 flex gap-2">
                  <Button
                    variant="amber"
                    loading={pendingAction === "abandon"}
                    loadingLabel="Ending workout…"
                    disabled={busy}
                    onClick={() => finish("abandon")}
                  >
                    End workout
                  </Button>
                  <Button variant="ghost" onClick={() => setConfirm(null)}>
                    Keep training
                  </Button>
                </div>
              </>
            )}
          </Card>
        )}

        {session?.status === "completed" && (
          <>
            <CompletedSummary session={session} history={history} unit={unit} />
            <details className="mt-5 rounded-2xl border border-white/15 p-5">
              <summary className="flex min-h-11 cursor-pointer items-center text-sm font-medium">
                Build a different week
              </summary>
              <TrainingConsent
                checked={planConsent}
                onChange={setPlanConsent}
                disabled={busy}
              />
              <Button
                className="mt-4"
                variant="secondary"
                loading={busy}
                loadingLabel="Building your week…"
                disabled={!planConsent || busy}
                onClick={planNext}
              >
                Build a new week
              </Button>
              {error && (
                <div className="mt-3">
                  <ActionFeedback kind="error">{error}</ActionFeedback>
                </div>
              )}
            </details>
          </>
        )}

        <div className="mt-6 space-y-3">
          {plan.exercises.map((ex, index) =>
            session ? (
              <ExerciseLog
                key={ex.id}
                index={index}
                exercise={ex}
                sets={session.sets.filter(
                  (set) => set.exercise_id === ex.exercise_id,
                )}
                unit={unit}
                open={session.status === "active"}
                onLog={(setIndex, loadKg, reps) =>
                  logSet(ex.exercise_id, setIndex, loadKg, reps)
                }
                onDelete={deleteSet}
              />
            ) : (
              <PlannedExercise
                key={ex.id}
                index={index}
                exercise={ex}
                unit={unit}
                editable={plan.status === "active"}
                onBump={bumpReps}
              />
            ),
          )}
        </div>
      </div>
      <RestTimer key={rest?.endsAt ?? "idle"} rest={rest} onChange={setRest} />
    </AppShell>
  );
}

function Elapsed({ since, paused }: { since: string; paused: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (paused) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [paused]);
  const start = new Date(
    since.endsWith("Z") || since.includes("+") ? since : `${since}Z`,
  ).getTime();
  return (
    <p>{paused ? "Paused" : `${formatClock((now - start) / 1000)} elapsed`}</p>
  );
}

function PlannedExercise({
  index,
  exercise,
  unit,
  editable,
  onBump,
}: {
  index: number;
  exercise: WorkoutPlan["exercises"][number];
  unit: WeightUnit;
  editable: boolean;
  onBump: (index: number, delta: number) => void;
}) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-sm uppercase text-white/75">
            {String(index + 1).padStart(2, "0")}
          </p>
          <div className="flex flex-wrap items-center gap-x-3">
          <h3 className="text-xl font-medium">
            {exerciseDisplayName(exercise.exercise_id, exercise.name)}
          </h3>
          <ExerciseDemo exerciseId={exercise.exercise_id} />
          </div>
          <p className="mt-1 text-sm leading-6 text-white/80">
            {exercise.notes}
          </p>
          {exercise.video_analysis && (
            <p className="mt-2 text-sm font-medium text-teal">
              Video coaching available
            </p>
          )}
        </div>
        <div className="text-right font-mono text-sm text-white/80">
          {formatExerciseDose(exercise, unit)}
          <div className="text-white/80">{exercise.rest_seconds}s rest</div>
          {editable && (
            <div className="mt-2 flex justify-end gap-2">
              <Button
                variant="ghost"
                aria-label={
                  exercise.measure === "seconds"
                    ? `Shorter hold for ${exercise.name}`
                    : `Fewer reps for ${exercise.name}`
                }
                onClick={() => onBump(index, -1)}
              >
                {exercise.measure === "seconds" ? "- sec" : "- reps"}
              </Button>
              <Button
                variant="ghost"
                aria-label={
                  exercise.measure === "seconds"
                    ? `Longer hold for ${exercise.name}`
                    : `More reps for ${exercise.name}`
                }
                onClick={() => onBump(index, 1)}
              >
                {exercise.measure === "seconds" ? "+ sec" : "+ reps"}
              </Button>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function CompletedSummary({
  session,
  history,
  unit,
}: {
  session: Session;
  history: Session[];
  unit: WeightUnit;
}) {
  const results = exerciseResults(session);
  const upToThis = history.filter(
    (row) => (row.completed_at || "") <= (session.completed_at || ""),
  );
  const comparisons = compareWithPrevious(
    upToThis.some((row) => row.id === session.id)
      ? upToThis
      : [session, ...upToThis],
  );
  return (
    <Card className="mt-6 border-teal/25 p-5">
      <p className="font-mono text-sm uppercase tracking-[0.2em] text-teal">
        Workout complete
      </p>
      <p className="mt-2 text-lg">
        {session.summary.completed_sets} sets · {session.summary.total_reps}{" "}
        reps
        {session.summary.timed_seconds
          ? ` · ${session.summary.timed_seconds}s holds`
          : ""}
        {session.summary.volume_kg > 0
          ? ` · ${formatVolume(session.summary.volume_kg, unit)} total volume`
          : ""}
      </p>
      <ul className="mt-3 space-y-1 text-sm text-white/80">
        {results.map((row) => (
          <li key={row.exercise_id}>
            {row.name}: {row.sets} {row.sets === 1 ? "set" : "sets"}, {row.reps}{" "}
            {row.measure === "seconds" ? "sec" : "reps"}
            {row.best_load_kg != null
              ? `, top set ${formatLoad(row.best_load_kg, unit)}`
              : ""}
          </li>
        ))}
      </ul>
      {comparisons.length > 0 && (
        <div className="mt-4 text-sm">
          <p className="text-white/80">Compared with your last time</p>
          <ul className="mt-1 space-y-1">
            {comparisons.map((row) => (
              <li key={row.exercise_id} className="text-white/80">
                {row.name}:{" "}
                {row.best_load_change_kg != null &&
                row.best_load_change_kg !== 0
                  ? `top set ${row.best_load_change_kg > 0 ? "+" : "−"}${formatLoad(Math.abs(row.best_load_change_kg), unit)}, `
                  : ""}
                {row.reps_change >= 0 ? "+" : "−"}
                {Math.abs(row.reps_change)} reps
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href="/history" className={buttonClass("primary")}>
          Review my progress
        </Link>
        <Link href="/program" className={buttonClass("secondary")}>
          Choose my next session
        </Link>
      </div>
    </Card>
  );
}
