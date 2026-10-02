"""Candidate workflows with real browser input and an isolated history database."""
from __future__ import annotations

import os
import json
from pathlib import Path

import pytest
from uc4_mcp.demo_runtime import candidate_demo_server

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser
REPO = Path(__file__).resolve().parents[2]
BROWSER_CHANNEL = None if os.environ.get("UC4_BROWSER_CHANNEL", "chromium") == "chromium" else "chrome"


def select_section(page, name):
    page.locator('#tab-' + name).click()


def preview_filters(page):
    context = page.request.get(page.url + 'health').json()
    result = dict(status='ready', clarification='', snapshot_id=context['snapshot_id'],
                  revision_id=context['revision_id'], filters=dict(search='', rag='AMBER',
                  decision='', marker='', excluded=None, include_missing=False,
                  ranges={'N_TRIALS_USED':{'min':3, 'max':None, 'unit':'trials'}}))
    page.route('**/filters/interpret', lambda route: route.fulfill(json=result))
    page.locator('#filter-request').fill('Show AMBER candidates with at least three usable trials')
    page.locator('#filter-interpret').click()
    playwright.expect(page.locator('#filter-preview')).to_be_visible()


def test_typed_filter_preview_apply_preserves_drafts(screen):
    page, folder = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail')).to_be_visible()
    select_section(page, "decision")
    page.locator('#reason').fill('Keep this manual decision draft')
    select_section(page, "enrichment")
    page.locator('#enrich-value').fill('Keep this evidence draft')
    page.locator('#rag').select_option('GREEN')
    page.locator('#sort').select_option('rag')
    expect(page.locator('#rows tr')).to_have_count(32)
    page.locator('#preferences-panel summary').click()
    page.locator('#remember-view').check()
    preview_filters(page)
    expect(page.locator('#rows tr')).to_have_count(32)
    page.locator('#filter-intent').screenshot(path=str(folder/'typed-filter-desktop.png'))
    expect(page.locator('#rag')).to_have_value('GREEN')
    expect(page.locator('#proposal-rag')).to_have_value('AMBER')
    page.locator('#proposal-N_TRIALS_USED-min').fill('2')
    page.locator('#filter-apply').click()
    expect(page.locator('#filter-preview')).to_be_hidden()
    expect(page.locator('#rag')).to_have_value('AMBER')
    expect(page.locator('#sort')).to_have_value('rag')
    expect(page.locator('#reason')).to_have_value('Keep this manual decision draft')
    expect(page.locator('#enrich-value')).to_have_value('Keep this evidence draft')
    expected = page.request.get(page.url + 'candidates', params={'rag':'AMBER', 'sort':'rag', 'ranges':json.dumps({'N_TRIALS_USED':{'min':2}})}).json()
    expect(page.locator('#rows tr')).to_have_count(expected['total'])
    ids = page.locator('#rows tr td:first-child').all_text_contents()
    assert ids == [r['material_id'] for r in expected['rows']]
    saved = page.evaluate("JSON.parse(localStorage.getItem('uc4.preferences'))")
    assert saved['view']['ranges'] == {'N_TRIALS_USED':{'min':2}}
    assert 'text' not in saved['view']
    with page.expect_download() as download:
        page.locator('#export').click()
    download.value.save_as(folder/'typed.csv')
    assert {line.split(',')[0] for line in (folder/'typed.csv').read_text().splitlines()[1:]} == set(ids)
    assert page.request.get(page.url + 'decisions').json() == []
    assert page.request.get(page.url + 'enrichment').json() == []
    page.reload()
    expect(page.locator('#rag')).to_have_value('AMBER')
    expect(page.locator('#filter-request')).to_have_value('')


def test_typed_filter_cancel_stale_validation_and_mobile(screen):
    page, folder = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.set_viewport_size({'width':390, 'height':844})
    preview_filters(page)
    page.locator('#filter-intent').screenshot(path=str(folder/'typed-filter-mobile.png'))
    page.locator('#filter-cancel').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#filter-preview')).to_be_hidden()
    expect(page.locator('#filter-request')).to_be_focused()
    expect(page.locator('#rows tr')).to_have_count(150)
    preview_filters(page)
    page.locator('#filter-request').fill('Show RED')
    expect(page.locator('#filter-preview')).to_be_hidden()
    preview_filters(page)
    page.locator('#rag').select_option('RED')
    expect(page.locator('#filter-preview')).to_be_hidden()
    expect(page.locator('#rows tr')).to_have_count(65)
    preview_filters(page)
    page.route('**/filters/validate', lambda route: route.fulfill(status=409, json={'detail':'Evidence changed. Interpret again.'}))
    page.locator('#filter-apply').click()
    expect(page.locator('#filter-intent-status')).to_contain_text('Evidence changed')
    expect(page.locator('#rag')).to_have_value('RED')
    page.locator('#reset').click()
    expect(page.locator('#filter-preview')).to_be_hidden()
    page.unroute('**/filters/interpret')
    page.locator('#filter-interpret').click()
    expect(page.locator('#filter-intent-status')).to_contain_text('Manual filters remain available')
    expect(page.locator('#filter-request')).not_to_have_value('')


def test_typed_filter_ignores_late_interpretation(screen):
    page, _ = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    # Hold the network response until the user has edited the request.
    page.evaluate("""() => {
      const original = window.fetch;
      window.fetch = (url, options) => url === '/filters/interpret'
        ? new Promise(resolve => { window.finishInterpret = () => resolve(new Response(JSON.stringify({
            status:'clarification', clarification:'Obsolete reply'}), {status:200})); })
        : original(url, options);
    }""")
    page.locator('#filter-request').fill('Show AMBER')
    page.locator('#filter-interpret').click()
    expect(page.locator('#filter-intent-status')).to_contain_text('Interpreting')
    page.locator('#filter-request').fill('Show GREEN')
    page.evaluate('window.finishInterpret()')
    expect(page.locator('#filter-intent-status')).to_have_text('')
    expect(page.locator('#filter-preview')).to_be_hidden()


@pytest.fixture(scope="session")
def candidate_browser():
    # Share the browser process, never a context, database or application server.
    with playwright.sync_playwright() as driver:
        browser = driver.chromium.launch(channel=BROWSER_CHANNEL, timeout=60000)
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def screen(tmp_path, candidate_browser):
    with candidate_demo_server(tmp_path, archive=REPO / "get_started/candidate_recommendations_synthetic.zip") as runtime:
        (tmp_path / "runtime.json").write_text(json.dumps({"startup_seconds":runtime.startup_seconds,
            "readiness":"HTTP /health checked", "database":str(runtime.history.path)}), encoding="utf-8")
        context = candidate_browser.new_context(viewport={"width":1440, "height":1100})
        context.set_default_navigation_timeout(60000)
        try:
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(runtime.url, wait_until="domcontentloaded")
            page.wait_for_function("document.querySelector('#count').textContent.startsWith('Candidates:')", timeout=60000)
            yield page, tmp_path
            assert not errors, errors
        finally:
            context.close()


