"""Read the UC4 v2 synthetic CSVs straight from the supplied zip, with provenance.

Ported from ``analysis/uc4_eda/load.py`` (the evidence record, left unchanged).
Each row gains ``_source_file`` (zip member name), ``_line_no`` (CSV line, header = 1)
and ``_row_id`` (the file's own key, as a string) so every value can be cited.
"""

from __future__ import annotations

import os
import re
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ZIP_ENV = "UC4_ZIP"
# Pinned to v2 (2026-09-29). The 2026-09-30 v3 archive changes the observation
# schema and GUID namespaces; the app moves to it in its own migration.
ZIP_NAME = "RE__Hatchworks_Hackathon_-_4th_Use_Case.zip"

# Table key -> member stem. Members may carry a " 1" download suffix.
FILES: dict[str, str] = {
    "germplasm": "germplasm_pedigree_synthetic",
    "trial": "trial_synthetic",
    "observation": "observation_synthetic",
    "operations": "operations_synthetic",
    "lab": "lab_observations_synthetic",
    "genomics": "genomics_synthetic",
    "recommendations": "trial_recommendations_synthetic",
}
EXPECTED_ROWS: dict[str, int] = {
    "germplasm": 150,
    "trial": 72,
    "observation": 720,
    "operations": 216,
    "lab": 360,
    "genomics": 150,
    "recommendations": 72,
}
# Table key -> the column that identifies a row in that file.
ROW_KEYS: dict[str, str] = {
    "germplasm": "MATERIAL_GUID",
    "trial": "TRIAL_GUID",
    "observation": "ID",
    "operations": "OPERATION_GUID",
    "lab": "ROWGUID",
    "genomics": "GENOMIC_SAMPLE_GUID",
    "recommendations": "TRIAL_GUID",
}


@dataclass(frozen=True)
class SourceInfo:
    """What ``list_sources`` says about a file beyond its counts.

    Attributes:
        synthetic_marker: ``(column, value)`` present on every row, marking mock data.
        lacks: What a reader might expect from the file that it does not hold.
    """

    synthetic_marker: tuple[str, str]
    lacks: str


_REMARK = ("REMARK", "SYNTHETIC — hackathon mock data")
SOURCES: dict[str, SourceInfo] = {
    "germplasm": SourceInfo(_REMARK, "Pedigree, parents, stage and advancement decision: "
                                     "IDs, status and material type only"),
    "trial": SourceInfo(_REMARK, "Design, begin date, replications and measured values: ID, "
                                 "start year, status and location only (values are in the "
                                 "recommendations file)"),
    "observation": SourceInfo(_REMARK, "Measured values: each row only links a line to a "
                                       "trial, with a replication number"),
    "operations": SourceInfo(_REMARK, "Quantities and results: type, status, date and plot "
                                      "only"),
    "lab": SourceInfo(_REMARK, "Trait names, a trial key and dates: line, trait GUID and a "
                               "number only"),
    "genomics": SourceInfo(_REMARK, "A trial key: one sample per line, not per trial"),
    "recommendations": SourceInfo(("IS_SYNTHETIC", "True"),
                                  "Thresholds: outcomes and a rationale only, so the SYNTH_V1 "
                                  "cut-points are inferred"),
}

# Trial-level traits in the recommendation file: code -> (label, unit).
TRAITS: dict[str, tuple[str, str]] = {
    "YIELD_T_HA": ("Grain yield", "t/ha"),
    "MOISTURE_PCT": ("Grain moisture", "%"),
    "DISEASE_SCORE": ("Disease score", "score"),
    "GENOMIC_BREEDING_VALUE_MEAN": ("Genomic breeding value, mean", "index"),
    "RESISTANT_MATERIAL_PCT": ("Resistant materials", "%"),
    "PLANT_HEIGHT_CM": ("Plant height", "cm"),
    "FLOWERING_DAYS": ("Days to flowering", "days"),
}
RECOMMENDATIONS: list[str] = ["PASS", "HOLD", "FAIL"]
MARKERS: dict[str, list[str]] = {
    "MARKER_DISEASE_RESISTANCE": ["SUSCEPTIBLE", "INTERMEDIATE", "RESISTANT"],
    "MARKER_YIELD_POTENTIAL": ["LOW", "MEDIUM", "HIGH"],
    "MARKER_DROUGHT_TOLERANCE": ["UNFAVOURABLE", "NEUTRAL", "FAVOURABLE"],
    "MARKER_MATURITY": ["EARLY", "MID", "LATE"],
}


