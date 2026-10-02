"""Typed filtering uses isolated history and never grants the model write tools."""
import json
import anyio

import pytest
from fastapi.testclient import TestClient

from fakes import FakeChat, say, call
from uc4_mcp.candidate_api import create_candidate_app
from uc4_mcp.candidate_history import CandidateHistory
from uc4_mcp.llm import LLMError


@pytest.fixture
def setup(tmp_path):
    history = CandidateHistory(path=tmp_path/'history.sqlite3', legacy_log=tmp_path/'legacy.jsonl')
    model = FakeChat([])
    client = TestClient(create_candidate_app(lambda: model, get_history=lambda: history))
    context = {k: client.get('/health').json()[k] for k in ('snapshot_id', 'revision_id')}
    return history, model, client, context


def test_example_matches_manual_query_without_writes(setup):
    history, model, client, context = setup
    before = client.get('/candidates').json()
    filters = {'rag':'AMBER', 'ranges':{'N_TRIALS_USED':{'min':3, 'unit':'trials'}}}
    model.script.append(say(json.dumps({'status':'ready', 'filters':filters})))
    result = client.post('/filters/interpret', json={**context, 'text':'Show AMBER candidates with at least three usable trials'}).json()
    assert result['filters']['ranges']['N_TRIALS_USED']['min'] == 3
    assert result['filters']['include_missing'] is False
    assert model.tools == [[]]
    assert len(model.seen) == 1 and len(model.seen[0]) == 2
    validated = client.post('/filters/validate', json={**context, 'filters':result['filters']})
    assert validated.status_code == 200
    manual = client.get('/candidates', params={'rag':'AMBER', 'ranges':json.dumps({'N_TRIALS_USED':{'min':3}})}).json()
    assert validated.json()['total'] == manual['total'] > 0
    exported = client.get('/candidates.csv', params={'rag':'AMBER', 'ranges':json.dumps({'N_TRIALS_USED':{'min':3}})}).text
    assert {line.split(',')[0] for line in exported.splitlines()[1:]} == {r['material_id'] for r in manual['rows']}
    assert client.get('/candidates').json() == before
    assert history.decisions() == [] and history.enrichment() == []
    # The corrected preview, not the original interpretation, is validated.
    result['filters']['ranges']['N_TRIALS_USED']['min'] = 4
    edited = client.post('/filters/validate', json={**context, 'filters':result['filters']})
    assert edited.status_code == 200 and edited.json()['total'] <= manual['total']


@pytest.mark.parametrize('text', ['Show reviewed candidates','Show decided candidates','Show latest overrides'])
def test_new_queues_require_manual_controls_without_model_call(setup, text):
    history, model, client, context = setup
    result = client.post('/filters/interpret', json={**context,'text':text})
    assert result.status_code == 200 and result.json()['status'] == 'clarification'
    assert 'Review state controls' in result.json()['clarification']
    assert result.json()['filters'] is None and not model.seen and not history.decisions()


@pytest.mark.parametrize('text', [
    'Predict which candidates will thrive in coastal soil',
    'Forecast candidate yield next season',
    'Show GREEN candidates and predict which will thrive in coastal soil',
    'Find yield improvement of three percentage points',
    'Show GREEN candidates with a three percentage-point yield improvement',
])
def test_unsupported_requests_clarify_without_partial_filters_or_model(setup, text):
    from uc4_mcp.filter_intent import interpret
    history, model, client, context = setup
    result = client.post('/filters/interpret', json={**context, 'text':text})
    assert result.status_code == 200
    assert result.json()['status'] == 'clarification' and result.json()['filters'] is None
    assert 'No partial filters were proposed' in result.json()['clarification']
    direct = anyio.run(interpret, text, model)
    assert direct.status == 'clarification' and direct.filters is None
    assert not model.seen and history.decisions() == [] and history.enrichment() == []


def test_prediction_clarification_available_without_model_configuration(setup):
    history, _, _, context = setup
    def unavailable():
        raise LLMError('Model unavailable')
    client = TestClient(create_candidate_app(unavailable, get_history=lambda: history))
    result = client.post('/filters/interpret', json={**context, 'text':'Predict candidate yield'})
    assert result.status_code == 200 and result.json()['status'] == 'clarification'
    assert result.json()['filters'] is None


