"""Behavioral checks for task-local evidence containment and preservation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import preflight


@pytest.fixture(name="task_root")
def fixture_task_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "task"
    root.mkdir()
    monkeypatch.setattr(preflight, "TASK_ROOT", root)
    return root


def test_inventory_writes_valid_json_under_task(task_root: Path) -> None:
    target = preflight.write_inventory(
        {"evidence_type": "synthetic_test", "version": 1},
        Path("results/inventory.json"),
    )

    assert target == task_root / "results" / "inventory.json"
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "evidence_type": "synthetic_test", "version": 1,
    }


def test_external_output_is_rejected_without_writing(task_root: Path) -> None:
    target = task_root.parent / "external.json"

    with pytest.raises(ValueError, match="within this task"):
        preflight.write_inventory({"version": 1}, target)

    assert not target.exists()
    assert not (task_root / "results").exists()


def test_parent_traversal_is_rejected(task_root: Path) -> None:
    with pytest.raises(ValueError, match="within this task"):
        preflight.write_inventory({"version": 1}, Path("results/../../escape.json"))

    assert not (task_root.parent / "escape.json").exists()


def test_task_document_cannot_be_overwritten(task_root: Path) -> None:
    with pytest.raises(ValueError, match="within this task"):
        preflight.write_inventory({"version": 1}, Path("task.md"))

    assert not (task_root / "task.md").exists()


def test_existing_evidence_is_preserved(task_root: Path) -> None:
    target = preflight.write_inventory({"version": 1}, Path("results/inventory.json"))

    with pytest.raises(FileExistsError):
        preflight.write_inventory({"version": 2}, target)

    assert target == task_root / "results" / "inventory.json"
    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 1}


def test_results_directory_is_not_a_file_target(task_root: Path) -> None:
    with pytest.raises(ValueError, match="name a file"):
        preflight.write_inventory({"version": 1}, Path("results"))

    assert not (task_root / "results").exists()


def test_non_json_evidence_does_not_create_results(task_root: Path) -> None:
    with pytest.raises(TypeError):
        preflight.write_inventory({"invalid": object()}, Path("results/invalid.json"))

    assert not (task_root / "results").exists()


def test_linked_results_cannot_escape_task(task_root: Path) -> None:
    outside = task_root.parent / "outside"
    outside.mkdir()
    try:
        (task_root / "results").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or privileges")

    with pytest.raises(ValueError, match="within this task"):
        preflight.write_inventory({"version": 1}, Path("results/escape.json"))

    assert not (outside / "escape.json").exists()