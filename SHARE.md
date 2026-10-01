# UC4 breeder dashboard — group handoff

Extract the entire ZIP to a writable local folder. Install **uv** if needed:
https://docs.astral.sh/uv/getting-started/installation/

On Windows, double-click **Start-Dashboard.cmd**. It installs the locked dependencies
on first launch and opens your browser when the server is ready. Internet access is
needed for the initial installation. Keep the terminal open while using the dashboard;
press Ctrl+C to stop it. Alternatively, run from the extracted folder:

```powershell
uv run --locked --project app uc4-ask serve --open-browser
```

The dashboard is at http://127.0.0.1:8766/ (HTTP, not HTTPS). If port 8766 is already
occupied, stop the previous server or add `--port 8767`. The package uses an editable
source layout; keep `app` and `get_started` together.

Browse all 150 candidates, combine filters, download CSV, select a candidate to inspect
evidence, record a breeder decision, or submit enrichment for review and activation.
The baseline is 32 GREEN, 53 AMBER and 65 RED. Rules are provisional and the data are
maize-like synthetic data for the vegetable-seed challenge.

Browsing, decisions and enrichment need no model credentials. For Ask, create a `.env`
file beside this document with your own `PORTKEY_API_KEY` and `UC4_LLM_MODEL` values
for your team's Portkey configuration. No credentials are supplied in this package.

Each extracted copy maintains its own decisions and revisions in `app/data/`.
This is a local demonstration, with self-declared reviewer names and no shared-user
authentication. Back up the database and its `snapshots` directory together. This ZIP
contains no previous breeder decisions. Historical v2 source archives are not included.

See `app/README.md` for workflows and `app/ARCHITECTURE.md` for implementation details.
`MANIFEST.json` records the Git revision and SHA-256 of every packaged input file;
the adjacent ZIP checksum verifies the complete download.

Maintainers: regenerate with `python scripts/package_app.py`. Outputs go into ignored
`dist/`; the builder uses an explicit allowlist and verifies the synthetic source hash.
