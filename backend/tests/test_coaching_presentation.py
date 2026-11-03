"""Fictional structured facts; no model inference or private media."""
import copy
from types import SimpleNamespace
from app.services.coaching.evidence import ground_coaching
from app.services.coaching.interpretation import canonicalize,display_interpretation,interpretation_problem
from app.services.coaching.presentation import presentation_contract,validate_explanation_selection
from app.services.meta.contracts import parse_coaching_payload,build_coaching_messages,build_coaching_model_input,coaching_response_format
from tests.test_upper_body_interpretation import context,wrong


def effort_result():
 ctx=context(other={'ascent_duration_difference_percent':20});ctx['reported_rpe']=10
 body=wrong(suggested_action='EXTEND_REST',decision_basis='reported_effort',current_rest_seconds=180,suggested_rest_seconds=210,
   explanation_id='effort_rest',explanation_evidence_ids=[],user_decision='pending',actionable=True)
 return ctx,canonicalize(body,ctx)


def test_effort_is_the_explanation_basis_independent_of_larger_angle_or_timing_difference():
 ctx,body=effort_result();wire=presentation_contract(SimpleNamespace(reported_rpe=10),body,ctx)
 assert wire['explanation_key']=='effort_rest' and wire['decision_basis']=='reported_effort'
 assert wire['reported_effort']==10 and wire['explanation_source']=='validated_model_selection'
 assert body['suggested_rest_seconds']==210 and body['primary_cue'] is None
 assert 'statement' not in str(wire['evidence'])


def test_exact_old_guarded_observation_cue_remains_compatible_without_becoming_an_instruction():
 ctx,body=effort_result();body['primary_cue']=body['observations'][0]['statement'];snapshot=copy.deepcopy(body)
 assert interpretation_problem(body,ctx) is None
 out=display_interpretation(body,ctx);assert out['suggested_action']=='EXTEND_REST' and out['actionable'] is True
 assert out['primary_cue'] is None and body==snapshot
 body['primary_cue']='Brace better because your technique is poor'
 assert interpretation_problem(body,ctx)


def test_unsupported_explanation_selection_never_requests_another_model_call_or_overrides_action():
 ctx,body=effort_result()
 for changes in [{'explanation_id':'keep_targets'},{'explanation_evidence_ids':['relative_depth:r999']},{'explanation_id':'brace_better'},{'decision_basis':'relative_depth'}]:
  bad={**body,**changes};original=copy.deepcopy(bad)
  assert validate_explanation_selection(bad,ctx) is None
  wire=presentation_contract(SimpleNamespace(reported_rpe=10),bad,ctx)
  assert wire['explanation_source']=='deterministic' and wire['explanation_key']=='effort_rest'
  assert bad==original


def test_timing_selection_requires_valid_metric_rep_evidence_not_prose():
 ctx=context(other={'ascent_duration_difference_percent':20})
 body=canonicalize(wrong(suggested_action='REDUCE_REPS',decision_basis='ascent_duration',
  observations=[{'metric':'ascent_duration','statement':'Perfect form with stronger bracing','evidence_seconds':[8.0],'magnitude':20}],
  explanation_id='timing_change',explanation_evidence_ids=['ascent_duration:r3']),ctx)
 assert validate_explanation_selection(body,ctx)=={'id':'timing_change','evidence_ids':['ascent_duration:r3']}
 assert 'Perfect' not in str(body) and body['primary_cue'] is None
 for ids in [[],['ascent_duration:r6'],['relative_depth:r3']]:assert validate_explanation_selection({**body,'explanation_evidence_ids':ids},ctx) is None


def test_existing_muse_request_carries_bounded_selection_and_original_durations_without_new_request():
 ctx=context();ctx['reps'][0].update(ascent_seconds=.8,descent_seconds=1.2)
 before=copy.deepcopy(ctx);wire=build_coaching_model_input(ctx)
 assert wire['repetitions'][0]['ascent_seconds']==.8 and wire['repetitions'][0]['descent_seconds']==1.2
 assert 'effort_rest' in wire['explanation_options']
 assert 'primary_cue to null' in build_coaching_messages(ctx)[0]['content']
 schema=coaching_response_format()['json_schema']['schema'];assert set(schema['required'])==set(schema['properties'])
 assert ctx==before


def test_model_claims_cannot_supply_a_technique_instruction_and_legacy_contract_is_accepted():
 ctx=context();raw={'summary':'A strong ideal rep proves perfect technique','observations':[], 'uncertainties':[],
  'suggested_action':'KEEP_PLAN','explanation':'Brace better','primary_cue':'Brace better','decision_basis':'keep',
  'suggested_reps':8,'suggested_rest_seconds':120,'suggested_load_kg':40}
 body=parse_coaching_payload(raw,ctx);out=ground_coaching(body,ctx,{})
 assert out['primary_cue'] is None and 'strong ideal' not in str(out) and 'Brace better' not in str(out)
 assert out['suggested_action']=='KEEP_PLAN'


def test_historical_or_unreliable_results_keep_their_review_only_contract():
 ctx,body=effort_result()
 body.update(historical_interpretation_corrected=True,user_decision='accepted',applied_change={'applied':True})
 assert presentation_contract(SimpleNamespace(reported_rpe=10),body,ctx)['review_only'] is True
 body.update(decision_basis='unavailable_measurement',actionable=False,user_decision='pending')
 assert presentation_contract(SimpleNamespace(reported_rpe=10),body,ctx)['measurement_uncertain'] is True


def test_model_can_select_a_different_supported_explanation_focus_not_just_an_unused_label():
 ctx,body=effort_result();body.update(explanation_id='effort_scope',suggested_reps=body['current_reps'])
 wire=presentation_contract(SimpleNamespace(reported_rpe=10),body,ctx)
 assert wire['explanation_key']=='effort_scope' and wire['explanation_source']=='validated_model_selection'
 assert validate_explanation_selection({**body,'suggested_reps':6},ctx) is None
 assert validate_explanation_selection({**body,'current_reps':None},ctx) is None
