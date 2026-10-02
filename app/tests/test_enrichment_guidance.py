"""Guided enrichment validation and preview provenance; all stores are disposable."""
import pytest
from fastapi.testclient import TestClient
from uc4_mcp.candidate_api import create_candidate_app
from uc4_mcp.candidate_history import CandidateHistory


@pytest.fixture
def history(tmp_path):
    return CandidateHistory(path=tmp_path / 'history.sqlite3', legacy_log=tmp_path / 'legacy.jsonl')


def payload(history, table='lab', field='NUMBER_VALUE'):
    detail = history.store().detail('SYN-MZ-00001')['result']
    row = detail['evidence'][table][0]
    unit = next((t['UNIT'] for t in detail['dictionary'] if t['TRAIT_GUID'] == row.get('TRAIT_GUID')), None)
    return dict(query=detail['material_id'], kind='correction', table=table, row_id=row['row_id'],
                field=field, value=91.25, unit=unit, actor='Ada', source='Worksheet 7, row 2',
                observed_at='2026-10-01', reason='Verified against original worksheet')


def approve(history, item):
    history.review(item['id'], 'submit', 'Ada', 'Ready for review')
    history.review(item['id'], 'approve', 'Ada', 'Verified the source')
    return history.preview(item['id'])


@pytest.mark.parametrize('change,message', [
    ({'source':'  '}, 'Evidence source'), ({'observed_at':''}, 'When observed'),
    ({'actor':' '}, 'Author'), ({'reason':'    x'}, 'Why change it'),
    ({'unit':'kg'}, 'Expected unit'), ({'value':''}, 'finite number'),
    ({'value':float('inf')}, 'finite number'), ({'value':True}, 'finite number'),
    ({'observed_at':'yesterday'}, 'ISO'), ({'supersedes':'unrelated'}, 'earlier addition'),
])
def test_invalid_correction_preserves_active_state(history, change, message):
    before = history.active_revision()
    with pytest.raises(ValueError, match=message):
        history.draft(**(payload(history) | change))
    assert history.enrichment() == []
    assert history.active_revision() == before


def test_preview_provenance_and_supersession(history):
    args = payload(history)
    original = history.tables['lab'].loc[history.tables['lab'].ROWGUID == args['row_id'], 'NUMBER_VALUE'].iloc[0]
    first = history.draft(**args)
    preview = approve(history, first)
    assert preview['snapshot_id'] == history.snapshot_id
    change = preview['source_change']
    assert change['original'] == change['current'] == original
    assert change['proposed'] == 91.25 and change['source'] == args['source']
    history.activate(first['id'], preview['base_revision'], 'Ada', 'Activate verified correction')
    with pytest.raises(ValueError, match='explicitly select'):
        history.draft(**(args | {'value':92}))
    second = history.draft(**(args | {'value':92, 'supersedes':first['id']}))
    preview = approve(history, second)
    assert preview['source_change']['current'] == 91.25
    assert preview['source_change']['original'] == original
    assert preview['source_change']['proposed'] == 92
    client = TestClient(create_candidate_app(lambda: None, get_history=lambda: history))
    response = client.get('/enrichment/' + second['id'] + '/preview')
    assert response.status_code == 200 and response.json()['source_change'] == preview['source_change']


@pytest.mark.parametrize('table,field,value,unit', [
    ('genomics','GENOMIC_BREEDING_VALUE',1.25,'index'),
    ('genomics','MARKER_DISEASE_RESISTANCE','RESISTANT',None),
    ('operations','STATUS_LID','MISSED',None),
    ('operations','DELAY_DAYS',2,'days'),
    ('operations','ACTUAL_DATE',None,None),
])
def test_supported_correction_types(history, table, field, value, unit):
    item = history.draft(**(payload(history, table, field) | {'value':value,'unit':unit}))
    preview = approve(history, item)
    assert preview['source_change']['proposed'] == value
    result = history.activate(item['id'], preview['base_revision'], 'Ada', 'Activate verified correction')
    assert result['revision_id'] == history.active_revision()
    with pytest.raises(ValueError, match='approved'):
        history.activate(item['id'], preview['base_revision'], 'Ada', 'Duplicate activation')


@pytest.mark.parametrize('field', ['NOTE','PEDIGREE','STAGE_CODE_LID','RESEARCH_STATION_GUID','SITE'])
def test_context_only_preview(history, field):
    item = history.draft(query='SYN-MZ-00001',kind='metadata',field=field,value='Sourced context',
                         actor='Ada',source='Notebook page 7',observed_at='2026-10-01',reason='Capture observed context')
    preview = approve(history, item)
    assert preview['affected'] == []
    assert preview['source_change']['proposed'] == 'Sourced context'


def test_unrelated_candidate_row_rejected(history):
    args = payload(history)
    with pytest.raises(ValueError, match='another candidate'):
        history.draft(**(args | {'query':'SYN-MZ-00002'}))


def test_http_rejects_boolean_measurement_without_coercion(history):
    client = TestClient(create_candidate_app(lambda: None, get_history=lambda: history))
    response = client.post('/enrichment', json=payload(history) | {'value':True})
    assert response.status_code == 422
    assert history.enrichment() == []


def test_shared_check_activation_matches_every_preview_row(history):
    detail = history.store().detail('SYN-MZ-00001')['result']
    checks = {x['TRIAL_ENTRY_GUID'] for x in detail['evidence']['bridge'] if x['ENTRY_ROLE_LID']=='CHECK'}
    row = next(x for x in detail['evidence']['observation'] if x['TRIAL_ENTRY_RELATIONSHIP_GUID'] in checks and x['TRAIT_CODE']=='YIELD_T_HA')
    item = history.draft(**(payload(history) | dict(table='observation',row_id=row['row_id'],value=row['NUMBER_VALUE']+1,unit='t/ha')))
    preview = approve(history, item)
    assert len(preview['affected']) > 1
    history.activate(item['id'],preview['base_revision'],'Ada','Activate verified shared evidence')
    for changed in preview['affected']:
        rec = history.store().resolve(changed['material_id'])['result']
        assert rec['metrics'] == changed['after_metrics']
        assert rec['rag'] == changed['after']
