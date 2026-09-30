"""Loading, link rates, key alignment and the version diff for the v3 archive."""

import pandas as pd
import pytest

from load import V2_ZIP_NAME, align, find_zip, guid_suffix, link_rates, load_tables
from versions import version_diff

Tables = dict[str, pd.DataFrame]


@pytest.fixture(scope="module")
def v3() -> Tables:
    return load_tables(find_zip())


@pytest.fixture(scope="module")
def v2() -> Tables:
    return load_tables(find_zip(name=V2_ZIP_NAME))


def test_find_zip_names_the_missing_archive(tmp_path) -> None:
    (tmp_path / "get_started").mkdir()
    with pytest.raises(FileNotFoundError, match="nope.zip"):
        find_zip(tmp_path, "nope.zip")


def test_only_genomics_and_recommendation_links_are_broken(v3: Tables) -> None:
    rates = link_rates(v3).set_index("link")
    broken = set(rates.index[rates["share"] < 1])
    assert broken == {"Genomics → line", "Recommendation → trial (GUID)",
                      "Recommendation → trial site"}
    assert rates.loc["Genomics → line", "resolved"] == 0
    assert rates.loc["Recommendation → trial (ID)", "resolved"] == 72


def test_align_repairs_both_namespaces_and_keeps_the_supplied_keys(v3: Tables) -> None:
    a = align(v3)
    assert a["genomics"]["MATERIAL_GUID"].isin(v3["germplasm"]["MATERIAL_GUID"]).all()
    assert a["recommendations"]["TRIAL_GUID"].isin(v3["trial"]["TRIAL_GUID"]).all()
    assert (a["genomics"]["SOURCE_MATERIAL_GUID"] == v3["genomics"]["MATERIAL_GUID"]).all()
    assert "SOURCE_TRIAL_GUID" not in v3["recommendations"]


def test_aligned_genomics_suffix_matches_the_line_number(v3: Tables) -> None:
    # The positional join is at least consistent with the line's own ID number.
    germ = v3["germplasm"]
    number = germ["MATERIAL_ID"].str.extract(r"(\d+)$")[0].astype(int)
    assert (guid_suffix(germ["MATERIAL_GUID"]).apply(int, base=16) == number).all()


def test_version_diff_finds_the_two_resent_files(v2: Tables, v3: Tables) -> None:
    d = version_diff(v2, v3).set_index("file")
    assert set(d.index[d["identical"]]) == {"genomics", "recommendations"}
    assert (d.loc[~d["identical"], "shared_guids"] == 0).all()
    assert d.loc["germplasm", "filled_cols_new"] == 44
    assert "GID" in d.loc["observation", "cols_removed"]
