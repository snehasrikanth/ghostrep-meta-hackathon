"use client";

import { TwinFigures } from "@/components/marketing/TwinFigures";
import { useEffect, useState } from "react";

export function HeroTwin() {
  const [depth, setDepth] = useState(0.32);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reduce.matches) return undefined;
    let frame = 0;
    let raf = 0;
    const tick = () => {
      frame += 1;
      setDepth(0.2 + 0.22 * (0.5 + 0.5 * Math.sin(frame / 48)));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="relative overflow-hidden rounded-[2rem] border border-white/8 bg-[#0c1016] shadow-[0_30px_80px_rgba(0,0,0,0.45)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_240px_at_70%_0%,rgba(32,214,199,0.12),transparent_60%)]" />
      <div className="relative flex items-center justify-between px-5 py-3.5">
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-white/40">Set analysis</p>
        <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-teal">Reference locked</p>
      </div>
      <div className="relative grid gap-3 px-4 pb-4 lg:grid-cols-[1.3fr_0.7fr]">
        <div className="relative overflow-hidden rounded-2xl bg-black/40">
          <TwinFigures depth={depth} className="mx-auto h-[340px] w-full max-w-[360px]" />
          <div className="pointer-events-none absolute left-4 top-4 flex gap-2">
            <Legend color="bg-teal" label="Reference" />
            <Legend color="bg-amber" label="Current" />
          </div>
        </div>
        <div className="grid grid-rows-[1fr_auto] gap-3">
          <div className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-white/35">Comparison</p>
            <p className="mt-3 font-display text-3xl tracking-tight">Aligned</p>
            <p className="mt-2 text-sm leading-6 text-white/50">
              The teal path stays put. The amber path is the live repetition, phase-matched to your own
              reference.
            </p>
            <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-white/8">
              <div className="h-full w-[72%] rounded-full bg-gradient-to-r from-teal to-amber" />
            </div>
            <p className="mt-2 font-mono text-[11px] text-white/35">Closer to your reference</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Array.from({ length: 8 }, (_, i) => (
              <span
                key={i}
                className={`rounded-full px-2.5 py-1 font-mono text-[11px] ${
                  i === 3 ? "bg-teal text-[#04110f]" : "border border-white/10 text-white/45"
                }`}
              >
                R{i + 1}
              </span>
            ))}
          </div>
        </div>
      </div>
      <p className="border-t border-white/6 px-5 py-3 font-mono text-[11px] uppercase tracking-[0.16em] text-white/30">
        Product visualization — sample comparison, not a live recording
      </p>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/8 bg-black/40 px-2.5 py-1 text-[11px] text-white/70">
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      {label}
    </span>
  );
}
