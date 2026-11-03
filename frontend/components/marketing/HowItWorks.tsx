const steps = [
  {
    n: "01",
    title: "Make it personal",
    copy: "Tell GhostRep about your goals, experience, and training preferences.",
  },
  {
    n: "02",
    title: "Train with a plan",
    copy: "Build a workout that fits your goals, equipment, and schedule.",
  },
  {
    n: "03",
    title: "Record your movement",
    copy: "Capture your exercise using a regular phone camera.",
  },
  {
    n: "04",
    title: "Meet your movement twin",
    copy: "See how each repetition compares with your own reference movement.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="mx-auto max-w-6xl px-5 py-24">
      <p className="font-mono text-xs uppercase tracking-[0.22em] text-teal">How it works</p>
      <h2 className="mt-3 max-w-xl font-display text-3xl font-semibold tracking-tight md:text-4xl">
        A smarter way to understand your training.
      </h2>
      <div className="mt-12 grid gap-4 md:grid-cols-4">
        {steps.map((step) => (
          <article
            key={step.n}
            className="group rounded-[1.5rem] border border-white/8 bg-card/80 p-5 transition hover:border-teal/25 hover:bg-white/[0.03]"
          >
            <p className="font-mono text-xs text-teal">{step.n}</p>
            <h3 className="mt-4 font-display text-xl tracking-tight">{step.title}</h3>
            <p className="mt-2 text-sm leading-6 text-white/55">{step.copy}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
