"""Read the UC4 synthetic CSVs straight from the supplied zip (never extracted).

v3 is the corrected archive the UC4 SME sent on 2026-09-30 ("a few attributes were
not interconnected" in v2). It supersedes v2 (2026-09-29, see ``v2/``) and the
kickoff v1 (see ``v1/``). Every GUID was regenerated between v2 and v3.

``align`` repairs the two key namespaces v3 still leaves disconnected so the rest of
the profile can join; ``link_rates`` reports the links exactly as recorded.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import cast

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Exact names, so a new SME drop in get_started/ never switches the profile silently.
ZIP_NAME = "RE__Hatchworks_Hackathon_-_4th_Use_Case_09-30-2026.zip"
V2_ZIP_NAME = "RE__Hatchworks_Hackathon_-_4th_Use_Case.zip"
VERSION = "v3"

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
# Traits measured per plot in v3 observations (TRAIT_CODE values).
FIELD_TRAITS: list[str] = ["YIELD_T_HA", "MOISTURE_PCT", "DISEASE_SCORE", "PLANT_HEIGHT_CM",
                           "FLOWERING_DAYS"]
QUALITY_FLAGS: list[str] = ["ACCEPTED", "REVIEW", "REJECTED"]
RECOMMENDATIONS: list[str] = ["PASS", "HOLD", "FAIL"]
MARKERS: dict[str, list[str]] = {
    "MARKER_DISEASE_RESISTANCE": ["SUSCEPTIBLE", "INTERMEDIATE", "RESISTANT"],
    "MARKER_YIELD_POTENTIAL": ["LOW", "MEDIUM", "HIGH"],
    "MARKER_DROUGHT_TOLERANCE": ["UNFAVOURABLE", "NEUTRAL", "FAVOURABLE"],
    "MARKER_MATURITY": ["EARLY", "MID", "LATE"],
}

# Recorded cross-file links: (label, from table, from column, to table, to column).
LINKS: list[tuple[str, str, str, str, str]] = [
    ("Observation → trial", "observation", "TRIAL_GUID", "trial", "TRIAL_GUID"),
    ("Observation → line", "observation", "MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
    ("Observation → trial site", "observation", "LOCATION_GUID", "trial", "LOCATION_GUID"),
    ("Operation → trial", "operations", "TRIAL_GUID", "trial", "TRIAL_GUID"),
    ("Operation → line", "operations", "MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
    ("Lab result → line", "lab", "MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
    ("Genomics → line", "genomics", "MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
    ("Recommendation → trial (GUID)", "recommendations", "TRIAL_GUID", "trial", "TRIAL_GUID"),
    ("Recommendation → trial (ID)", "recommendations", "TRIAL_ID", "trial", "TRIAL_ID"),
    ("Recommendation → trial site", "recommendations", "LOCATION_GUID", "trial", "LOCATION_GUID"),
    ("Female parent → line", "germplasm", "FEMALE_PARENT_MATERIAL_GUID", "germplasm",
     "MATERIAL_GUID"),
    ("Male parent → line", "germplasm", "MALE_PARENT_MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
    ("Parent trial → trial", "germplasm", "FEMALE_PARENT_TRIAL_ID", "trial", "TRIAL_ID"),
    ("Trial male line → line", "trial", "MALE_MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
]


def find_zip(root: Path = PROJECT_ROOT, name: str = ZIP_NAME) -> Path:
    """Locate a UC4 archive under ``get_started/`` by its exact name.

    Args:
        root: Project root holding ``get_started/``.
        name: Archive file name; defaults to the v3 archive this profile describes.

    Raises:
        FileNotFoundError: If the archive is absent.
    """
    path = root / "get_started" / name
    if not path.is_file():
        raise FileNotFoundError(f"No archive {name!r} in {root / 'get_started'}")
    return path


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


def link_rates(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """How many distinct values of each recorded link resolve in the target file.

    Must be given the tables as loaded, not ``align``-ed, or the repaired links pass.
    """
    rows = []
    for label, src, col, dst, key in LINKS:
        vals = set(t[src][col].dropna())
        hit = len(vals & set(t[dst][key].dropna()))
        rows.append({"link": label, "from": f"{src}.{col}", "to": f"{dst}.{key}",
                     "distinct": len(vals), "resolved": hit,
                     "share": round(hit / len(vals), 3) if vals else float("nan")})
    return pd.DataFrame(rows)


def guid_suffix(s: pd.Series) -> pd.Series:
    """Last GUID block: ``1FC9E916-899C-6A96-0000-000000000007`` -> ``000000000007``."""
    return cast(pd.Series, s.str.split("-").str[-1])


def align(t: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Copy of the tables with the two v3 key namespaces mapped onto trial and germplasm.

    * Recommendations carry their own TRIAL_GUID and LOCATION_GUID; both are replaced
      by the trial file's, joined on the recorded ``TRIAL_ID`` (a real, shared key).
    * Genomics carries its own MATERIAL_GUID prefix; it is replaced by the germplasm
      GUID with the same last block. This is **positional**: no file records it.

    The supplied values are kept in ``SOURCE_*`` columns.
    """
    out = dict(t)
    trial = t["trial"].set_index("TRIAL_ID")
    rec = t["recommendations"]
    trial_ids = cast(pd.Series, rec["TRIAL_ID"])
    out["recommendations"] = rec.assign(
        SOURCE_TRIAL_GUID=rec["TRIAL_GUID"], SOURCE_LOCATION_GUID=rec["LOCATION_GUID"],
        TRIAL_GUID=trial_ids.map(cast(pd.Series, trial["TRIAL_GUID"])),
        LOCATION_GUID=trial_ids.map(cast(pd.Series, trial["LOCATION_GUID"])))
    germ_guid = cast(pd.Series, t["germplasm"]["MATERIAL_GUID"])
    by_suffix = pd.Series(germ_guid.to_numpy(), index=guid_suffix(germ_guid))
    gen = t["genomics"]
    gen_guid = cast(pd.Series, gen["MATERIAL_GUID"])
    out["genomics"] = gen.assign(SOURCE_MATERIAL_GUID=gen_guid,
                                 MATERIAL_GUID=guid_suffix(gen_guid).map(by_suffix))
    return out


