"""Step 2: loading the v2 archive with provenance, and locating it."""

import hashlib
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from uc4_mcp.sources import (
    EXPECTED_ROWS,
    FILES,
    ROW_KEYS,
    SOURCES,
    ZIP_ENV,
    ZIP_NAME,
    find_zip,
    lab_trait_label,
    load_tables,
    member_stem,
)

Tables = dict[str, pd.DataFrame]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return path


# --- source catalogue --------------------------------------------------------


@pytest.mark.parametrize("key", list(FILES))
def test_every_row_carries_its_synthetic_marker(tables: Tables, key: str) -> None:
    column, value = SOURCES[key].synthetic_marker
    assert (tables[key][column].astype(str) == value).all()


def test_every_source_says_what_it_lacks() -> None:
    assert list(SOURCES) == list(FILES)
    assert all(s.lacks for s in SOURCES.values())


# --- loading ----------------------------------------------------------------


def test_row_counts(tables: Tables) -> None:
    assert {k: len(df) for k, df in tables.items()} == EXPECTED_ROWS


def test_matching_row_counts_do_not_hide_incompatible_schema(zip_path: Path, tmp_path: Path) -> None:
    target = tmp_path / "unsupported.zip"
    with zipfile.ZipFile(zip_path) as source, zipfile.ZipFile(target, "w") as output:
        for name in source.namelist():
            contents = source.read(name)
            if member_stem(name) == FILES["observation"]:
                frame = pd.read_csv(__import__("io").BytesIO(contents)).drop(columns=["GID"])
                contents = frame.to_csv(index=False).encode()
            output.writestr(name, contents)
    with pytest.raises(ValueError, match="lacks v2 columns GID.*v3 requires a data migration"):
        load_tables(target)


@pytest.mark.parametrize("key", list(FILES))
def test_row_id_unique_non_null_str(tables: Tables, key: str) -> None:
    df = tables[key]
    assert (df["_row_id"] == df[ROW_KEYS[key]]).all()
    assert df["_row_id"].notna().all()
    assert df["_row_id"].is_unique
    assert all(isinstance(v, str) for v in df["_row_id"])


def test_observation_id_loads_as_string(tables: Tables) -> None:
    assert tables["observation"]["_row_id"].iloc[0] == "1"


@pytest.mark.parametrize("key", list(FILES))
def test_line_numbers_follow_csv_lines(tables: Tables, zip_path: Path, key: str) -> None:
    df = tables[key]
    with zipfile.ZipFile(zip_path) as zf:
        physical = zf.read(df["_source_file"].iloc[0]).decode().splitlines()
    # Holds only if no record spans lines, so this also guards the index + 2 mapping.
    assert df["_line_no"].iloc[0] == 2
    assert df["_line_no"].iloc[-1] == len(physical)


@pytest.mark.parametrize("key", list(FILES))
def test_source_file_is_member_name(tables: Tables, key: str) -> None:
    names = tables[key]["_source_file"].unique()
    assert len(names) == 1
    assert member_stem(names[0]) == FILES[key]
    assert names[0].endswith(".csv")


def test_materials_link_to_germplasm(tables: Tables) -> None:
    germ = tables["germplasm"]["MATERIAL_GUID"]
    assert tables["observation"]["GID"].isin(germ).all()
    for key in ("operations", "lab", "genomics"):
        assert tables[key]["MATERIAL_GUID"].isin(germ).all(), key


def test_trials_link_both_ways_to_recommendations(tables: Tables) -> None:
    trial = set(tables["trial"]["TRIAL_GUID"])
    rec = set(tables["recommendations"]["TRIAL_GUID"])
    assert trial == rec


def test_observations_and_operations_link_to_trials(tables: Tables) -> None:
    trial = tables["trial"]["TRIAL_GUID"]
    assert tables["observation"]["ATTACHED_TO_FIELD_ENTITY_ID"].isin(trial).all()
    assert tables["operations"]["TRIAL_GUID"].isin(trial).all()


@pytest.mark.parametrize("key", list(FILES))
def test_no_replacement_characters(tables: Tables, key: str) -> None:
    df = tables[key]
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    bad = [c for c in text_cols if df[c].astype(str).str.contains("�").any()]
    assert bad == []


def test_zip_unchanged_by_loading(zip_path: Path) -> None:
    before = _sha256(zip_path)
    load_tables(zip_path)
    assert _sha256(zip_path) == before


def test_duplicate_member_stems_raise(tmp_path: Path) -> None:
    zp = _write_zip(
        tmp_path / "dup.zip",
        {"trial_synthetic.csv": "TRIAL_GUID\na\n", "trial_synthetic 1.csv": "TRIAL_GUID\nb\n"},
    )
    with pytest.raises(ValueError, match="trial_synthetic"):
        load_tables(zp)


def test_missing_member_raises(tmp_path: Path) -> None:
    zp = _write_zip(tmp_path / "empty.zip", {"readme.txt": "x"})
    with pytest.raises(KeyError, match="germplasm_pedigree_synthetic"):
        load_tables(zp)


def test_member_stem_drops_folder_extension_and_copy_suffix() -> None:
    assert member_stem("dir/trial_synthetic 1.csv") == "trial_synthetic"
    assert member_stem("genomics_synthetic.csv") == "genomics_synthetic"


def test_lab_trait_label() -> None:
    assert lab_trait_label("4C47D913-29F1-97EA-0000-000000000042") == "Lab trait ...42"


# --- locating the archive ---------------------------------------------------


def test_env_var_overrides_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "anywhere.zip"
    target.write_bytes(b"")
    monkeypatch.setenv(ZIP_ENV, str(target))
    assert find_zip() == target


def test_env_var_pointing_nowhere_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ZIP_ENV, str(tmp_path / "missing.zip"))
    with pytest.raises(FileNotFoundError, match=ZIP_ENV):
        find_zip()


def test_lookup_walks_up_to_get_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ZIP_ENV, raising=False)
    (tmp_path / "get_started").mkdir()
    target = tmp_path / "get_started" / ZIP_NAME
    target.write_bytes(b"")
    deep = tmp_path / "app" / "src"
    deep.mkdir(parents=True)
    assert find_zip([deep]) == target


def test_lookup_without_archive_raises_naming_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ZIP_ENV, raising=False)
    (tmp_path / "get_started").mkdir()
    with pytest.raises(FileNotFoundError, match=ZIP_ENV):
        find_zip([tmp_path])


def test_newer_archive_alongside_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ZIP_ENV, raising=False)
    folder = tmp_path / "get_started"
    folder.mkdir()
    target = folder / ZIP_NAME
    target.write_bytes(b"")
    (folder / ZIP_NAME.replace(".zip", "_09-30-2026.zip")).write_bytes(b"")
    assert find_zip([tmp_path]) == target
