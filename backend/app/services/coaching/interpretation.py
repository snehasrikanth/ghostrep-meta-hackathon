"""Canonical replay facts; free model prose cannot supply an angle's direction.

Projection is pure: historical payloads/decisions/measurements are never rewritten.
"""
from __future__ import annotations
import json
import math

VERSION='upper-body-v1'
NOTICE='Corrected measurement interpretation of stored coaching. Original text and decision history are retained; this is not a new model response.'
BLOCKED='Stored upper-body wording has not been validated against these measurements. Review the corrected interpretation; no new target change can be applied.'
PROVIDER_UNAVAILABLE='Personalized coaching was unavailable. This is a basic recommendation based on measured movement.'
CHANGES={'REDUCE_REPS','REDUCE_LOAD_CONSERVATIVELY','EXTEND_REST'}
INDEPENDENT={'relative_depth','ascent_duration','descent_duration'}
FIELDS={'relative_depth':'depth_difference_percent','ascent_duration':'ascent_duration_difference_percent',
        'descent_duration':'descent_duration_difference_percent','knee_angle':'knee_angle_rmse_deg','hip_path':'hip_rmse','similarity':'similarity'}
TEXT_FIELDS=('summary','reason','primary_cue','observations','confidence_notes','uncertainties','suggested_action','decision_basis')