def lab_trait_label(guid: str) -> str:
    """Short, stable label for an unnamed lab TRAIT_GUID (no trait dictionary supplied)."""
    return f"Lab trait ...{guid[-2:]}"


def plot_means(obs: pd.DataFrame, flags: list[str] | None = None) -> pd.DataFrame:
    """Mean plot value per trial (rows, TRIAL_GUID) and field trait (columns).

    Args:
        obs: The observation table.
        flags: Quality flags to keep; default all.
    """
    if flags is not None:
        obs = cast(pd.DataFrame, obs[obs["QUALITY_FLAG_LID"].isin(flags)])
    return obs.pivot_table(index="TRIAL_GUID", columns="TRAIT_CODE", values="OBSERVATION_VALUE",
                           aggfunc="mean")


def material_table(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per line: identity, pedigree status, genomics, lab and plot means, evidence counts.

    Expects ``align``-ed tables so genomics joins. Plot means use ACCEPTED values only.
    """
    germ = cast(pd.DataFrame, t["germplasm"].set_index("MATERIAL_GUID")[
        ["MATERIAL_ID", "STAGE_CODE_LID", "GENERATION_CODE", "ADVANCEMENT_DECISION"]])
    gen_cols = ["GENOMIC_BREEDING_VALUE", *MARKERS, "QC_STATUS_LID"]
    gen = t["genomics"].set_index("MATERIAL_GUID")[gen_cols]
    lab = t["lab"].assign(TRAIT=lambda d: d["TRAIT_GUID"].map(lab_trait_label))
    lab_means = lab.pivot_table(
        index="MATERIAL_GUID", columns="TRAIT", values="NUMBER_VALUE", aggfunc="mean"
    )
    obs = t["observation"]
    accepted = obs[obs["QUALITY_FLAG_LID"] == "ACCEPTED"]
    field = accepted.pivot_table(index="MATERIAL_GUID", columns="TRAIT_CODE",
                                 values="OBSERVATION_VALUE", aggfunc="mean").add_suffix(" (plots)")
    counts = pd.DataFrame(
        {
            "n_trials": obs.groupby("MATERIAL_GUID")["TRIAL_GUID"].nunique(),
            "n_plot_values": obs.groupby("MATERIAL_GUID").size(),
            "n_operations": t["operations"].groupby("MATERIAL_GUID").size(),
            "n_lab": t["lab"].groupby("MATERIAL_GUID").size(),
        }
    )
    out = germ.join(gen).join(lab_means).join(field).join(counts)
    count_cols = list(counts.columns)
    out[count_cols] = out[count_cols].fillna(0).astype(int)
    return cast(pd.DataFrame, out.reset_index())
