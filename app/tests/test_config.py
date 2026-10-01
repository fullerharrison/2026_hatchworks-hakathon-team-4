"""The repo-root .env loads automatically; a missing key stops the CLI before it runs."""

import os
from pathlib import Path

import pytest

from uc4_mcp import cli, config


def test_load_env_file_reads_values(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("UC4_TEST_KEY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("UC4_TEST_KEY", raising=False)
    assert config.load_env_file(env) is True
    assert os.environ["UC4_TEST_KEY"] == "from-file"


def test_load_env_file_does_not_override_the_shell(tmp_path: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("UC4_TEST_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("UC4_TEST_KEY", "from-shell")
    assert config.load_env_file(env) is True
    assert os.environ["UC4_TEST_KEY"] == "from-shell"


def test_load_env_file_missing_is_not_an_error(tmp_path: Path) -> None:
    assert config.load_env_file(tmp_path / "absent.env") is False


def test_missing_keys_reports_absent_and_blank() -> None:
    assert config.missing_keys(("A", "B", "C"), {"A": "x", "B": "  "}) == ["B", "C"]
    assert config.missing_keys(("A",), {"A": "x"}) == []


def test_cli_refuses_to_run_without_the_portkey_key(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        tmp_path: Path) -> None:
    absent = tmp_path / "absent.env"
    monkeypatch.setattr(config, "ENV_FILE", absent)
    monkeypatch.setattr(cli, "ENV_FILE", absent)
    monkeypatch.delenv("PORTKEY_API_KEY", raising=False)
    monkeypatch.setattr(cli, "configure_cli_logging", lambda: None)
    with pytest.raises(SystemExit) as exc:
        cli.main(["ping"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "PORTKEY_API_KEY" in err and str(absent) in err
