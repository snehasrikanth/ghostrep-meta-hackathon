from __future__ import annotations

import numpy as np

from app.services.movement.reps import DetectedRep


def select_reference_rep(reps: list[DetectedRep]) -> DetectedRep | None:
    """Pick the best *observed* reference — not first, not deepest, not 'perfect form'."""
    complete = [r for r in reps if r.is_complete and r.metrics.get("comparison_eligible", True)]
    if not complete:
        return None

    depths = np.array([r.metrics.get("relative_depth", 0.0) for r in complete])
    durations = np.array([r.metrics.get("duration_seconds", 0.0) for r in complete])
    med_depth = float(np.median(depths))
    med_dur = float(np.median(durations))

    best: DetectedRep | None = None
    best_score = -1.0
    for rep in complete:
        depth = rep.metrics.get("relative_depth", 0.0)
        duration = rep.metrics.get("duration_seconds", 0.0)
        smoothness = rep.metrics.get("smoothness", 0.0)
        visibility = rep.metrics.get("mean_visibility", 0.0)
        rom_mid = 1.0 - min(1.0, abs(depth - med_depth) / 0.25)
        dur_mid = 1.0 - min(1.0, abs(duration - med_dur) / max(med_dur, 0.4))
        completeness = 1.0 if rep.is_complete else 0.2
        score = (
            0.25 * visibility
            + 0.20 * smoothness
            + 0.20 * completeness
            + 0.15 * rom_mid
            + 0.20 * dur_mid
        )
        # Prefer usable range of motion, but do not maximize depth.
        if depth < 0.16:
            score *= 0.6
        if score > best_score:
            best_score = score
            best = rep
    return best
