"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { appliedSummary, applyTargetLabel, formatRepLoad, observationCopy } from "@/lib/coaching";
import { feedbackLabel, restDuration, setDecision } from "@/lib/decision";
import { formatLoad, type WeightUnit } from "@/lib/training";
import type { Analysis, Coaching } from "@/lib/types";
import { useId, useState } from "react";
import { Clock3, Play } from "lucide-react";
import Link from "next/link";

export function DecisionCard({coaching:c, analysis, sample, planId, unit, onChanged, onReplay, onRest}: {
  coaching:Coaching; analysis:Analysis; sample:boolean; planId:string|null; unit:WeightUnit;
  onChanged:(c:Coaching)=>void; onReplay:(seconds:number|null,repId?:number|null)=>void; onRest:(seconds:number)=>void;
}) {
  const d=setDecision(c,sample), confirmationId=useId();
  const [review,setReview]=useState(false), [busy,setBusy]=useState(false), [error,setError]=useState<string|null>(null);
  const closed=d.state==="closed";
  const rest=c.workout_rest_seconds ?? c.current_rest_seconds;
  const canRest=!sample && c.session_status==="active" && d.state!=="review" && !["STOP_AND_SEEK_PROFESSIONAL_ADVICE","REQUEST_NEW_RECORDING"].includes(c.suggested_action) && rest!=null;
  const evidence=c.presentation?.evidence[0];
  const observations=c.presentation?.observations ?? [];
  const currentTarget = `${formatRepLoad(c.workout_reps??c.current_reps,c.workout_load_kg??c.current_load_kg,unit)} · ${rest!=null?`${restDuration(rest)} rest`:"Rest not set"}`;
  const target=d.proposed
    ? c.suggested_action==="EXTEND_REST" ? `${restDuration(c.suggested_rest_seconds!) } rest` : c.suggested_action==="REDUCE_REPS" ? `${c.suggested_reps} reps` : formatLoad(c.suggested_load_kg,unit)
    : c.suggested_action==="EXTEND_REST" && rest!=null ? `${restDuration(rest)} rest` : currentTarget;
  function replay() {
    onReplay(evidence?.seconds ?? analysis.reps.find(r=>r.rep_id===analysis.reference_rep)?.start_seconds ?? 0,evidence?.rep_id ?? analysis.reference_rep);
    document.getElementById("set-replay")?.scrollIntoView({block:"start"});
  }
  async function decide(decision:"accepted"|"rejected") {
    setBusy(true);setError(null);
    try {onChanged(await api.decideCoaching(c,decision));setReview(false);}
    catch(err) {setError(err instanceof Error?err.message:"Could not save your choice. Try again.");if(err instanceof ApiError&&err.status===409)onChanged(await api.getCoaching(c.set_id));}
    finally {setBusy(false);}
  }
  const status={pending:d.change?"Awaiting your choice":"Ready to review",applied:"Applied",rejected:"Declined",kept:"Saved",review:"Review only",closed:"Workout ended",sample:"Read-only example"}[d.state];
  return <Card className="min-w-0 border-teal/25 bg-teal/5 p-4 sm:p-5 [overflow-wrap:anywhere]">
    <section id="set-recommendation" tabIndex={-1} className="scroll-mt-24" aria-label="Your next action">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><p className="font-medium text-teal">{closed?"Saved decision":"Your next action"}</p><span className="rounded-full border border-white/15 px-2.5 py-1 text-white/80">{status}</span></div>
      <h2 style={{fontFamily:"var(--font-sora), ui-sans-serif, system-ui, sans-serif"}} className="mt-3 text-xl font-semibold leading-snug sm:text-2xl">{d.headline}</h2>
      <p role={analysis.measurement_warning?"note":undefined} className={`mt-2 text-sm leading-6 ${analysis.measurement_warning?"text-amber":"text-white/85"}`}>{analysis.measurement_warning || d.explanation}</p>
      <p className="mt-2 text-xs text-white/65">{feedbackLabel(c,sample)}</p>
      {c.historical_interpretation_corrected && <p role="note" className="mt-3 text-sm leading-6 text-amber">Saved interpretation corrected. Original measurements and decision history are unchanged.</p>}
      {d.state!=="sample" && <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-3"><p className="text-xs text-white/70">{d.proposed?"Suggested change · not applied":closed?"Saved workout targets":"Current workout target"}</p><p className="mt-1 text-base font-medium text-teal">{target}</p></div>}
      {d.mayDecide && d.change && !review && <Button className="mt-4" aria-expanded={false} aria-controls={confirmationId} onClick={()=>setReview(true)}>{d.reviewLabel}</Button>}
      {d.mayDecide && !d.change && <Button className="mt-4" loading={busy} loadingLabel="Saving…" onClick={()=>decide("accepted")}>Keep current targets</Button>}
      {d.mayDecide && d.change && review && <div id={confirmationId} role="region" aria-label="Confirm target change" className="mt-4 rounded-xl border border-teal/25 p-3">
        <p className="text-sm leading-6 text-white/85">Current: {currentTarget}.</p>
        <p className="mt-1 text-sm leading-6">Only your approval changes the remaining workout targets.</p>
        <div className="mt-3 flex flex-wrap gap-2"><Button loading={busy} loadingLabel="Saving…" onClick={()=>decide("accepted")}>{applyTargetLabel(c)}</Button><Button variant="secondary" disabled={busy} onClick={()=>decide("rejected")}>Keep my targets</Button></div>
      </div>}
      {d.state==="review" || d.state==="sample" ? <Button className="mt-4" onClick={replay}><Play size={16} aria-hidden="true"/>Review evidence</Button> : !d.mayDecide && canRest ? <Button className="mt-4" onClick={()=>onRest(rest!)}><Clock3 size={16} aria-hidden="true"/>Start {restDuration(rest!)} rest</Button> : null}
      {appliedSummary(c,unit) && !sample && <p role="status" className="sr-only">{appliedSummary(c,unit)}</p>}
      <Link href={planId?`/workouts/${planId}`:"/history"} className="mt-3 flex min-h-11 items-center text-sm font-medium text-teal">{planId?closed?"View workout":"Back to workout":"Back to progress"} →</Link>
      {canRest && d.mayDecide && <Button variant="ghost" className="mt-1" onClick={()=>onRest(rest!)}><Clock3 size={15} aria-hidden="true"/>Rest with current target · {restDuration(rest!)}</Button>}
      <details className="mt-2 border-t border-white/10"><summary className="flex min-h-11 cursor-pointer items-center text-sm text-teal">Decision evidence and limits</summary>
        {appliedSummary(c,unit) && !sample && <p className="mt-2 text-xs leading-6 text-teal">{appliedSummary(c,unit)}</p>}
        <p className="mt-2 text-xs leading-6 text-white/70">Your reference is one observed rep, not an ideal-form standard. Tracking quality does not rate technique correctness. Lowering and standing-up times describe this recording.</p>
        {c.action_blocked_reason && <p className="mt-2 text-xs leading-6 text-amber">{c.action_blocked_reason}</p>}
        {observations.map(o=><button key={`${o.metric}-${o.rep_id}`} disabled={!o.evidence_seconds.length} onClick={()=>{onReplay(o.evidence_seconds[0]??null,o.rep_id);document.getElementById("set-replay")?.scrollIntoView({block:"start"});}} className="block min-h-11 w-full py-2 text-left text-xs leading-6 text-teal">{observationCopy(o,analysis)}{o.magnitude!=null && <span className="block text-white/65">{o.magnitude.toFixed(1)}{["ascent_duration","descent_duration","relative_depth"].includes(o.metric)?"% difference":"° difference"} · replay</span>}</button>)}
      </details>
      {error && <p role="alert" className="mt-3 text-sm text-amber">{error}</p>}
    </section>
  </Card>;
}
