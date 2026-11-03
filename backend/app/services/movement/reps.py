from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from scipy.signal import find_peaks
from app.services.movement.reliability import geometry_frames, reliable_side

from app.services.movement.geometry import knee_angle, relative_depth, torso_inclination_deg
from app.services.movement.signals import choose_side, interpolate_nans, moving_average, series


@dataclass
class DetectedRep:
    rep_id: int
    start_idx: int
    bottom_idx: int
    end_idx: int
    start_seconds: float
    bottom_seconds: float
    end_seconds: float
    descent_seconds: float
    ascent_seconds: float
    is_complete: bool
    confidence: float
    metrics: dict[str, float] = field(default_factory=dict)


def detect_squat_reps(frames: list[dict], min_depth: float = 0.18) -> tuple[list[DetectedRep], str]:
    """Detect down/up cycles independently of their depth relative to other reps.

    Prominence is body-relative, not a full-range requirement. Tracking gaps
    longer than 0.2 seconds split the signal instead of being interpolated.
    """
    if len(frames) < 8:
        return [], "right"
    frames = geometry_frames(frames)
    side, checks = reliable_side(frames)
    frames = [{**f, "_measurement_valid": checks[i]["valid"]} for i,f in enumerate(frames)]
    times = _monotonic_times(frames)
    hip, knee, ankle, shoulder = (f"{side}_{name}" for name in ("hip", "knee", "ankle", "shoulder"))
    valid = np.array([c["valid"] for c in checks])
    y = series(frames, hip, "y")
    detection_valid = np.array([c["detection_valid"] for c in checks])
    y[~detection_valid] = np.nan
    # Only isolated, brief holes may be bridged for boundary finding. Metrics
    # still retain the observed reliability and never use filled landmarks.
    i = 0
    gap_limit = max(.2, float(np.median(np.diff(times))) * 1.5)
    while i < len(y):
        if np.isfinite(y[i]):
            i += 1; continue
        start = i
        while i < len(y) and not np.isfinite(y[i]): i += 1
        if start > 0 and i < len(y) and times[i] - times[start-1] <= gap_limit:
            y[start:i] = np.interp(times[start:i], [times[start-1], times[i]], [y[start-1], y[i]])
    spans = []; start = None
    for i in range(len(y) + 1):
        good = i < len(y) and np.isfinite(y[i])
        if good and start is None: start = i
        if not good and start is not None:
            if i - start >= 8: spans.append((start, i))
            start = None
    reps = []
    for lo, hi in spans:
        sm = moving_average(y[lo:hi], 3)
        torso = []
        for f in frames[lo:hi]:
            lm=f["landmarks"]
            if shoulder in lm and hip in lm:
                a,b=lm[shoulder],lm[hip]
                torso.append(np.hypot((a["x"]-b["x"])*a.get("_aspect",1),a["y"]-b["y"]))
        scale = float(np.median(torso)) if torso else .2
        threshold = max(.018, .10 * scale)
        dt = max(.001, float(np.median(np.diff(times[lo:hi]))))
        peaks, _ = find_peaks(sm, prominence=threshold, distance=max(1, int(.55 / dt)))
        peaks = list(peaks)
        if len(sm) > 5 and sm[-1] - np.min(sm[-min(len(sm), int(3/dt)):]) > threshold and (not peaks or len(sm)-1-peaks[-1] > .6/dt):
            peaks.append(len(sm)-1)
        if len(sm) > 5 and sm[0] - np.min(sm[:min(len(sm), int(3/dt))]) > threshold:
            peaks.insert(0,0)
        for n, peak in enumerate(peaks):
            left = peaks[n-1] if n else 0
            right = peaks[n+1] if n+1 < len(peaks) else len(sm)-1
            begin = left + int(np.argmin(sm[left:peak+1]))
            end = peak + int(np.argmin(sm[peak:right+1]))
            baseline = min(float(sm[begin]),float(sm[end]))
            amplitude = float(sm[peak] - baseline)
            # Trim long standing pauses to the onset/return bands.
            band = max(.005, amplitude * .12)
            starts = np.where(sm[begin:peak+1] <= baseline + band)[0]
            if starts.size: begin += int(starts[-1])
            ends = np.where(sm[peak:end+1] <= baseline + band)[0]
            if ends.size: end = peak + int(ends[0])
            a,b,c = lo+begin,lo+peak,lo+end
            knees = [knee_angle(f["landmarks"][hip], f["landmarks"][knee], f["landmarks"][ankle])
                     for f in frames[a:c+1] if all(x in f["landmarks"] for x in (hip,knee,ankle))]
            if not knees or amplitude < threshold: continue
            bend = max(knees) - min(knees)
            if bend < 12: continue  # translation/straight-leg setup, not knee flexion
            smooth = moving_average(interpolate_nans(series(frames,hip,"y")),3)
            velocity = np.gradient(smooth,times)
            leg_height = float(np.nanmedian(series(frames[a:c+1],ankle,"y"))) - baseline
            # Tiny flexion plus tiny hip travel cannot distinguish setup from
            # intentional partial-range practice. Keep it visible as uncertain.
            ambiguous_range = min(knees) > 150 and bend < 30 and amplitude < min_depth * max(.05,leg_height)
            partial = ambiguous_range or begin == peak or end == peak or abs(sm[begin]-sm[end]) > max(.02, amplitude*.3)
            rep = _build_rep(frames,times,len(reps)+1,a,b,c,side,hip,knee,ankle,shoulder,
                             baseline,smooth,velocity,amplitude,force_incomplete=partial)
            valid_fraction = float(np.mean(valid[a:c+1]))
            eligible = rep.is_complete and valid_fraction >= .9 and all(np.isfinite(rep.metrics.get(key,np.nan)) for key in ("relative_depth","min_knee_angle_deg","max_torso_inclination_deg","smoothness"))
            if not eligible:
                for key in ["relative_depth", "min_knee_angle_deg", "max_torso_inclination_deg", "smoothness"]:
                    rep.metrics[key] = None
            rep.metrics["comparison_eligible"] = bool(eligible)
            rep.metrics["reliability"] = {"valid_fraction": valid_fraction, "issues": sorted({r for row in checks[a:c+1] for r in row["reasons"]})}
            near_gap=any(not row["detection_valid"] for row in checks[max(0,a-2):min(len(checks),c+3)])
            rep.metrics["movement_status"] = "complete" if rep.is_complete else "uncertain" if near_gap or ambiguous_range else "partial"
            if ambiguous_range:
                rep.metrics["reliability"]["issues"].append("small_flexion_could_be_setup_or_partial_range")
            rep.metrics["observed_range"] = "reduced" if min(knees) > 140 else "observed"
            reps.append(rep)
    return reps, side


