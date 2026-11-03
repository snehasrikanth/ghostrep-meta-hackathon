"use client";

import { AppShell } from "@/components/layout/AppShell";
import { ApiError, api } from "@/lib/api";
import { startDestination } from "@/lib/training";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function StartPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const hasProfile = await api.getProfile().then(
        () => true,
        (err) => {
          if (err instanceof ApiError && err.status === 404) return false;
          throw err;
        },
      );
      const [current, next] = hasProfile
        ? await Promise.all([api.currentSession(), api.nextWorkout()])
        : [{ session: null }, { plan: null }];
      if (!cancelled) router.replace(startDestination({ hasProfile, current: current.session, next: next.plan }));
    })().catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not load your training."));
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <AppShell>
      {error ? (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      ) : (
        <p role="status" className="text-base text-white/85">
          Finding your next workout…
        </p>
      )}
    </AppShell>
  );
}
