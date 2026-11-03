"use client";

import { GhostPlayer, type SeekCue } from "@/components/ghost/GhostPlayer";
import { ExerciseDemo } from "@/components/workout/ExerciseDemo";
import { DecisionCard } from "@/components/analysis/DecisionCard";
import { CoachChat } from "@/components/analysis/CoachChat";
import { fallbackCoaching } from "@/lib/decision";
import { LastSetComparison } from "@/components/analysis/LastSetComparison";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProcessingStatus, processingStageLabel } from "@/components/workout/ProcessingStatus";
import { RestTimer } from "@/components/workout/RestTimer";
import { useRestTimer } from "@/lib/useRestTimer";
import { api } from "@/lib/api";
import { canRetryRecording, retryRecordingHref } from "@/lib/capture";
import { requestedComparisonEvidence } from "@/lib/setComparison";
import {
  mainFinding,
  referenceCopy,
  coachingForDisplay,
  detectedRepCount,
} from "@/lib/coaching";
import { exerciseDisplayName, formatLoad, unitFromProfile, type WeightUnit } from "@/lib/training";
import type { Analysis, Coaching, Overlay, RecordedSet } from "@/lib/types";
import { ArrowRight, Play, Video } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function AnalysisPage() {
  return (
    <Suspense>
      <AnalysisInner />
    </Suspense>
  );
}

