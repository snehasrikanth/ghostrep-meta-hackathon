import { Card } from "@/components/ui/card";
import { formatLoad, type WeightUnit } from "@/lib/training";
import type { ComparedSet, SetComparison } from "@/lib/types";
import Link from "next/link";
import { ChevronDown } from "lucide-react";

function setContext(set: ComparedSet, unit: WeightUnit) {
  return `${set.load_kg == null ? "Load not entered" : formatLoad(set.load_kg, unit)} · ${set.reported_effort == null ? "Effort not entered" : `Effort ${set.reported_effort}/10`}`;
}

function comparisonContext(previous: ComparedSet, current: ComparedSet, unit: WeightUnit) {
  const load = previous.load_kg != null && previous.load_kg === current.load_kg
    ? `${formatLoad(current.load_kg, unit)} in both`
    : `${previous.load_kg == null ? "not entered" : formatLoad(previous.load_kg, unit)} → ${current.load_kg == null ? "not entered" : formatLoad(current.load_kg, unit)}`;
  const effort = previous.reported_effort != null && previous.reported_effort === current.reported_effort
    ? `${current.reported_effort}/10 in both`
    : `${previous.reported_effort == null ? "not entered" : `${previous.reported_effort}/10`} → ${current.reported_effort == null ? "not entered" : `${current.reported_effort}/10`}`;
  return `Load: ${load} · Effort: ${effort}`;
}

export function LastSetComparison({ comparison: c, unit }: { comparison: SetComparison; unit: WeightUnit }) {
  const timings=c.metrics.filter(m=>m.unit==="seconds_per_rep" && Number.isFinite(m.previous) && Number.isFinite(m.current)).slice(0,2);
  return (
    <Card className="mt-5 min-w-0 border-teal/20 p-4 sm:p-5">
      <section id="set-comparison" tabIndex={-1} aria-label="Compared with your last set" className="min-w-0 scroll-mt-24 [overflow-wrap:anywhere]">
        <h2 className="text-sm font-medium text-white/90">Compared with your last set</h2>
        <h3 className="mt-2 text-lg font-semibold leading-snug text-teal">
          <span aria-hidden="true" className="mr-2">{c.emoji}</span>{c.headline}
        </h3>
        <p className="mt-2 text-sm leading-6 text-white/85">{c.status !== "compared" ? c.summary : c.follow_up?.status === "improved" ? "Timing varied less than last set. Consistency does not establish correct technique." : c.follow_up?.status === "remains" ? "Rep timing still varied noticeably. This alone is not a technique fault." : "Timing can be compared; a progress judgment is unavailable. Shorter is not automatically better."}</p>
        {c.status === "compared" && timings.length>0 && <><p className="mt-3 text-xs text-white/65">Average per usable rep · previous → current</p><dl className="mt-2 grid gap-2 text-xs text-white/80">
          {timings.map(m=><div key={m.key} className="flex flex-wrap justify-between gap-2"><dt>{m.label}</dt><dd className="tabular-nums">{m.previous.toFixed(1)}s → {m.current.toFixed(1)}s</dd></div>)}
        </dl></>}
        <details className="group mt-3 border-t border-white/10 pt-1">
          <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-2 text-sm text-teal">Comparison evidence and limits<ChevronDown size={16} aria-hidden="true" className="shrink-0 group-open:rotate-180" /></summary>
        {c.previous && c.current && (
          <>
            <p className="mt-3 text-xs leading-5 text-white/75">{c.previous.label} → {c.current.label} · same exercise, same workout</p>
            <p className="mt-2 text-xs leading-5 text-white/80">{comparisonContext(c.previous, c.current, unit)}</p>
            {c.metrics.length > 0 && (
              <table className="mt-3 w-full table-fixed text-left text-sm">
                <caption className="sr-only">Timing per usable measured repetition, previous and current set. Shorter is not automatically better.</caption>
                <thead className="text-xs text-white/75">
                  <tr><th scope="col" className="w-[44%] pb-2 pr-2 font-medium">Measurement</th><th scope="col" className="pb-2 pr-2 font-medium">Previous</th><th scope="col" className="pb-2 font-medium">Current</th></tr>
                </thead>
                <tbody>
                  {c.metrics.map(m => (
                    <tr key={m.key} className="border-t border-white/10 align-top">
                      <th scope="row" className="py-2 pr-2 font-normal text-white/85">{m.label}</th>
                      <td className="py-2 pr-2 tabular-nums">{m.unit === "reps" ? m.previous : `${m.previous.toFixed(1)}s`}</td>
                      <td className="py-2 tabular-nums">{m.unit === "reps" ? m.current : `${m.current.toFixed(1)}s`}{m.change && m.change !== "About the same" && <span className="mt-1 block text-xs leading-5 text-white/75">{m.change}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
          {c.follow_up && <p className="my-3 text-sm leading-6 text-white/85">{c.follow_up.explanation}</p>}
          {c.next_step && <p className="mb-3 text-sm leading-6 text-white/85">{c.next_step}</p>}
          {c.previous && c.current && (
            <dl className="space-y-3 pb-3 text-xs leading-5 text-white/80">
              {[c.previous, c.current].map(set => (
                <div key={set.set_id}>
                  <dt className="font-medium text-white">{set.label} · <time dateTime={set.recorded_at}>{new Date(set.recorded_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}</time></dt>
                  <dd>{set.usable_reps} usable / {set.detected_reps} detected reps · {set.planned_reps ?? "No"} planned · {set.logged_reps ?? "No"} logged</dd>
                  <dd>{setContext(set, unit)}</dd>
                </div>
              ))}
            </dl>
          )}
          {c.follow_up?.previous_observation && <p className="mb-2 text-sm leading-6 text-white/85">Previous note (outcome assessed only where measurable): “{c.follow_up.previous_observation}”</p>}
          {c.follow_up?.evidence && <Link className="mb-2 inline-flex min-h-11 items-center text-sm text-teal underline" href={`/analysis/${c.follow_up.evidence.set_id}?rep=${c.follow_up.evidence.rep_id}&t=${c.follow_up.evidence.seconds}`}>Open previous evidence · rep {c.follow_up.evidence.rep_id}</Link>}
          <ul className="list-disc space-y-2 pl-4 text-xs leading-5 text-white/75">
            {c.details.map((detail, i) => <li key={i}>{detail}</li>)}
          </ul>
        </details>
      </section>
    </Card>
  );
}