def _initial_standing(hip_smooth: np.ndarray, knee_smooth: np.ndarray) -> tuple[float, float]:
    """Hip height and knee angle from upright frames before the first deep flexion."""
    deep = np.where(knee_smooth < 135)[0]
    upright = np.where(knee_smooth >= 155)[0]
    pool = upright[upright < deep[0]] if deep.size and upright.size else upright
    if pool.size >= 2:
        return float(np.median(hip_smooth[pool])), float(np.median(knee_smooth[pool]))
    return float(np.percentile(hip_smooth, 20)), float(np.nanpercentile(knee_smooth, 80))


def _has_upright_before_squat(timestamps: np.ndarray, knee_smooth: np.ndarray, velocity: np.ndarray) -> bool:
    """True when a quiet upright stance happens before the first deep knee bend.

    The opening frames of a slow squat can still show an extended knee. Those
    frames are already moving, so they are not a setup stance.
    """
    deep = np.where(knee_smooth < 140)[0]
    if deep.size == 0:
        return True
    run_start = None
    for i in range(int(deep[0])):
        quiet = knee_smooth[i] >= 155 and abs(float(velocity[i])) <= 0.012
        if quiet:
            if run_start is None:
                run_start = i
            elif float(timestamps[i] - timestamps[run_start]) >= 0.2:
                return True
        else:
            run_start = None
    return False