def finite(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def angle_scope(payload,context):
    return any('torso_lean_difference_deg' in d or 'torso_angle_rmse_deg' in d for d in context.get('drift',[])) or any(o.get('metric')=='torso_inclination' for o in payload.get('observations',[]) if isinstance(o,dict))


def upper_body_statement(rep_id, point):
    fact=point.get('upper_body_comparison') or {}
    support=fact.get('phase_support') or {}
    validated=(fact.get('method')=='phase_aligned_image_vertical_v1' and fact.get('comparison_usable') is True and fact.get('valid_samples',0)>=8 and fact.get('valid_fraction',0)>=.8 and all(support.get(p,{}).get('valid_samples',0)>=3 and support.get(p,{}).get('valid_fraction',0)>=.8 for p in ('descent','ascent')))
    direction=fact.get('direction') if validated else 'unavailable'
    if direction=='closer_to_vertical':return f"Rep {rep_id}'s upper body was closer to vertical than your reference across matched movement phases."
    if direction=='farther_from_vertical':return f"Rep {rep_id}'s upper body was farther from vertical than your reference across matched movement phases."
    if direction=='mixed':return f"Rep {rep_id}'s upper body was closer to vertical at some matched points and farther at others."
    if direction=='similar':return f"Rep {rep_id}'s upper-body angle stayed close to your reference."
    return f"Rep {rep_id}'s upper-body angle differed from your reference."


def _observation(metric,rep,point,times):
    rid=rep['rep_id'];value=None
    if metric=='torso_inclination':
        value=point.get('torso_angle_rmse_deg',point.get('torso_lean_difference_deg'))
        fact=point.get("upper_body_comparison") or {}
        if fact.get('method')=='phase_aligned_image_vertical_v1':value=fact.get('rms_difference_deg')
        if not finite(value) or value<0 or (fact.get("method")=="phase_aligned_image_vertical_v1" and fact.get("comparison_usable") is False):return None
        text=upper_body_statement(rid,point)
    elif metric in FIELDS:
        value=point.get(FIELDS[metric])
        if not finite(value):return None
        if metric=='relative_depth':text=f"Rep {rid} reached about {abs(value):.0f}% {'less' if value<0 else 'more'} relative squat depth than your reference."
        elif metric in {'ascent_duration','descent_duration'}:
            phase='stand up' if metric=='ascent_duration' else 'lower down'
            text=f"Rep {rid} took about {abs(value):.0f}% {'longer' if value>=0 else 'less time'} to {phase} than your reference."
        elif metric=='knee_angle':text=f"Rep {rid}'s knee-angle movement differed from your reference."
        elif metric=='hip_path':text=f"Rep {rid}'s hip movement differed from your reference."
        else:text=f"Rep {rid}'s measured movement was compared with your personal reference; this is not a technique score."
    else:return None
    return {'metric':metric,'rep_id':rid,'statement':text,'evidence_seconds':times,'magnitude':value}


def canonical_observations(payload,context):
    reps=context.get('reps') or [];points={d.get('rep_id'):d for d in context.get('drift') or [] if d.get('comparison_valid') is not False}
    out=[];seen=set()
    for raw in payload.get('observations') or []:
        if not isinstance(raw,dict):continue
        metric=raw.get('metric');times=[t for t in raw.get('evidence_seconds') or [] if finite(t)]
        if metric=='camera_quality':
            if (context.get('quality') or {}).get('usable') is False:
                out.append({'metric':metric,'statement':'Recording quality limits this comparison. Review the recording before changing targets.','evidence_seconds':[],'magnitude':None})
            continue
        # Rep identity comes from evidence windows, not the model's prose.
        eligible=[r for r in reps if r.get('comparison_eligible') is not False]
        strict=[r for r in eligible if any(r['start_seconds']<=t<=r['end_seconds'] for t in times)]
        candidates=strict or [r for r in eligible if any(r['start_seconds']-.25<=t<=r['end_seconds']+.25 for t in times)]
        rep=next((r for r in candidates if r['rep_id']==raw.get('rep_id')), candidates[0] if candidates else None)
        if not rep or rep['rep_id']==context.get('reference_rep'):continue
        point=points.get(rep['rep_id'])
        if not point:continue
        times=[t for t in times if rep['start_seconds']-.25<=t<=rep['end_seconds']+.25]
        key=(metric,rep['rep_id'])
        item=_observation(metric,rep,point,times)
        if item and key not in seen:out.append(item);seen.add(key)
    return out


def canonicalize(payload,context):
    if not angle_scope(payload,context):return dict(payload)
    out=dict(payload);observations=canonical_observations(payload,context)
    mechanical=[o for o in observations if o['metric'] in {'torso_inclination','relative_depth','ascent_duration','descent_duration','knee_angle'}]
    if mechanical:
        focus=max(mechanical,key=lambda o:abs(o.get('magnitude') or 0))
        observations=[focus]+[o for o in observations if o is not focus]
    action=payload.get('suggested_action');basis=payload.get('decision_basis')
    rpe=context.get('reported_rpe');effort=finite(rpe) and rpe>=9.5
    def independent_support(o):
        value=o.get('magnitude')
        if not finite(value) or o['metric']!=basis:return False
        return (basis=='relative_depth' and value<=-8) or (basis=='ascent_duration' and value>=15) or (basis=='descent_duration' and abs(value)>=20)
    supported=any(independent_support(o) for o in observations)
    if action=='EXTEND_REST' and effort:basis='reported_effort';supported=True
    if action in CHANGES and not supported:
        action='NO_RECOMMENDATION';basis='unavailable'
        out.update(actionable=False,state='review_only',action_blocked_reason='Upper-body angle difference alone does not support changing reps, load or rest.')
    if action=='KEEP_PLAN' and effort:
        action='EXTEND_REST';basis='reported_effort'
        if payload.get('current_rest_seconds') is not None:out['suggested_rest_seconds']=min(300,payload['current_rest_seconds']+30)
    if action=='KEEP_PLAN':reason='Differences from your own reference do not establish incorrect posture. Keep the current workout targets.'
    elif action in CHANGES and basis=='reported_effort':reason='Rest is extended because you reported very high effort (RPE), independently of upper-body angle differences.'
    elif action in CHANGES:
        supported_text=next(o['statement'] for o in observations if o['metric']==basis)
        reason='The proposed adjustment is based on this independent measurement: '+supported_text+' Review the target before using it.'
    elif action=='STOP_AND_SEEK_PROFESSIONAL_ADVICE':reason='A declared limitation requires individual professional guidance. No training adjustment is proposed here.'
    elif action=='REQUEST_NEW_RECORDING':reason='A clearer recording is needed before changing targets.'
    else:reason='Review the replay before changing targets. Upper-body angle difference alone does not justify a rep or load reduction.'
    out.update(interpretation_version=VERSION,observations=observations,
        summary=' '.join(o['statement'] for o in observations[:3]) or 'No supported movement difference was established from the available evidence.',
        primary_cue=None,reason=reason,
        suggested_action=action,decision_basis=basis,
        evidence_references=sorted({t for o in observations for t in o['evidence_seconds']}),
        confidence_notes=['Upper-body difference is an unsigned phase-aligned RMS magnitude. Direction, when available, describes image vertical only. A personal reference is not an ideal-form standard.'],
        uncertainties=['Differences alone do not establish incorrect posture, deterioration or a need to change upper-body lean.']+
            ([PROVIDER_UNAVAILABLE] if PROVIDER_UNAVAILABLE in (payload.get('uncertainties') or []) else []))
    if 'explanation' in out:out['explanation']=reason
    if action in {'NO_RECOMMENDATION','KEEP_PLAN','REQUEST_NEW_RECORDING','STOP_AND_SEEK_PROFESSIONAL_ADVICE'}:
        for suggested,current in [('suggested_reps','current_reps'),('suggested_load_kg','current_load_kg'),('suggested_rest_seconds','current_rest_seconds')]:out[suggested]=payload.get(current)
    return out


def record_context(rec):
    from app.services.coaching.prescription import coach_input_targets
    a=rec.analysis
    return {'quality':json.loads(a.quality_json) if a else {},'drift':json.loads(a.drift_json) if a else [],
        'reference_rep':a.reference_rep if a else None,
        'reps':[{'rep_id':r.rep_index,'start_seconds':r.start_seconds,'bottom_seconds':r.bottom_seconds,'end_seconds':r.end_seconds,
                 'descent_seconds':r.descent_seconds,'ascent_seconds':r.ascent_seconds,
                 'comparison_eligible':json.loads(r.metrics_json).get('comparison_eligible',r.is_complete)} for r in rec.reps if r.is_complete],
        'reported_rpe':rec.reported_rpe,**coach_input_targets(rec)}


def interpretation_problem(payload,context):
    if not angle_scope(payload,context):return None
    projected=canonicalize(payload,context)
    # Older guarded results put the first canonical observation in primary_cue.
    # Accept only that exact legacy value; do not invalidate a legitimate saved
    # decision merely because presentation no longer calls an observation a cue.
    legacy_cue = projected['observations'][0]['statement'] if projected['observations'] else None
    cue_valid = payload.get('primary_cue') in (None, legacy_cue)
    if payload.get('interpretation_version')!=VERSION or not cue_valid or any(payload.get(k)!=projected.get(k) for k in TEXT_FIELDS if k!='primary_cue'):return BLOCKED
    return None


def display_interpretation(payload,context):
    problem=interpretation_problem(payload,context)
    out=canonicalize(payload,context)
    if problem:
        out.update(historical_interpretation_corrected=True,interpretation_notice=NOTICE,
            actionable=False,can_activate=False,state='review_only',action_blocked_reason=problem,activation_blocked_reason=problem,
            historical_decision_action=payload.get('suggested_action'),suggested_action='NO_RECOMMENDATION')
        # Preserve actual accepted/rejected decisions and applied deltas; don't offer an old future target.
        for suggested,current in [('suggested_reps','current_reps'),('suggested_load_kg','current_load_kg'),('suggested_rest_seconds','current_rest_seconds')]:out[suggested]=payload.get(current)
    return out
