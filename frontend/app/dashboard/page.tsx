"use client";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { TrainingConsent } from "@/components/workout/TrainingConsent";
import { WeekGrid } from "@/components/program/WeekGrid";
import { TrainingStructure } from "@/components/program/TrainingStructure";
import { ApiError, api } from "@/lib/api";
import { buttonClass } from "@/lib/buttonStyles";
import { captureHref } from "@/lib/capture";
import { localISODate, planStructure } from "@/lib/program";
import {
  STATUS_LABEL,
  formatLoad,
  isDoneSet,
  latestRealSquat,
  sessionTypeLabel,
  unitFromProfile,
} from "@/lib/training";
import type { Profile, Program, Session, WorkoutPlan } from "@/lib/types";
import { ArrowRight, Camera, Check, Clock3, Dumbbell } from "lucide-react";
import Link from "@/components/ui/Link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

export default function DashboardPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [missingProfile, setMissingProfile] = useState(false);
  const [next, setNext] = useState<WorkoutPlan | null>(null);
  const [proposal, setProposal] = useState<WorkoutPlan | null>(null);
  const [current, setCurrent] = useState<Session | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [program, setProgram] = useState<Program | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [p, n, proposed, c, s, week] = await Promise.allSettled([
      api.getProfile(),
      api.nextWorkout(),
      api.getProposal(),
      api.currentSession(),
      api.listSessions(),
      api.getProgram(localISODate(), 1),
    ]);
    if (p.status === "fulfilled") {
      setProfile(p.value);
      setMissingProfile(false);
    } else if (p.reason instanceof ApiError && p.reason.status === 404)
      setMissingProfile(true);
    if (n.status === "fulfilled") setNext(n.value.plan);
    if (proposed.status === "fulfilled") setProposal(proposed.value.plan);
    if (c.status === "fulfilled") setCurrent(c.value.session);
    if (s.status === "fulfilled") setSessions(s.value.sessions);
    if (week.status === "fulfilled") setProgram(week.value);
    setError(
      (p.status === "rejected" &&
        !(p.reason instanceof ApiError && p.reason.status === 404)) ||
        n.status === "rejected" ||
        c.status === "rejected"
        ? "Your training could not be fully loaded. Try again to see the latest saved state."
        : null,
    );
    setLoaded(true);
  }, []);
  useEffect(() => {
    queueMicrotask(() => {
      void load();
    });
  }, [load]);
  async function buildPlan() {
    if (!consent) return;
    setBusy(true);
    setBuildError(null);
    try {
      const plan = await api.generateWorkout(true);
      router.push(`/workouts/${plan.id}`);
    } catch (err) {
      setBuildError(
        err instanceof Error
          ? err.message
          : "Could not build your week. Your active plan is unchanged.",
      );
      setBusy(false);
    }
  }
  const unit = unitFromProfile(profile);
  const completed = sessions.filter((s) => s.status === "completed" && s.sets.some(isDoneSet));
  const recent = sessions
    .filter(
      (s) => !["active", "paused"].includes(s.status) && s.sets.some(isDoneSet),
    )
    .slice(0, 3);
  const analysis = latestRealSquat(sessions);
  const selectedId = current?.plan_id || next?.id;
  const squat = next?.exercises.find(
    (ex) => ex.exercise_id === "barbell_squat",
  );
  const accepted = Boolean(program?.is_accepted);
  const sessionProposal =
    proposal && planStructure(proposal).proposal_kind === "session";
  const mainHref = current
    ? current.plan_id
      ? `/workouts/${current.plan_id}`
      : `/record?session=${current.id}`
    : next
      ? `/workouts/${next.id}`
      : proposal
        ? `/workouts/${proposal.id}`
        : accepted
          ? "/program"
          : "/onboarding";
  const primaryLabel = current
    ? "Continue workout"
    : next
      ? "Open next workout"
      : proposal
        ? sessionProposal
          ? "Review my session"
          : "Review my week"
        : accepted
          ? "Choose my next session"
          : "Complete my profile";
  if (loaded && missingProfile)
    return (
      <AppShell>
        <div className="mx-auto max-w-2xl py-12">
          <Dumbbell className="h-10 w-10 text-teal" aria-hidden />
          <p className="mt-5 text-sm font-medium text-teal">
            Step 1 · Your training profile
          </p>
          <h1 className="mt-3 text-4xl font-semibold">
            Let’s build a week that fits you.
          </h1>
          <p className="mt-4 text-base leading-7 text-white/85">
            Choose your goal, schedule, and equipment. Next you’ll review your
            week, then start today’s workout.
          </p>
          <Link href="/onboarding" className={buttonClass("primary", "mt-6")}>
            Complete my profile
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </AppShell>
    );
  return (
    <AppShell>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-teal">Today</p>
          <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">
            {profile?.display_name
              ? `Welcome back, ${profile.display_name.split(" ")[0]}.`
              : "Your next step starts here."}
          </h1>
        </div>
        <p className="text-sm text-white/80">
          {new Date().toLocaleDateString(undefined, {
            weekday: "long",
            month: "short",
            day: "numeric",
          })}
        </p>
      </div>
      {!loaded && (
        <p role="status" className="mb-4 text-sm text-teal">
          Loading your saved training…
        </p>
      )}
      {error && (
        <div className="mb-4">
          <ActionFeedback kind="error">
            {error}
            <Button
              variant="secondary"
              className="ml-3"
              onClick={() => {
                setLoaded(false);
                void load();
              }}
            >
              Try again
            </Button>
          </ActionFeedback>
        </div>
      )}
      {program && (
        <TrainingStructure
          split={program.split}
          count={program.days_per_week}
          accepted={accepted}
          compact
        />
      )}
      <section
        className="mt-5 overflow-hidden rounded-3xl border border-white/15 bg-[radial-gradient(ellipse_at_top_right,rgba(32,214,199,0.10),transparent_70%)] p-6 sm:p-8"
        aria-label="Today's next step"
      >
        <div className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
          <div>
            <p className="text-sm font-medium text-teal">
              {current
                ? current.status === "paused"
                  ? "Today · paused workout"
                  : "Today · workout in progress"
                : next
                  ? "Today’s workout"
                  : proposal
                    ? "Your week is ready to review"
                    : accepted
                      ? "Today · choose a session"
                      : "Your training week"}
            </p>
            <h2 className="mt-3 max-w-2xl text-3xl font-semibold leading-tight">
              {current?.plan_name ||
                next?.name ||
                (proposal
                  ? "Review your sessions, then activate your plan."
                  : accepted
                    ? "Choose a session for today."
                    : "Start with your training preferences.")}
            </h2>
            <p className="mt-3 max-w-xl text-base leading-7 text-white/85">
              {current
                ? `${current.summary.completed_sets} ${current.summary.completed_sets === 1 ? "set is" : "sets are"} saved. Continue where you left off.`
                : next
                  ? `Session focus: ${sessionTypeLabel(next.session_type)}. Warm-up and working sets are ready.`
                  : proposal
                    ? "Your current workout and logged sets stay saved while you review."
                    : accepted
                      ? "Your weekly plan is active. Open My plan to pick the next session."
                      : "Tell us what fits your goal, schedule, and available equipment."}
            </p>
            {next && (
              <p className="mt-3 flex items-center gap-2 text-sm text-white/85">
                <Clock3 className="h-4 w-4" aria-hidden />
                About {next.estimated_minutes || next.duration_minutes} minutes
                · Session {planStructure(next).session_index + 1} of{" "}
                {planStructure(next).sessions_per_week}
              </p>
            )}
            {loaded && !error && (
              <div className="mt-6 flex flex-wrap gap-3">
                <Link href={mainHref} className={buttonClass("primary")}>
                  {primaryLabel}
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
                {(next || current) && (
                  <Link href="/program" className={buttonClass("secondary")}>
                    View my week
                  </Link>
                )}
              </div>
            )}
          </div>
          <div className="rounded-2xl border border-white/10 bg-black/20 p-5">
            <p className="text-sm font-medium text-teal">Today vs this week</p>
            <dl className="mt-4 space-y-4 text-sm text-white/85">
              <div>
                <dt className="font-medium text-white">Today</dt>
                <dd className="mt-1 leading-6">
                  {current
                    ? `${current.status === "paused" ? "Paused" : "In progress"} · ${current.summary.completed_sets} ${current.summary.completed_sets === 1 ? "set" : "sets"} saved`
                    : next
                      ? `${sessionTypeLabel(next.session_type) || next.name} · session ${planStructure(next).session_index + 1} of ${planStructure(next).sessions_per_week}`
                      : accepted
                        ? "Pick a session from your active week"
                        : "Build and review your week first"}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-white">This week</dt>
                <dd className="mt-1 leading-6">
                  {program
                    ? `${accepted ? "Active plan" : "Proposed plan"} · ${program.days_per_week} sessions`
                    : "Your weekly structure appears after you build a plan"}
                </dd>
              </div>
            </dl>
            {squat && (
              <Link
                href={captureHref({
                  planId: selectedId,
                  sessionId: current?.id,
                  exerciseId: "barbell_squat",
                })}
                className="mt-5 inline-flex min-h-11 items-center gap-2 text-sm font-medium text-teal"
              >
                <Camera className="h-4 w-4" aria-hidden />
                Record workout →
              </Link>
            )}
          </div>
        </div>
      </section>
      {proposal && (next || current) && (
        <Card className="mt-4 flex flex-wrap items-center justify-between gap-4 p-5">
          <div>
            <p className="text-sm font-medium text-teal">
              {sessionProposal
                ? "Session awaiting review"
                : "New week awaiting review"}
            </p>
            <p className="mt-1 text-base font-medium">{proposal.name}</p>
            <p className="mt-1 text-sm text-white/80">
              Your active workout is unchanged. The proposal stays saved.
            </p>
          </div>
          <Link
            href={`/workouts/${proposal.id}`}
            className={buttonClass("secondary")}
          >
            Review saved proposal
          </Link>
        </Card>
      )}
      {program && (
        <section className="mt-8">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-medium">Your weekly plan</h2>
              <p className="mt-1 text-sm text-white/80">
                Each card is one session’s focus. Today’s workout is labeled
                separately above.
              </p>
            </div>
            <Link
              href="/program"
              className="inline-flex min-h-11 items-center text-sm font-medium text-teal"
            >
              View full week →
            </Link>
          </div>
          <WeekGrid week={program.weeks[0]} compact />
        </section>
      )}
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {[
          { label: "Workouts completed", value: completed.length },
          {
            label: "Working sets logged",
            value: completed.reduce((n, s) => n + s.summary.completed_sets, 0),
          },
          {
            label: "Squat working weight",
            value: formatLoad(
              squat?.suggested_load_kg ?? profile?.current_squat_load_kg,
              unit,
            ),
          },
        ].map((item) => (
          <Card key={item.label} className="p-5">
            <p className="text-sm text-white/80">{item.label}</p>
            <p className="mt-2 text-3xl font-semibold">
              {loaded ? item.value : "—"}
            </p>
          </Card>
        ))}
      </div>
      <div className="mt-8 grid gap-5 lg:grid-cols-2">
        <Card className="p-6">
          <p className="text-sm font-medium text-teal">Movement journal</p>
          <h2 className="mt-2 text-xl font-medium">
            {analysis ? "Your latest video check-in" : "Keep a video of your progress."}
          </h2>
          <p className="mt-3 text-sm leading-6 text-white/85">
            {analysis
              ? `${analysis.completed_reps} reps recorded. Revisit the comparison and your next-set coaching.`
              : "Record a working set, review your movement, and build a history you can learn from."}
          </p>
          <Link
            href={
              analysis
                ? `/analysis/${analysis.id}`
                : captureHref({ planId: selectedId })
            }
            className="mt-3 inline-flex min-h-11 items-center text-sm font-medium text-teal"
          >
            {analysis ? "Revisit my analysis →" : "Record workout →"}
          </Link>
        </Card>
        <Card className="p-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-xl font-medium">Recent training</h2>
            <Link
              href="/history"
              className="inline-flex min-h-11 items-center text-sm text-teal"
            >
              All progress →
            </Link>
          </div>
          <div className="mt-3 space-y-4">
            {recent.length ? (
              recent.map((s) => (
                <div key={s.id} className="flex items-center gap-3">
                  <Check className="h-5 w-5 shrink-0 text-teal" aria-hidden />
                  <div>
                    <Link
                      href={s.plan_id ? `/workouts/${s.plan_id}` : "/history"}
                      className="text-base font-medium hover:text-teal"
                    >
                      {s.plan_name || "Video training"}
                    </Link>
                    <p className="mt-1 text-sm text-white/80">
                      {STATUS_LABEL[s.status]} · {s.summary.completed_sets} sets
                      · {s.summary.total_reps} reps
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-sm leading-6 text-white/80">
                Your completed and logged workouts will appear here.
              </p>
            )}
          </div>
        </Card>
      </div>
      {profile && (
        <details className="mt-8 rounded-2xl border border-white/15 p-5">
          <summary className="flex min-h-11 cursor-pointer items-center text-base font-medium">
            Build a different week
          </summary>
          <p className="mt-3 text-sm leading-6 text-white/85">
            Review a new proposal before replacing your accepted plan.
          </p>
          <TrainingConsent
            checked={consent}
            onChange={setConsent}
            disabled={busy}
          />
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              loading={busy}
              loadingLabel="Building your week…"
              disabled={busy || !consent}
              onClick={buildPlan}
            >
              Build a new week
            </Button>
            <Link href="/onboarding" className={buttonClass("ghost")}>
              Update preferences
            </Link>
          </div>
          {!consent && (
            <p className="mt-3 text-sm text-white/80">
              Agree above to enable plan generation.
            </p>
          )}
          {busy && (
            <div className="mt-3">
              <ActionFeedback kind="loading">
                Building a week around your preferences. This can take about a
                minute.
              </ActionFeedback>
            </div>
          )}
          {buildError && (
            <div className="mt-3">
              <ActionFeedback kind="error">{buildError}</ActionFeedback>
            </div>
          )}
        </details>
      )}
    </AppShell>
  );
}
