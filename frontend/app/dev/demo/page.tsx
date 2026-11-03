"use client";

import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

type Status = {
  available: boolean;
  active: boolean;
  seeded: boolean;
  can_return: boolean;
  display_name?: string | null;
};

export default function DevDemoPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.demoStatus().then(setStatus).catch(() => setStatus({ available: false, active: false, seeded: false, can_return: false }));
  }, []);

  async function enter() {
    setBusy(true);
    setError(null);
    try {
      await api.enterDemo();
      window.location.assign("/dashboard"); // eslint-disable-line @next/next/no-location-assign-relative-destination
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : "Could not open the demo account.");
    }
  }

  return (
    <AppShell>
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal">Development</p>
      <h1 className="mt-2 text-3xl font-semibold">Demo athlete switch</h1>
      <p className="mt-2 max-w-xl text-sm text-white/55">
        Jordan is a seeded development account with illustrative history. It is not the primary product experience and
        does not copy records into your account.
      </p>
      <Card className="mt-6 max-w-xl p-5">
        {!status?.available ? (
          <p className="text-sm text-white/50">Demo switching is disabled in this environment.</p>
        ) : status.active ? (
          <p className="text-sm text-white/60">You are already viewing the demo athlete. Use the bar above to return.</p>
        ) : !status.seeded ? (
          <p className="text-sm text-white/50">Seed the demo account first: <span className="font-mono text-white/70">uv run python -m app.demo seed</span></p>
        ) : (
          <>
            <p className="text-sm text-white/60">Open {status.display_name || "the demo athlete"} for local walkthroughs.</p>
            <Button className="mt-4" disabled={busy} onClick={enter}>
              {busy ? "Opening…" : "Open demo account"}
            </Button>
          </>
        )}
        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      </Card>
    </AppShell>
  );
}
