"use client";

import { TwinFigures } from "@/components/marketing/TwinFigures";
import { cn } from "@/lib/cn";
import { useState } from "react";

const reps = [
  { id: 1, depth: 0.22, note: "Close to reference" },
  { id: 2, depth: 0.28, note: "Slightly deeper" },
  { id: 3, depth: 0.18, note: "Shallower than reference" },
  { id: 4, depth: 0.34, note: "More knee travel" },
  { id: 5, depth: 0.26, note: "Steady" },
  { id: 6, depth: 0.4, note: "Noticeable change" },
  { id: 7, depth: 0.36, note: "Still drifting" },
  { id: 8, depth: 0.44, note: "Furthest this set" },
];

export function TwinShowcase() {
  const [active, setActive] = useState(3);
  const current = reps[active];

  return (
    <section id="product" className="mx-auto max-w-6xl px-5 py-8">
      <div className="overflow-hidden rounded-[2rem] border border-white/8 bg-[#0c1016]">
        <div className="grid lg:grid-cols-[0.9fr_1.1fr]">
          <div className="flex flex-col justify-center p-8 md:p-12">
            <p className="font-mono text-xs uppercase tracking-[0.22em] text-teal">Movement twin</p>
            <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight md:text-4xl">
              See the difference you couldn&apos;t feel.
            </h2>
            <p className="mt-4 max-w-md text-sm leading-7 text-white/55">
              Your movements change from rep to rep. GhostRep helps make those differences visible by
              lining each repetition up with a reference taken from your own set.
            </p>
            <div className="mt-8 flex flex-wrap gap-2">
              {reps.map((rep, index) => (
                <button
                  key={rep.id}
                  type="button"
                  onClick={() => setActive(index)}
                  className={cn(
                    "rounded-full px-3 py-1.5 font-mono text-xs transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal",
                    index === active ? "bg-teal text-[#04110f]" : "border border-white/10 text-white/50 hover:text-white",
                  )}
                >
                  R{rep.id}
                </button>
              ))}
            </div>
            <p className="mt-4 text-sm text-white/60">{current.note}</p>
          </div>
          <div className="relative border-t border-white/6 lg:border-l lg:border-t-0">
            <div className="absolute left-5 top-5 z-10 flex gap-2">
              <span className="rounded-full bg-black/50 px-2.5 py-1 font-mono text-[11px] text-teal">Descent</span>
              <span className="rounded-full bg-black/50 px-2.5 py-1 font-mono text-[11px] text-white/45">Ascent</span>
            </div>
            <TwinFigures depth={current.depth} className="h-[420px] w-full" />
            <p className="px-5 pb-5 font-mono text-[11px] uppercase tracking-[0.16em] text-white/30">
              Conceptual demonstration — not a recorded workout
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
