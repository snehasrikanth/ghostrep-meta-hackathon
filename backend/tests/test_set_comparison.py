"""Generated measurements, fictional identities, real owned API reads. No private video."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models.entities import AnalysisResult, CoachingDecision, RecordedSet, RepMetric, WorkoutSession

@pytest.fixture
def scenario(tmp_path):
    with TestClient(app) as client:
        profile=client.post('/profiles',json={'display_name':'Fictional comparison test','goal':'build_strength','experience':'intermediate','days_per_week':3,'session_duration_minutes':45,'equipment':['barbell'],'limitations':[]}).json()
        with SessionLocal() as db:
            session=WorkoutSession(user_id=profile['user_id']);db.add(session);db.commit()
            yield client,db,profile['user_id'],session,tmp_path

def add_set(s,number,ascent=None,descent=None,*,metric='ascent_duration',**overrides):
    _,db,uid,session,folder=s;ascent=ascent or [1,1,1,2,2,2];descent=descent or [1]*len(ascent)
    media=folder/(str(uuid.uuid4())+'.mp4');media.write_bytes(b'generated metadata fixture; not accuracy evidence')
    rec=RecordedSet(user_id=uid,session_id=session.id,exercise_id='barbell_squat',set_index=number,entry_source='video',analysis_requested=True,processing_status='COMPLETED',normalized_path=str(media),original_filename='fictional.mp4',target_reps=8,completed_reps=len(ascent),load_kg=40,reported_rpe=7,duration_seconds=60,created_at=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=number or 0))
    for k,v in overrides.items():setattr(rec,k,v)
    db.add(rec);db.flush();drift=[]
    for i,(up,down) in enumerate(zip(ascent,descent)):
        rid=i+1;start=i*5
        rec.reps.append(RepMetric(rep_index=rid,start_seconds=start,bottom_seconds=start+down,end_seconds=start+down+up,descent_seconds=down,ascent_seconds=up,is_complete=True,is_reference=rid==1,confidence=.95,metrics_json=json.dumps({'comparison_eligible':True,'reliability':{'valid_fraction':1,'issues':[]},'max_torso_inclination_deg':40})))
        drift.append({'rep_id':rid,'comparison_valid':True,'similarity':80,'ascent_duration_difference_percent':100*(up/ascent[0]-1),'descent_duration_difference_percent':100*(down/descent[0]-1),'torso_lean_difference_deg':30})
    rec.analysis=AnalysisResult(reference_rep=1,quality_json=json.dumps({'usable':True,'comparison_usable':True,'side':'right','issues':[]}),drift_json=json.dumps(drift),overlay_json='{"frames":[]}',analysis_version='local-v4',pose_available=True)
    idx=min(3,len(ascent)-1);key={'ascent_duration':'ascent_duration_difference_percent','descent_duration':'descent_duration_difference_percent','torso_inclination':'torso_lean_difference_deg'}.get(metric)
    obs=[{'metric':metric,'statement':'A previous measured observation.','evidence_seconds':[rec.reps[idx].bottom_seconds],'magnitude':drift[idx].get(key)}] if metric else []
    body={'source':'local','summary':'Stored fictional coaching','reason':'Review the replay','primary_cue':'Keep your midsection firm while reviewing your movement.','suggested_action':'KEEP_PLAN','observations':obs,'uncertainties':[],'confidence_notes':[]}
    rec.coaching=CoachingDecision(source='local',proposed_action='KEEP_PLAN',summary=body['summary'],reason=body['reason'],payload_json=json.dumps(body));db.commit();return rec

def read(s,rec):
    r=s[0].get('/analysis/'+rec.id);assert r.status_code==200,r.text
    assert r.json()['set_index']==rec.set_index
    return r.json()['previous_set_comparison']

def test_first_set_is_friendly_without_invented_comparison(scenario):
    out=read(scenario,add_set(scenario,1));assert out['status']=='first' and out['previous'] is None and out['metrics']==[]
    assert out['current']['usable_reps']==6 and 'starting point' in out['headline']

def test_set_order_wins_over_recording_and_analysis_completion_order(scenario):
    one=add_set(scenario,1);two=add_set(scenario,2,created_at=datetime(2026,1,5,tzinfo=timezone.utc));current=add_set(scenario,3)
    one.analysis.created_at=datetime(2026,2,3);two.analysis.created_at=datetime(2026,2,2);current.analysis.created_at=datetime(2026,2,1);scenario[1].commit()
    assert read(scenario,current)['previous']['set_id']==two.id

def test_sample_deleted_other_exercise_and_other_session_are_excluded(scenario):
    previous=add_set(scenario,1);sample=add_set(scenario,2,entry_source='demo');add_set(scenario,2,original_filename='DEMO_FIXTURE');add_set(scenario,2,normalized_path=None);add_set(scenario,2,normalized_path='/nonexistent/private-test.mp4');add_set(scenario,2,exercise_id='barbell_row')
    other=WorkoutSession(user_id=scenario[2]);scenario[1].add(other);scenario[1].commit();add_set(scenario,2,session_id=other.id);current=add_set(scenario,3)
    assert read(scenario,current)['previous']['set_id']==previous.id
    assert read(scenario,sample)['status']=='unavailable'

def test_real_api_user_ownership_and_predecessor_isolation(scenario):
    current=add_set(scenario,3)
    with TestClient(app) as stranger:
        uid=stranger.post('/profiles',json={'goal':'build_strength','experience':'beginner','days_per_week':3,'session_duration_minutes':40,'equipment':['barbell'],'limitations':[]}).json()['user_id'];foreign=add_set(scenario,2,user_id=uid)
        assert stranger.get('/analysis/'+current.id).status_code==404
        assert scenario[0].get('/analysis/'+foreign.id).status_code==404
        assert read(scenario,current)['previous'] is None

def test_unreliable_immediate_predecessor_is_not_skipped(scenario):
    add_set(scenario,1);bad=add_set(scenario,2);current=add_set(scenario,3);bad.analysis.quality_json='{"usable":false,"comparison_usable":false}';scenario[1].commit();out=read(scenario,current)
    assert out['previous']['set_id']==bad.id and out['status']=='unavailable' and out['metrics']==[] and 'previous' in out['summary']

@pytest.mark.parametrize('failure',['quality','missing_flags','missing_reliability','ineligible','timestamps','reference'])
def test_unreliable_or_legacy_current_fields_are_not_guessed(scenario,failure):
    add_set(scenario,1);current=add_set(scenario,2)
    if failure=='quality':current.analysis.quality_json='{"usable":true,"comparison_usable":false}'
    elif failure=='reference':current.reps[0].metrics_json='{"comparison_eligible":false}'
    else:
        for r in current.reps:
            m=json.loads(r.metrics_json)
            if failure=='missing_flags':m.pop('comparison_eligible')
            if failure=='missing_reliability':m.pop('reliability')
            if failure=='ineligible':m['comparison_eligible']=False
            if failure=='timestamps':r.ascent_seconds+=1
            r.metrics_json=json.dumps(m)
    scenario[1].commit();out=read(scenario,current);assert out['status']=='unavailable' and out['metrics']==[]

def test_legacy_fallback_uses_recording_time_not_analysis_time(scenario):
    a=add_set(scenario,None,created_at=datetime(2026,1,1));b=add_set(scenario,None,created_at=datetime(2026,1,2));current=add_set(scenario,None,created_at=datetime(2026,1,3));a.analysis.created_at=datetime(2026,3,1);b.analysis.created_at=datetime(2026,2,1);scenario[1].commit()
    out=read(scenario,current);assert out['previous']['set_id']==b.id and out['previous']['label']=='Earlier recording'

def test_conflicting_legacy_order_is_unavailable(scenario):
    add_set(scenario,2,created_at=datetime(2026,1,1));add_set(scenario,1,created_at=datetime(2026,1,2));current=add_set(scenario,None,created_at=datetime(2026,1,3));out=read(scenario,current)
    assert out['status']=='unavailable' and 'ambiguous' in out['summary']

def test_supported_consistency_improvement_is_not_speed_or_technique(scenario):
    previous=add_set(scenario,1);current=add_set(scenario,2,ascent=[1.5]*6);current.analysis.reference_rep=6;scenario[1].commit();out=read(scenario,current)
    assert out['follow_up']['status']=='improved' and out['headline']=='More consistent this set!'
    row=next(m for m in out['metrics'] if m['key']=='ascent_duration');assert row['previous']==row['current']==1.5
    assert 'not technique correction' in out['follow_up']['explanation']
    assert out['follow_up']['evidence']['set_id']==previous.id and out['follow_up']['evidence']['rep_id']==4

def test_unchanged_pattern_remains_and_neutral_speed_change_is_not_progress(scenario):
    add_set(scenario,1);same=add_set(scenario,2);out=read(scenario,same);assert out['follow_up']['status']=='remains'
    add_set(scenario,3,ascent=[2]*6);faster=add_set(scenario,4,ascent=[1]*6);out=read(scenario,faster)
    assert out['follow_up']['status']=='unavailable' and out['headline']=='Here’s how this set compares.'
    assert next(m for m in out['metrics'] if m['key']=='ascent_duration')['change']=='1.0s shorter'

@pytest.mark.parametrize('change',[{'ascent':[1.5]*4,'completed_reps':9,'target_reps':10},{'load_kg':None},{'reported_rpe':None},{'load_kg':50},{'reported_rpe':9}])
def test_changed_counts_or_load_effort_and_missing_context_withhold_progress(scenario,change):
    add_set(scenario,1);current=add_set(scenario,2,**({'ascent':[1.5]*6}|change));out=read(scenario,current)
    assert out['status']=='compared' and out['follow_up']['status']=='unavailable'
    assert out['current']['logged_reps']==current.completed_reps and out['current']['planned_reps']==current.target_reps
    assert out['current']['usable_reps']==len(current.reps)
    if 'load_kg' in change:assert out['current']['load_kg']==change['load_kg']

def test_position_cue_is_not_scored_from_different_references(scenario):
    previous=add_set(scenario,1,metric='torso_inclination');current=add_set(scenario,2,ascent=[1.5]*6);body=json.loads(previous.coaching.payload_json);body['observations'][0]['statement']='More forward lean; lean farther forward.';previous.coaching.payload_json=json.dumps(body);current.analysis.reference_rep=6;scenario[1].commit();out=read(scenario,current)
    assert out['follow_up']['status']=='unavailable' and 'camera position is not verified' in out['follow_up']['explanation']
    assert 'forward' not in json.dumps(out)

@pytest.mark.parametrize('view',['left','warning','pipeline'])
def test_view_or_pipeline_mismatch_prevents_consistency_judgment(scenario,view):
    add_set(scenario,1);current=add_set(scenario,2,ascent=[1.5]*6);q=json.loads(current.analysis.quality_json)
    if view=='left':q['side']='left'
    if view=='warning':q['issues']=[{'code':'camera_angle','severity':'warn','message':'Changed view'}]
    if view=='pipeline':current.analysis.analysis_version='local-v3'
    current.analysis.quality_json=json.dumps(q);scenario[1].commit();out=read(scenario,current)
    assert out['follow_up']['status']=='unavailable' and out['status']=='compared'

def test_free_text_cue_is_unmeasured_without_keyword_guessing(scenario):
    previous=add_set(scenario,1,metric=None);current=add_set(scenario,2,ascent=[1.5]*6);drift=json.loads(previous.analysis.drift_json)
    for d in drift:d.pop('torso_lean_difference_deg')
    previous.analysis.drift_json=json.dumps(drift);scenario[1].commit();out=read(scenario,current)
    assert out['follow_up']['status']=='unavailable' and out['follow_up']['previous_observation']=='Keep your midsection firm while reviewing your movement.'
    assert 'no supported metric association' in out['follow_up']['explanation']

def test_few_reps_and_partial_movements_cannot_be_consistency_progress(scenario):
    add_set(scenario,1,ascent=[1,1,2]);current=add_set(scenario,2,ascent=[1.5]*3);out=read(scenario,current)
    assert out['status']=='compared' and 'four usable reps' in out['follow_up']['explanation']
    partial=add_set(scenario,3);partial.reps[-1].is_complete=False;scenario[1].commit();out=read(scenario,partial)
    assert out['current']['detected_reps']==5 and out['follow_up']['status']!='improved'

def test_model_failure_does_not_require_call_or_mutate_saved_data(scenario):
    previous=add_set(scenario,1);current=add_set(scenario,2,ascent=[1.5]*6);before=(previous.coaching.payload_json,previous.analysis.drift_json,current.analysis.drift_json,current.completed_reps,current.target_reps)
    with patch('app.services.meta.muse.MuseProvider.generate_coaching',side_effect=RuntimeError('offline')) as provider:
        one=read(scenario,current);two=read(scenario,current)
        provider.assert_not_called()
    scenario[1].expire_all();assert one==two and one['follow_up']['status']=='improved'
    assert before==(previous.coaching.payload_json,previous.analysis.drift_json,current.analysis.drift_json,current.completed_reps,current.target_reps)

@pytest.mark.parametrize('old,new,status',[(.2,.15,'improved'),(.2,.16,'remains'),(.4,.32,'remains'),(.14,0,'unavailable')])
def test_consistency_thresholds_require_both_absolute_and_relative_change(scenario,old,new,status):
    add_set(scenario,1,ascent=[1-old]*3+[1+old]*3);current=add_set(scenario,2,ascent=[1-new]*3+[1+new]*3)
    assert read(scenario,current)['follow_up']['status']==status

def test_corrected_log_count_is_never_treated_as_measured_reps(scenario):
    add_set(scenario,1);current=add_set(scenario,2,ascent=[1.5]*6,completed_reps=9);out=read(scenario,current)
    assert out['current']['detected_reps']==out['current']['usable_reps']==6 and out['current']['logged_reps']==9
    assert out['follow_up']['status']=='unavailable' and 'logged count differs' in out['follow_up']['explanation']

def test_setup_idle_and_total_recording_duration_are_not_phase_execution_time(scenario):
    add_set(scenario,1);current=add_set(scenario,2,duration_seconds=5000)
    for r in current.reps:
        r.start_seconds+=100;r.bottom_seconds+=100;r.end_seconds+=100
    scenario[1].commit();out=read(scenario,current)
    assert next(m for m in out['metrics'] if m['key']=='descent_duration')['current']==1
    assert next(m for m in out['metrics'] if m['key']=='ascent_duration')['current']==1.5
    assert out['follow_up']['status']=='remains'

def test_known_zero_load_is_not_missing_context(scenario):
    add_set(scenario,1,load_kg=0);current=add_set(scenario,2,ascent=[1.5]*6,load_kg=0);out=read(scenario,current)
    assert out['follow_up']['status']=='improved' and out['previous']['load_kg']==out['current']['load_kg']==0

def test_earlier_unanalyzed_manual_set_does_not_invent_a_comparison(scenario):
    db=scenario[1];manual=RecordedSet(user_id=scenario[2],session_id=scenario[3].id,exercise_id='barbell_squat',set_index=1,entry_source='manual',analysis_requested=False,processing_status='LOGGED',completed_reps=8,target_reps=8);db.add(manual);db.commit()
    current=add_set(scenario,2);out=read(scenario,current)
    assert out['status']=='first' and out['previous'] is None

def test_inconsistent_stored_timing_observation_cannot_justify_progress(scenario):
    previous=add_set(scenario,1);current=add_set(scenario,2,ascent=[1.5]*6)
    drift=json.loads(previous.analysis.drift_json)
    for d in drift:
        if d['rep_id']==4:d['ascent_duration_difference_percent']=50 # saved phase durations establish 100%
    previous.analysis.drift_json=json.dumps(drift);scenario[1].commit();out=read(scenario,current)
    assert out['follow_up']['status']=='unavailable' and 'cannot be confirmed' in out['follow_up']['explanation']
    assert out['headline']=='Here’s how this set compares.'

def test_previous_note_from_a_replaced_analysis_cannot_be_scored_as_progress(scenario):
    from app.services.coaching.compatibility import recommendation_context
    previous=add_set(scenario,1);current=add_set(scenario,2,ascent=[1.5]*6)
    body=json.loads(previous.coaching.payload_json);body['recommendation_context']=recommendation_context(previous);previous.coaching.payload_json=json.dumps(body)
    previous.analysis.reference_rep=2;scenario[1].commit();out=read(scenario,current)
    assert out['follow_up']['status']=='unavailable' and 'analysis changed' in out['follow_up']['explanation']
    assert out['headline']=='Here’s how this set compares.'
