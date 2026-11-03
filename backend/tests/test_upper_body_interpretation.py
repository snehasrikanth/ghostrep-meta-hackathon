"""Generated geometry and fictional route data; never private recording fixtures."""
import copy
import json
import math
import numpy as np
import pytest
from app.services.movement.alignment import AlignedPair
from app.services.movement.upper_body import upper_body_comparison
from app.services.coaching.evidence import ground_coaching
from app.services.coaching.interpretation import canonicalize,display_interpretation
from app.services.meta.contracts import build_coaching_model_input


def pose(angle,aspect=.5625):
    a=math.radians(angle)
    return {'right_shoulder':{'x':.5+.2*math.sin(a)/aspect,'y':.65-.2*math.cos(a),'visibility':.99,'_aspect':aspect,'_valid':True},
            'right_hip':{'x':.5,'y':.65,'visibility':.99,'_aspect':aspect,'_valid':True}}


def paired(current,reference):
    n=len(current);return AlignedPair(np.linspace(0,1,n),['descent']*(n//2)+['ascent']*(n-n//2),[pose(a) for a in current],[pose(a) for a in reference])


def fact(current,reference):return upper_body_comparison(paired(current,reference),'right_shoulder','right_hip')


def context(body=None,legacy=False,other=None):
    point={'rep_id':3,'comparison_valid':True,'torso_lean_difference_deg':30,'similarity':40}
    if not legacy:point['upper_body_comparison']=body or fact([10]*20,[40]*20)
    if other:point.update(other)
    return {'quality':{'usable':True,'comparison_usable':True},'reference_rep':6,'drift':[point],
        'reps':[{'rep_id':3,'start_seconds':7,'bottom_seconds':8,'end_seconds':9,'comparison_eligible':True}],
        'profile':{},'reported_rpe':7,'current_reps':8,'current_rest':120,'current_load':40}


def wrong(**overrides):
    return {'source':'muse_spark','summary':'Rep 3 had incorrect posture with more forward lean.',
        'reason':'Lean farther forward to avoid deterioration. Reduce reps because of this lean.',
        'primary_cue':'Lean farther forward.', 'suggested_action':'REDUCE_REPS','suggested_reps':6,
        'suggested_load_kg':40,'suggested_rest_seconds':120,'current_reps':8,'current_rest_seconds':120,'current_load_kg':40,
        'observations':[{'metric':'torso_inclination','statement':'Rep 3 showed more forward lean.','evidence_seconds':[8.0],'magnitude':30}],
        'confidence_notes':['More upright is incorrect posture.'],'uncertainties':[],**overrides}


@pytest.mark.parametrize('current,reference,direction,sign',[(10,40,'closer_to_vertical',-1),(40,10,'farther_from_vertical',1)])
def test_opposite_directions_have_identical_unsigned_magnitude(current,reference,direction,sign):
    out=fact([current]*20,[reference]*20)
    assert out['rms_difference_deg']==pytest.approx(30)
    assert out['signed_mean_difference_deg']==pytest.approx(sign*30)
    assert out['direction']==direction and out['valid_samples']==20
    assert out['phase_support']['descent']['valid_samples']==10


def test_mixed_phase_changes_do_not_become_one_direction():
    out=fact([10]*10+[50]*10,[30]*20)
    assert out['direction']=='mixed' and out['signed_mean_difference_deg']==pytest.approx(0,abs=1e-5)
    out=ground_coaching(wrong(),context(out),{})
    assert 'some matched points' in out['observations'][0]['statement']
    assert 'more forward' not in json.dumps(out)


@pytest.mark.parametrize('failure',['missing','unreliable','too_few','ineligible'])
def test_insufficient_reliable_pairs_cannot_supply_direction(failure):
    a=paired([10]*20,[40]*20)
    if failure=='missing':
        for p in a.current_points[:7]:p.pop('right_shoulder')
    if failure=='unreliable':
        for p in a.reference_points[:7]:p['right_hip']['_valid']=False
    if failure=='too_few':a=paired([10]*6,[40]*6)
    out=upper_body_comparison(a,'right_shoulder','right_hip',eligible=failure!='ineligible')
    assert out['direction']=='unavailable' and out['comparison_usable'] is False
    projected=ground_coaching(wrong(),context(out),{})
    assert projected['suggested_action']=='NO_RECOMMENDATION'
    assert projected['observations']==[]


def test_unsigned_legacy_magnitude_is_neutral_not_signed():
    out=ground_coaching(wrong(),context(legacy=True),{})
    assert out['observations'][0]['statement']=="Rep 3's upper-body angle differed from your reference."
    assert out['observations'][0]['evidence_seconds']==[8]
    assert out['suggested_action']=='NO_RECOMMENDATION'
    wire=build_coaching_model_input(context(legacy=True))
    assert 'torso_lean_difference_deg' not in wire['comparisons'][0]
    assert wire['comparisons'][0]['upper_body_comparison']['direction']=='unavailable'


def test_wrong_muse_prose_is_replaced_in_every_display_field_not_just_observations():
    out=ground_coaching(wrong(),context(),{})
    for forbidden in ['more forward','farther forward','incorrect posture with','avoid deterioration']:
        assert forbidden not in json.dumps(out)
    assert 'closer to vertical' in out['summary'] and out['primary_cue'] is None
    assert out['suggested_action']=='NO_RECOMMENDATION' and out['actionable'] is False
    assert out['suggested_reps']==8 and out['suggested_load_kg']==40


def test_prose_cannot_smuggle_angle_claim_using_a_different_metric():
    ctx=context(other={'ascent_duration_difference_percent':20})
    out=ground_coaching(wrong(observations=[{'metric':'ascent_duration','statement':'Rep 3 leaned farther forward.','evidence_seconds':[8],'magnitude':20}]),ctx,{})
    assert 'forward' not in json.dumps(out)
    assert 'longer to stand up' in out['summary']
    assert out['suggested_action']=='NO_RECOMMENDATION'  # no independent structured reason supplied


def test_legitimate_independent_timing_reason_and_keep_plan_remain_usable():
    ctx=context(other={'ascent_duration_difference_percent':20})
    payload=wrong(observations=[{'metric':'ascent_duration','statement':'Rep 3 took longer.','evidence_seconds':[8],'magnitude':20}],decision_basis='ascent_duration')
    out=ground_coaching(payload,ctx,{})
    assert out['suggested_action']=='REDUCE_REPS' and out['suggested_reps']==6
    assert 'independent measurement' in out['reason']
    keep=ground_coaching(wrong(suggested_action='KEEP_PLAN'),ctx,{})
    assert keep['suggested_action']=='KEEP_PLAN' and keep['suggested_reps']==8


def test_historical_projection_preserves_original_evidence_and_decision_history():
    original=wrong(user_decision='accepted',applied_change={'applied':True,'action':'REDUCE_REPS','before':{'target_reps':8},'after':{'target_reps':6}})
    snapshot=copy.deepcopy(original)
    out=display_interpretation(original,context(legacy=True))
    assert original==snapshot
    assert out['historical_interpretation_corrected'] and out['user_decision']=='accepted'
    assert out['applied_change']==original['applied_change']
    assert not out['actionable'] and not out['can_activate']
    assert 'more forward' not in json.dumps(out)


def test_historical_routes_cannot_accept_or_activate_wrong_direction_even_with_valid_context():
    from app.database import SessionLocal
    from app.models.entities import RecordedSet,CoachingVersion
    from app.services.coaching.compatibility import recommendation_context
    from tests.test_coaching_decision import _start_recording_fixture,_squat_targets
    client,plan_id,_,set_id=_start_recording_fixture()
    try:
        targets=_squat_targets(plan_id)
        with SessionLocal() as db:
            rec=db.get(RecordedSet,set_id);r=next(r for r in rec.reps if r.is_complete and not r.is_reference)
            # A valid legacy unsigned comparison, unmodified measurements.
            bad=wrong(current_reps=targets['target_reps'],current_rest_seconds=targets['rest_seconds'],current_load_kg=targets['suggested_load_kg'],suggested_reps=targets['target_reps']-2,
                observations=[{'metric':'torso_inclination','statement':'More forward lean; reduce reps.','evidence_seconds':[r.bottom_seconds],'magnitude':10}])
            bad['recommendation_context']=recommendation_context(rec)
            rec.coaching.payload_json=json.dumps(bad);rec.coaching.summary=bad['summary'];rec.coaching.reason=bad['reason'];rec.coaching.proposed_action='REDUCE_REPS'
            row=CoachingVersion(set_id=set_id,source='muse_spark',source_label='Stored protocol test',proposed_action='REDUCE_REPS',summary=bad['summary'],reason=bad['reason'],payload_json=json.dumps(bad),artifact_id='fictional-direction',verified=True,context_json=json.dumps(recommendation_context(rec)))
            db.add(row);db.flush();version_id=row.id;original=rec.coaching.payload_json;db.commit()
        out=client.get('/coaching/'+set_id).json()
        assert out['actionable'] is False and out['historical_interpretation_corrected']
        assert 'more forward' not in json.dumps(out)
        assert not out['stored_versions'][0]['can_activate']
        identity={'recommendation_id':out['id'],'expected_revision':out['revision']}
        assert client.post('/coaching/'+set_id+'/decision',json={**identity,'decision':'accepted'}).status_code==409
        assert client.post(f'/coaching/{set_id}/versions/{version_id}/activate',json=identity).status_code==409
        assert _squat_targets(plan_id)==targets
        with SessionLocal() as db:assert db.get(RecordedSet,set_id).coaching.payload_json==original
    finally:client.__exit__(None,None,None)


def test_wrong_muse_response_passes_through_real_provider_grounding_with_mock_transport(tmp_path):
    from app.config import Settings
    from app.services.meta.muse import MuseProvider
    from app.services.meta.gateway import MetaGateway
    from tests.test_meta_offline import FakeTransport
    raw=wrong();wire={k:raw[k] for k in ['summary','observations','uncertainties','suggested_action','suggested_reps','suggested_rest_seconds','suggested_load_kg','primary_cue']}
    wire['explanation']=raw['reason']
    transport=FakeTransport(content=json.dumps(wire))
    settings=Settings(_env_file=None,data_dir=tmp_path,coaching_provider='meta_live',enable_meta_api=True,model_api_key='fictional-key',meta_require_explicit_approval=False,meta_max_retries=0)
    out=MuseProvider(settings,MetaGateway(settings),transport).generate_coaching(context())
    assert len(transport.calls)==1
    assert out['suggested_action']=='NO_RECOMMENDATION'
    assert 'more forward' not in json.dumps(out) and 'closer to vertical' in out['summary']


def test_aspect_and_mirrored_image_do_not_become_anatomical_forward_direction():
    a=paired([10]*20,[40]*20)
    normal=upper_body_comparison(a,'right_shoulder','right_hip')
    for track in a.current_points+a.reference_points:
        for point in track.values():point['x']=1-point['x']
    mirrored=upper_body_comparison(a,'right_shoulder','right_hip')
    assert mirrored['rms_difference_deg']==pytest.approx(normal['rms_difference_deg'])
    assert mirrored['direction']==normal['direction']=='closer_to_vertical'
    # Same pixel geometry represented on another aspect ratio stays equivalent.
    for track in a.current_points+a.reference_points:
        for point in track.values():point['x']*=point['_aspect']/2;point['_aspect']=2
    wide=upper_body_comparison(a,'right_shoulder','right_hip')
    assert wide['rms_difference_deg']==pytest.approx(normal['rms_difference_deg'])


def test_imported_historical_wrong_direction_is_read_only_and_original_artifact_unchanged():
    from pathlib import Path
    import hashlib
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models.entities import RecordedSet
    from app.services.coaching.compatibility import recommendation_context
    from app.services.meta.saved_results import saved_coaching_path
    from tests.test_coaching_decision import _start_recording_fixture,_squat_targets
    from tests.test_release_saved import _write_live_coaching
    client,plan_id,_,set_id=_start_recording_fixture()
    try:
        with SessionLocal() as db:
            rec=db.get(RecordedSet,set_id);body=json.loads(rec.coaching.payload_json)
            r=next(r for r in rec.reps if not r.is_reference and r.is_complete)
            body.update(source='muse_spark',source_label='Mocked stored response — no real inference',summary='Rep leaned more forward.',reason='Lean farther forward to fix posture.',primary_cue='Lean farther forward.',suggested_action='REDUCE_REPS',
                suggested_reps=_squat_targets(plan_id)['target_reps']-2,decision_basis=None,
                observations=[{'metric':'torso_inclination','statement':'Rep leaned more forward.','magnitude':12,'evidence_seconds':[r.bottom_seconds]}])
            body.pop('interpretation_version',None);body['recommendation_context']=recommendation_context(rec)
        _write_live_coaching(set_id,result=body)
        path=saved_coaching_path(get_settings());before=hashlib.sha256(path.read_bytes()).hexdigest()
        targets=_squat_targets(plan_id)
        response=client.post('/coaching/'+set_id+'/import-saved');assert response.status_code==200,response.text
        version=response.json();assert not version['can_activate'] and not version['actionable']
        assert 'more forward' not in json.dumps(version)
        c=client.get('/coaching/'+set_id).json()
        assert client.post(f'/coaching/{set_id}/versions/{version["id"]}/activate',json={'recommendation_id':c['id'],'expected_revision':c['revision']}).status_code==409
        assert targets==_squat_targets(plan_id) and before==hashlib.sha256(path.read_bytes()).hexdigest()
    finally:client.__exit__(None,None,None)


def test_minor_or_opposite_tempo_difference_cannot_rescue_an_unsupported_angle_adjustment():
    ctx=context(other={'ascent_duration_difference_percent':-2.7})
    payload=wrong(decision_basis='ascent_duration',observations=[{'metric':'torso_inclination','statement':'More forward lean','evidence_seconds':[8],'magnitude':30},
        {'metric':'ascent_duration','statement':'Slowing down','evidence_seconds':[8],'magnitude':50}])
    out=ground_coaching(payload,ctx,{})
    assert out['suggested_action']=='NO_RECOMMENDATION'
    assert next(o for o in out['observations'] if o['metric']=='ascent_duration')['magnitude']==-2.7
    assert 'forward' not in json.dumps(out)


def test_count_correction_preserves_effort_and_legitimate_decision_unless_explicitly_cleared():
    from app.database import SessionLocal
    from app.models.entities import RecordedSet
    from tests.test_coaching_decision import _start_recording_fixture, _force_action
    client, _, session_id, set_id = _start_recording_fixture()
    try:
        with SessionLocal() as db:
            rec = db.get(RecordedSet, set_id)
            rec.reported_rpe = 10
            db.commit()
        _force_action(set_id, 'EXTEND_REST', suggested_rest_seconds=180)
        accepted = client.post('/coaching/'+set_id+'/decision', json={'decision':'accepted'})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()['applied_change']['applied']
        with SessionLocal() as db:
            original = db.get(RecordedSet, set_id).coaching.payload_json
        fields = {'exercise_id':'barbell_squat','set_index':1,'completed_reps':5,'load_kg':40}
        corrected = client.post('/sessions/'+session_id+'/sets', json=fields)
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()['reported_rpe'] == 10
        out = client.get('/coaching/'+set_id).json()
        assert out['user_decision'] == 'accepted' and out['applied_change'] == accepted.json()['applied_change']
        assert out['suggested_action'] == 'EXTEND_REST'
        assert 'reported very high effort' in out['reason']
        assert not out.get('historical_interpretation_corrected')
        with SessionLocal() as db:
            assert db.get(RecordedSet, set_id).coaching.payload_json == original
        cleared = client.post('/sessions/'+session_id+'/sets', json={**fields,'reported_rpe':None})
        assert cleared.status_code == 200 and cleared.json()['reported_rpe'] is None
    finally:
        client.__exit__(None, None, None)
