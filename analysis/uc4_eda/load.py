"""Read the UC4 v2 synthetic CSVs straight from the supplied zip (never extracted).

v2 is the archive the UC4 SME sent on 2026-09-29 with the pre-configured scoring
file. It supersedes the kickoff (v1) archive: see ``v1/`` for the v1 profile.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import cast

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ZIP_GLOB = "RE__Hatchworks_Hackathon_-_4th_Use_Case*.zip"

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


def find_zip(root: Path = PROJECT_ROOT) -> Path:
    """Locate the UC4 v2 archive under ``get_started/``.

    Raises:
        FileNotFoundError: If no matching archive exists.
    """
    matches = sorted((root / "get_started").glob(ZIP_GLOB))
    if not matches:
        raise FileNotFoundError(f"No archive matching {ZIP_GLOB!r} in {root / 'get_started'}")
    return matches[-1]


def member_stem(name: str) -> str:
    """File stem without folder, extension or a trailing download copy number."""
    return re.sub(r" \d+$", "", Path(name).stem)


def load_tables(zip_path: Path) -> dict[str, pd.DataFrame]:
    """Load all seven CSVs and check their row counts against the profiled sizes.

    Raises:
        KeyError: If an expected CSV is missing from the archive.
        ValueError: If a file's row count differs from ``EXPECTED_ROWS``.
    """
    tables: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(zip_path) as zf:
        members = {member_stem(n): n for n in zf.namelist() if n.endswith(".csv")}
        for key, stem in FILES.items():
            with zf.open(members[stem]) as fh:
                df = pd.read_csv(fh, encoding_errors="replace")
            if len(df) != EXPECTED_ROWS[key]:
                raise ValueError(f"{stem}: {len(df)} rows, expected {EXPECTED_ROWS[key]}")
            tables[key] = df
    return tables


def lab_trait_label(guid: str) -> str:
    """Short, stable label for an unnamed lab TRAIT_GUID (no trait dictionary supplied)."""
    return f"Lab trait ...{guid[-2:]}"


def material_table(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per material: identity, genomics, lab means and evidence counts.

    v2 observations carry no trait values, so there are no field-trait means here.
    """
    germ = t["germplasm"].set_index("MATERIAL_GUID")[["MATERIAL_ID"]]
    gen_cols = ["GENOMIC_BREEDING_VALUE", *MARKERS, "QC_STATUS_LID"]
    gen = t["genomics"].set_index("MATERIAL_GUID")[gen_cols]
    lab = t["lab"].assign(TRAIT=lambda d: d["TRAIT_GUID"].map(lab_trait_label))
    lab_means = lab.pivot_table(
        index="MATERIAL_GUID", columns="TRAIT", values="NUMBER_VALUE", aggfunc="mean"
    )
    counts = pd.DataFrame(
        {
            "n_trials": t["observation"].groupby("GID")["ATTACHED_TO_FIELD_ENTITY_ID"].nunique(),
            "n_operations": t["operations"].groupby("MATERIAL_GUID").size(),
            "n_lab": t["lab"].groupby("MATERIAL_GUID").size(),
        }
    )
    out = germ.join(gen).join(lab_means).join(counts)
    count_cols = list(counts.columns)
    out[count_cols] = out[count_cols].fillna(0).astype(int)
    return cast(pd.DataFrame, out.reset_index())