def _squat_amplitude(hip_smooth: np.ndarray, knee_smooth: np.ndarray, standing_y: float) -> float:
    flexed = hip_smooth[knee_smooth < 145]
    if flexed.size >= 3:
        return max(float(np.percentile(flexed, 70) - standing_y), 0.06)
    return max(float(np.percentile(hip_smooth, 90) - standing_y), 0.06)


def _knee_series(frames: list[dict], hip: str, knee: str, ankle: str) -> np.ndarray:
    values = []
    for frame in frames:
        lm = frame["landmarks"]
        if hip in lm and knee in lm and ankle in lm:
            values.append(knee_angle(lm[hip], lm[knee], lm[ankle]))
        else:
            values.append(np.nan)
    return moving_average(interpolate_nans(np.array(values, dtype=np.float64)), window=5)


def _rep_onset(
    i: int,
    descent_frames: int,
    hip_smooth: np.ndarray,
    knee_smooth: np.ndarray,
    timestamps: np.ndarray,
    standing_y: float,
    standing_knee: float,
    enter_drop: float,
) -> int:
    """Walk back to the last upright frame, but never across a long setup."""
    start = max(0, i - descent_frames)
    while start > 0:
        earlier = start - 1
        if timestamps[i] - timestamps[earlier] > 1.0:
            break
        still_up = hip_smooth[earlier] <= standing_y + enter_drop * 0.45 and knee_smooth[earlier] >= standing_knee - 5
        if still_up:
            break
        start = earlier
    return start


def _append_rep(
    reps: list[DetectedRep],
    frames: list[dict],
    timestamps: np.ndarray,
    start_i: int,
    bottom_i: int,
    end_i: int,
    side: str,
    hip: str,
    knee: str,
    ankle: str,
    shoulder: str,
    standing_y: float,
    hip_smooth: np.ndarray,
    velocity: np.ndarray,
    amplitude: float,
    force_incomplete: bool = False,
) -> None:
    start_i = int(np.clip(start_i, 0, len(frames) - 1))
    end_i = int(np.clip(end_i, start_i, len(frames) - 1))
    segment = hip_smooth[start_i : end_i + 1]
    if segment.size:
        bottom_i = start_i + int(np.argmax(segment))
    rep = _build_rep(
        frames, timestamps, len(reps) + 1, start_i, bottom_i, end_i,
        side, hip, knee, ankle, shoulder, standing_y, hip_smooth, velocity, amplitude,
        force_incomplete=force_incomplete,
    )
    min_knee = rep.metrics.get("min_knee_angle_deg", float("nan"))
    # Straight knees mean walkout or bar setup, not a squat.
    if not np.isfinite(min_knee) or min_knee > 140:
        return
    reps.append(rep)


