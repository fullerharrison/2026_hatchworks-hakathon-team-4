# UC4 operating and development process

This guide covers breeder review and local developer handoff. Start with the [app README](README.md); [architecture](ARCHITECTURE.md) explains storage and components, and [API reference](API.md) defines integrations. Instructions assume commands run from the repository or extracted package root.

## Breeder review and evidence changes

1. Check the candidate identity, evidence revision and provisional system recommendation. Inspect criteria and source rows in **Evidence** before deciding. Supplied RAG, calculated RAG and your breeder action are distinct.
2. Open **Decision**, enter name, choice and reason, and check location/meeting and source channel. Use Unknown when location is unavailable. **Review decision** shows the proposed event; **Record decision** saves it. **Edit** returns without writing.
3. Check the saved receipt, **Recorded by**, and **History**. Open the original recommendation/evidence to verify the saved context. Reloading or reopening keeps the saved state. Use **Record another decision** only when deliberately adding a later event.
4. If the save response is lost, retry the same confirmation. If another decision or evidence revision has changed, refresh and review again. Unsaved choices/reasons are not restored after reload.

For an addition, open **Enrichment** and choose **Add context or a note** or **Correct existing evidence**. Select an existing candidate-linked source. Shared check rows and operations are identified; lab evidence stays material-level. Inspect the current value, fixed units and original source details. Operation dates have an explicit Unknown option.

Provide author, observation time, evidence source and rationale. Save the draft, submit it, then approve or reject it with a separate review reason. An approved draft can be previewed: inspect the original/current/proposed source value, changed measurements and recommendations for all affected candidates, source caveats and base revision. Activate only after this review, with a separate name and activation reason. Cancellation leaves active evidence unchanged and retains the saved draft. A stale preview must be refreshed.

Replacing an active correction requires explicitly choosing the earlier addition for that source row/field. Notes accumulate. Activation creates another revision; historical decisions retain their original evidence. A source inconsistency is a visible caveat rather than a new scoring rule. Unsupported traits can be documented in notes; new scoring traits require code and policy changes.

Preferences are optional browser conveniences. Save identity/context explicitly and separately opt into remembering the view. Forget preferences when leaving a shared browser. Recorded decisions and evidence revisions remain in server storage. Names are unverified, and the same author may review an addition in this demo.

## Developer verification

Use the supplied candidate archive and **fresh isolated storage** for checks. Never rehearse against the team's active database. For a manually launched test instance, set both paths in a separate PowerShell terminal before launching:

```powershell
$env:UC4_CANDIDATE_DB = '.test-tmp-manual-review/history.sqlite3'
$env:UC4_DECISION_LOG = '.test-tmp-manual-review/legacy.jsonl'
uv run --locked --project app uc4-ask serve --port 8876 --open-browser
```

Choose a fresh folder for each review. These environment settings affect that terminal only. Shell settings override root `.env`. Do not set `UC4_ZIP` to a historical archive for candidate verification.

The full repository regression suite requires both the candidate source and original v2 archive. Browser/live tests are excluded by default:

```powershell
uv lock --check --project app
uv run --locked --project app pytest -q app/tests -p no:cacheprovider --basetemp .test-tmp-check-offline
```

For the extracted handoff, which includes only the candidate source, run this candidate-focused offline subset:

```powershell
uv run --locked --project app pytest -q app/tests/test_candidate_migration.py app/tests/test_candidate_usability.py app/tests/test_demo_runtime.py app/tests/test_enrichment_guidance.py app/tests/test_filter_intent.py -p no:cacheprovider --basetemp .test-tmp-check-candidate
```

Install matching browser assets, then run the full candidate browser suite:

```powershell
uv run --locked --project app --group browser python -m playwright install chromium
uv run --locked --project app --group browser pytest -q -m browser app/tests/test_candidate_browser.py -p no:cacheprovider --basetemp .test-tmp-check-browser
```

Each browser test starts its own isolated history/server and fresh browser context. Default is Playwright Chromium; set `UC4_BROWSER_CHANNEL=chrome` for installed Chrome. Use a fresh writable `--basetemp` for each run; `-p no:cacheprovider` avoids shared cache permissions.

After configuring a private `.env`, verify AI access explicitly:

