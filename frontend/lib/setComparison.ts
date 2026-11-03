import type { Rep } from "./types";

/** Deep links replay only an owned, measured rep after its analysis is loaded. */
export function requestedComparisonEvidence(reps: Rep[], repParam: string | null, timeParam: string | null) {
  if (!repParam || timeParam == null || timeParam.trim() === "") return null;
  const id = Number(repParam), seconds = Number(timeParam);
  if (!Number.isInteger(id) || !Number.isFinite(seconds)) return null;
  const rep = reps.find(r => r.rep_id === id && r.is_complete && r.comparison_eligible !== false);
  if (!rep || seconds < rep.start_seconds || seconds > rep.end_seconds) return null;
  return {repId:id, seconds};
}
