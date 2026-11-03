"""Read-only, bounded explanations. Model prose never authorizes a training action."""
from app.services.coaching.interpretation import canonical_observations, finite

def evidence_id(observation):
    return f"{observation['metric']}:r{observation['rep_id']}" if observation.get('rep_id') is not None else None


def explanation_key(payload, context, observations):
    action = payload.get('suggested_action')
    basis = payload.get('decision_basis')
    effort = context.get('reported_rpe')
    if action == 'EXTEND_REST' and finite(effort) and effort >= 9.5:
        return 'effort_rest', 'reported_effort'
    if action in {'EXTEND_REST', 'REDUCE_REPS', 'REDUCE_LOAD_CONSERVATIVELY'}:
        if basis in {'ascent_duration', 'descent_duration'} and any(o['metric'] == basis for o in observations):
            return 'timing_change', basis
        if basis == 'relative_depth' and any(o['metric'] == basis for o in observations):
            return 'range_change', basis
    return ('keep_targets', 'keep') if action == 'KEEP_PLAN' else ('review_evidence', 'unavailable')


def validate_explanation_selection(payload, context):
    """Optional selection in the existing Muse response; invalid choices just fall back.

    Exact clauses are rendered from trusted fields. No keyword classifier can
    safely certify arbitrary model claims about bracing, fatigue or ideal form.
    """
    observations = canonical_observations(payload, context)
    key, basis = explanation_key(payload, context, observations)
    ids = payload.get('explanation_evidence_ids') or []
    allowed = {evidence_id(o) for o in observations if o['metric'] == basis}
    selected = payload.get('explanation_id')
    compatible = selected == key or (selected == 'effort_scope' and key == 'effort_rest'
        and finite(payload.get('current_reps')) and payload.get('current_reps') == payload.get('suggested_reps'))
    if not compatible or payload.get('decision_basis') != basis:
        return None
    if not isinstance(ids, list) or any(not isinstance(i, str) or i not in allowed for i in ids):
        return None
    if key in {'timing_change', 'range_change'} and not ids:
        return None
    return {'id': selected, 'evidence_ids': ids}


def presentation_contract(rec, payload, context):
    """Current facts/status plus a validated focus; never mutates stored responses."""
    observations = canonical_observations(payload, context)
    key, basis = explanation_key(payload, context, observations)
    selection = validate_explanation_selection(payload, context)
    return {
        'version': 'set-decision-v1', 'decision_basis': basis,
        'explanation_key': selection['id'] if selection else key,
        'explanation_source': 'validated_model_selection' if selection else 'deterministic',
        'reported_effort': rec.reported_rpe,
        'evidence': [{'id': evidence_id(o), 'rep_id': o['rep_id'], 'seconds': o['evidence_seconds'][0]}
                     for o in observations if evidence_id(o) and o.get('evidence_seconds')],
        'observations': observations,
        'review_only': bool(payload.get('historical_interpretation_corrected')) or (payload.get('actionable') is False and payload.get('user_decision') == 'pending'),
        'measurement_uncertain': payload.get('decision_basis') == 'unavailable_measurement' or (context.get('quality') or {}).get('comparison_usable') is False or (context.get('quality') or {}).get('usable') is False,
    }
