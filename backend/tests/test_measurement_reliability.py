"""Mechanism regressions from generated poses; no recording-derived fixtures."""
import copy
import math
import pytest
from app.services.movement.synthetic import synthesize_squat_set
from app.services.movement.pipeline import analyze_pose_sequence
from app.services.movement.reliability import geometry_frames
from app.services.movement.geometry import knee_angle
from app.services.coaching.local_coach import generate_local_coaching
from app.services.coaching.evidence import ground_coaching
from app.services.meta.contracts import build_coaching_model_input


def context(result):
    return {'quality':result['quality'],'drift':result['drift'],'reference_rep':result['reference_rep'],
        'reps':[{'rep_id':r.rep_id,'start_seconds':r.start_seconds,'bottom_seconds':r.bottom_seconds,'end_seconds':r.end_seconds,
                 'comparison_eligible':r.metrics['comparison_eligible']} for r in result['reps'] if r.is_complete],
        'profile':{},'current_reps':8,'current_rest':120,'current_load':40,'reported_rpe':7}


def test_aspect_ratio_is_applied_to_angles():
    # Pixel positions form a 90 degree angle on two different canvases.
    poses=[]
    for w,h in [(400,800),(800,400)]:
        f={'timestamp':0,'width':w,'height':h,'landmarks':{
            'hip':{'x':100/w,'y':100/h},'knee':{'x':100/w,'y':200/h},'ankle':{'x':200/w,'y':200/h}}}
        lm=geometry_frames([f])[0]['landmarks'];poses.append(knee_angle(lm['hip'],lm['knee'],lm['ankle']))
    assert poses==pytest.approx([90,90])


def test_middle_shallower_cycles_are_detected_and_explained_without_worsening_claim():
    frames=synthesize_squat_set(6,drift=False)
    n=len(frames)//6
    for f in frames[2*n:4*n]:
        lm=f['landmarks']
        for side in ['left','right']:
            hip=lm[side+'_hip'];shoulder=lm[side+'_shoulder'];knee=lm[side+'_knee']
            baseline=.42+(0 if side=='right' else .005)
            shift=(hip['y']-baseline)*.4
            hip['y']-=shift;shoulder['y']-=shift
            knee['y']=.62+(.01 if side=='left' else 0)+(knee['y']-.62-(.01 if side=='left' else 0))*.6
    result=analyze_pose_sequence(frames)
    assert sum(r.is_complete for r in result['reps'])==6
    for rid in [3,4]:
        item=next(d for d in result['drift'] if d['rep_id']==rid)
        assert item['depth_difference_percent'] < -20
        assert item['comparison_valid']
    coach=generate_local_coaching(**context(result))
    assert coach['suggested_action']=='KEEP_PLAN'
    assert any('Rep 3' in o['statement'] for o in coach['observations'])
    assert any('Rep 4' in o['statement'] for o in coach['observations'])
    assert all(not d['onset'] for d in result['drift'])


def test_long_occlusion_is_not_interpolated_into_a_rep():
    frames=synthesize_squat_set(4,drift=False)
    for f in frames:
        if 2.5<f['timestamp']<5.5: f['landmarks']={}
    result=analyze_pose_sequence(frames)
    assert result['quality']['unreliable_intervals']
    assert all(not(r.start_seconds<2.5 and r.end_seconds>5.5) for r in result['reps'])
    assert result['reference_rep'] is None
    coach=generate_local_coaching(**context(result))
    assert coach['suggested_action']=='NO_RECOMMENDATION'
    assert not coach['observations']


def test_high_visibility_collapsed_final_track_is_not_a_reference():
    frames=synthesize_squat_set(4,drift=False)
    for f in frames:
        if f['timestamp']>8:
            for point in f['landmarks'].values():
                point['x']=.5+(point['x']-.5)*.12
                point['y']=.85+(point['y']-.85)*.12
                point['visibility']=.99
    result=analyze_pose_sequence(frames)
    assert result['quality']['reliable_fraction']<.85
    assert result['reference_rep'] is None
    assert result['quality']['comparison_usable'] is False
    assert result['drift']==[]


def test_translating_upright_setup_is_not_a_squat():
    original=synthesize_squat_set(1,drift=False)[-1]
    frames=[]
    for i in range(100):
        f=copy.deepcopy(original);f['timestamp']=i/15
        for p in f['landmarks'].values():p['y']+=.08*math.sin(i/15*2)
        frames.append(f)
    result=analyze_pose_sequence(frames)
    assert not any(r.is_complete for r in result['reps'])
    assert result['reference_rep'] is None


def test_invalid_metrics_cannot_become_model_reassurance_or_actionable_evidence():
    ctx={'quality':{'usable':True,'comparison_usable':False},'drift':[], 'reps':[], 'reference_rep':None}
    raw={'summary':'Solid tracking and normal variation. Strong final rep.', 'reason':'Looks consistent.',
         'suggested_action':'EXTEND_REST','observations':[]}
    out=ground_coaching(raw,ctx,{})
    assert out['suggested_action']=='NO_RECOMMENDATION' and out['actionable'] is False
    assert 'Solid tracking' not in out['summary'] and 'normal variation' not in out['summary']
    assert out['primary_cue'] is None
    assert not build_coaching_model_input(ctx)['comparisons']


