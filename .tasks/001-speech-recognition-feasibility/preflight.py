"""Collect an offline, non-sensitive developer-machine probe for Phase 1.

Run with Python 3.12+; results are restricted to this task's results directory.
No models, audio devices, credentials, network endpoints or app stores are opened.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


TASK_ROOT = Path(__file__).resolve().parent
PACKAGES = (
    "moonshine-voice",
    "transformers",
    "torch",
    "nemo_toolkit",
    "onnxruntime",
)
WINDOWS_PROBES = {
    "cpu": (
        "Get-CimInstance Win32_Processor | "
        "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | "
        "ConvertTo-Json -Compress"
    ),
    "memory": (
        "Get-CimInstance Win32_ComputerSystem | "
        "Select-Object TotalPhysicalMemory | ConvertTo-Json -Compress"
    ),
    "gpu": (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress"
    ),
    "browser": (
        r"$paths = @('C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',"
        r"'C:\Program Files\Microsoft\Edge\Application\msedge.exe',"
        r"'C:\Program Files\Google\Chrome\Application\chrome.exe',"
        r"'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'); "
        "$paths | Where-Object { Test-Path -LiteralPath $_ } | "
        "ForEach-Object { (Get-Item -LiteralPath $_).VersionInfo | "
        "Select-Object ProductName,ProductVersion } | ConvertTo-Json -Compress"
    ),
}


def _windows_probe(command: str) -> dict[str, object]:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        return {"status": "unknown", "reason": "PowerShell unavailable"}
    try:
        result = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unknown", "reason": "Inventory probe unavailable"}
    if result.returncode != 0 or not result.stdout.strip():
        return {"status": "unknown", "reason": "No inventory result"}
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "unknown", "reason": "Unparseable inventory result"}
    return {"status": "locally_verified_inventory", "value": value}


def collect_inventory() -> dict[str, object]:
    """Inspect this machine without loading ASR packages or accessing audio.

    Returns:
        JSON-compatible inventory, unknowns and explicit unapproved gates.
        Installed versions describe this interpreter, not the editor environment.

    Raises:
        OSError: If the task volume cannot be inspected.
    """
    disk = shutil.disk_usage(TASK_ROOT)
    installed: dict[str, str | None] = {}
    for package in PACKAGES:
        try:
            installed[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            installed[package] = None
    hardware = {
        name: _windows_probe(command)
        if platform.system() == "Windows"
        else {"status": "unknown", "reason": "Windows-only inventory probe"}
        for name, command in WINDOWS_PROBES.items()
    }
    return {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_type": "local_inventory_not_asr_benchmark",
        "machine_role": "developer_probe_demo_target_unconfirmed",
        "os": {"system": platform.system(), "release": platform.release(),
               "version": platform.version(), "architecture": platform.machine()},
        "python": {"version": platform.python_version(),
                   "implementation": platform.python_implementation()},
        "logical_cpu_count": os.cpu_count(),
        "hardware": hardware,
        "gpu_memory_caveat": "Win32 AdapterRAM is not reliable VRAM evidence",
        "task_volume": {"total_bytes": disk.total, "free_bytes": disk.free},
        "installed_asr_distributions": installed,
        "unknowns": ["microphone", "demo_machine", "language_and_accents",
                     "noise_environment", "approved_disk_and_network_budget",
                     "verified_gpu_vram_and_compute_provider"],
        "approvals": {"researcher_and_time_cap": "pending",
                      "downloads_and_runtime_install": "pending",
                      "recording_and_retention": "pending",
                      "hosted_audio": "pending", "workflow_spike": "pending"},
    }


def write_inventory(inventory: dict[str, object], output: Path) -> Path:
    """Write a new inventory only under this task's results directory.

    Args:
        inventory: JSON-compatible evidence; callers must omit secrets.
        output: Absolute path or a path relative to the task root.

    Returns:
        Resolved path of the new UTF-8 JSON file.

    Raises:
        ValueError: If the path escapes results, including through a symlink.
        FileExistsError: If evidence already exists; overwrites are forbidden.
        OSError: If directory creation or writing fails.
        TypeError: If evidence cannot be serialized to JSON.
    """
    root = TASK_ROOT.resolve()
    results = (root / "results").resolve()
    target = (output if output.is_absolute() else root / output).resolve()
    if not results.is_relative_to(root) or not target.is_relative_to(results):
        raise ValueError("Evidence output must stay within this task's results")
    if target == results:
        raise ValueError("Evidence output must name a file")
    payload = json.dumps(inventory, indent=2, ensure_ascii=True, allow_nan=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as stream:
        stream.write(payload + "\n")
    return target


def main() -> int:
    """Run the offline inventory CLI, returning zero on success or two on failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=Path(f"results/machine-{datetime.now(timezone.utc):%Y-%m-%d}.json"),
        help="New evidence path inside this task's results directory",
    )
    args = parser.parse_args()
    try:
        target = write_inventory(collect_inventory(), args.output)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"Preflight failed: {error}\n")
    print(f"Inventory saved: {target.relative_to(TASK_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())