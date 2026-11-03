import { FeatureGrid } from "@/components/marketing/FeatureGrid";
import { HeroTwin } from "@/components/marketing/HeroTwin";
import { HowItWorks } from "@/components/marketing/HowItWorks";
import { TwinShowcase } from "@/components/marketing/TwinShowcase";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { buttonClass } from "@/lib/buttonStyles";
import Link from "next/link";

export default function Home() {
  return (
    <div>
      <SiteHeader />

      <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 pb-20 pt-14 lg:grid-cols-[1.05fr_0.95fr] lg:pt-20">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.22em] text-teal">Personalized movement coaching</p>
          <h1 className="mt-4 max-w-xl font-display text-5xl font-semibold leading-[1.02] tracking-tight md:text-6xl">
            Your best rep becomes your coach.
          </h1>
          <p className="mt-5 max-w-lg font-display text-xl text-white/70">See your movement. Understand your progress.</p>
          <p className="mt-4 max-w-lg text-sm leading-7 text-white/50">
            Turn an ordinary workout video into personalized movement insights. Compare each
            repetition with your own reference movement, notice how your technique changes, and train
            with clearer feedback.
          </p>
          <p className="mt-4 max-w-lg text-sm leading-6 text-white/80">Video coaching for barbell squats. Log sets and save video replays for other lifts.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/start" className={buttonClass("primary")}>
              Start Training
            </Link>
            <Link href="/record?demo=1" className={buttonClass("secondary")}>
              Explore GhostRep
            </Link>
          </div>
        </div>
        <HeroTwin />
      </section>

      <HowItWorks />
      <TwinShowcase />
      <FeatureGrid />

      <section className="mx-auto max-w-6xl px-5 pb-24">
        <div className="overflow-hidden rounded-[2rem] border border-white/8 bg-[linear-gradient(180deg,rgba(32,214,199,0.08),rgba(12,16,22,0.2))] px-8 py-14 text-center md:px-16">
          <h2 className="font-display text-3xl font-semibold tracking-tight md:text-4xl">
            Ready to see what every rep reveals?
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-sm leading-7 text-white/55">
            Make your next workout more informed, one repetition at a time.
          </p>
          <Link href="/start" className={buttonClass("primary", "mt-8")}>
            Start Training
          </Link>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
