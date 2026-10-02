"""Run a real-browser synthetic AMBER review; --timed rehearses the seven-minute slot.

Uses fresh isolated DB/log/snapshot storage under app/data/verification/ on every run. The configured
model gateway is used for Ask. No team decision store or source archive is edited.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright, expect

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app/src"))
from uc4_mcp.demo_runtime import candidate_demo_server, no_model
from uc4_mcp.config import load_env_file
from uc4_mcp.cli import make_model

parser = argparse.ArgumentParser()
parser.add_argument('--timed', action='store_true')
parser.add_argument('--offline', action='store_true', help='Exercise the honest model-unavailable path without a model request.')
parser.add_argument('--browser', choices=('chromium','chrome'), default='chromium')
args = parser.parse_args()
run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
mode = 'rehearsal' if args.timed else 'review'
out = REPO / 'app/data/verification' / (mode + '-' + run_id)
out.mkdir(parents=True)
scratch = out / 'storage'
report = dict(mode=mode, automated=True, human_participant=False, started_utc=run_id,
              history_database=str(scratch/'history.sqlite3'), browser=args.browser, live_model_requested=not args.offline, actions=[], stages=[], findings=[])
if not args.offline:
    load_env_file()
model_factory = no_model if args.offline else make_model
start=None

def save():
    (out/'run.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

def action(label, fn):
    before=time.monotonic()
    result=fn()
    report['actions'].append(dict(label=label,elapsed_seconds=round(time.monotonic()-start,2),duration_seconds=round(time.monotonic()-before,2)))
    save()
    return result

def stage(offset, label):
    if args.timed:
        while time.monotonic()-start < offset:
            remaining=offset-(time.monotonic()-start)
            print(json.dumps({'waiting_for':label,'seconds_remaining':round(remaining)}),flush=True)
            time.sleep(min(20,remaining))
    actual=time.monotonic()-start
    report['stages'].append(dict(label=label,planned_seconds=offset,actual_seconds=round(actual,2),late_seconds=round(max(0,actual-offset),2) if args.timed else None))
    print(json.dumps({'stage':label,'elapsed_seconds':round(actual,2)}),flush=True)
    save()

try:
    with candidate_demo_server(scratch, model_factory, REPO/'get_started/candidate_recommendations_synthetic.zip') as runtime:
        url = runtime.url
        report['startup_seconds'] = runtime.startup_seconds
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel=None if args.browser=='chromium' else 'chrome', timeout=60000)
            page=browser.new_page(viewport={'width':1440,'height':1100})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_function("document.querySelector('#count').textContent.startsWith('Candidates:')", timeout=60000)
            expect(page.locator('#rows tr')).to_have_count(150)
            start=time.monotonic()
            stage(0,'Problem and synthetic-data scope')
            report['health']=page.request.get(url+'health', max_retries=2).json()
            assert len(page.request.get(url+'decisions', max_retries=2).json())==0
            report['narration']='Scattered field and lab evidence must be reviewed without confusing system recommendations with breeder decisions. This is a provisional synthetic maize-like demonstration.'
            page.screenshot(path=str(out/'01-start.png'))

            stage(45,'Shortlist, assessment and original source')
            action('Filter system RAG to AMBER',lambda:page.locator('#rag').select_option('AMBER'))
            expect(page.locator('#rows tr')).to_have_count(53)
            action('Search SYN-MZ-00001',lambda:page.locator('#search').fill('SYN-MZ-00001'))
            expect(page.locator('#rows tr')).to_have_count(1)
            expect(page.locator('#rows tr')).to_contain_text('SYN-MZ-00001')
            action('Open candidate',lambda:page.locator('#rows tr').click())
            expect(page.locator('#detail-title')).to_contain_text('SYN-MZ-00001')
            detail=page.request.get(url+'candidates/SYN-MZ-00001', max_retries=2).json()
            assert detail['rag']=='AMBER' and detail['metrics']['N_TRIALS_USED']==1
            action('Expand all criteria',lambda:page.locator('#all-criteria > summary').click())
            moisture_index=next(i for i,c in enumerate(detail['assessments']) if c['field']=='MOISTURE_PCT_MEAN')
            row=page.locator('#criteria > tr').nth(moisture_index)
            action('Inspect moisture source and full precision',lambda:row.get_by_role('button',name='View evidence',exact=True).click())
            expect(page.locator('#evidence-dialog')).to_be_visible()
            source={'observed':detail['metrics']['MOISTURE_PCT_MEAN'],'threshold':detail['assessments'][moisture_index]['threshold']}
            expect(page.locator('#evidence-dialog-body')).to_contain_text(str(source['observed']))
            moisture_rows=[r for r in detail['evidence']['observation'] if r['TRAIT_CODE']=='MOISTURE_PCT']
            assert moisture_rows and all(r['source_file'] and r['row_id'] for r in moisture_rows)
            assert all(t=='Moisture' for t in page.locator('.source-table tbody tr td:nth-child(3)').all_text_contents())
            report['source_review']={'candidate':detail['material_id'],'guid':detail['material_guid'],
                'revision':detail['revision_id'],'policy':detail['rule_version'],
                'observed_moisture':source['observed'],'green_threshold':source['threshold'],
                'usable_trials':1,'source_rows':moisture_rows}

            page.screenshot(path=str(out/'02-source.png'))
            action('Close source dialog',lambda:page.locator('#evidence-close').click())

            stage(135,'Live grounded question and citation')
            action('Type why AMBER question',lambda:page.locator('#question').fill('Why is this candidate AMBER? Cite the evidence.'))
            with page.expect_response(lambda r:r.url.endswith('/ask') and r.request.method=='POST',timeout=180000) as response:
                action('Submit Ask',lambda:page.locator('#ask-form button[type=submit]').click())
            answer=response.value.json()
            report['ask']={k:answer[k] for k in ('status','text','citations','context','problems') if k in answer}
            report['ask_completed_seconds']=round(time.monotonic()-start,2)
            if answer.get('status')=='answered' and any(c['found'] for c in answer.get('citations',[])):
                expect(page.locator('#answer')).to_have_attribute('data-answer-state', 'answered')
                expect(page.locator('#answer .answer-status')).to_contain_text('Answered')
                action('Open answer dialog',lambda:page.locator('#answer button').click())
                action('Open answer citation',lambda:page.locator('.answer-sources button').first.click())
                expect(page.locator('#evidence-dialog-body')).to_contain_text('SYN-MZ-00001')
                assert page.locator('#evidence-dialog pre').count()==0
                page.screenshot(path=str(out/'03-ask-citation.png'))
                action('Close evidence dialog',lambda:page.locator('#evidence-close').click())
            else:
                report['findings'].append('Live Ask unavailable/unverified: continue with manual source evidence; do not claim a successful live model.')
                page.screenshot(path=str(out/'03-ask-unavailable.png'))
            save()

            stage(195,'Record HOLD and reopen decision history')
            action('Open Decision tab',lambda:page.locator('#tab-decision').click())
            action('Enter self-declared reviewer name',lambda:page.locator('#actor').fill('Demo reviewer - automated rehearsal'))
            action('Select HOLD',lambda:page.locator('#action').select_option('HOLD'))
            action('Enter decision rationale',lambda:page.locator('#reason').fill('Hold pending another usable trial and review of moisture above the provisional GREEN target.'))
            report['review_context']={'location':page.locator('#location').input_value(),'source_channel':page.locator('#source-channel').input_value()}
            action('Review proposed HOLD',lambda:page.locator('#review-decision').click())
            expect(page.locator('#decision-review-title')).to_be_focused()
            expect(page.locator('#decision-review-summary')).to_contain_text(detail['material_id'])
            expect(page.locator('#decision-review-summary')).to_contain_text(detail['recommendation_id'])
            assert page.request.get(url+'decisions', max_retries=2).json()==[], 'Review must not record a decision'
            page.locator('#decision-review').screenshot(path=str(out/'04-decision-review.png'))
            action('Record confirmed HOLD',lambda:page.locator('#record-decision').click())
            expect(page.locator('#decision-message')).to_contain_text('Decision recorded:')
            decisions=page.request.get(url+'decisions', max_retries=2).json()
            assert len(decisions)==1 and decisions[0]['action']=='HOLD'
            event=decisions[0]
            assert event['recommendation']['recommendation_id']==detail['recommendation_id']
            assert not event['overrides']
            report['decision']=event
            action('View saved decision history',lambda:page.locator('#view-decision-history').click())
            page.locator('#decision-history').evaluate("el=>el.scrollIntoView({block:'start'})")
            page.screenshot(path=str(out/'04-hold-history.png'))
            action('Reload to check persistence',lambda:page.reload(wait_until='domcontentloaded', timeout=60000))
            expect(page.locator('#rows tr')).to_have_count(150)
            action('Reopen candidate after reload',lambda:page.locator('#rows tr').filter(has_text='SYN-MZ-00001').click())
            action('Open History tab',lambda:page.locator('#tab-history').click())
            expect(page.locator('#decision-history')).to_contain_text('Recorded by Demo reviewer')
            assert page.request.get(url+'candidates/SYN-MZ-00001', max_retries=2).json()['recommendation_id']==detail['recommendation_id']
            expect(page.locator('#decision-history')).to_contain_text(event['id'])
            action('Open saved recommendation',lambda:page.get_by_role('button',name='View original recommendation and evidence',exact=True).click())
            expect(page.locator('#evidence-dialog-body')).to_contain_text(detail['recommendation_id'])
            with page.expect_response(lambda r:'/revisions/' in r.url and '/candidates/' in r.url) as original_response:
                action('Reopen original evidence',lambda:page.get_by_role('button',name='Browse original evidence',exact=True).click())
            original = original_response.value.json()
            assert original_response.value.ok and original['revision_id']==detail['revision_id']
            page.screenshot(path=str(out/'05-original-evidence.png'))
            action('Return to history',lambda:page.locator('#evidence-close').click())

            stage(285,'Baseline evidence and workflow observations')
            report['findings'] += [
                'Assessment explains the two unmet gates correctly: moisture 23.77% and one usable trial. Supplied rationale still says 23.8; both are source/display rounding of the same measurement.',
                'Source inspection opens a trait-filtered table in a dialog. Full-precision observations and original row references remain inspectable without JSON.',
                'Margins describe distance above a maximum or below a minimum; original precision remains visible in the evidence dialog.',
                'The decision requires three entries (name, action, reason), an explicit Review decision and a separate Record decision; review alone creates no event.',
                'HOLD matches system AMBER: history correctly reports override no. Do not describe this demo as an override.',
                'Reload resets shortlist filters and candidate selection, requiring one reopen step to inspect the saved history.',
                'The full Ask answer and citations open in a dialog; the sticky question bar retains a compact View answer control.',
                'This is automated operator evidence, not a breeder comprehension or time-saving measurement.'
            ]
            stage(345,'Limitations and pilot next step')
            report['human_followup']=['Breeder interpretation of signed margins and source details','Disease/cold-test terminology review','Real-device software-keyboard check','Whole-team speaking rehearsal']
            stage(390,'Buffer and handover')
            assert not errors,errors
            assert len(page.request.get(url+'decisions', max_retries=2).json())==1
            stage(420,'End of seven-minute slot' if args.timed else 'Review complete')
            report['duration_seconds']=round(time.monotonic()-start,2)
            report['interaction_count']=len(report['actions'])
            report['slot_overrun_seconds']=round(max(0, report['duration_seconds']-420),2) if args.timed else None
            report['result']='passed' if answer.get('status')=='answered' and any(c.get('found') for c in answer.get('citations',[])) else 'manual_pass_live_ask_not_verified'
            report['browser_errors']=errors
            save()
            page.context.close()
            browser.close()
except Exception as exc:
    report['result']='failed'
    report['failure']=str(exc)
    save()
    raise
print(json.dumps({'result':report['result'],'report':str(out/'run.json'),'duration_seconds':report.get('duration_seconds')}),flush=True)
