"""Isolated contract fixtures, never live results. Model transports are forbidden."""
from concurrent.futures import ThreadPoolExecutor
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models.entities import CoachingDecision, CoachingVersion, RecordedSet
from app.services.coaching.compatibility import recommendation_context
from app.services.meta.saved_results import saved_coaching_path
from tests.test_coaching_decision import _start_recording_fixture, _squat_targets, _set_squat_targets
from tests.test_release_saved import _write_live_coaching
from tests.helpers import upload_recording_fixture


@pytest.fixture(autouse=True)
def no_model_transport():
    with patch('app.services.meta.transport.OpenAIMetaTransport.__init__', side_effect=AssertionError('No model transport')):
        yield


def _import(client, set_id, action='REDUCE_REPS', **overrides):
    with SessionLocal() as db:
        rec = db.get(RecordedSet, set_id)
        body = json.loads(rec.coaching.payload_json)
        rx = recommendation_context(rec)['targets']
    body.update(source='muse_spark', source_label='Muse protocol fixture (isolated test)', suggested_action=action,
                suggested_reps=rx['target_reps']-2 if action == 'REDUCE_REPS' else rx['target_reps'],
                suggested_rest_seconds=rx['rest_seconds']+30 if action == 'EXTEND_REST' else rx['rest_seconds'],
                suggested_load_kg=round(rx['suggested_load_kg']*.9, 1) if action == 'REDUCE_LOAD_CONSERVATIVELY' and rx['suggested_load_kg'] else rx['suggested_load_kg'])
    body.update(overrides)
    from app.services.coaching.interpretation import canonicalize,record_context
    with SessionLocal() as db:
        body=canonicalize(body,record_context(db.get(RecordedSet,set_id)))
    _write_live_coaching(set_id, result=body)
    response = client.post(f'/coaching/{set_id}/import-saved')
    assert response.status_code == 200, response.text
    return response.json()


def _identity(client, set_id):
    c = client.get(f'/coaching/{set_id}').json()
    return {'recommendation_id': c['id'], 'expected_revision': c['revision']}


def _activate(client, set_id, version, identity=None):
    return client.post(f'/coaching/{set_id}/versions/{version["id"]}/activate', json=identity or _identity(client, set_id))


def _decide(client, set_id, decision, identity=None):
    return client.post(f'/coaching/{set_id}/decision', json={**(identity or _identity(client, set_id)), 'decision': decision})


@pytest.mark.parametrize('action', ['REDUCE_REPS', 'EXTEND_REST', 'REDUCE_LOAD_CONSERVATIVELY', 'KEEP_PLAN'])
def test_import_activate_accept_persists_matching_exercise_and_preserves_local(action):
    client, plan_id, _, set_id = _start_recording_fixture()
    try:
        before_plan = client.get(f'/workouts/{plan_id}').json()['exercises']
        before = _squat_targets(plan_id)
        with SessionLocal() as db:
            local = db.query(CoachingDecision).filter_by(set_id=set_id).one()
            original = (local.source, local.payload_json, local.user_decision)
        identity = _identity(client, set_id)
        version = _import(client, set_id, action)
        assert version['actionable'] is False and version['can_activate'] is True
        assert _squat_targets(plan_id) == before and _identity(client, set_id) == identity
        activated = _activate(client, set_id, version, identity)
        assert activated.status_code == 200, activated.text
        assert activated.json()['active_version_id'] == version['id']
        assert activated.json()['source_label'] == 'Muse protocol fixture (isolated test)'
        assert sum(v['actionable'] for v in activated.json()['stored_versions']) == 1
        assert _squat_targets(plan_id) == before
        with SessionLocal() as db:
            archived = db.query(CoachingVersion).filter(CoachingVersion.set_id == set_id, CoachingVersion.artifact_id.like('previous:%')).one()
            assert (archived.source, archived.payload_json, archived.user_decision) == original
        assert _decide(client, set_id, 'accepted', identity).status_code == 409
        assert client.post(f'/coaching/{set_id}/decision', json={'decision':'accepted'}).status_code == 409
        accepted = _decide(client, set_id, 'accepted')
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()['user_decision'] == 'accepted'
        assert accepted.json()['applied_change']['applied'] is (action != 'KEEP_PLAN')
        after = _squat_targets(plan_id)
        assert accepted.json()['applied_change']['after'] == after
        refreshed = client.get(f'/workouts/{plan_id}').json()['exercises']
        assert [e for e in refreshed if e['exercise_id'] != 'barbell_squat'] == [e for e in before_plan if e['exercise_id'] != 'barbell_squat']
        assert client.get(f'/coaching/{set_id}').json()['state'] == 'already_decided'
        assert _decide(client, set_id, 'accepted').status_code == 409
        assert _activate(client, set_id, version).status_code == 409
        assert _squat_targets(plan_id) == after
    finally:
        client.__exit__(None, None, None)


