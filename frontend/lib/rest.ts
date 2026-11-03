export type RestState = {
  label: string;
  endsAt: number;
  total: number;
  pausedRemainingMs?: number;
} | null;

/** Preserve a session's clock through refresh, pause and resume. */
export function restoreRest(rest: RestState, status: string, now: number, pausedAt?: string | null): RestState {
  if (!rest || !["active", "paused"].includes(status) || typeof rest.label !== "string" ||
      !Number.isFinite(rest.endsAt) || !Number.isFinite(rest.total) || rest.total <= 0) return null;
  if (rest.pausedRemainingMs != null && (!Number.isFinite(rest.pausedRemainingMs) || rest.pausedRemainingMs < 0)) return null;
  if (status === "paused") {
    const pauseTime = pausedAt ? Date.parse(pausedAt) : now;
    return {...rest, pausedRemainingMs: rest.pausedRemainingMs ??
      Math.max(0, rest.endsAt - (Number.isFinite(pauseTime) ? Math.min(now, pauseTime) : now))};
  }
  if (rest.pausedRemainingMs != null) {
    return {label: rest.label, total: rest.total, endsAt: now + rest.pausedRemainingMs};
  }
  return rest.endsAt > now - 15 * 60_000 ? rest : null;
}

export function extendRest(rest: NonNullable<RestState>): NonNullable<RestState> {
  return {...rest, endsAt: rest.endsAt + 15_000, total: rest.total + 15,
    ...(rest.pausedRemainingMs != null ? {pausedRemainingMs: rest.pausedRemainingMs + 15_000} : {})};
}