def test_candidate_filter_decision_review_and_history(screen):
    page, folder = screen
    expect = playwright.expect
    expect(page.locator("#rows tr")).to_have_count(150)
    page.locator("#rag").select_option("GREEN")
    expect(page.locator("#rows tr")).to_have_count(32)
    page.locator("#metric").select_option("N_TRIALS_USED")
    page.locator("#min").fill("2")
    page.locator("#add-range").click()
    expect(page.locator("#ranges")).to_contain_text("Usable trials")
    expect(page.locator("#rows tr")).to_have_count(32)
    with page.expect_download() as download:
        page.locator("#export").click()
    downloaded = download.value
    downloaded.save_as(folder / "filtered.csv")
    assert len((folder / "filtered.csv").read_text().splitlines()) == 33
    page.locator("#reset").click()
    expect(page.locator("#rows tr")).to_have_count(150)
    page.locator("#search").fill("SYN-MZ-00001")
    expect(page.locator("#rows tr")).to_have_count(1)
    page.locator("#rows tr").click()
    expect(page.locator("#detail")).to_be_visible()
    expect(page.locator("#recommendation")).to_contain_text("AMBER")
    select_section(page, "decision")
    page.locator("#actor").fill("Breeder Ada")
    select_section(page, "decision")
    page.locator("#action").select_option("ADVANCE")
    select_section(page, "decision")
    page.locator("#decision-context summary").click()
    select_section(page, "decision")
    page.locator("#location").fill("Research review meeting")
    select_section(page, "decision")
    page.locator("#source-channel").fill("Breeder screen")
    select_section(page, "decision")
    page.locator("#reason").fill("Advance after reviewing the field evidence")
    select_section(page, "decision")
    page.locator("#review-decision").click()
    select_section(page, "decision")
    page.locator("#record-decision").click()
    expect(page.locator("#decision-history")).to_contain_text("Recorded by Breeder Ada")
    expect(page.locator("#decision-history")).to_contain_text("override yes")
    select_section(page, "enrichment")
    page.locator("#enrich-author").fill("Breeder Ada")
    select_section(page, "enrichment")
    page.locator("#enrich-value").fill("Repeat cold test before the next review")
    select_section(page, "enrichment")
    page.locator("#observed-at").fill("2026-10-01T09:30")
    select_section(page, "enrichment")
    page.locator("#enrich-source").fill("Breeder notebook")
    select_section(page, "enrichment")
    page.locator("#enrich-reason").fill("Capture follow-up for the next decision")
    select_section(page, "enrichment")
    page.locator("#enrichment-form button[type=submit]").click()
    expect(page.locator("#enrichment-history")).to_contain_text("DRAFT")
    select_section(page, "enrichment")
    page.get_by_role("button", name="Submit for review", exact=True).click()
    select_section(page, "enrichment")
    page.locator("#enrichment-action-reason").fill("Ready for review")
    page.get_by_role("button", name="Confirm submission", exact=True).click()
    expect(page.locator("#enrichment-history")).to_contain_text("SUBMITTED")
    page.get_by_role("button", name="Approve", exact=True).click()
    select_section(page, "enrichment")
    page.locator("#enrichment-action-reason").fill("Checked source evidence")
    page.get_by_role("button", name="Confirm approval", exact=True).click()
    expect(page.locator("#enrichment-history")).to_contain_text("APPROVED")
    select_section(page, "enrichment")
    page.get_by_role("button", name="Preview impact", exact=True).click()
    expect(page.locator("#enrichment-message")).to_contain_text("0 candidates")
    select_section(page, "enrichment")
    page.locator("#enrichment-action-reason").fill("Activate verified evidence")
    with page.expect_response(lambda response: response.url.endswith('/activate')) as activation:
        select_section(page, "enrichment")
        page.get_by_role("button", name="Activate reviewed change", exact=True).click()
    assert activation.value.ok
    expect(page.locator("#enrichment-history")).to_contain_text("ACTIVATED")
    expect(page.locator("#decision-history")).to_contain_text("baseline:")
    select_section(page, "history")
    page.get_by_role("button", name="View original recommendation and evidence", exact=True).click()
    expect(page.locator("#evidence-dialog-body")).to_contain_text("baseline:")
    with page.expect_response(lambda response: "/revisions/baseline" in response.url) as original_evidence:
        page.get_by_role("button", name="Browse original evidence", exact=True).click()
    assert original_evidence.value.ok
    assert original_evidence.value.json()["revision_id"].startswith("baseline:")
    page.locator("#evidence-close").click()
    page.locator("#open-history").click()
    expect(page.locator("#evidence-dialog-body")).to_contain_text("Original source archive")
    page.locator("#evidence-close").click()
    page.locator("#question").fill("Why is this candidate amber?")
    page.locator("#ask-form button[type=submit]").click()
    expect(page.locator("#answer")).to_contain_text("Ask is unavailable right now")
    page.screenshot(path=str(folder / "candidate-workflow.png"), full_page=True)


def test_usability_help_alias_switch_and_mobile_ask(screen):
    page, folder = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rag').select_option('RED')
    expect(page.locator('#active-filters')).to_contain_text('RED')
    page.locator('#active-filters button').click()
    expect(page.locator('#rows tr')).to_have_count(150)
    help_button=page.locator('label').filter(has=page.locator('#search')).get_by_role('button')
    help_button.focus()
    expect(help_button).to_have_attribute('aria-expanded','true')
    help_button.press('Escape')
    expect(help_button).to_have_attribute('aria-expanded','false')
    page.locator('#rows tr').first.click()
    expect(page.locator('#criteria')).to_contain_text('Outside GREEN target')
    expect(page.locator('#criteria')).to_contain_text('23.77')
    expect(page.locator('#action')).to_have_value('')
    select_section(page, "decision")
    page.locator('#actor').fill('Session Ada')
    save_preferences(page, name='Session Ada')
    select_section(page, "decision")
    page.locator('#action').select_option('HOLD')
    select_section(page, "decision")
    page.locator('#reason').fill('Needs additional evidence')
    page.locator('#rows tr').nth(1).click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00002')
    expect(page.locator('#reason')).to_have_value('')
    expect(page.locator('#action')).to_have_value('')
    expect(page.locator('#actor')).to_have_value('Session Ada')
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#actor')).to_have_value('Session Ada')
    page.locator('#preferences-panel').evaluate('(node) => node.open = true')
    page.locator('#forget-preferences').click()
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#actor')).to_have_value('')
    page.set_viewport_size({'width':390,'height':844})
    select_section(page, "decision")
    page.locator('#reason').scroll_into_view_if_needed()
    expect(page.locator('#ask-launcher')).to_be_visible()
    page.locator('#ask-launcher').click()
    expect(page.locator('#question')).to_be_focused()
    page.locator('#question').fill('Why is this candidate AMBER?')
    page.locator('#ask-form button[type=submit]').click()
    expect(page.locator('#answer')).to_contain_text('Ask is unavailable right now')
    expect(page.locator('#question')).to_have_value('Why is this candidate AMBER?')
    page.screenshot(path=str(folder/'mobile-ask.png'),full_page=False)
    page.locator('#ask-close').click()
    expect(page.locator('#ask-launcher')).to_be_focused()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(folder/'mobile-decision.png'),full_page=False)


def test_ask_delayed_response_keeps_original_context(screen):
    page, folder = screen
    expect=playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00001')
    held=[]
    page.route('**/ask',lambda route:held.append(route))
    page.locator('#question').fill('Why is this candidate AMBER?')
    page.locator('#ask-form button[type=submit]').click()
    page.locator('#rows tr').nth(1).click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00002')
    assert held and held[0].request.post_data_json['candidate']
    held[0].fulfill(json={'status':'answered','text':'Original moisture 23.7666666667% evidence answer','disclaimer':'Synthetic',
        'context':{'candidate':'SYN-MZ-00001','revision_id':'original-revision'},
        'citations':[{'ref':'tool:get_candidate','found':True}],
        'tool_calls':[{'name':'get_candidate','result':{'material_id':'SYN-MZ-00001'}}]})
    expect(page.locator('#answer')).to_contain_text('SYN-MZ-00001 / original-revision')
    expect(page.locator('#ask-context')).to_contain_text('SYN-MZ-00002')
    page.locator('#answer button').click()
    expect(page.locator('#evidence-dialog-body')).to_contain_text('23.77%')
    page.locator('.answer-sources button').click()
    expect(page.locator('#evidence-dialog-body')).to_contain_text('SYN-MZ-00001')
    page.locator('#evidence-back').click()
    expect(page.locator('#evidence-dialog-body')).to_contain_text('23.77%')
    page.locator('#evidence-close').click()
    expect(page.locator('#answer button')).to_be_focused()