def _build_rep(
    frames: list[dict],
    timestamps: np.ndarray,
    rep_id: int,
    start_i: int,
    bottom_i: int,
    end_i: int,
    side: str,
    hip: str,
    knee: str,
    ankle: str,
    shoulder: str,
    standing: float,
    hip_smooth: np.ndarray,
    velocity: np.ndarray,
    amplitude: float,
    force_incomplete: bool = False,
) -> DetectedRep:
    start_t = float(timestamps[start_i])
    bottom_t = float(timestamps[min(bottom_i, end_i)])
    end_t = float(timestamps[end_i])
    descent = max(0.0, bottom_t - start_t)
    ascent = max(0.0, end_t - bottom_t)
    pause = _bottom_pause(timestamps, hip_smooth, velocity, start_i, end_i, amplitude)
    complete = (
        not force_incomplete
        and descent >= 0.25
        and ascent >= 0.25
        and (end_t - start_t) >= 0.7
    )

    knees: list[float] = []
    torsos: list[float] = []
    depths: list[float] = []
    vis: list[float] = []
    for idx in range(start_i, end_i + 1):
        if not frames[idx].get("_measurement_valid", True):
            continue
        lm = frames[idx]["landmarks"]
        if hip in lm and knee in lm and ankle in lm:
            knees.append(knee_angle(lm[hip], lm[knee], lm[ankle]))
            depths.append(relative_depth(lm[hip]["y"], standing, lm[ankle]["y"]))
            vis.append(
                np.mean(
                    [
                        lm[hip].get("visibility", 0.0),
                        lm[knee].get("visibility", 0.0),
                        lm[ankle].get("visibility", 0.0),
                    ]
                )
            )
        if shoulder in lm and hip in lm:
            torsos.append(torso_inclination_deg(lm[shoulder], lm[hip]))

    knee_arr = np.array(knees, dtype=np.float64)
    torso_arr = np.array(torsos, dtype=np.float64)
    depth_arr = np.array(depths, dtype=np.float64)
    vis_arr = np.array(vis, dtype=np.float64) if vis else np.array([0.0])

    min_knee = float(np.nanmin(knee_arr)) if knee_arr.size else float("nan")
    max_torso = float(np.nanmax(torso_arr)) if torso_arr.size else float("nan")
    peak_depth = float(np.nanmax(depth_arr)) if depth_arr.size else 0.0
    smoothness = _smoothness(knee_arr)
    confidence = float(
        np.clip(
            0.45 * float(np.nanmean(vis_arr))
            + 0.25 * (1.0 if complete else 0.2)
            + 0.15 * (1.0 if peak_depth >= 0.2 else 0.4)
            + 0.15 * smoothness,
            0.0,
            1.0,
        )
    )
    return DetectedRep(
        rep_id=rep_id,
        start_idx=start_i,
        bottom_idx=bottom_i,
        end_idx=end_i,
        start_seconds=start_t,
        bottom_seconds=bottom_t,
        end_seconds=end_t,
        descent_seconds=descent,
        ascent_seconds=ascent,
        is_complete=complete,
        confidence=confidence,
        metrics={
            "min_knee_angle_deg": min_knee,
            "max_torso_inclination_deg": max_torso,
            "relative_depth": peak_depth,
            "duration_seconds": end_t - start_t,
            "smoothness": smoothness,
            "mean_visibility": float(np.nanmean(vis_arr)),
            "bottom_pause_seconds": pause,
        },
    )


def _monotonic_times(frames: list[dict]) -> np.ndarray:
    raw = np.array([float(f["timestamp"]) for f in frames], dtype=np.float64)
    if raw.size == 0:
        return raw
    out = raw.copy()
    for i in range(1, len(out)):
        if not np.isfinite(out[i]) or out[i] <= out[i - 1]:
            step = out[i - 1] - out[i - 2] if i > 1 else 1.0 / 15.0
            out[i] = out[i - 1] + max(step, 1e-3)
    return out


def _bottom_pause(
    timestamps: np.ndarray,
    hip_smooth: np.ndarray,
    velocity: np.ndarray,
    start_i: int,
    end_i: int,
    amplitude: float,
) -> float:
    if end_i <= start_i:
        return 0.0
    window = hip_smooth[start_i : end_i + 1]
    deepest = float(np.max(window))
    band = max(0.04 * amplitude, 0.008)
    pause = 0.0
    i = start_i
    while i <= end_i:
        near = abs(hip_smooth[i] - deepest) <= band and abs(velocity[i]) <= max(0.02, 0.08 * amplitude)
        if not near:
            i += 1
            continue
        j = i
        while j + 1 <= end_i and abs(hip_smooth[j + 1] - deepest) <= band and abs(velocity[j + 1]) <= max(0.02, 0.08 * amplitude):
            j += 1
        pause = max(pause, float(timestamps[j] - timestamps[i]))
        i = j + 1
    return pause


def _smoothness(signal: np.ndarray) -> float:
    finite = signal[np.isfinite(signal)]
    if finite.size < 4:
        return 0.4
    jerk = np.diff(finite, n=2)
    rms = float(np.sqrt(np.mean(jerk**2)))
    return float(np.clip(1.0 / (1.0 + 8.0 * rms), 0.0, 1.0))
