"""Upper-body angle to image vertical: magnitude and direction are separate facts."""
from __future__ import annotations

import math
import numpy as np
from app.services.movement.geometry import torso_inclination_deg

METHOD = "phase_aligned_image_vertical_v1"
DEADBAND_DEG = 3.0  # Noise tolerance heuristic, not a clinical threshold/confidence interval.


def _valid_point(p):
    try:
        return bool(p and p.get('_valid',True) and float(p.get('visibility',0))>=.35 and
            all(math.isfinite(float(p[k])) for k in ('x','y')) and math.isfinite(float(p.get('_aspect',1))) and float(p.get('_aspect',1))>0)
    except (TypeError,ValueError,KeyError):return False


def upper_body_comparison(aligned, shoulder: str, hip: str, *, eligible: bool = True) -> dict:
    deltas=[]; phases=[]; totals={p:aligned.phase.count(p) for p in ("descent","ascent")}
    for phase,cur,ref in zip(aligned.phase,aligned.current_points,aligned.reference_points):
        points=[track.get(name) for track in (cur,ref) for name in (shoulder,hip)]
        if not all(_valid_point(p) for p in points):
            continue
        a=torso_inclination_deg(cur[shoulder],cur[hip]); b=torso_inclination_deg(ref[shoulder],ref[hip])
        if not (math.isfinite(a) and math.isfinite(b) and 0<=a<90 and 0<=b<90):continue
        deltas.append(a-b);phases.append(phase)
    arr=np.asarray(deltas);coverage=len(arr)/max(len(aligned.phase),1)
    result={'method':METHOD,'unit':'degrees','magnitude_kind':'unsigned_root_mean_square',
            'rms_difference_deg':float(np.sqrt(np.mean(arr**2))) if len(arr) else None,
            'signed_mean_difference_deg':float(np.mean(arr)) if len(arr) else None,
            'sign_definition':'current angle from image vertical minus reference; positive is farther from vertical, not anatomical forward',
            'aggregation':'paired samples after descent/ascent alignment; direction requires agreement in both phases',
            'deadband_deg':DEADBAND_DEG,'valid_samples':len(arr),'aligned_samples':len(aligned.phase),
            'valid_fraction':coverage,'direction':'unavailable','reason':'Insufficient reliable aligned samples.',
            'phase_support':{}}
    supported=eligible and len(arr)>=8 and coverage>=.8
    for phase in ('descent','ascent'):
        values=arr[np.asarray(phases)==phase] if len(arr) else arr
        count=len(values);fraction=count/max(totals[phase],1)
        result['phase_support'][phase]={'valid_samples':count,'valid_fraction':fraction,
            'closer_fraction':float(np.mean(values < -DEADBAND_DEG)) if count else 0,
            'farther_fraction':float(np.mean(values > DEADBAND_DEG)) if count else 0,
            'within_deadband_fraction':float(np.mean(np.abs(values)<=DEADBAND_DEG)) if count else 0}
        supported=supported and count>=3 and fraction>=.8
    result["comparison_usable"]=bool(supported)
    if not supported:
        if not eligible:result['reason']='Current or reference repetition is not eligible for comparison.'
        return result
    support=list(result['phase_support'].values())
    if all(p['closer_fraction']>=.8 and p['farther_fraction']<=.05 for p in support):direction='closer_to_vertical'
    elif all(p['farther_fraction']>=.8 and p['closer_fraction']<=.05 for p in support):direction='farther_from_vertical'
    elif all(p['within_deadband_fraction']>=.8 for p in support):direction='similar'
    elif np.mean(arr < -DEADBAND_DEG)>=.1 and np.mean(arr > DEADBAND_DEG)>=.1:direction='mixed'
    else:direction='unavailable'
    result.update(direction=direction,reason='Direction varies across matched samples.' if direction=='mixed' else
                  'No consistent direction across both movement phases.' if direction=='unavailable' else
                  'Direction relative to image vertical is supported in both matched phases; not an anatomical or technique judgment.')
    return result