function AnalysisInner() {
  const params = useParams<{ id: string }>();
  const query = useSearchParams();
  const evidenceRep = query.get("rep"), evidenceTime = query.get("t");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [recording, setRecording] = useState<RecordedSet | null>(null);
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [storedCoaching, setCoaching] = useState<Coaching | null>(null);
  const coaching = analysis ? storedCoaching ? coachingForDisplay(analysis, storedCoaching) : fallbackCoaching(analysis) : null;
  const [unit, setUnit] = useState<WeightUnit>("kg");
  const [rep, setRep] = useState<number | null>(null);
  const [seek, setSeek] = useState<SeekCue | null>(null);
  const sample = analysis?.is_sample === true || analysis?.mode === "demo";
  const [rest, setRest] = useRestTimer(sample ? null : analysis?.session_id, analysis?.session_status, analysis?.session_paused_at);
  const [retry, setRetry] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const a = await api.getAnalysis(params.id);
        if (cancelled) return;
        setAnalysis(a);
        setError(null);
        if (a.status !== "COMPLETED") {
          const saved = await api.getRecording(a.set_id).catch(() => null);
          if (cancelled) return;
          if (saved) setRecording(saved);
        }
        if (a.status === "COMPLETED") {
          const [o, c, p] = await Promise.all([
            api.getOverlay(params.id),
            api.getCoaching(params.id).catch(() => null),
            api.getProfile().catch(() => null),
          ]);
          if (cancelled) return;
          setOverlay(o);
          setCoaching(c);
          const requested = requestedComparisonEvidence(a.reps, evidenceRep, evidenceTime);
          setRep(requested?.repId ?? a.reference_rep);
          setSeek(requested ? {t:requested.seconds,key:Date.now()} : null);
          setUnit(unitFromProfile(p));
        } else if (a.status !== "FAILED" && !a.processing_stalled) timer = setTimeout(load, 1000);
      } catch (err) {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Could not load this analysis.",
          );
      }
    }
    void load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [params.id, retry, evidenceRep, evidenceTime]);
  useEffect(() => {
    let cancelled = false;
    void api.getProfile().then(profile => {
      if (!cancelled) setUnit(unitFromProfile(profile));
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [params.id]);
  const chartData = useMemo(
    () =>
      (analysis?.reps || []).map((r) => ({
        name: `R${r.rep_id}`,
        duration: +(r.end_seconds - r.start_seconds).toFixed(2),
        depth: r.metrics.relative_depth,
        torso: r.metrics.max_torso_inclination_deg,
        ascent: r.ascent_seconds,
        descent: r.descent_seconds,
      })),
    [analysis],
  );
  const planId = analysis?.plan_id || coaching?.plan_id || null;
  const finding = analysis ? mainFinding(analysis, coaching) : null;
  const reference = analysis ? referenceCopy(analysis) : null;
  const selected = analysis?.reps.find((r) => r.rep_id === rep);
  function replay(t: number | null, id?: number | null) {
    if (t == null) return;
    if (id != null) setRep(id);
    setSeek((previous) => ({ t, key: (previous?.key ?? 0) + 1 }));
  }
  async function deleteReplay() {
    setDeleting(true);
    try {
      await api.deleteMedia(params.id);
      setOverlay(await api.getOverlay(params.id));
      setDeleteConfirm(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not delete the replay.",
      );
    } finally {
      setDeleting(false);
    }
  }
  if (!analysis)
    return (
      <AppShell>
        <p role="status" className={error ? "text-red-400" : "text-white/80"}>
          {error || "Loading your set…"}
        </p>
        {error && <Button variant="secondary" onClick={() => {setError(null);setRetry(n=>n+1);}}>Retry status check</Button>}
      </AppShell>
    );
  if (analysis.status !== "COMPLETED")
    return (
      <AppShell>
        <Link
          href={planId ? `/workouts/${planId}` : "/record"}
          className="inline-flex min-h-11 items-center text-sm text-teal"
        >
          ← {planId ? "My workout" : "Back to recording"}
        </Link>

        <div className="mt-4 grid items-start gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <Card className="overflow-hidden p-4 sm:p-5">
            <h1 className="text-xl font-semibold">{sample ? "Your sample set" : "Your recording"}</h1>
            <p className="mt-2 text-sm leading-6 text-white/75">{sample ? "Illustrative data · separate from your training." : "Your set is saved. Keep your clip in view while we prepare your analysis."}</p>
            <p role="status" className="mt-3 text-sm font-medium text-teal lg:hidden">{processingStageLabel(analysis.status,analysis.processing_stalled)}</p>
            <div className="mt-4 flex min-h-64 items-center justify-center overflow-hidden rounded-2xl bg-black">
              {recording?.has_video ? (
                <video className="h-[min(38vh,20rem)] w-full object-contain lg:h-[min(50vh,26rem)]" src={api.mediaUrl(analysis.set_id)} controls playsInline preload="metadata" aria-label="Your uploaded set" />
              ) : (
                <div className="flex min-h-64 flex-col items-center justify-center gap-3 px-6 py-10 text-center text-sm text-white/70">
                  <Video className="h-8 w-8 text-teal" aria-hidden="true" />
                  <p>{sample ? "Your illustrative replay will appear with the results." : analysis.status === "FAILED" ? "The video preview could not be prepared." : "Preparing your saved video preview…"}</p>
                </div>
              )}
            </div>
            {analysis.duration_seconds != null && <p className="mt-3 text-sm text-white/75">{Math.round(analysis.duration_seconds)}-second recording{recording?.has_video ? " · Available to replay" : ""}</p>}
          </Card>
          <Card className="p-5 sm:p-6">
            <p className="font-mono text-xs uppercase tracking-wider text-teal">{analysis.status === "FAILED" || analysis.processing_stalled ? "Your saved set needs attention" : "Analyzing your set"}</p>
            <h2 className="mt-3 text-2xl font-semibold">{recording?.exercise_name || analysis.exercise_id.replaceAll("_", " ")}{recording?.set_index ? ` · set ${recording.set_index}` : ""}</h2>
            <div className="mt-4 flex flex-wrap gap-2 text-sm text-white/85">
              {analysis.planned_reps != null && <span className="rounded-full border border-white/15 px-3 py-2">Target: {analysis.planned_reps} reps</span>}
              {recording?.load_kg != null && <span className="rounded-full border border-white/15 px-3 py-2">{formatLoad(recording.load_kg, unit)}</span>}
              {recording?.reported_rpe != null && <span className="rounded-full border border-white/15 px-3 py-2">Reported effort: {recording.reported_rpe}/10</span>}
            </div>
            <p className="mt-4 text-sm leading-7 text-white/80">{analysis.status === "FAILED" || analysis.processing_stalled ? "Your saved work is preserved. Check the status or return to training; your recording will not be submitted again automatically." : "We’re checking this recording and preparing your movement comparison and next-set guidance. Your results will open here automatically."}</p>
            <ProcessingStatus stage={analysis.status} message={analysis.message} startedAt={analysis.processing_started_at} timings={analysis.stage_timings} stalled={analysis.processing_stalled} />
            {error && <p role="alert" className="mt-4 text-sm text-amber">{error} Your recording is saved. Check status to reconnect.</p>}
            {analysis.processing_stalled && <p role="alert" className="mt-4 text-sm text-amber">Processing has not advanced. Check status again to reconnect to this saved set.</p>}
            <div className="mt-5 flex flex-wrap items-center gap-3">
              {recording && canRetryRecording(recording) && <Link href={retryRecordingHref(recording, planId)} className="inline-flex min-h-11 items-center rounded-full bg-teal px-5 py-3 text-sm font-semibold text-black">Replace recording and retry</Link>}
              {(error || analysis.processing_stalled || analysis.status === "FAILED") && <Button variant="secondary" onClick={() => {setError(null);setRetry(n=>n+1);}}>Check status again</Button>}
              <Link href={planId ? `/workouts/${planId}` : "/history"} className="inline-flex min-h-11 items-center text-sm text-teal">{planId ? "Back to workout" : "Back to progress"} <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" /></Link>
            </div>
            {analysis.status !== "FAILED" && !analysis.processing_stalled && !error && <p className="mt-2 text-xs leading-6 text-white/60">You can return to your workout and reopen this set. There’s no need to upload it again.</p>}
          </Card>
        </div>
      </AppShell>
    );

  return (
    <AppShell>
      <div className={rest ? "pb-24" : ""}>
        <Link
          href={planId ? `/workouts/${planId}` : "/history"}
          className="text-sm text-teal"
        >
          ← {planId ? "Back to workout" : "Back to progress"}
        </Link>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-medium text-teal">{sample ? "Sample demonstration · not training" : "Your set analysis"}</p>
            <h1 className="mt-1 text-2xl font-semibold sm:text-3xl">{analysis.set_index != null ? `Set ${analysis.set_index} · ` : ""}{exerciseDisplayName(analysis.exercise_id, analysis.exercise_id === "barbell_squat" ? "Barbell squat" : undefined)}</h1>
          </div>
          <ExerciseDemo exerciseId={analysis.exercise_id} />
        </div>
        <p className="mt-3 text-base text-white/90"><strong>{detectedRepCount(analysis)} reps detected</strong> / {analysis.planned_reps != null ? `${analysis.planned_reps} planned` : "Target not entered"}
          {!sample && analysis.completed_reps !== detectedRepCount(analysis) && <> · <strong>{analysis.completed_reps ?? "Not"} logged</strong></>}
        </p>
        {!sample && <details className="mt-1 text-xs leading-5 text-white/70"><summary className="flex min-h-11 cursor-pointer items-center text-teal">Counts and logging</summary><p>Training log: {analysis.completed_reps ?? "Not"} logged. Log corrections do not create measured reps.</p><Link className="inline-flex min-h-11 items-center text-teal underline" href={planId ? `/workouts/${planId}` : "/history"}>Review workout log</Link></details>}
        {Boolean(analysis.partial_movements || analysis.uncertain_movements) && <p className="mt-2 text-sm leading-6 text-amber">{analysis.partial_movements ?? 0} partial · {analysis.uncertain_movements ?? 0} uncertain segments. These are not additional detected reps.</p>}
        {!sample && analysis.planned_reps != null && detectedRepCount(analysis) === analysis.planned_reps && finding?.kind !== "recording" && <p className="mt-1 text-sm text-teal">You reached your planned rep count.</p>}
            {finding?.kind === "difference" && <Card className="mt-4 border-teal/35 bg-teal/5 p-4 sm:p-5">
              <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-teal">
                What to notice
              </p>
              <h2 className="mt-2 text-xl font-semibold leading-snug text-teal sm:text-2xl">
                {finding?.what}
              </h2>
              {finding?.kind === "difference" && <p className="mt-3 text-xs leading-6 text-white/75">A difference from your own reference, not a verdict that the movement was wrong.</p>}
              {finding?.seconds != null && (
                <button
                  onClick={() => {replay(finding.seconds, finding.repId); document.getElementById("set-replay")?.scrollIntoView({block:"start"});}}
                  className="mt-4 inline-flex min-h-11 min-w-11 items-center gap-2 text-sm text-teal"
                >
                  <Play className="h-4 w-4" />
                  Compare this rep
                  {finding.repId ? ` · rep ${finding.repId}` : ""}
                </button>
              )}
            </Card>}
        <div className="mt-4 grid items-start gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
          <div className="min-w-0 space-y-4 lg:col-start-2 lg:row-start-1">
            {coaching && (
              <DecisionCard
                coaching={coaching}
                analysis={analysis}
                sample={sample}
                planId={planId}
                unit={unit}
                onChanged={setCoaching}
                onReplay={replay}
                onRest={(seconds) =>
                  setRest({
                    label: "Barbell squat",
                    endsAt: Date.now() + seconds * 1000,
                    total: seconds,
                  })
                }
              />
            )}

          </div>
          <div id="set-replay" tabIndex={-1} className="min-w-0 scroll-mt-24 lg:col-start-1 lg:row-start-1">
            {overlay ? (
              <GhostPlayer
                overlay={overlay}
                setId={analysis.set_id}
                seekTo={seek}
                onTime={() => undefined}
              />
            ) : (
              <Card className="p-8 text-sm text-white/80">
                Preparing replay…
              </Card>
            )}
            {analysis.previous_set_comparison && <LastSetComparison comparison={analysis.previous_set_comparison} unit={unit} />}
            <Card className="mt-5 p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium">
                  Look closer, rep by rep.
                </h2>
                <span className="text-xs text-teal">{analysis.reference_rep ? "Teal = your reference" : "No reliable reference"}</span>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {analysis.reps.map((item) => (
                  <button
                    key={item.rep_id}
                    onClick={() => replay(item.start_seconds, item.rep_id)}
                    aria-pressed={rep === item.rep_id}
                    className={`min-h-11 min-w-11 rounded-xl border px-3 py-2 font-mono text-sm ${rep === item.rep_id ? "border-teal bg-teal/15 text-teal" : "border-white/10 text-white/80"}`}
                  >
                    R{item.rep_id}
                    {item.is_reference ? " ★" : ""}
                    {!item.is_complete ? item.movement_status === "uncertain" ? " uncertain" : " partial" : ""}
                  </button>
                ))}
              </div>
              {selected && (
                <details className="mt-2 text-xs text-white/80"><summary className="flex min-h-11 cursor-pointer items-center text-teal">Selected rep measurements</summary><p>
                  Rep {selected.rep_id} · {Number.isFinite(selected.descent_seconds) ? `${selected.descent_seconds.toFixed(1)}s lowering` : "Lowering time unavailable"}
                  {" · "}{Number.isFinite(selected.ascent_seconds) ? `${selected.ascent_seconds.toFixed(1)}s standing up` : "Standing-up time unavailable"} ·{" "}
                  {selected.comparison_eligible === false ? "comparison unavailable" : `${(selected.confidence * 100).toFixed(0)}% tracking estimate`}
                  <span className="mt-1 block">Tracking estimates are heuristics about the recording, not accuracy or technique-correctness ratings.</span>
                </p></details>
              )}
            </Card>
            {reference && (
              <details className="mt-4 rounded-2xl border border-white/10 p-5">
                <summary className="cursor-pointer text-sm text-white/85">
                  How your personal reference is chosen
                </summary>
                <p className="mt-3 text-sm leading-6 text-white/80">
                  {reference.body}
                </p>
                {analysis.reference_rep && (
                  <button
                    onClick={() => {
                      const r = analysis.reps.find(
                        (r) => r.rep_id === analysis.reference_rep,
                      );
                      replay(r?.start_seconds ?? null, analysis.reference_rep);
                    }}
                    className="mt-3 min-h-11 min-w-11 text-sm text-teal"
                  >
                    Replay my reference →
                  </button>
                )}
              </details>
            )}
          </div>
        </div>
        <div className="mt-6">
            {(analysis.id===params.id||analysis.set_id===params.id)&&<CoachChat key={analysis.set_id} setId={analysis.set_id} exerciseId={analysis.exercise_id} selectedRep={rep} onReplay={replay}/>}
        </div>
        <details className="mt-8 rounded-3xl border border-white/10 p-5">
          <summary className="cursor-pointer text-sm font-medium text-white/70">
            Explore the measurements
          </summary>
          <p className="mt-3 text-xs leading-6 text-white/75">
            Camera estimates describe this recording. They don’t score safety or
            diagnose technique.
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <MetricChart
              title="Time per rep (seconds)"
              data={chartData}
              field="duration"
            />
            <MetricChart
              title="Squat depth (relative depth)"
              data={chartData}
              field="depth"
            />
            <MetricChart
              title="Time standing up (ascent, seconds)"
              data={chartData}
              field="ascent"
            />
            <MetricChart
              title="Upper-body lean (torso angle, degrees)"
              data={chartData}
              field="torso"
            />
          </div>
          {analysis.tracking_quality?.notes?.map((n) => (
            <p key={n} className="mt-3 text-xs text-white/75">
              {n}
            </p>
          ))}
        </details>
        <details className="mt-4 rounded-2xl border border-white/10 p-5">
          <summary className="cursor-pointer text-sm text-white/80">
            Recording privacy
          </summary>
          <p className="mt-3 text-sm leading-6 text-white/80">
            Delete the stored replay whenever you want. Your logged reps,
            measurements, and coaching remain in your training history.
          </p>
          {overlay?.video_url ? (
            <div className="mt-4">
              {deleteConfirm ? (
                <div>
                  <p className="text-sm text-white/70">
                    Permanently delete this video replay?
                  </p>
                  <div className="mt-3 flex gap-2">
                    <Button
                      variant="amber"
                      disabled={deleting}
                      onClick={deleteReplay}
                    >
                      {deleting ? "Deleting…" : "Delete video"}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => setDeleteConfirm(false)}
                    >
                      Keep replay
                    </Button>
                  </div>
                </div>
              ) : (
                <Button
                  variant="secondary"
                  onClick={() => setDeleteConfirm(true)}
                >
                  Delete my replay
                </Button>
              )}
            </div>
          ) : (
            <p className="mt-3 text-xs text-teal">No video replay is stored.</p>
          )}
        </details>
        {error && (
          <p role="alert" className="mt-4 text-sm text-red-400">
            {error}
          </p>
        )}
      </div>
      <RestTimer key={rest?.endsAt ?? "idle"} rest={rest} onChange={setRest} />
    </AppShell>
  );
}

function MetricChart({
  title,
  data,
  field,
}: {
  title: string;
  data: Record<string, unknown>[];
  field: string;
}) {
  return (
    <div className="rounded-2xl bg-black/20 p-4">
      <p className="text-xs text-white/80">{title}</p>
      <div className="mt-3 h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid stroke="rgba(255,255,255,.05)" />
            <XAxis dataKey="name" stroke="#8b93a1" />
            <YAxis stroke="#8b93a1" />
            <Tooltip
              contentStyle={{
                background: "#13181f",
                border: "1px solid #333",
                borderRadius: 12,
              }}
            />
            <Bar dataKey={field} name={title} fill="#20d6c7" radius={5} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