def test_saturated_comparisons_are_not_technique_scores():
    ctx={'quality':{'usable':True},'reference_rep':1,'reps':[],
        'drift':[{'rep_id':2,'similarity':0},{'rep_id':3,'similarity':0}]}
    out=ground_coaching({'summary':'Perfectly tracked','suggested_action':'KEEP_PLAN'},ctx,{})
    assert out['suggested_action']=='NO_RECOMMENDATION'
    assert 'saturated' in out['summary']


def test_log_correction_preserves_detected_reps_and_recording_target_and_stales_coaching():
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.test_lower_body_focus import lower_profile
    from tests.helpers import accept_if_proposed,upload_recording_fixture
    with TestClient(app) as client:
        client.post('/profiles',json=lower_profile())
        plan=accept_if_proposed(client,client.post('/workouts/generate',json={}).json())
        session=client.post('/sessions',json={'plan_id':plan['id']}).json()
        rec=upload_recording_fixture(client,session['id'],target_reps=6,set_index=1).json()
        original=client.get('/analysis/'+rec['id']).json()
        assert original['detected_reps']==6 and original['planned_reps']==6
        corrected=client.post('/sessions/'+session['id']+'/sets',json={'exercise_id':'barbell_squat','set_index':1,'completed_reps':7,'target_reps':8})
        assert corrected.status_code==200
        result=client.get('/analysis/'+rec['id']).json()
        assert result['detected_reps']==6 and result['completed_reps']==7
        assert result['planned_reps']==6 and len(result['reps'])==6
        coaching=client.get('/coaching/'+rec['id']).json()
        assert not coaching['actionable']
        assert client.post('/coaching/'+rec['id']+'/decision',json={'decision':'accepted'}).status_code==409


def test_stored_contradictory_reference_is_read_only_across_decision_and_version_paths():
    import json
    from app.database import SessionLocal
    from app.models.entities import RecordedSet
    from tests.test_coaching_decision import _start_recording_fixture, _squat_targets
    from tests.test_coaching_activation import _import, _activate, _decide
    client, plan_id, _, set_id = _start_recording_fixture()
    try:
        version = _import(client,set_id)
        targets = _squat_targets(plan_id)
        with SessionLocal() as db:
            rec=db.get(RecordedSet,set_id)
            reference=next(r for r in rec.reps if r.is_reference)
            corrupted=json.loads(reference.metrics_json)
            corrupted['max_torso_inclination_deg']=178
            reference.metrics_json=json.dumps(corrupted)
            original=rec.coaching.payload_json
            db.commit()
        output=client.get('/analysis/'+set_id).json()
        assert output['reference_rep'] is None and output['drift']==[]
        assert not any(r['is_reference'] for r in output['reps'])
        assert all(r['metrics']['max_torso_inclination_deg'] is None for r in output['reps'])
        coach=client.get('/coaching/'+set_id).json()
        assert coach['actionable'] is False and coach['suggested_action']=='NO_RECOMMENDATION'
        assert _activate(client,set_id,version).status_code==409
        assert _decide(client,set_id,'accepted').status_code==409
        assert _squat_targets(plan_id)==targets
        with SessionLocal() as db:
            assert db.get(RecordedSet,set_id).coaching.payload_json==original
    finally:
        client.__exit__(None,None,None)


def test_invalid_measurements_do_not_trigger_a_live_coaching_request(tmp_path):
    from app.config import Settings
    from app.services.meta.muse import MuseProvider
    from unittest.mock import Mock
    result=analyze_pose_sequence(synthesize_squat_set(3,drift=False))
    ctx=context(result);ctx['quality']={**ctx['quality'],'comparison_usable':False}
    transport=Mock();gateway=Mock()
    coach=MuseProvider(Settings(_env_file=None,coaching_provider='meta_live',data_dir=tmp_path),gateway,transport=transport).generate_coaching(ctx)
    assert coach['source']=='local' and coach['suggested_action']=='NO_RECOMMENDATION'
    assert not transport.method_calls and not gateway.method_calls


def test_small_setup_flexion_is_kept_as_uncertain_instead_of_a_complete_squat():
    frames=[]
    for i in range(100):
        phase=math.sin(math.pi*i/99)**2
        points={}
        for side in ['left','right']:
            points[side+'_shoulder']={'x':.5,'y':.2+.04*phase,'visibility':.99}
            points[side+'_hip']={'x':.5,'y':.42+.04*phase,'visibility':.99}
            points[side+'_knee']={'x':.5+.035*phase,'y':.64,'visibility':.99}
            points[side+'_ankle']={'x':.5,'y':.86,'visibility':.99}
        frames.append({'timestamp':i/15,'width':640,'height':640,'landmarks':points})
    from app.services.movement.reps import detect_squat_reps
    reps,_=detect_squat_reps(frames)
    assert reps and not any(r.is_complete for r in reps)
    assert all(r.metrics['movement_status']=='uncertain' for r in reps)
    assert not any(r.metrics['comparison_eligible'] for r in reps)
