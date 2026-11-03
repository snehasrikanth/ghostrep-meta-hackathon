import { GHOSTREP_AMBER, GHOSTREP_TEAL } from "@/components/brand/mark";

const features = [
  {
    title: "Your Personal Movement Twin",
    copy: "Compare repetitions against a reference built from your own movement—not someone else's ideal.",
    visual: <TwinMini />,
  },
  {
    title: "Every Rep, Measured",
    copy: "Explore repetition timing, movement depth, and consistency with clear visual breakdowns.",
    visual: <MetricsMini />,
  },
  {
    title: "Feedback That Adapts",
    copy: "Turn measured movement changes into understandable observations and informed next-set decisions.",
    visual: <CoachMini />,
  },
];

export function FeatureGrid() {
  return (
    <section id="features" className="mx-auto max-w-6xl px-5 py-24">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-teal">Why GhostRep</p>
      <h2 className="mt-3 max-w-xl font-display text-3xl font-semibold tracking-tight md:text-4xl">
        Built around the way you move.
      </h2>
      <div className="mt-12 grid gap-4 lg:grid-cols-3">
        {features.map((feature) => (
          <article key={feature.title} className="rounded-[1.6rem] border border-white/8 bg-card/80 p-5">
            <div className="overflow-hidden rounded-2xl border border-white/6 bg-black/30">{feature.visual}</div>
            <h3 className="mt-5 font-display text-xl tracking-tight">{feature.title}</h3>
            <p className="mt-2 text-sm leading-6 text-white/55">{feature.copy}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function TwinMini() {
  return (
    <svg viewBox="0 0 280 120" className="h-28 w-full" aria-hidden>
      <path d="M40 88 C 80 28, 120 28, 160 88" fill="none" stroke={GHOSTREP_TEAL} strokeWidth="3" opacity="0.85" />
      <path d="M48 88 C 92 38, 132 20, 176 88" fill="none" stroke={GHOSTREP_AMBER} strokeWidth="3" opacity="0.9" />
    </svg>
  );
}

function MetricsMini() {
  return (
    <svg viewBox="0 0 280 120" className="h-28 w-full" aria-hidden>
      {[48, 62, 54, 70, 58, 76, 64, 80].map((h, i) => (
        <rect
          key={i}
          x={36 + i * 28}
          y={100 - h}
          width="16"
          height={h}
          rx="4"
          fill={i === 3 ? GHOSTREP_TEAL : "rgba(255,255,255,0.16)"}
        />
      ))}
    </svg>
  );
}

function CoachMini() {
  return (
    <div className="flex h-28 items-center px-5">
      <div className="w-full rounded-xl border border-white/8 bg-white/[0.03] px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-teal">Keep plan</p>
        <p className="mt-1 text-sm text-white/70">Stay with the set you just earned.</p>
      </div>
    </div>
  );
}
