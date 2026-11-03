import { BrandLockup } from "@/components/brand/BrandLockup";
import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="border-t border-white/6">
      <div className="mx-auto grid max-w-6xl gap-8 px-5 py-12 md:grid-cols-[1.4fr_1fr_1fr]">
        <div>
          <BrandLockup compact />
          <p className="mt-3 max-w-sm text-sm leading-6 text-white/45">
            Your best rep becomes your coach.
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-white/35">Product</p>
          <div className="mt-3 flex flex-col gap-2 text-sm text-white/55">
            <a href="#how-it-works" className="hover:text-white">How it works</a>
            <a href="#features" className="hover:text-white">Features</a>
            <Link href="/start" className="hover:text-white">Start training</Link>
            <Link href="/dashboard" className="hover:text-white">Dashboard</Link>
          </div>
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-white/35">Notes</p>
          <p className="mt-3 text-sm leading-6 text-white/45">
            You can delete saved video replays. Provider deletion is requested after processing;
            automatic local expiry is not guaranteed. GhostRep is a training tool, not a medical device.
          </p>
        </div>
      </div>
    </footer>
  );
}
