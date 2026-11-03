"use client";

import { Check, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { formatClock } from "@/lib/training";

const STAGES = [
  ["UPLOADED", "Video uploaded"],
  ["VALIDATING", "Checking your video"],
  ["PREPROCESSING", "Preparing your replay"],
  ["ESTIMATING_POSE", "Tracking your movement"],
  ["DETECTING_REPS", "Finding your repetitions"],
  ["SEGMENTING", "Creating your movement outlines"],
  ["COMPUTING_METRICS", "Comparing your repetitions"],
  ["GENERATING_COACHING", "Next-set guidance"],
] as const;

export function processingStageLabel(stage: string, stalled = false): string {
  return stalled ? "Processing needs attention" : stage === "GENERATING_COACHING" ? "Your coach is reviewing your set…" : stage === "FAILED" ? "Processing needs attention" : stage === "COMPLETED" ? "Analysis ready" : stage === "SAVED" ? "Replay saved" : STAGES.find(([id]) => id === stage)?.[1] || "Processing your recording";
}

export function ProcessingStatus({ stage, message, startedAt, timings, stalled=false }: {
  stage: string;
  message?: string | null;
  startedAt?: string | null;
  timings?: Record<string, number>;
  stalled?: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());
  const terminal = stalled || ["COMPLETED", "FAILED", "SAVED"].includes(stage);
  useEffect(() => {
    if (terminal) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [terminal]);
  const start = startedAt ? Date.parse(startedAt) : NaN;
  const elapsed = Number.isFinite(start) ? Math.max(0, Math.floor((now - start) / 1000)) : null;
  const activeIndex = STAGES.findIndex(([id]) => id === stage);
  const title = processingStageLabel(stage,stalled);

  return (
    <div className="mt-5 rounded-2xl border border-white/10 bg-black/20 p-4 text-sm leading-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p role="status" className={stage === "FAILED" || stalled ? "font-medium text-amber" : "font-medium text-teal"}>{title}</p>
        {elapsed != null && <p className="font-mono text-xs text-white/65">{formatClock(elapsed)} elapsed</p>}
      </div>
      {!terminal && activeIndex >= 0 && (
        <ol className="mt-4 space-y-3" aria-label="Recording analysis progress">
          {STAGES.map(([id, label], index) => {
            // A past optional stage is not proof that outlines were generated.
            if (id === "SEGMENTING" && stage !== id && timings?.SEGMENTING == null) return null;
            const past = index < activeIndex;
            const current = index === activeIndex;
            return (
              <li key={id} aria-current={current ? "step" : undefined} className={`flex items-center gap-3 ${current ? "text-teal" : past ? "text-white/80" : "text-white/50"}`}>
                {past ? <Check className="h-4 w-4 shrink-0" aria-hidden="true" /> : current ? <LoaderCircle className="h-4 w-4 shrink-0 motion-safe:animate-spin" aria-hidden="true" /> : <span className="mx-1 h-2 w-2 shrink-0 rounded-full border border-current" aria-hidden="true" />}
                <span>{current ? title : label}</span>
              </li>
            );
          })}
        </ol>
      )}
      {stage === "SEGMENTING" && <p className="mt-4 text-xs leading-6 text-white/75">Outlines can take a little longer. If they aren’t ready in time, we’ll continue with the available movement analysis.</p>}
      {message && (terminal || activeIndex < 0) && <p className="mt-3 text-white/80">{stage === "FAILED" ? "This recording could not be analyzed. Your saved log is preserved; replace the clip to try again." : "Your recording is saved. Check its status again to reconnect."}</p>}
      {timings && Object.keys(timings).length > 0 && <details className="mt-3 text-xs text-white/65"><summary className="flex min-h-11 cursor-pointer items-center">Time spent on each step</summary>{Object.entries(timings).map(([name, seconds]) => <p key={name}>{STAGES.find(([id])=>id===name)?.[1] || "Recording preparation"}: {seconds.toFixed(1)}s</p>)}</details>}
    </div>
  );
}