@pytest.mark.parametrize("failure", ["gateway", "http", "network"])
def test_ask_failure_blocks_overlap_preserves_question_and_allows_retry(screen, failure):
    page, folder = screen
    expect = playwright.expect
    if failure == "http":
        page.set_viewport_size({"width":390, "height":844})
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00001')
    if failure == "http":
        page.locator('#ask-launcher').click()
    held = []
    page.route('**/ask', lambda route: held.append(route))
    question = 'What is keeping this candidate from GREEN?'
    page.locator('#question').fill(question)
    button = page.locator('#ask-form button[type=submit]')
    button.click()
    expect(button).to_be_disabled()
    expect(page.locator('#ask-form')).to_have_attribute('aria-busy', 'true')
    page.locator('#question').press('Enter')
    assert len(held) == 1
    detail = 'LLM gateway error: Error code: 500 - bedrock unexpected error'
    if failure == "gateway":
        held[0].fulfill(json={'status':'error', 'text':detail,
            'context':{'candidate':'SYN-MZ-00001','revision_id':'request-revision'},
            'citations':[], 'tool_calls':[]})
    elif failure == "http":
        held[0].fulfill(status=503, json={'detail':detail})
    else:
        held[0].abort('failed')
    expect(page.locator('#answer')).to_contain_text('Ask is unavailable right now')
    expect(page.locator('#answer')).to_contain_text('SYN-MZ-00001')
    expect(page.locator('#answer')).not_to_contain_text('bedrock')
    expect(page.locator('#answer button')).to_have_count(0)
    expect(page.locator('#question')).to_have_value(question)
    expect(button).to_be_enabled()
    expect(page.locator('#ask-form')).to_have_attribute('aria-busy', 'false')
    page.screenshot(path=str(folder / (failure + '-ask-unavailable.png')))
    button.click()
    expect(button).to_be_disabled()
    assert len(held) == 2
    held[1].fulfill(json={'status':'answered', 'text':'Retrieved evidence answer.',
        'context':{'candidate':'SYN-MZ-00001','revision_id':'request-revision'},
        'citations':[], 'tool_calls':[]})
    expect(page.locator('#answer')).to_contain_text('Answer ready')
    expect(button).to_be_enabled()
    expect(page.locator('#question')).to_have_value(question)
    assert page.request.get(page.url + 'decisions').json() == []
    assert page.request.get(page.url + 'enrichment').json() == []


def test_decision_retry_uses_same_confirmation_and_no_duplicate_event(screen):
    page,folder=screen
    expect=playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    select_section(page, "decision")
    page.locator('#actor').fill('Retry Ada')
    select_section(page, "decision")
    page.locator('#action').select_option('HOLD')
    select_section(page, "decision")
    page.locator('#reason').fill('Wait for another usable trial')
    requests=[]
    def lose_first_response(route):
        requests.append(route.request.post_data_json)
        result=route.fetch()
        if len(requests)==1:
            route.abort()
        else:
            route.fulfill(response=result)
    page.route('**/decisions',lose_first_response)
    select_section(page, "decision")
    page.locator('#review-decision').click()
    select_section(page, "decision")
    page.locator('#record-decision').click()
    expect(page.locator('#decision-message')).to_contain_text('Save could not be confirmed')
    select_section(page, "decision")
    page.locator('#record-decision').click()
    expect(page.locator('#decision-message')).to_contain_text('Decision recorded:')
    assert len(requests)==2 and requests[0]['request_id']==requests[1]['request_id']
    assert len(page.request.get(page.url+'decisions').json())==1
    expect(page.locator('#reason')).to_have_value('')


def test_four_source_cases_match_api_assessments(screen):
    page,folder=screen
    expect=playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    for material in ('SYN-MZ-00004','SYN-MZ-00001','SYN-MZ-00007','SYN-MZ-00149'):
        detail=page.request.get(page.url+'candidates/'+material).json()
        page.locator('#search').fill(material)
        expect(page.locator('#rows tr')).to_have_count(1)
        expect(page.locator('#rows tr')).to_contain_text(material)
        page.locator('#rows tr').click()
        expect(page.locator('#detail-title')).to_contain_text(material)
        for index,a in enumerate(detail['assessments']):
            row=page.locator('#criteria > tr').nth(index)
            expect(row).to_contain_text(a['status'])
            if isinstance(a['value'],(int,float)):
                value=str(int(a['value'])) if a['field'].startswith('N_TRIALS') else f"{a['value']:.2f}"
                expect(row.locator('td').nth(1)).to_contain_text(value)
        if detail['metrics']['N_TRIALS_USED']==0:
            expect(page.locator('#recommendation')).to_contain_text('No usable field data')
    page.locator('#search').fill('SYN-MZ-00001')
    expect(page.locator('#rows tr')).to_have_count(1)
    expect(page.locator('#rows tr')).to_contain_text('SYN-MZ-00001')
    page.locator('#rows tr').click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00001')
    page.locator('#detail-title').evaluate("el => el.scrollIntoView({block:'start'})")
    page.screenshot(path=str(folder/'desktop-assessment.png'))