def test_rejection_and_simultaneous_activation_and_decisions():
    client, plan_id, _, set_id = _start_recording_fixture()
    try:
        before = _squat_targets(plan_id)
        version = _import(client, set_id)
        identity = _identity(client, set_id)
        with ThreadPoolExecutor(2) as pool:
            replies = list(pool.map(lambda _: _activate(client, set_id, version, identity), range(2)))
        assert [r.status_code for r in replies] == [200, 200]
        assert _identity(client, set_id)['expected_revision'] == 1
        with SessionLocal() as db:
            assert db.query(CoachingVersion).filter_by(set_id=set_id).count() == 2
        identity = _identity(client, set_id)
        with ThreadPoolExecutor(2) as pool:
            replies = list(pool.map(lambda _: _decide(client, set_id, 'rejected', identity), range(2)))
        assert sorted(r.status_code for r in replies) == [200, 409]
        assert _squat_targets(plan_id) == before
        assert client.get(f'/coaching/{set_id}').json()['applied_change']['reason'] == 'rejected'
    finally:
        client.__exit__(None, None, None)


def test_stale_targets_refuse_activation_and_acceptance_without_saving_decision():
    client, plan_id, _, set_id = _start_recording_fixture()
    try:
        version = _import(client, set_id)
        before = _squat_targets(plan_id)
        _set_squat_targets(plan_id, rest_seconds=before['rest_seconds']+10)
        assert _activate(client, set_id, version).status_code == 409
        _set_squat_targets(plan_id, rest_seconds=before['rest_seconds'])
        assert _activate(client, set_id, version).status_code == 200
        _set_squat_targets(plan_id, target_reps=before['target_reps']-1)
        changed = _squat_targets(plan_id)
        assert _decide(client, set_id, 'accepted').status_code == 409
        assert client.get(f'/coaching/{set_id}').json()['user_decision'] == 'pending'
        assert _squat_targets(plan_id) == changed
        assert _decide(client, set_id, 'rejected').status_code == 200
        assert _squat_targets(plan_id) == changed
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize('finish', ['complete', 'abandon'])
def test_closed_workout_cannot_rewrite(finish):
    client, plan_id, session_id, set_id = _start_recording_fixture()
    try:
        before = _squat_targets(plan_id)
        version = _import(client, set_id)
        assert _activate(client, set_id, version).status_code == 200
        assert client.post(f'/sessions/{session_id}/{finish}').status_code == 200
        decided = _decide(client, set_id, 'accepted')
        assert decided.status_code == 200
        assert decided.json()['applied_change']['reason'] == 'workout_closed'
        assert _squat_targets(plan_id) == before
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize('bad', [{'suggested_reps':None}, {'suggested_reps':100}, {'suggested_action':'NO_RECOMMENDATION'}, {'observations':[]}])
def test_unsupported_or_incomplete_output_stays_review_only(bad):
    client, _, _, set_id = _start_recording_fixture()
    try:
        version = _import(client, set_id, **bad)
        assert version['can_activate'] is False
        assert _activate(client, set_id, version).status_code == 409
    finally:
        client.__exit__(None, None, None)


