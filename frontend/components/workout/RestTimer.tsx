"use client";

import { Button } from "@/components/ui/button";
import { formatClock } from "@/lib/training";
import { extendRest, type RestState } from "@/lib/rest";
import { useEffect, useState } from "react";

export type { RestState } from "@/lib/rest";

export function RestTimer({ rest, onChange }: {rest: RestState; onChange: (next: RestState) => void}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!rest || rest.pausedRemainingMs != null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [rest]);
  if (!rest) return null;
  const paused = rest.pausedRemainingMs != null;
  const left = Math.max(0, paused ? rest.pausedRemainingMs! / 1000 : (rest.endsAt - now) / 1000);
  const done = left <= 0;
  return (
    <div role="timer" aria-label={paused ? "Rest paused" : done ? "Rest complete" : "Rest timer"}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-[#0b0f14]/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-2 px-4 py-2">
        <div className="min-w-0">
          <p className="truncate text-xs text-white/80" title={rest.label}>{paused ? "Rest paused" : done ? "Rest done" : "Resting"} · {rest.label}</p>
          <p className={done ? "font-mono text-xl text-amber" : "font-mono text-xl text-teal"}>{done ? "Ready for your next set" : formatClock(left)}</p>
        </div>
        <div className="flex shrink-0 gap-1">
          {!done && <Button variant="secondary" className="min-w-11 px-3" onClick={() => onChange(extendRest(rest))}>+15s</Button>}
          <Button variant="ghost" className="min-w-11 px-3" onClick={() => onChange(null)}>{done ? "Dismiss" : "Skip rest"}</Button>
        </div>
      </div>
    </div>
  );
}