def test_evidence_dialog_filters_source_rows_and_preserves_draft(screen):
    page,folder=screen
    expect=playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00001')
    select_section(page, "decision")
    page.locator('#reason').fill('Keep this unsaved decision draft')
    select_section(page, 'evidence')
    row=page.locator('#criteria > tr').nth(2)
    expect(row).to_contain_text('0.77 pp above maximum')
    row.get_by_role('button',name='View evidence',exact=True).click()
    expect(page.locator('#evidence-dialog')).to_be_visible()
    expect(page.locator('#evidence-dialog-body')).to_contain_text('23.766666666666666')
    expect(page.locator('.source-table tbody tr')).not_to_have_count(0)
    for text in page.locator('.source-table tbody tr td:nth-child(3)').all_text_contents():
        assert text=='Moisture'
    expect(page.locator('.source-table')).to_contain_text('Check')
    page.locator('.source-table details summary').first.click()
    expect(page.locator('.source-table')).to_contain_text('Source row')
    page.screenshot(path=str(folder/'source-dialog-desktop.png'))
    page.locator('#evidence-close').press('Escape')
    expect(page.locator('#evidence-dialog')).not_to_be_visible()
    expect(row.get_by_role('button',name='View evidence',exact=True)).to_be_focused()
    expect(page.locator('#reason')).to_have_value('Keep this unsaved decision draft')
    page.set_viewport_size({'width':390,'height':844})
    row.get_by_role('button',name='View evidence',exact=True).click()
    expect(page.locator('#evidence-dialog')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#evidence-dialog').evaluate('el=>el.scrollWidth <= el.clientWidth')
    page.screenshot(path=str(folder/'source-dialog-mobile.png'))
    page.locator('#evidence-close').click()
    page.locator('#rules-panel summary').click()
    page.get_by_role('button',name='View policy evidence',exact=True).click()
    expect(page.locator('#evidence-dialog-title')).to_contain_text('Policy evidence')
    page.locator('#evidence-close').click()
    assert page.locator('pre').count()==0


def test_answer_popup_formats_text_safely_and_mobile_citation_back(screen):
    page,folder=screen
    expect=playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00001')
    page.route('**/ask',lambda route:route.fulfill(json={
        'status':'answered','text':'**Moisture** is 23.766666%. [tool:score_candidate]\n\n<img src=x onerror=alert(1)>',
        'disclaimer':'Synthetic evidence','context':{'candidate':'SYN-MZ-00001','revision_id':'original'},
        'citations':[{'ref':'tool:score_candidate','found':True}],
        'tool_calls':[{'name':'score_candidate','result':{'result':{'material_id':'SYN-MZ-00001','rag':'AMBER','metrics':{'MOISTURE_PCT_MEAN':23.766666}}}}]}))
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#ask-launcher').click()
    page.locator('#question').fill('Why AMBER?')
    page.locator('#ask-form button[type=submit]').click()
    expect(page.locator('#answer')).to_contain_text('Answer ready')
    assert 'Moisture' not in page.locator('#answer').inner_text()
    page.locator('#answer button').click()
    expect(page.locator('#evidence-dialog-body strong')).to_have_text('Moisture')
    expect(page.locator('#evidence-dialog-body')).to_contain_text('23.77%')
    assert page.locator('#evidence-dialog-body img').count()==0
    page.locator('.answer-sources button').click()
    expect(page.locator('#evidence-dialog-body')).to_contain_text('AMBER')
    page.locator('#evidence-back').click()
    expect(page.locator('#evidence-dialog-body strong')).to_have_text('Moisture')
    page.screenshot(path=str(folder/'answer-dialog-mobile.png'))
    page.locator('#evidence-close').click()
    expect(page.locator('#answer button')).to_be_focused()
    expect(page.locator('#ask-dialog')).to_be_visible()
    page.locator('#ask-close').click()
    expect(page.locator('#ask-launcher')).to_be_focused()
    assert page.locator('pre').count()==0



def save_preferences(page, name="Breeder Ada", location="Review meeting", channel="Breeder review"):
    page.locator('#preferences-panel').evaluate('(node) => node.open = true')
    page.locator('#preference-name').fill(name)
    page.locator('#preference-location').fill(location)
    page.locator('#preference-channel').fill(channel)
    page.locator('#preferences-form button').click()
    playwright.expect(page.locator('#preferences-status')).to_contain_text('saved in this browser')


def test_preferences_explicit_defaults_and_decision_separation(screen):
    page, folder = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    writes = []
    page.on('request', lambda req: writes.append(req.url) if req.method == 'POST' else None)
    page.locator('#rows tr').first.click()
    select_section(page, "decision")
    page.locator('#actor').fill('Unsaved breeder')
    select_section(page, "decision")
    page.locator('#action').select_option('HOLD')
    select_section(page, "decision")
    page.locator('#reason').fill('Unsaved decision reason')
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    expect(page.locator('#detail')).to_be_hidden()
    assert page.evaluate('localStorage.getItem("uc4.preferences")') is None
    save_preferences(page)
    page.locator('#rows tr').first.click()
    expect(page.locator('#actor')).to_have_value('Breeder Ada')
    expect(page.locator('#location')).to_have_value('Review meeting')
    page.locator('#decision-context').evaluate('(node) => node.open = true')
    select_section(page, "decision")
    page.locator('#location').fill('One-off meeting')
    select_section(page, "decision")
    page.locator('#trial-context').fill('Trial A')
    select_section(page, "decision")
    page.locator('#action').select_option('HOLD')
    select_section(page, "decision")
    page.locator('#reason').fill('Private decision draft')
    page.locator('#preference-name').fill('Unsaved preference edit')
    expect(page.locator('#preferences-status')).to_contain_text('Unsaved preference edits')
    page.locator('#rows tr').nth(1).click()
    expect(page.locator('#location')).to_have_value('Review meeting')
    for field in ('action', 'reason', 'trial-context'):
        expect(page.locator('#'+field)).to_have_value('')
    stored = page.evaluate('JSON.parse(localStorage.getItem("uc4.preferences"))')
    assert stored['defaults']['name'] == 'Breeder Ada'
    assert not stored['rememberView'] and stored['view'] is None
    assert 'Private' not in str(stored) and 'Trial A' not in str(stored)
    assert writes == []
    # A fresh browser context has no tab session storage, but imports the same
    # durable browser storage, as on a subsequent visit to this app origin.
    browser_state = page.context.storage_state()
    with page.context.browser.new_context(storage_state=browser_state) as context:
        next_page = context.new_page()
        next_page.goto(page.url)
        expect(next_page.locator('#rows tr')).to_have_count(150)
        next_page.locator('#rows tr').first.click()
        expect(next_page.locator('#actor')).to_have_value('Breeder Ada')
        expect(next_page.locator('#location')).to_have_value('Review meeting')
        expect(next_page.locator('#reason')).to_have_value('')
    page.locator('#preferences-panel').screenshot(path=str(folder/'preferences-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#preference-name').focus()
    page.locator('#preference-name').press('Tab')
    expect(page.locator('#preference-location')).to_be_focused()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#forget-preferences').evaluate("node => node.scrollIntoView({block:'center'})")
    page.screenshot(path=str(folder/'preferences-mobile.png'), full_page=False)


def test_preferences_resume_reset_forget_and_history(screen):
    page, _ = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    save_preferences(page)
    page.locator('#remember-view').check()
    page.locator('#rows tr').first.click()
    title = page.locator('#detail-title').inner_text()
    select_section(page, "decision")
    page.locator('#action').select_option('HOLD')
    select_section(page, "decision")
    page.locator('#reason').fill('Review again after another field season')
    select_section(page, "decision")
    page.locator('#review-decision').click()
    select_section(page, "decision")
    page.locator('#record-decision').click()
    expect(page.locator('#decision-message')).to_contain_text('Decision recorded')
    for field, value in [('search','SYN-MZ'),('rag','AMBER'),('decision','HOLD'),
                         ('marker','RESISTANT'),('excluded','false'),('sort','N_TRIALS_USED')]:
        if field == 'search':
            page.locator('#'+field).fill(value)
        else:
            page.locator('#'+field).select_option(value)
    page.locator('#descending').check()
    page.locator('#include-missing').check()
    page.locator('#metric').select_option('N_TRIALS_USED')
    page.locator('#min').fill('1')
    page.locator('#max').fill('9')
    page.locator('#add-range').click()
    page.locator('#min').fill('99')  # Unapplied input is not a preference.
    page.wait_for_function('JSON.parse(localStorage.getItem("uc4.preferences")).view.filters.descending')
    page.reload()
    expect(page.locator('#detail-title')).to_have_text(title)
    expect(page.locator('#decision-history')).to_contain_text('Recorded by Breeder Ada')
    for field, value in [('search','SYN-MZ'),('rag','AMBER'),('decision','HOLD'),
                         ('marker','RESISTANT'),('excluded','false'),('sort','N_TRIALS_USED')]:
        expect(page.locator('#'+field)).to_have_value(value)
    expect(page.locator('#descending')).to_be_checked()
    expect(page.locator('#include-missing')).to_be_checked()
    expect(page.locator('#ranges')).to_contain_text('1 to 9')
    expect(page.locator('#min')).to_have_value('')
    expect(page.locator('#reason')).to_have_value('')
    page.locator('#search').fill('does-not-match')
    expect(page.locator('#rows tr')).to_have_count(0)
    expect(page.locator('#selection-status')).to_contain_text('outside current filters')
    page.locator('#reset').click()
    expect(page.locator('#rows tr')).to_have_count(150)
    expect(page.locator('#detail')).to_be_hidden()
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    expect(page.locator('#detail')).to_be_hidden()
    page.locator('#rows tr').first.click()
    expect(page.locator('#actor')).to_have_value('Breeder Ada')
    page.locator('#preferences-panel').evaluate('(node) => node.open = true')
    page.locator('#remember-view').uncheck()
    stored = page.evaluate('JSON.parse(localStorage.getItem("uc4.preferences"))')
    assert stored['view'] is None and stored['defaults']['name'] == 'Breeder Ada'
    page.locator('#forget-preferences').click()
    assert page.evaluate('localStorage.getItem("uc4.preferences")') is None
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#actor')).to_have_value('')
    expect(page.locator('#decision-history')).to_contain_text('Recorded by Breeder Ada')


@pytest.mark.parametrize('damage', ['json', 'version', 'filter', 'range', 'snapshot', 'missing'])
def test_preferences_invalid_or_stale_storage(screen, damage):
    page, _ = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    save_preferences(page)
    page.locator('#remember-view').check()
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail')).to_be_visible()
    page.wait_for_function('JSON.parse(localStorage.getItem("uc4.preferences")).view.selected !== null')
    page.evaluate("""damage => {
      const key='uc4.preferences', value=JSON.parse(localStorage.getItem(key));
      if(damage==='version')value.version=999;
      if(damage==='filter')value.view.filters.rag='PURPLE';
      if(damage==='range')value.view.ranges={N_TRIALS_USED:{min:10,max:1}};
      if(damage==='snapshot')value.view.snapshot='different-dataset';
      if(damage==='missing')value.view.selected='not-a-real-candidate';
      localStorage.setItem(key,damage==='json'?'bad json':JSON.stringify(value));
    }""", damage)
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    expect(page.locator('#detail')).to_be_hidden()
    expect(page.locator('#preferences-status')).to_contain_text(
        'dataset changed' if damage=='snapshot' else 'no longer available' if damage=='missing' else 'could not be restored')
    page.locator('#rows tr').first.click()
    expect(page.locator('#actor')).to_have_value('Breeder Ada' if damage in ('snapshot','missing') else '')


def test_preferences_storage_failure_and_delayed_selection(screen):
    page, _ = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.evaluate("() => {Storage.prototype.setItem = () => {throw new DOMException('Blocked','SecurityError')}}")
    page.locator('#preferences-panel').evaluate('(node) => node.open = true')
    page.locator('#preference-name').fill('Not saved')
    page.locator('#preferences-form button').click()
    expect(page.locator('#preferences-status')).to_contain_text('could not be saved')
    page.locator('#remember-view').click()
    expect(page.locator('#remember-view')).not_to_be_checked()
    pending = []
    page.route('**/candidates/SYN-MZ-00001', lambda route: pending.append(route))
    page.locator('#rows tr').first.click()
    page.wait_for_timeout(100)
    assert pending
    page.locator('#reset').click()
    pending.pop().continue_()
    expect(page.locator('#rows tr')).to_have_count(150)
    expect(page.locator('#detail')).to_be_hidden()
    page.unroute('**/candidates/SYN-MZ-00001')
    page.locator('#rows tr').nth(1).click()
    expect(page.locator('#detail')).to_be_visible()
    expect(page.locator('#actor')).to_have_value('')



@pytest.mark.parametrize('control', ['reset', 'forget-preferences'])
def test_preferences_cancel_delayed_restore(screen, control):
    page, _ = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    save_preferences(page)
    page.locator('#remember-view').check()
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail')).to_be_visible()
    page.wait_for_function('JSON.parse(localStorage.getItem("uc4.preferences")).view.selected !== null')
    guid = page.evaluate('JSON.parse(localStorage.getItem("uc4.preferences")).view.selected')
    pending = []
    page.route('**/candidates/'+guid, lambda route: pending.append(route))
    page.reload()
    page.wait_for_timeout(200)
    assert pending
    page.locator('#preferences-panel').evaluate('(node) => node.open = true')
    page.locator('#'+control).click()
    with page.expect_response('**/candidates/'+guid):
        pending.pop().continue_()
    expect(page.locator('#rows tr')).to_have_count(150)
    expect(page.locator('#detail')).to_be_hidden()
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    expect(page.locator('#detail')).to_be_hidden()


def test_preferences_storage_denied_on_start_and_legacy_alias(screen):
    page, _ = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    page.evaluate('sessionStorage.setItem("uc4.alias", "Legacy Ada")')
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#actor')).to_have_value('Legacy Ada')
    assert page.evaluate('localStorage.getItem("uc4.preferences")') is None
    page.add_init_script("Storage.prototype.getItem = () => {throw new DOMException('Blocked','SecurityError')}")
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    expect(page.locator('#preferences-status')).to_contain_text('storage is unavailable')
    page.locator('#rows tr').first.click()
    expect(page.locator('#actor')).to_have_value('')


def test_preferences_forget_propagates_to_open_tabs(screen):
    page, _ = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    save_preferences(page)
    page.locator('#remember-view').check()
    other = page.context.new_page()
    other.goto(page.url)
    expect(other.locator('#rows tr')).to_have_count(150)
    page.locator('#forget-preferences').click()
    expect(other.locator('#preferences-status')).to_contain_text('forgotten in another tab')
    other.locator('#rag').select_option('RED')
    expect(other.locator('#rows tr')).to_have_count(65)
    assert other.evaluate('localStorage.getItem("uc4.preferences")') is None
    other.close()


def test_preferences_restores_current_evidence_revision(screen):
    page, _ = screen
    expect = playwright.expect
    expect(page.locator('#rows tr')).to_have_count(150)
    save_preferences(page)
    page.locator('#remember-view').check()
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail')).to_be_visible()
    page.wait_for_function('JSON.parse(localStorage.getItem("uc4.preferences")).view.selected !== null')
    original = page.request.get(page.url+'candidates/SYN-MZ-00001').json()
    draft = page.request.post(page.url+'enrichment', data={
        'query':original['material_guid'], 'kind':'metadata', 'field':'NOTE',
        'value':'Current revision test', 'actor':'Reviewer', 'reason':'Verify current evidence',
        'observed_at':'2026-10-01', 'source':'Browser test'}).json()
    for action in ('submit','approve'):
        response = page.request.post(page.url+'enrichment/'+draft['id']+'/review',
            data={'action':action,'actor':'Reviewer','reason':'Verify current evidence'})
        assert response.ok
    response = page.request.post(page.url+'enrichment/'+draft['id']+'/activate',
        data={'base_revision':original['revision_id'],'actor':'Reviewer','reason':'Verify current evidence'})
    assert response.ok
    page.reload()
    expect(page.locator('#detail')).to_be_visible()
    current = page.request.get(page.url+'candidates/SYN-MZ-00001').json()
    assert current['revision_id'] != original['revision_id']
    expect(page.locator('#decision-identity')).to_contain_text(current['revision_id'])
    expect(page.locator('#reason')).to_have_value('')
    expect(page.locator('#action')).to_have_value('')



def test_preferences_survive_browser_restart(screen):
    page, folder = screen
    expect = playwright.expect
    profile = folder / 'persistent-browser'
    browser_type = page.context.browser.browser_type
    with browser_type.launch_persistent_context(profile, channel=BROWSER_CHANNEL) as context:
        first = context.new_page()
        first.goto(page.url)
        expect(first.locator('#rows tr')).to_have_count(150)
        save_preferences(first, name='Returning breeder')
        first.locator('#remember-view').check()
        first.locator('#rows tr').first.click()
        expect(first.locator('#detail')).to_be_visible()
        first.locator('#rag').select_option('AMBER')
        expect(first.locator('#rows tr')).to_have_count(53)
    with browser_type.launch_persistent_context(profile, channel=BROWSER_CHANNEL) as context:
        returned = context.new_page()
        returned.goto(page.url)
        expect(returned.locator('#rows tr')).to_have_count(53)
        expect(returned.locator('#detail-title')).to_contain_text('SYN-MZ-00001')
        expect(returned.locator('#actor')).to_have_value('Returning breeder')
        expect(returned.locator('#reason')).to_have_value('')
        expect(returned.locator('#action')).to_have_value('')


def guided_review(page):
    expect = playwright.expect
    select_section(page, "enrichment")
    page.get_by_role('button', name='Submit for review', exact=True).first.click()
    select_section(page, "enrichment")
    page.locator('#enrichment-action-reason').fill('Ready for source review')
    page.get_by_role('button', name='Confirm submission', exact=True).click()
    expect(page.locator('#enrichment-history')).to_contain_text('SUBMITTED')
    page.get_by_role('button', name='Approve', exact=True).first.click()
    select_section(page, "enrichment")
    page.locator('#enrichment-action-reason').fill('Verified against the worksheet')
    page.get_by_role('button', name='Confirm approval', exact=True).click()
    expect(page.locator('#enrichment-history')).to_contain_text('APPROVED')


def test_guided_lab_correction_cancel_activate_and_supersede(screen):
    page, folder = screen
    expect = playwright.expect
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail')).to_be_visible()
    detail = page.request.get(page.url + 'candidates/SYN-MZ-00001').json()
    select_section(page, "enrichment")
    page.locator('#enrich-kind').select_option('correction')
    options = page.locator('#enrich-target option').evaluate_all('(xs)=>xs.map(x=>x.value)')
    target = next(x for x in options if json.loads(x)['table'] == 'lab')
    select_section(page, "enrichment")
    page.locator('#enrich-target').select_option(target)
    expect(page.locator('#enrich-definition')).to_contain_text('no trial relationship')
    expect(page.locator('#enrich-unit')).to_have_attribute('readonly', '')
    select_section(page, "enrichment")
    page.locator('#enrich-author').fill('Ada')
    select_section(page, "enrichment")
    page.locator('#enrich-value').fill('92.25')
    select_section(page, "enrichment")
    page.locator('#observed-at').fill('2026-10-01T09:30')
    select_section(page, "enrichment")
    page.locator('#enrich-source').fill('Hypothetical worksheet 7 for test')
    select_section(page, "enrichment")
    page.locator('#enrich-reason').fill('Hypothetical transcription correction')
    select_section(page, "enrichment")
    page.locator('#enrichment-form button[type=submit]').click()
    expect(page.locator('#enrichment-history')).to_contain_text('DRAFT')
    guided_review(page)
    select_section(page, "enrichment")
    page.get_by_role('button', name='Preview impact', exact=True).click()
    expect(page.locator('#enrichment-message')).to_contain_text('Earlier breeder decisions retain')
    expect(page.locator('#enrichment-message table').first).to_contain_text('92.25')
    assert page.request.get(page.url + 'health').json()['revision_id'] == detail['revision_id']
    select_section(page, "enrichment")
    page.locator('#enrichment-message').screenshot(path=str(folder / 'guided-preview-desktop.png'))
    page.get_by_role('button', name='Cancel activation').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#enrichment-message')).to_be_empty()
    assert page.request.get(page.url + 'health').json()['revision_id'] == detail['revision_id']
    select_section(page, "enrichment")
    page.get_by_role('button', name='Preview impact', exact=True).click()
    select_section(page, "enrichment")
    page.locator('#enrichment-action-reason').fill('Publish verified evidence')
    select_section(page, "decision")
    page.locator('#reason').fill('Preserve my unsaved breeder decision')
    page.locator('#sort').select_option('rag')
    page.evaluate('''() => {
        const original=window.fetch;
        window.fetch=async (url,options)=>{
            const response=await original(url,options);
            if(url.endsWith('/activate'))return new Promise(resolve=>{window.releaseActivation=()=>resolve(response);});
            return response;
        };
    }''')
    select_section(page, "enrichment")
    page.get_by_role('button', name='Activate reviewed change', exact=True).click()
    page.wait_for_function('typeof window.releaseActivation === "function"')
    page.evaluate('loadList()')
    expect(page.locator('#enrichment-message')).to_contain_text('Evidence changed')
    page.evaluate('window.releaseActivation()')
    expect(page.locator('#enrichment-history')).to_contain_text('ACTIVATED')
    expect(page.locator('#reason')).to_have_value('Preserve my unsaved breeder decision')
    expect(page.locator('#sort')).to_have_value('rag')
    expect(page.locator('#enrich-supersedes')).to_be_visible()
    expect(page.locator('#enrich-supersedes')).to_have_value('')
    select_section(page, "enrichment")
    page.locator('#enrich-value').fill('93.25')
    select_section(page, "enrichment")
    page.locator('#enrich-supersedes').select_option(index=1)
    select_section(page, "enrichment")
    page.locator('#enrichment-form button[type=submit]').click()
    expect(page.locator('#enrichment-history')).to_contain_text('DRAFT')
    guided_review(page)
    select_section(page, "enrichment")
    page.get_by_role('button', name='Preview impact', exact=True).click()
    expect(page.locator('#enrichment-message')).to_contain_text('92.25 → 93.25')
    page.set_viewport_size({'width':390,'height':844})
    select_section(page, "enrichment")
    page.locator('#enrichment-message').screenshot(path=str(folder / 'guided-preview-mobile.png'))
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.get_by_role('button', name='Cancel activation').click()
    select_section(page, "enrichment")
    page.locator('#enrichment-form').screenshot(path=str(folder / 'guided-form-mobile.png'))


def test_guided_controls_stale_and_late_preview(screen):
    page, _ = screen
    expect = playwright.expect
    page.locator('#rows tr').first.click()
    expect(page.locator('#detail')).to_be_visible()
    select_section(page, "enrichment")
    page.locator('#enrich-kind').select_option('correction')
    options = page.locator('#enrich-target option').evaluate_all('(xs)=>xs.map(x=>x.value)')
    for field, control in [('STATUS_LID','enrich-choice'),('ACTUAL_DATE','enrich-value'),('DELAY_DAYS','enrich-value'),('MARKER_DISEASE_RESISTANCE','enrich-choice')]:
        select_section(page, "enrichment")
        page.locator('#enrich-target').select_option(next(x for x in options if json.loads(x)['field']==field))
        expect(page.locator('#'+control)).to_be_visible()
        if field == 'ACTUAL_DATE':
            page.locator('#enrich-unknown').check()
            expect(page.locator('#enrich-value')).to_be_disabled()
        if field == 'DELAY_DAYS':
            expect(page.locator('#enrich-unit')).to_have_value('days')
            expect(page.locator('#enrich-value')).to_be_enabled()
    item = page.request.post(page.url+'enrichment', data=dict(query='SYN-MZ-00001',kind='metadata',field='NOTE',value='Hypothetical note',actor='Ada',reason='Record context',observed_at='2026-10-01',source='Notebook')).json()
    for action in ['submit','approve']:
        assert page.request.post(page.url+f'enrichment/{item["id"]}/review',data=dict(action=action,actor='Ada',reason='Checked context')).ok
    page.locator('#rows tr').filter(has_text='SYN-MZ-00001').click()
    select_section(page, "enrichment")
    page.get_by_role('button',name='Preview impact',exact=True).click()
    expect(page.locator('#enrichment-message')).to_contain_text('Measurements and system recommendations are unchanged')
    select_section(page, "enrichment")
    page.locator('#enrichment-action-actor').fill('Ada')
    select_section(page, "enrichment")
    page.locator('#enrichment-action-reason').fill('Publish verified context')
    page.route('**/enrichment/*/activate',lambda route: route.fulfill(status=409,json={'detail':'Evidence revision changed; review the new preview'}))
    select_section(page, "enrichment")
    page.get_by_role('button',name='Activate reviewed change',exact=True).click()
    expect(page.locator('#enrichment-message')).to_contain_text('Evidence revision changed')
    expect(page.get_by_role('button',name='Activate reviewed change',exact=True)).to_be_disabled()
    page.get_by_role('button',name='Cancel activation').click()
    page.evaluate('''() => { const original=window.fetch; window.fetch=(url,options)=>url.endsWith('/preview') ? new Promise(resolve=>{window.finishPreview=()=>original(url,options).then(resolve);}) : original(url,options); }''')
    select_section(page, "enrichment")
    page.get_by_role('button',name='Preview impact',exact=True).click()
    expect(page.locator('#enrichment-message')).to_contain_text('Computing impact')
    page.locator('#rows tr').filter(has_text='SYN-MZ-00002').click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00002')
    page.evaluate('window.finishPreview()')
    expect(page.locator('#enrichment-message')).to_be_empty()
    expect(page.get_by_role('button',name='Activate reviewed change',exact=True)).to_have_count(0)

def prepare_manual_decision(page):
    playwright.expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    select_section(page, "decision")
    page.locator('#actor').fill('Manual Ada')
    select_section(page, "decision")
    page.locator('#action').select_option('ADVANCE')
    select_section(page, "decision")
    page.locator('#reason').fill('Advance after reviewing all available trials')


def test_manual_inline_review_edit_and_traceable_receipt(screen):
    page, folder = screen
    expect = playwright.expect
    prepare_manual_decision(page)
    select_section(page, "decision")
    page.locator('#decision-context summary').click()
    select_section(page, "decision")
    page.locator('#trial-context').fill('Reviewer supplied trial context')
    select_section(page, "decision")
    page.locator('#review-decision').click()
    expect(page.locator('#decision-review-title')).to_be_focused()
    expect(page.locator('#decision-review-summary')).to_contain_text('Manual Ada (self-declared, unverified)')
    assert page.request.get(page.url+'decisions').json() == []
    select_section(page, "decision")
    page.locator('#edit-decision').click()
    expect(page.locator('#reason')).to_be_focused()
    expect(page.locator('#reason')).to_have_value('Advance after reviewing all available trials')
    select_section(page, "decision")
    page.locator('#review-decision').click()
    page.set_viewport_size({'width':390, 'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    select_section(page, "decision")
    page.locator('#decision-review').screenshot(path=str(folder/'manual-review-mobile.png'))
    select_section(page, "decision")
    page.locator('#record-decision').evaluate('(button) => { button.click(); button.click(); }')
    expect(page.locator('#decision-message')).to_contain_text('Decision recorded:')
    events = page.request.get(page.url+'decisions').json()
    assert len(events) == 1
    event = events[0]
    expect(page.locator('#decision-history')).to_contain_text(event['id'])
    expect(page.locator('#decision-history')).to_contain_text('Reviewer supplied trial context')
    select_section(page, "history")
    page.get_by_role('button', name='View original recommendation and evidence', exact=True).click()
    expect(page.locator('#evidence-dialog-body')).to_contain_text(event['recommendation']['recommendation_id'])
    page.get_by_role('button', name='Browse original evidence', exact=True).click()
    expect(page.locator('#evidence-dialog-body')).not_to_contain_text('Loading original evidence')
    expect(page.locator('#evidence-dialog-body')).not_to_contain_text('Original evidence unavailable')
    page.locator('#evidence-close').click()
    page.reload()
    expect(page.locator('#rows tr')).to_have_count(150)
    page.locator('#rows tr').first.click()
    expect(page.locator('#decision-history')).to_contain_text(event['id'])
    expect(page.locator('#reason')).to_have_value('')


def test_manual_review_invalid_inputs_switch_and_concurrent_decision(screen):
    page, _ = screen
    expect = playwright.expect
    prepare_manual_decision(page)
    select_section(page, "decision")
    page.locator('#actor').fill('   ')
    select_section(page, "decision")
    page.locator('#review-decision').click()
    expect(page.locator('#decision-review')).to_be_hidden()
    select_section(page, "decision")
    page.locator('#actor').fill('Manual Ada')
    select_section(page, "decision")
    page.locator('#reason').fill('     ')
    select_section(page, "decision")
    page.locator('#review-decision').click()
    expect(page.locator('#decision-review')).to_be_hidden()
    select_section(page, "decision")
    page.locator('#reason').fill('Wait for further trials')
    select_section(page, "decision")
    page.locator('#review-decision').click()
    # Another reviewer records after this browser captured the latest-decision identity.
    body = page.evaluate('JSON.parse(state.decisionReview.signature)')
    response = page.request.post(page.url+'decisions', data={**body, 'actor':'Other breeder', 'request_id':'concurrent-review'})
    assert response.ok
    select_section(page, "decision")
    page.locator('#record-decision').click()
    expect(page.locator('#decision-message')).to_contain_text('Review the refreshed candidate')
    expect(page.locator('#decision-review')).to_be_hidden()
    assert len(page.request.get(page.url+'decisions').json()) == 1
    expect(page.locator('#reason')).to_have_value('Wait for further trials')
    expect(page.locator('#decision-entry')).to_be_hidden()
    page.locator('#another-decision').click()
    page.locator('#actor').fill('Manual Ada')
    page.locator('#action').select_option('HOLD')
    page.locator('#reason').fill('Wait for further trials')
    page.locator('#review-decision').click()
    page.locator('#rows tr').nth(1).click()
    expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00002')
    expect(page.locator('#actor')).to_have_value('')
    expect(page.locator('#decision-review')).to_be_hidden()
    expect(page.locator('#reason')).to_have_value('')
    assert len(page.request.get(page.url+'decisions').json()) == 1


def test_manual_saved_receipt_survives_history_refresh_failure(screen):
    page, _ = screen
    expect = playwright.expect
    prepare_manual_decision(page)
    select_section(page, "decision")
    page.locator('#review-decision').click()
    page.route('**/candidates/*', lambda route: route.abort())
    select_section(page, "decision")
    page.locator('#record-decision').click()
    expect(page.locator('#decision-message')).to_contain_text('Decision recorded:')
    expect(page.locator('#decision-message')).to_contain_text('History refresh failed')
    assert len(page.request.get(page.url+'decisions').json()) == 1

def test_manual_stale_revision_requires_fresh_review(screen):
    page, _ = screen
    expect = playwright.expect
    prepare_manual_decision(page)
    select_section(page, "decision")
    page.locator('#review-decision').click()
    original = page.request.get(page.url+'candidates/SYN-MZ-00001').json()
    draft = page.request.post(page.url+'enrichment', data={
        'query':original['material_guid'], 'kind':'metadata', 'field':'NOTE',
        'value':'New evidence context', 'actor':'Reviewer', 'reason':'Record new context',
        'observed_at':'2026-10-01', 'source':'Test notebook'}).json()
    for action in ('submit','approve'):
        assert page.request.post(page.url+'enrichment/'+draft['id']+'/review',
            data={'action':action,'actor':'Reviewer','reason':'Verified context'}).ok
    assert page.request.post(page.url+'enrichment/'+draft['id']+'/activate',
        data={'base_revision':original['revision_id'],'actor':'Reviewer','reason':'Activate context'}).ok
    select_section(page, "decision")
    page.locator('#record-decision').click()
    expect(page.locator('#decision-message')).to_contain_text('Review the refreshed candidate')
    assert page.request.get(page.url+'decisions').json() == []
    expect(page.locator('#decision-review')).to_be_hidden()
    select_section(page, "decision")
    page.locator('#review-decision').click()
    select_section(page, "decision")
    page.locator('#record-decision').click()
    expect(page.locator('#decision-message')).to_contain_text('Decision recorded:')
    event = page.request.get(page.url+'decisions').json()[0]
    assert event['recommendation']['revision_id'] != original['revision_id']


@pytest.mark.parametrize("mobile", [False, True])
def test_saved_decision_gate_tabs_and_intentional_second_event(screen, mobile):
    page, folder = screen
    expect = playwright.expect
    page.context.tracing.start(screenshots=True, snapshots=True, sources=True)
    requests = []
    page.on('request', lambda r: requests.append(r.post_data_json) if r.url.endswith('/decisions') and r.method == 'POST' else None)
    if mobile:
        page.set_viewport_size({'width':390, 'height':844})
    prepare_manual_decision(page)
    page.locator('#tab-decision').focus()
    page.keyboard.press('ArrowLeft')
    expect(page.locator('#tab-evidence')).to_be_focused()
    expect(page.locator('#panel-evidence')).to_be_visible()
    expect(page.locator('#panel-decision')).to_be_hidden()
    page.keyboard.press('ArrowRight')
    expect(page.locator('#reason')).to_have_value('Advance after reviewing all available trials')
    page.locator('#review-decision').click()
    select_section(page, 'history')
    expect(page.locator('#decision-history')).to_contain_text('No breeder decisions yet')
    select_section(page, 'decision')
    expect(page.locator('#decision-review')).to_be_visible()
    page.locator('#record-decision').evaluate('(button)=>{button.click();button.click();}')
    expect(page.locator('#decision-saved')).to_be_visible()
    expect(page.locator('#decision-entry')).to_be_hidden()
    expect(page.locator('#decision-saved-summary strong')).to_have_text('Recorded by Manual Ada')
    first = page.request.get(page.url+'decisions').json()[0]
    page.locator('#view-decision-history').click()
    expect(page.locator('#panel-history')).to_be_visible()
    expect(page.locator('#decision-history strong')).to_have_text('Recorded by Manual Ada')
    page.locator('#decision-history details summary').click()
    expect(page.locator('#decision-history')).to_contain_text(first['id'])
    page.screenshot(path=str(folder/'saved-history.png'))
    page.reload()
    page.locator('#rows tr').first.click()
    select_section(page, 'decision')
    expect(page.locator('#decision-entry')).to_be_hidden()
    expect(page.locator('#decision-saved-summary')).to_contain_text(first['id'])
    page.locator('#rows tr').nth(1).click()
    select_section(page, 'decision')
    expect(page.locator('#decision-entry')).to_be_visible()
    expect(page.locator('#reason')).to_have_value('')
    page.locator('#rows tr').first.click()
    select_section(page, 'decision')
    expect(page.locator('#decision-entry')).to_be_hidden()
    assert len(page.request.get(page.url+'decisions').json()) == 1
    assert len(requests) == 1
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    expect(page.locator('#another-decision')).to_be_in_viewport()
    expect(page.locator('#candidate-navigation')).to_be_in_viewport()
    page.screenshot(path=str(folder/'saved-decision.png'))
    page.locator('#another-decision').click()
    expect(page.locator('#reason')).to_have_value('')
    page.locator('#actor').fill('Manual Ada')
    page.locator('#action').select_option('ADVANCE')
    page.locator('#reason').fill(first['reason'])
    page.locator('#review-decision').click()
    expect(page.locator('#decision-previous')).to_contain_text('Recording adds another history event')
    page.locator('#record-decision').click()
    expect(page.locator('#decision-saved')).to_be_visible()
    events = page.request.get(page.url+'decisions').json()
    assert len(events) == 2
    assert events[1]['previous_decision_id'] == first['id']
    assert events[1]['request_id'] != first['request_id']
    (folder/'decision-requests.json').write_text(json.dumps(requests, indent=2))
    page.context.tracing.stop(path=folder/'save-navigation-trace.zip')


@pytest.mark.parametrize('destination', ['history', 'other-candidate', 'pending-candidate'])
def test_save_response_during_navigation_keeps_candidate_and_receipt(screen, destination):
    page, _ = screen
    expect = playwright.expect
    prepare_manual_decision(page)
    held = []
    page.route('**/decisions', lambda route: held.append(route) if route.request.method == 'POST' else route.continue_())
    page.locator('#review-decision').click()
    page.locator('#record-decision').click()
    expect(page.locator('#record-decision')).to_be_disabled()
    pending = []
    if destination == 'history':
        select_section(page, 'history')
    else:
        if destination == 'pending-candidate':
            page.route('**/candidates/SYN-MZ-00002', lambda route: pending.append(route))
        page.locator('#rows tr').nth(1).click()
        if destination == 'other-candidate':
            expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00002')
    assert held
    result = held[0].fetch()
    held[0].fulfill(response=result)
    if pending:
        pending[0].fulfill(response=pending[0].fetch())
    if destination == 'history':
        expect(page.locator('#tab-history')).to_have_attribute('aria-selected', 'true')
        select_section(page, 'decision')
        expect(page.locator('#decision-saved')).to_be_visible()
    else:
        expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00002')
        select_section(page, 'decision')
        expect(page.locator('#decision-saved')).to_be_hidden()
        expect(page.locator('#decision-message')).to_be_empty()
        page.locator('#rows tr').first.click()
        select_section(page, 'decision')
        expect(page.locator('#decision-saved')).to_be_visible()
    assert len(page.request.get(page.url+'decisions').json()) == 1


@pytest.mark.parametrize('status,multiline', [('answered',True), ('answered',False), ('unverified',True)])
def test_answer_summary_details_and_warnings(screen, status, multiline):
    page, _ = screen
    expect = playwright.expect
    text = 'Direct answer [tool:score_candidate]'
    if multiline:
        text += '\n\nSupporting explanation [tool:score_candidate]'
    page.route('**/ask', lambda route: route.fulfill(json={
        'status':status, 'text':text, 'disclaimer':'Provisional; breeder decides.',
        'context':{'candidate':'SYN-MZ-00001','revision_id':'original'},
        'citations':[{'ref':'tool:score_candidate','found':status=='answered'}],
        'tool_calls':[{'name':'score_candidate','result':{'rag':'AMBER'}}]}))
    page.locator('#question').fill('Why AMBER?')
    page.locator('#ask-form button[type=submit]').click()
    page.locator('#answer button').click()
    expect(page.locator('#evidence-dialog-body')).to_contain_text('Direct answer')
    expect(page.locator('.answer-sources')).to_be_visible()
    if multiline:
        expect(page.locator('.answer-details')).not_to_have_attribute('open', '')
        expect(page.locator('.answer-details .answer-paragraph')).to_be_hidden()
        page.locator('.answer-details summary').click()
        expect(page.locator('.answer-details .answer-paragraph')).to_be_visible()
        expect(page.locator('.answer-details .answer-paragraph')).to_contain_text('Supporting explanation')
    else:
        expect(page.locator('.answer-details')).to_have_count(0)
    if status == 'unverified':
        expect(page.locator('#evidence-dialog-body .warn')).to_be_visible()
    page.locator('.answer-sources button').click()
    expect(page.locator('#evidence-dialog-body')).to_contain_text('original')
    expect(page.locator('#evidence-dialog-body')).to_contain_text('AMBER' if status=='answered' else 'could not be verified')


def test_saved_state_uses_history_order_not_receipt_timestamp(screen):
    page, _ = screen
    expect = playwright.expect
    prepare_manual_decision(page)
    page.locator('#review-decision').click()
    page.locator('#record-decision').click()
    expect(page.locator('#decision-saved')).to_be_visible()
    first = page.request.get(page.url+'decisions').json()[0]
    response = page.request.post(page.url+'decisions', data={
        'query':first['material_guid'], 'action':'HOLD', 'actor':'Other breeder',
        'reason':'Wait for additional evidence', 'context':first['context'],
        'recommendation_id':first['recommendation']['recommendation_id'],
        'previous_decision_id':first['id'], 'request_id':'later-deliberate-event'})
    assert response.ok
    latest = response.json()
    def same_second(route):
        response = route.fetch()
        detail = response.json()
        for event in detail['decisions']:
            event['timestamp'] = first['timestamp']
        route.fulfill(response=response, json=detail)
    page.route('**/candidates/SYN-MZ-00001', same_second)
    page.locator('#rows tr').first.click()
    select_section(page, 'decision')
    expect(page.locator('#decision-saved-summary')).to_contain_text(latest['id'])
    expect(page.locator('#decision-saved-summary strong')).to_have_text('Recorded by Other breeder')
    expect(page.locator('#another-decision')).to_be_enabled()