def test_failed_saves_roll_back_activation_and_target_change():
    client, plan_id, _, set_id = _start_recording_fixture()
    try:
        before = _squat_targets(plan_id)
        version = _import(client, set_id)
        failure = OperationalError('simulated isolated save failure', {}, Exception('disk full'))
        with patch('app.api.routes.coaching.Session.commit', side_effect=failure):
            failed = _activate(client, set_id, version)
        assert failed.status_code == 503
        assert _identity(client, set_id)['expected_revision'] == 0
        assert _activate(client, set_id, version).status_code == 200
        with patch('app.api.routes.coaching.Session.commit', side_effect=failure):
            failed = _decide(client, set_id, 'accepted')
        assert failed.status_code == 503
        assert client.get(f'/coaching/{set_id}').json()['user_decision'] == 'pending'
        assert _squat_targets(plan_id) == before
    finally:
        client.__exit__(None, None, None)


def test_bad_artifacts_analysis_and_cross_user_access_are_refused():
    client, _, _, set_id = _start_recording_fixture()
    try:
        version = _import(client, set_id)
        with TestClient(app) as other:
            assert other.get(f'/coaching/{set_id}').status_code == 404
            assert other.post(f'/coaching/{set_id}/import-saved').status_code == 404
            assert _activate(other, set_id, version, _identity(client,set_id)).status_code == 404
            assert _decide(other, set_id, 'accepted', _identity(client,set_id)).status_code == 404
        for metadata in [{'schema_validation':'failed'}, {'chat_calls':2}, {'model':'other-model'}, {'result':{'set_id':None}}, {'result':{'recommendation_context':{}}}, {'result':{'suggested_reps':'bad'}}]:
            _write_live_coaching(set_id, **metadata)
            assert client.post(f'/coaching/{set_id}/import-saved').status_code == 409
        path = saved_coaching_path(get_settings())
        path.write_text('{')
        assert client.post(f'/coaching/{set_id}/import-saved').status_code == 409
        with SessionLocal() as db:
            rec = db.get(RecordedSet, set_id)
            rec.analysis.quality_json = json.dumps({'usable':False, 'issues':[]})
            db.commit()
        assert _activate(client, set_id, version).status_code == 409
        assert _decide(client, set_id, 'accepted').status_code == 409
        with SessionLocal() as db:
            rec = db.get(RecordedSet, set_id)
            rec.processing_status = 'FAILED'
            db.commit()
        assert _activate(client,set_id,version).status_code == 409
    finally:
        client.__exit__(None, None, None)


def test_two_sets_cannot_apply_changes_to_the_same_old_prescription():
    client, plan_id, session_id, first = _start_recording_fixture()
    try:
        from tests.test_coaching_decision import _wait_analysis
        second = upload_recording_fixture(client, session_id).json()['id']
        _wait_analysis(client,second)
        for set_id in [first,second]:
            version=_import(client,set_id)
            assert _activate(client,set_id,version).status_code == 200
        before=_squat_targets(plan_id)
        identities={s:_identity(client,s) for s in [first,second]}
        with ThreadPoolExecutor(2) as pool:
            replies=list(pool.map(lambda s:_decide(client,s,'accepted',identities[s]),[first,second]))
        assert sorted(r.status_code for r in replies) == [200,409]
        assert _squat_targets(plan_id)['target_reps'] == before['target_reps']-2
    finally:
        client.__exit__(None,None,None)


def test_already_decided_local_and_foreign_version_cannot_be_replaced():
    client, _, session_id, first = _start_recording_fixture()
    try:
        from tests.test_coaching_decision import _wait_analysis
        version=_import(client,first)
        second=upload_recording_fixture(client, session_id).json()['id']
        _wait_analysis(client,second)
        assert _activate(client,second,version).status_code == 404
        assert _decide(client,first,'rejected').status_code == 200
        assert _activate(client,first,version).status_code == 409
    finally:
        client.__exit__(None,None,None)
