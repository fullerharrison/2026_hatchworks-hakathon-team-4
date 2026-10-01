"""The repo-root ``.env`` and the variables the app cannot start without.

``uc4-ask`` and ``uc4-mcp`` load the file themselves, so no ``uv run --env-file`` is needed.
Values already exported in the shell win: ``.env`` only fills the gaps.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"
# The question agent needs the Portkey key; the model is validated by ``llm.load_settings``
# (``UC4_LLM_MODEL`` or ``[llm] model`` in agent.toml). The MCP server needs no secrets.
AGENT_REQUIRED = ("PORTKEY_API_KEY",)


def load_env_file(path: Path | None = None) -> bool:
    """Load ``KEY=value`` pairs from ``path`` (default: repo-root ``.env``) into ``os.environ``.

    Existing variables are never overwritten, so a shell export beats the file. A missing
    file is not an error.

    Args:
        path: Explicit file to load; ``None`` uses ``ENV_FILE``.

    Returns:
        True if the file exists and its values were applied.
    """
    target = path or ENV_FILE
    if not target.is_file():
        return False
    return bool(load_dotenv(target, override=False))


def missing_keys(required: Iterable[str],
                 env: Mapping[str, str] = os.environ) -> list[str]:
    """Required variables that are absent or blank, sorted for a stable message."""
    return sorted(key for key in required if not env.get(key, "").strip())


def ensure_env(required: Iterable[str] = AGENT_REQUIRED) -> list[str]:
    """Load ``.env``, then report the required variables it and the shell did not supply."""
    load_env_file()
    return missing_keys(required)
