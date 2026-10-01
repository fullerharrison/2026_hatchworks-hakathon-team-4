"""Build a source-layout group handoff; never include local state or credentials."""
from pathlib import Path
import hashlib
import json
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "get_started/candidate_recommendations_synthetic.zip"
EXPECTED = "c195330223d0e3bb334dc9c2e1f338a37f058f5cb3b564d9d2140c7a5011da46"


def build():
    files = ["SHARE.md", ".env.example", "Start-Dashboard.cmd", "scripts/package_app.py", SOURCE,
             "app/pyproject.toml", "app/uv.lock", "app/.python-version", "app/agent.toml",
             "app/README.md", "app/API.md", "app/ARCHITECTURE.md",
             "app/evals/questions.json", "app/evals/questions_v2.json"]
    for directory, extensions in [("app/src", {".py", ".html", ".css", ".js"}),
                                   ("app/tests", {".py"})]:
        files.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob("*")
                     if p.is_file() and p.suffix in extensions and "__pycache__" not in p.parts)
    payloads = {name: (ROOT / name).read_bytes() for name in sorted(set(files))}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    if hashes[SOURCE] != EXPECTED:
        raise ValueError("Synthetic archive hash differs from the reviewed source")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    manifest = {"git_revision": revision, "working_tree_dirty": dirty, "sha256": hashes}
    target = ROOT / "dist" / f"uc4-candidate-dashboard-{revision[:8]}.zip"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr("uc4-dashboard/" + name, data)
        archive.writestr("uc4-dashboard/MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    print(f"{target}\n{len(payloads)} files; SHA-256 {digest}; dirty={dirty}")
    return target


if __name__ == "__main__":
    build()
