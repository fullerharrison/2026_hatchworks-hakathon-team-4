"""Shared fixtures: the v2 archive is loaded once per test session."""

from pathlib import Path

import pandas as pd
import pytest

from uc4_mcp.sources import find_zip, load_tables


@pytest.fixture(scope="session")
def zip_path() -> Path:
    """The v2 archive; fails with find_zip's message (names UC4_ZIP) when absent."""
    try:
        return find_zip()
    except FileNotFoundError as e:
        pytest.fail(str(e), pytrace=False)


@pytest.fixture(scope="session")
def tables(zip_path: Path) -> dict[str, pd.DataFrame]:
    """All seven tables with provenance columns."""
    return load_tables(zip_path)