def find_zip(starts: Sequence[Path] | None = None) -> Path:
    """Locate the UC4 v2 archive.

    ``$UC4_ZIP`` wins. Otherwise walk up from each start (default: the current
    directory, then this package) to the first directory holding ``get_started/``
    and take ``ZIP_NAME`` there. The name is exact so a newer SME drop in the
    same folder never switches the app's data without a code change.

    Args:
        starts: Directories to walk up from; for tests.

    Returns:
        Path to the archive.

    Raises:
        FileNotFoundError: If ``$UC4_ZIP`` is not a file or no archive is found.
    """
    env = os.environ.get(ZIP_ENV)
    if env:
        if not Path(env).is_file():
            raise FileNotFoundError(f"{ZIP_ENV}={env!r} is not a file")
        return Path(env)
    if starts is None:
        starts = (Path.cwd(), Path(__file__).resolve().parent)
    folder = _find_get_started(starts)
    if folder is None:
        raise FileNotFoundError(
            f"No get_started/ folder above {[str(s) for s in starts]}; "
            f"set {ZIP_ENV} to the archive path"
        )
    target = folder / ZIP_NAME
    if not target.is_file():
        raise FileNotFoundError(
            f"No archive {ZIP_NAME!r} in {folder}; "
            f"put it there (it is git-ignored) or set {ZIP_ENV}"
        )
    return target


def _find_get_started(starts: Iterable[Path]) -> Path | None:
    for start in starts:
        for directory in (start, *start.parents):
            if (directory / "get_started").is_dir():
                return directory / "get_started"
    return None


def member_stem(name: str) -> str:
    """File stem without folder, extension or a trailing download copy number."""
    return re.sub(r" \d+$", "", Path(name).stem)


def _csv_members(names: Iterable[str]) -> dict[str, str]:
    members: dict[str, str] = {}
    for name in names:
        if not name.endswith(".csv"):
            continue
        stem = member_stem(name)
        if stem in members:
            raise ValueError(f"Two members share stem {stem!r}: {members[stem]!r}, {name!r}")
        members[stem] = name
    return members


def load_tables(zip_path: Path) -> dict[str, pd.DataFrame]:
    """Load all seven CSVs with provenance columns, checking row counts.

    The zip is opened read-only and never extracted.

    Args:
        zip_path: The v2 archive (see ``find_zip``).

    Returns:
        Table key -> DataFrame with ``_source_file``, ``_line_no`` and ``_row_id``.

    Raises:
        KeyError: If an expected CSV is missing from the archive.
        ValueError: If two members share a stem, or a row count differs from
            ``EXPECTED_ROWS``.
    """
    tables: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(zip_path) as zf:
        members = _csv_members(zf.namelist())
        for key, stem in FILES.items():
            if stem not in members:
                raise KeyError(f"{stem}.csv not in {zip_path.name}")
            name, key_col = members[stem], ROW_KEYS[key]
            with zf.open(name) as fh:
                df = pd.read_csv(fh, encoding_errors="replace", dtype={key_col: str})
            if len(df) != EXPECTED_ROWS[key]:
                raise ValueError(f"{stem}: {len(df)} rows, expected {EXPECTED_ROWS[key]}")
            df["_source_file"] = name
            df["_line_no"] = range(2, len(df) + 2)
            df["_row_id"] = df[key_col]
            tables[key] = df
    return tables


def lab_trait_label(guid: str) -> str:
    """Short, stable label for an unnamed lab TRAIT_GUID (no trait dictionary supplied)."""
    return f"Lab trait ...{guid[-2:]}"
