"""Start an isolated, operator-controlled session for the self-guided breeder pack."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import uuid
import webbrowser

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app/src"))
from uc4_mcp.demo_runtime import candidate_demo_server, no_model
from uc4_mcp.cli import make_model
from uc4_mcp.config import load_env_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--participant', required=True, help='Review alias, for example P01')
    parser.add_argument('--condition', required=True, choices=('no-defaults', 'saved-defaults'))
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--open-browser', action='store_true', help='Open the review once the app is ready.')
    args = parser.parse_args()
    if not args.offline:
        load_env_file()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    out = REPO / 'app/data/reviews' / run_id
    out.mkdir(parents=True)
    scratch = out / 'storage'
    report = dict(participant_alias=args.participant, condition=args.condition,
                  started_utc=run_id, human_measurements='pending worksheet',
                  history_database=str(scratch / 'history.sqlite3'), status='starting')
    report_path = out / 'session.json'

    def save():
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')

    save()
    try:
        with candidate_demo_server(scratch, no_model if args.offline else make_model,
                                   REPO / 'get_started/candidate_recommendations_synthetic.zip') as runtime:
            report.update(url=runtime.url, startup_seconds=runtime.startup_seconds, status='ready')
            save()
            print(f'Open {runtime.url}\nCondition: {args.condition}\nEvidence: {report_path}', flush=True)
            print('Follow app/HUMAN_REVIEW.md for the short review. Your session report is saved locally.', flush=True)
            if args.open_browser:
                try:
                    webbrowser.open(runtime.url)
                except webbrowser.Error:
                    print('The browser could not open automatically. Open the URL printed above.', flush=True)
            started = time.monotonic()
            try:
                input('Press Enter to stop after the review, or Ctrl+C to cancel: ')
                report['status'] = 'closed'
            except (KeyboardInterrupt, EOFError):
                report['status'] = 'cancelled'
            finally:
                report['session_open_seconds'] = round(time.monotonic() - started, 2)
                report['session_duration_is_not_task_timing'] = True
                report['events'] = [dict(event_id=d['id'], action=d['action'], timestamp=d['timestamp'],
                                        candidate=d['material_id'], recommendation_id=d['recommendation']['recommendation_id'])
                                    for d in runtime.history.decisions()]
                save()
    except Exception as exc:
        report.update(status='failed', failure=str(exc))
        save()
        raise


if __name__ == '__main__':
    main()
