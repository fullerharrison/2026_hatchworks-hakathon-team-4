"""What changed between two UC4 archives, file by file."""

from __future__ import annotations

import pandas as pd


def _guid_values(df: pd.DataFrame) -> set[str]:
    cols = [c for c in df.columns if "GUID" in c]
    return set(df[cols].stack().dropna().astype(str)) if cols else set()


def _filled(df: pd.DataFrame) -> set[str]:
    return {c for c in df.columns if df[c].notna().any()}


def version_diff(old: dict[str, pd.DataFrame], new: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per file: shape and fill in each version, schema changes and GUID overlap.

    Args:
        old: Tables of the earlier archive, keyed as in ``load.FILES``.
        new: Tables of the later archive.

    Returns:
        Columns ``file``, ``identical`` (same content in both), ``rows_old``/``rows_new``, ``filled_cols_old``/``filled_cols_new``,
        ``cols_added``, ``cols_removed``, ``newly_filled`` (existing columns empty before,
        filled now) and ``shared_guids`` (GUID values present in both versions).
    """
    rows = []
    for key, n in new.items():
        o = old[key]
        added = sorted(set(n.columns) - set(o.columns))
        removed = sorted(set(o.columns) - set(n.columns))
        newly = sorted((_filled(n) - _filled(o)) & set(o.columns))
        rows.append({
            "file": key, "identical": o.equals(n), "rows_old": len(o), "rows_new": len(n),
            "filled_cols_old": len(_filled(o)), "filled_cols_new": len(_filled(n)),
            "cols_added": ", ".join(added), "cols_removed": ", ".join(removed),
            "newly_filled": ", ".join(newly), "n_newly_filled": len(newly),
            "shared_guids": len(_guid_values(o) & _guid_values(n)),
        })
    return pd.DataFrame(rows)