```powershell
uv run --locked --project app uc4-ask ping
uv run --locked --project app pytest -q -s -m live app/tests/test_filter_intent_live.py -p no:cacheprovider --basetemp .test-tmp-check-live
```

In the full repository, also run the isolated walkthroughs:

```powershell
uv run --locked --project app --group browser python scripts/rehearse.py --offline
uv run --locked --project app --group browser python scripts/rehearse.py
```

They write timestamped reports and isolated history/snapshots under ignored `app/data/verification/`. `--timed` adds seven-minute interaction checkpoints; it does not simulate spoken narration or human comprehension. Use [the breeder guide](HUMAN_REVIEW.md) for the short human review. Review sessions store reports and separate history under ignored `app/data/reviews/`. Live calls spend model tokens; skips, configuration-only health and model-unavailable walkthroughs do not establish live AI success.

## Handoff completion and packaging

Confirm baseline totals (150; 32 GREEN, 53 AMBER, 65 RED), source arithmetic and full-precision scoring. Verify list/filter/CSV, evidence, keyboard/mobile tabs, preferences, review/record/receipt/history, deliberate second decisions, retry/conflict handling, and enrichment preview/activation. Require grounded live Ask citations and the live filter evaluation to pass for an AI-ready handoff.

Update README, architecture, process and API docs when behavior changes. Record actual commands, results, source identity, limitations and artifact locations in release notes and local verification reports. Keep dated historical evidence intact. Human comprehension, deliberate-second-decision retesting and a spoken team rehearsal remain human checks; automated duration is not a breeder task time. Provisional crop policy still requires biological review.

Build a local distribution using the [package builder](../scripts/package_app.py):

```powershell
python scripts/package_app.py
uv run --locked --project app --group browser python scripts/verify_package.py
```

The explicit allowlist includes runtime code/assets, candidate data, locked dependencies, app guides, tests and frozen fixture provenance. It excludes private `.env`, runtime database/logs, past breeder decisions and historical source archives. Outputs are an ignored `dist/` ZIP and adjacent SHA-256 file. `MANIFEST.json` records each input hash, Git revision and whether the working tree was dirty; a dirty build contains the current files and is not a committed release.

Extract to a new writable folder, verify the ZIP checksum/manifest, and launch with the locked command from [team setup](../SHARE.md). Confirm health, all static assets, baseline and restart persistence. Check browser launch after readiness. Verify the archive contains no credentials or existing history. Distribution, publication and deployment are separate actions.

## Backup and restore

1. Stop every dashboard and MCP process using the database.
2. Copy the SQLite database and its adjacent `snapshots/` directory together to a backup folder. Keep any SQLite journal/WAL companion files if present. Also retain the configured original candidate ZIP and the legacy JSONL input if used. Treat stored names, reasons and context as private review data.
3. Restore into a new writable folder without overwriting the active store. Keep `snapshots/` next to the restored database. Set `UC4_CANDIDATE_DB` to its path and `UC4_ZIP` to the corresponding compatible archive; start the app and check revision identity, history and original-evidence reopening.

Browser-local preferences are separate from database backups. A new browser/address starts with new preferences. Switching source archives on restart selects that source's baseline while retaining earlier history.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `uv` unavailable | Install uv using the instructions linked in SHARE.md; reopen the terminal. |
| Port already in use | Stop the earlier server or choose another `--port`; browser preferences are specific to the address. |
| Browser cannot connect | Use HTTP, keep the server terminal open and check `/health`; inspect startup errors. |
| Source archive missing/wrong mode | Check `get_started/` and `UC4_ZIP`; historical mode needs the original v2 archive. |
| Ask/Interpret unavailable | Check the private token, accessible model route and gateway connectivity; restart after changing `.env`. Manual review remains available. |
| Conflict after review/preview | Refresh evidence/history, review again and regenerate an enrichment preview before activation. |
| Preferences fail to save | Check browser storage; manual review still works. Use Forget to remove stale saved preferences. |
| Browser executable missing | Install Playwright Chromium with the app browser dependency group, or explicitly select installed Chrome. |
| Temporary/cache access denied | Use a fresh writable basetemp and disable pytest's cache provider. |

App logs are under ignored `app/logs/`; runtime history is under the configured database directory. Do not include credentials or private review data in a public bug report.
