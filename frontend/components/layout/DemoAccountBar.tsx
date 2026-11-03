"use client";

import { buttonClass } from "@/lib/buttonStyles";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

type Status = {
  available: boolean;
  active: boolean;
  seeded: boolean;
  can_return: boolean;
};

export function DemoAccountBar() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.demoStatus().then(setStatus).catch(() => setStatus({ available: false, active: false, seeded: false, can_return: false }));
  }, []);

  async function leave() {
    setBusy(true);
    setError(null);
    try {
      await api.exitDemo();
      window.location.assign("/dashboard"); // eslint-disable-line @next/next/no-location-assign-relative-destination
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : "Could not return to your account.");
    }
  }

  if (!status?.available || !status.active) return null;

  return (
    <div className="border-b border-white/8 bg-white/[0.03]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-5 py-2 text-sm">
        <p className="text-white/80">
          <span className="rounded-full border border-white/15 px-2 py-0.5 font-medium uppercase tracking-[0.14em] text-white/80">
            Demo account
          </span>
          <span className="ml-2">Illustrative training history. This is not the primary product experience.</span>
        </p>
        <button className={buttonClass("ghost", "min-h-11 px-3 py-1 text-sm")} disabled={busy} onClick={leave}>
          {busy ? "Returning…" : "Back to my account"}
        </button>
        {error && <p className="w-full text-red-400">{error}</p>}
      </div>
    </div>
  );
}
