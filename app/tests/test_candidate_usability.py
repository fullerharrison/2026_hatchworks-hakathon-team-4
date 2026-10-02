"""Core usability contracts, with isolated evidence/history and scripted models."""
import pytest
from fastapi.testclient import TestClient
from uc4_mcp.candidate_api import create_candidate_app
from uc4_mcp.candidate_history import CandidateHistory
from fakes import FakeChat, call, say

@pytest.fixture
def history(tmp_path):
    return CandidateHistory(path=tmp_path/'history.sqlite3', legacy_log=tmp_path/'legacy.jsonl')

def test_rule_and_assessments_preserve_baseline(history):
    client=TestClient(create_candidate_app(lambda: None,get_history=lambda:history))
    rule=client.get('/rule').json()
    assert len(rule['gates'])==7 and len(rule['knockouts'])==3 and len(rule['warnings'])==2
    assert rule['no_field_data_precedence']=='AMBER'
    rows=client.get('/candidates').json()['rows']
    assert {c:sum(r['rag']==c for r in rows) for c in ('GREEN','AMBER','RED')}=={'GREEN':32,'AMBER':53,'RED':65}
    cases=[next(r for r in rows if r['rag']==c) for c in ('GREEN','AMBER','RED')]
    cases.append(next(r for r in rows if r['metrics']['N_TRIALS_USED']==0))
    for row in cases:
        r=client.get('/candidates/'+row['material_id']).json()
        assert len(r['assessments'])==7
        for a in r['assessments']:
            assert a['status']==('Unknown' if a['value'] is None else 'Meets gate' if a['passed'] else 'Outside GREEN target')
            if a['value'] is not None and a['test']!='in':
                assert a['margin']==pytest.approx(a['value']-a['threshold'])
        assert r['dictionary']
        assert bool(r['evidence']['bridge']) == (r['metrics']['N_TRIALS'] > 0)
    amber=client.get('/candidates/SYN-MZ-00001').json()
    moisture=next(a for a in amber['assessments'] if a['field']=='MOISTURE_PCT_MEAN')
    assert moisture['margin']==pytest.approx(0.7666666666666666)

def test_ask_pins_revision_during_activation_and_respects_explicit_candidate(history):
    base=history.active_revision()
    item=history.draft(query='SYN-MZ-00001',kind='metadata',field='NOTE',value='New context',actor='Ada',reason='Record context',observed_at='2026-10-01',source='Notebook')
    history.review(item['id'],'submit','Ada','Submit context')
    history.review(item['id'],'approve','Ada','Review context')
    class ActivatingChat(FakeChat):
        async def complete(self,messages,tools):
            if not self.seen:
                history.activate(item['id'],base,'Ada','Activate context')
            return await super().complete(messages,tools)
    model=ActivatingChat([call('get_candidate',query='SYN-MZ-00002'),say('Evidence inspected [tool:get_candidate].')])
    client=TestClient(create_candidate_app(lambda:model,get_history=lambda:history))
    response=client.post('/ask',json={'question':'Tell me about SYN-MZ-00002','candidate':'SYN-MZ-00001','revision_id':base}).json()
    assert response['status']=='answered'
    assert response['context']['revision_id']==base!=history.active_revision()
    result=response['tool_calls'][0]['result']['result']
    assert result['revision_id']==base and result['material_id']=='SYN-MZ-00002'
    assert response['citations'][0]['found']
    assert 'explicit references to other candidates take precedence' in model.seen[0][-1]['content']
    assert client.post('/ask',json={'question':'Why?','revision_id':'missing'}).status_code==404
    assert client.post('/ask',json={'question':'Why?','candidate':'SYN-MZ-0001'}).status_code==409

def test_legacy_ask_request_remains_supported(history):
    model=FakeChat([call('get_candidate_rule'),say('Policy inspected [tool:get_candidate_rule].')])
    client=TestClient(create_candidate_app(lambda:model,get_history=lambda:history))
    result=client.post('/ask',json={'question':'Explain the policy','history':[]}).json()
    assert result['status']=='answered' and result['context']['candidate'] is None


def test_unknown_and_unrounded_assessment_status(history):
    store=history.store()
    guid=store.resolve('SYN-MZ-00001')['result']['material_guid']
    record=next(r for r in store.effective.to_dict('records') if r['MATERIAL_GUID']==guid)
    record['MOISTURE_PCT_MEAN']=23.00001
    record['GERMINATION_PCT']=float('nan')
    store.by_guid[guid]=store._recommendation(record)
    detail=store.detail(guid)['result']
    assessments={a['field']:a for a in detail['assessments']}
    assert assessments['MOISTURE_PCT_MEAN']['status']=='Outside GREEN target'
    assert round(assessments['MOISTURE_PCT_MEAN']['value'],2)==23.0
    assert assessments['GERMINATION_PCT']['status']=='Unknown'
    assert assessments['GERMINATION_PCT']['margin'] is None
