# UC4 breeder dashboard - team handoff

Extract the entire ZIP to a writable local folder. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed. On Windows, double-click **Start-Dashboard.cmd**. It installs locked dependencies on first launch and opens your browser after the server is ready. Internet access is needed for initial installation. Keep the terminal open while using the dashboard; press Ctrl+C to stop it.

If using a Git checkout instead, obtain the team's candidate archive separately and place it at `get_started/candidate_recommendations_synthetic.zip` before launching. Source archives are excluded from Git. The runnable team ZIP already contains this archive.

Alternatively, run from the extracted folder:

```powershell
uv run --locked --project app uc4-ask serve --open-browser
```

Use [http://127.0.0.1:8766/](http://127.0.0.1:8766/), with HTTP. If the port is occupied, stop the previous server or add `--port 8767`. Keep `app`, `get_started` and the root files together in the editable source layout. In a second terminal, `Invoke-RestMethod http://127.0.0.1:8766/health` should return `status: ok` and `candidates: 150` for the baseline.

Browse candidates, combine filters, download CSV and inspect source evidence. The detail tabs are Evidence, Decision, History and Enrichment. Review and explicitly record a breeder decision, inspect its saved receipt and original evidence, and choose Record another decision when intentionally adding a later event. Enrichment uses draft, submission, review, impact preview and explicit activation. Baseline: **32 GREEN, 53 AMBER, 65 RED**. Rules are provisional for maize-like synthetic data.

## Enable AI features

Browsing, manual filters, decisions and enrichment need no model credentials. Ask and typed filter interpretation need each user's own Portkey token and accessible model route:

1. Copy `.env.example` to `.env` beside `Start-Dashboard.cmd`.
2. Set `PORTKEY_API_KEY` to your own token.
3. Set `UC4_LLM_MODEL` to a route accessible to that token. Obtain the identifier from the team's Portkey configuration.
4. Leave optional routing fields blank unless required by your configuration.
5. Restart the dashboard. Existing shell variables take precedence over `.env`.

From PowerShell, without overwriting an existing configuration:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
uv run --locked --project app uc4-ask ping
```

Keep the completed `.env` private; it is excluded from Git and packages. No credentials are provided. Health's model field describes configuration; `ping` and an actual cited Ask answer verify gateway access.

## State and verification

For human review, double-click **Start-Breeder-Review.cmd**. It opens a fresh practice session in your browser, separate from normal decision history. Follow the [short breeder review guide](app/HUMAN_REVIEW.md), leave the command window open, and press Enter there when finished to retain the review report.

Each extracted copy maintains decisions and revisions in `app/data/`. Names are self-declared, and the demo has no shared-user authentication. Preferences belong to the browser/app address; Forget my preferences clears them without deleting recorded history. Back up the stopped database and its adjacent snapshots together, following the [process guide](app/PROCESS.md#backup-and-restore).

The ZIP contains current candidate data and no previous breeder decisions or historical v2 source archive. The [app README](app/README.md) covers operation, [process guide](app/PROCESS.md) covers candidate verification and handoff, [architecture](app/ARCHITECTURE.md) covers components/storage, and [API reference](app/API.md) covers integrations. [Release notes](app/RELEASE_NOTES.md) describe delivered features and current AI limits. The full repository additionally contains analysis and historical project documents; original historical source archives are supplied separately.

`MANIFEST.json` records the Git revision, dirty-working-tree status and SHA-256 of every packaged input. The adjacent ZIP checksum verifies the complete download. A package built from a dirty tree represents its current files, not a committed release. Maintainers regenerate from the full Git checkout with `python scripts/package_app.py`; outputs go to ignored `dist/`. The builder uses an explicit allowlist and checks the reviewed candidate source hash.
