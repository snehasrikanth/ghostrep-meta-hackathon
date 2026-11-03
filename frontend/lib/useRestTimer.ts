"use client";

import { restoreRest, type RestState } from "./rest";
import { useCallback, useEffect, useState } from "react";

/** Storage and rendered state are both scoped to one workout. */
export function useRestTimer(sessionId: string | null | undefined, status: string | null | undefined = "active", pausedAt?: string | null) {
  const key = sessionId ? "ghostrep.rest." + sessionId : null;
  const [state, setState] = useState<{key: string | null; rest: RestState}>({key: null, rest: null});
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      let next: RestState = null;
      try {
        next = restoreRest(key ? JSON.parse(localStorage.getItem(key) || "null") : null, status || "active", Date.now(), pausedAt);
        if (key) {
          if (next) localStorage.setItem(key, JSON.stringify(next));
          else localStorage.removeItem(key);
        }
      } catch { /* A malformed or unavailable local clock is discarded. */ }
      setState({key, rest: next});
    });
    return () => { active = false; };
  }, [key, status, pausedAt]);
  const update = useCallback((next: RestState) => {
    const rest = key ? restoreRest(next, status || "active", Date.now(), pausedAt) : null;
    setState({key, rest});
    if (!key) return;
    try {
      if (rest) localStorage.setItem(key, JSON.stringify(rest));
      else localStorage.removeItem(key);
    } catch { /* The in-page timer works without persistent storage. */ }
  }, [key, status, pausedAt]);
  const rest = state.key === key && ["active", "paused"].includes(status || "active") ? state.rest : null;
  return [rest, update] as const;
}