@pytest.mark.parametrize('filters', [
    {'rag':'BLUE'}, {'action':'ADVANCE'}, {'sort':'rag'},
    {'ranges':{'UNKNOWN':{'min':1, 'unit':'%'}}},
    {'ranges':{'GERMINATION_PCT':{'min':90, 'unit':'ppm'}}},
    {'ranges':{'GERMINATION_PCT':{'min':91, 'max':90, 'unit':'%'}}},
    {'ranges':{'N_TRIALS_USED':{'min':2.5, 'unit':'trials'}}},
    {'ranges':{'N_TRIALS_USED':{'min':-1, 'unit':'trials'}}},
    {'ranges':{'N_TRIALS_USED':{'min':True, 'unit':'trials'}}},
    {'ranges':{'N_TRIALS_USED':{'unit':'trials'}}},
    {'include_missing':'false'}, {'search':'UNKNOWN-CANDIDATE'},
])
def test_reject_invalid_edited_filters(setup, filters):
    _, _, client, context = setup
    assert client.post('/filters/validate', json={**context, 'filters':filters}).status_code == 422


@pytest.mark.parametrize('completion', [say('not JSON'), say('{"status":"ready","filters":{"action":"HOLD"}}'),
    say('{"status":"clarification","filters":{"rag":"AMBER"},"clarification":"Which rule?"}'),
    call('record_decision', action='ADVANCE'), LLMError('Model timeout')])
def test_invalid_output_and_model_failure_are_read_only(setup, completion):
    history, model, client, context = setup
    model.script.append(completion)
    assert client.post('/filters/interpret', json={**context, 'text':'Show candidates'}).status_code == 503
    assert history.decisions() == [] and history.enrichment() == []


@pytest.mark.parametrize('text', ['Show not AMBER', 'Germination above 90%', 'Make 90% my GREEN minimum',
    'Show AMBER and record HOLD', 'Predict regional yield', 'At least three but at most two usable trials'])
def test_clarification_has_no_partial_filters(setup, text):
    _, model, client, context = setup
    model.script.append(say(json.dumps({'status':'clarification', 'clarification':'Please clarify the supported filters.'})))
    result = client.post('/filters/interpret', json={**context, 'text':text}).json()
    assert result['status'] == 'clarification' and result['filters'] is None


def test_stale_context_and_empty_request(setup):
    _, model, client, context = setup
    assert client.post('/filters/interpret', json={**context, 'text':' '}).status_code == 422
    assert client.post('/filters/interpret', json={**context, 'revision_id':'stale', 'text':'Show AMBER'}).status_code == 409
    assert client.post('/filters/validate', json={**context, 'snapshot_id':'stale', 'filters':{}}).status_code == 409
    assert not model.seen


def test_decimal_missing_and_finite_bounds(setup):
    _, _, client, context = setup
    body = {**context, 'filters':{'include_missing':True, 'ranges':{'GERMINATION_PCT':{'min':90.5, 'unit':'%'}}}}
    assert client.post('/filters/validate', json=body).status_code == 200
    body['filters']['ranges']['GERMINATION_PCT']['min'] = float('inf')
    assert client.post('/filters/validate', content=json.dumps(body), headers={'Content-Type':'application/json'}).status_code == 422


def test_revision_change_during_interpretation_rejects_proposal(setup):
    history, model, client, context = setup
    item = history.draft(query='SYN-MZ-00001', kind='metadata', field='NOTE', value='Review context',
                         actor='Test', reason='Record context', observed_at='2026-10-01', source='Notebook')
    history.review(item['id'], 'submit', 'Test', 'Submit context')
    history.review(item['id'], 'approve', 'Test', 'Review context')
    original = model.complete

    async def changing_model(messages, tools):
        history.activate(item['id'], context['revision_id'], 'Test', 'Activate context')
        return await original(messages, tools)

    model.complete = changing_model
    model.script.append(say('{"status":"ready","filters":{"rag":"AMBER"}}'))
    result = client.post('/filters/interpret', json={**context, 'text':'Show AMBER'})
    assert result.status_code == 409
    assert history.decisions() == []
