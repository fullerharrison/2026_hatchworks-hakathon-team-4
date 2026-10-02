"""Run a bounded offline interval comparison and preserve prior task evidence.

Runs the same installed tiny model at three SDK update intervals. No preparation,
downloads, microphone, app endpoints or guessed CPU-thread options are used.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from benchmark import UPDATE_INTERVALS, assess_fidelity, contained_path
from preflight import TASK_ROOT, write_inventory


CONFIGURATIONS = (("control-0500ms", 0.5), ("floor-1000ms", 1.0), ("floor-2000ms", 2.0))


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _preserved_files() -> dict[str, str]:
    files = [path for path in (TASK_ROOT / "results").iterdir() if path.is_file()]
    files.extend((TASK_ROOT / "corpus").glob("*.wav"))
    files.extend((TASK_ROOT / "corpus").glob("*.json"))
    files.extend([TASK_ROOT / "requirements.lock.txt"])
    return {str(path.relative_to(TASK_ROOT)): _hash(path) for path in sorted(files)}


def _outside_state() -> dict[str, str]:
    root = TASK_ROOT.parents[1]
    result = subprocess.run(
        ["git", "diff", "--name-only"], cwd=root, capture_output=True,
        text=True, check=True,
    )
    state = {}
    for name in result.stdout.splitlines():
        if name.startswith(".tasks/001-speech-recognition-feasibility/"):
            continue
        path = root / name
        if path.name.startswith(".env"):
            state[name] = "credential_related_path_not_read"
        else:
            state[name] = _hash(path) if path.is_file() else "deleted"
    return state


def fidelity_for_result(result: dict[str, Any], rubric: dict[str, Any]) -> dict[str, Any]:
    """Assess first-repetition transcripts using a fixed synthetic-only rubric.

    Args:
        result: Saved ASR result, preserving original transcripts and failures.
        rubric: Explicit per-clip component checks, not a general semantic parser.

    Returns:
        Per-mode component counts and verbatim diagnostic failure examples.

    Raises:
        ValueError: If a speech clip has no diagnostic rubric.
    """
    report: dict[str, Any] = {}
    for mode in ("utterance", "native_streaming"):
        components: dict[str, dict[str, int]] = {}
        cases = []
        for run in result["runs"]:
            if run["mode"] != mode or run["repetition"] != 1 or run["outcome"] == "no_speech":
                continue
            checks = rubric["clips"].get(run["clip_id"])
            if checks is None:
                raise ValueError(f"Missing fidelity rubric: {run['clip_id']}")
            text = run["measurement"]["text"] if run["status"] == "ok" else None
            flags = assess_fidelity(text, checks) if text is not None else {
                component: False for component in checks
            }
            for component, passed in flags.items():
                count = components.setdefault(component, {"passed": 0, "total": 0})
                count["total"] += 1
                count["passed"] += int(passed)
            cases.append({"clip_id": run["clip_id"], "reference": run["reference"],
                          "hypothesis": text, "components": flags, "status": run["status"]})
        report[mode] = {"components": components, "cases": cases}
    return report


def execute(prefix: str, budget_seconds: int) -> dict[str, Any]:
    """Compare fixed SDK intervals in fresh processes under a bounded deadline.

    Args:
        prefix: New task-local result filename prefix, not a path.
        budget_seconds: At most 2400 seconds, reserving time for analysis/reporting.

    Returns:
        Configuration results, fidelity counts and input/evidence preservation checks.

    Raises:
        ValueError: If a target exists or preservation checks fail.
        OSError: If a subprocess or evidence file cannot be accessed.
    """
    if not prefix.replace("-", "").isalnum() or not 1 <= budget_seconds <= 2400:
        raise ValueError("Use a simple new prefix and a budget of 1..2400 seconds")
    for name, _ in CONFIGURATIONS:
        for suffix in ("json", "log"):
            if contained_path(Path(f"results/{prefix}-{name}.{suffix}")).exists():
                raise ValueError("Comparison outputs already exist; choose a new prefix")
    rubric_path = contained_path(Path("corpus/fidelity-rubric.json"))
    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    before = _preserved_files()
    outside_before = _outside_state()
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    deadline = started + budget_seconds
    comparisons = []
    for name, interval in CONFIGURATIONS:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            comparisons.append({"name": name, "status": "unrun_timebox_exhausted"})
            continue
        output = contained_path(Path(f"results/{prefix}-{name}.json"))
        command = [
            sys.executable, "-B", "-W", "error", str(TASK_ROOT / "run_moonshine.py"),
            "--runtime", "results/moonshine-runtime.json", "--output", str(output),
            "--repetitions", "3", "--update-interval", str(interval),
        ]
        print(f"Starting {name}: three repetitions, same local WAVs", flush=True)
        run_started = time.perf_counter()
        entry: dict[str, Any] = {"name": name, "update_interval_seconds": interval}
        try:
            process = subprocess.run(command, cwd=TASK_ROOT, capture_output=True,
                                     text=True, timeout=min(900, remaining), check=False)
            with contained_path(Path(f"results/{prefix}-{name}.log")).open("x", encoding="utf-8") as log:
                log.write(process.stdout + process.stderr)
            entry.update(status="completed" if process.returncode == 0 else "failed",
                         returncode=process.returncode)
        except subprocess.TimeoutExpired as error:
            entry.update(status="timeout", timeout_seconds=min(900, remaining))
            with contained_path(Path(f"results/{prefix}-{name}.log")).open("x", encoding="utf-8") as log:
                log.write(str(error.stdout or "") + str(error.stderr or ""))
        entry["wall_seconds"] = time.perf_counter() - run_started
        if entry["status"] == "completed":
            result = json.loads(output.read_text(encoding="utf-8"))
            entry.update(result_path=str(output.relative_to(TASK_ROOT)),
                         trials=len(result["runs"]), summary=result["summary"],
                         fidelity=fidelity_for_result(result, rubric))
        comparisons.append(entry)
        print(f"Finished {name}: {entry['status']} in {entry['wall_seconds']:.1f}s", flush=True)
    preserved = all(_hash(contained_path(Path(name))) == digest for name, digest in before.items())
    outside_after = _outside_state()
    historical = json.loads((TASK_ROOT / "results/moonshine-synthetic-3x.json").read_text(encoding="utf-8"))
    return {
        "schema_version": 1, "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparison_wall_seconds": time.perf_counter() - started,
        "budget_seconds": budget_seconds, "settings": "SDK update interval only; no thread flags",
        "rubric_path": "corpus/fidelity-rubric.json", "rubric_sha256": _hash(rubric_path),
        "historical_baseline": {"path": "results/moonshine-synthetic-3x.json",
                                "summary": historical["summary"],
                                "fidelity": fidelity_for_result(historical, rubric)},
        "preserved_file_hashes": before, "prior_evidence_and_inputs_unchanged": preserved,
        "outside_tracked_changes_unchanged": outside_before == outside_after,
        "outside_state_before": outside_before, "outside_state_after": outside_after,
        "configurations": comparisons,
        "limitations": ["fixed_order_not_counterbalanced", "one_synthetic_voice",
                        "fixture_specific_diagnostics_not_general_semantic_accuracy",
                        "no_browser_no_microphone_no_writes"],
    }


def main() -> int:
    """Run or preview the fixed comparison plan, preserving all old outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="moonshine-tuning")
    parser.add_argument("--budget-seconds", type=int, default=2400)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"intervals": UPDATE_INTERVALS, "repetitions": 3,
                          "downloads": False, "microphone": False,
                          "time_budget_seconds": args.budget_seconds}))
        return 0
    target = contained_path(Path(f"results/{args.prefix}-comparison.json"))
    if target.exists():
        parser.error("Comparison evidence already exists; choose a new prefix")
    report = execute(args.prefix, args.budget_seconds)
    write_inventory(report, target)
    print(f"Comparison saved: {target.relative_to(TASK_ROOT)}")
    return 0 if report["prior_evidence_and_inputs_unchanged"] and report["outside_tracked_changes_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())