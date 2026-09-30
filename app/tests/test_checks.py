"""Step 5: consistency flags. Counts come from the EDA's chronology_checks.csv where it
has a row, and are hard-coded (re-measured on the v2 zip) where it does not."""

import ast
import json
from collections.abc import Callable, Mapping
from pathlib import Path

import pandas as pd
import pytest
from test_lifecycle import EDA_TABLES, synthetic_tables

import uc4_mcp.rules
from uc4_mcp import checks
from uc4_mcp.checks import FLAG_CODES, FlagIndex, all_flags
from uc4_mcp.models import SEVERITIES, Flag, parse_evidence_ref, to_json_safe

Tables = dict[str, pd.DataFrame]
FlagMap = Mapping[str, tuple[Flag, ...]]
GUID = "620A7637-3BE2-7307-0000-{:012X}"  # trial n (hex suffix)
OP = "372ED14B-F396-F334-0000-{:012X}"  # operation n (hex suffix)


@pytest.fixture(scope="module")
def index(tables: Tables) -> FlagIndex:
    return all_flags(tables)


@pytest.fixture(scope="module")
def eda() -> pd.DataFrame:
    return pd.read_csv(EDA_TABLES / "chronology_checks.csv", keep_default_na=False
                       ).set_index("rule")


def keys_with(flags: FlagMap, code: str) -> set[str]:
    return {k for k, fs in flags.items() if any(f.code == code for f in fs)}


def every_flag(index: FlagIndex) -> list[Flag]:
    return [f for scope in (index.by_trial, index.by_operation, index.by_line)
            for fs in scope.values() for f in fs]


# --- counts against the evidence record ---------------------------------------


@pytest.mark.parametrize("code, rule, example", [
    ("OPS_OUTSIDE_TRIAL_YEAR", "Operation dated outside its trial's start year", "SYN-TR-0002"),
    ("COMPLETE_TRIAL_HAS_PLANNED_OPS", "Completed trial still has planned operations",
     "SYN-TR-0001"),
    ("PLANNED_OPS_PAST_EXTRACT", "Planned operation dated before the extract", OP.format(3)),
    ("OP_LINE_NOT_IN_TRIAL", "Operation's trial + material not linked in observations",
     OP.format(1)),
    ("RATIONALE_READS_AS_PASS", "Rationale reports all four criteria met, yet not PASS",
     "SYN-TR-0037"),
])
def test_flag_counts_equal_the_eda_violations(index: FlagIndex, tables: Tables,
                                              eda: pd.DataFrame, code: str, rule: str,
                                              example: str) -> None:
    scope = {"trial": index.by_trial, "operation": index.by_operation}[FLAG_CODES[code].scope]
    keys = keys_with(scope, code)
    assert len(keys) == eda.loc[rule, "violations"]
    assert eda.loc[rule, "example"] == example
    if example.startswith("SYN-TR-"):  # the EDA names trials by ID; flags key on GUIDs
        guid = GUID.format(int(example[-4:]))
        ops = tables["operations"]
        keys = keys | set(ops.loc[ops["OPERATION_GUID"].isin(list(keys)), "TRIAL_GUID"])
        assert guid in keys
    else:
        assert example in keys


def test_rationale_flag_is_exactly_the_four_trials(index: FlagIndex) -> None:
    got = keys_with(index.by_trial, "RATIONALE_READS_AS_PASS")
    assert got == {GUID.format(n) for n in (37, 38, 46, 52)}


def test_every_trial_has_inferred_thresholds(index: FlagIndex) -> None:
    assert len(keys_with(index.by_trial, "THRESHOLDS_INFERRED")) == 72


def test_aggregate_flag_counts_gbv_and_resistant_mismatches(index: FlagIndex,
                                                            eda: pd.DataFrame) -> None:
    flags = [f for fs in index.by_trial.values() for f in fs
             if f.code == "AGGREGATE_LINKS_UNVERIFIED"]
    gbv, res = zip(*(f.message.split("; resistant % ") for f in flags))
    assert len(flags) == 72
    assert sum("≠" in m for m in gbv) == 72
    assert sum("≠" in m for m in res) == 62
    assert eda.loc["Trial GBV mean differs from its observation-linked materials",
                   "violations"] == 72
    assert eda.loc["Trial resistant % differs from its observation-linked materials",
                   "violations"] == 62


def test_aggregate_flag_cites_recommendation_observations_and_genomics(
        index: FlagIndex) -> None:
    flags = [f for fs in index.by_trial.values() for f in fs
             if f.code == "AGGREGATE_LINKS_UNVERIFIED"]
    for f in flags:
        files = [parse_evidence_ref(r)[0] for r in f.evidence_row_ids]
        assert len(files) == 21
        assert files[0] == "trial_recommendations_synthetic.csv"
        assert files.count("observation_synthetic 1.csv") == 10
        assert files.count("genomics_synthetic.csv") == 10


def test_aggregate_message_example(index: FlagIndex) -> None:
    (f,) = [f for f in index.by_trial[GUID.format(37)] if f.code == "AGGREGATE_LINKS_UNVERIFIED"]
    assert f.message.startswith("Supplied GBV mean ")
    assert "over the 10 observation-linked lines; resistant % " in f.message


def test_operation_flag_spread(index: FlagIndex, tables: Tables) -> None:
    ops = tables["operations"].set_index("OPERATION_GUID")
    trials = lambda code: set(ops.loc[list(keys_with(index.by_operation, code)), "TRIAL_GUID"])
    assert len(trials("OPS_OUTSIDE_TRIAL_YEAR")) == 48
    assert len(trials("PLANNED_OPS_PAST_EXTRACT")) == 60
    assert len(trials("OP_LINE_NOT_IN_TRIAL")) == 72
    unlinked = list(keys_with(index.by_operation, "OP_LINE_NOT_IN_TRIAL"))
    assert ops.loc[unlinked, "MATERIAL_GUID"].nunique() == 96


def test_outside_year_covers_all_three_ops_of_its_trials(index: FlagIndex,
                                                          tables: Tables) -> None:
    ops = tables["operations"]
    flagged = ops[ops["OPERATION_GUID"].isin(list(keys_with(index.by_operation,
                                                       "OPS_OUTSIDE_TRIAL_YEAR")))]
    assert bool(flagged.groupby("TRIAL_GUID").size().eq(3).all())


def test_every_line_has_lab_rows_without_a_trial_key(index: FlagIndex,
                                                     tables: Tables) -> None:
    keys = keys_with(index.by_line, "LAB_NOT_TRIAL_LINKED")
    assert len(keys) == 150
    lab = tables["lab"].groupby("MATERIAL_GUID").size()
    for guid in keys:
        (f,) = index.by_line[guid]
        assert len(f.evidence_row_ids) == lab[guid] and lab[guid] in (2, 3)


def test_message_examples(index: FlagIndex) -> None:
    (f,) = [f for f in index.by_operation[OP.format(1)] if f.code == "OPS_OUTSIDE_TRIAL_YEAR"]
    assert f.message == "PLANTING on 2026-09-21 is outside trial start year 2025"
    (f,) = [f for f in index.by_trial[GUID.format(1)]
            if f.code == "COMPLETE_TRIAL_HAS_PLANNED_OPS"]
    assert f.message.startswith("Trial is COMPLETE but ")
    assert f.message.endswith(" still PLANNED")


# --- denominators ---------------------------------------------------------------


def test_denominators(tables: Tables) -> None:
    assert (tables["trial"]["STATUS_LID"] == "COMPLETE").sum() == 72
    assert tables["lab"]["MATERIAL_GUID"].nunique() == len(tables["germplasm"]) == 150


# --- not checkable -> no flag (synthetic tables) --------------------------------


def _set(table: str, row: int, **values: object) -> Callable[[Tables], None]:
    def mutate(t: Tables) -> None:
        df = t[table].astype({c: float if isinstance(v, float) else object
                              for c, v in values.items()})
        for col, v in values.items():
            df.loc[df.index[row], col] = v
        t[table] = df
    return mutate


def _drop(table: str, row: int) -> Callable[[Tables], None]:
    def mutate(t: Tables) -> None:
        t[table] = t[table].drop(t[table].index[row])
    return mutate


def _drop_lab(t: Tables) -> None:
    t["lab"] = t["lab"].iloc[0:0]


@pytest.mark.parametrize("code, key, mutate", [
    ("OPS_OUTSIDE_TRIAL_YEAR", "P3", _set("trial", 1, START_YEAR=float("nan"))),
    ("PLANNED_OPS_PAST_EXTRACT", "P2", _set("operations", 1, OPERATION_DATE=None)),
    ("OP_LINE_NOT_IN_TRIAL", "P2", _set("operations", 1, MATERIAL_GUID=None)),
    ("AGGREGATE_LINKS_UNVERIFIED", "T2", _drop("observation", 1)),
    ("AGGREGATE_LINKS_UNVERIFIED", "T2",
     _set("recommendations", 1, GENOMIC_BREEDING_VALUE_MEAN=float("nan"))),
    ("RATIONALE_READS_AS_PASS", "T1", _set("recommendations", 0, RECOMMENDATION_RATIONALE=None)),
    ("LAB_NOT_TRIAL_LINKED", "M1", _drop_lab),
    ("COMPLETE_TRIAL_HAS_PLANNED_OPS", "T1", _set("trial", 0, STATUS_LID="ACTIVE")),
], ids=["no-start-year", "no-op-date", "no-op-line", "no-obs-links", "no-supplied-gbv",
        "no-rationale", "no-lab-rows", "not-complete"])
def test_missing_side_gives_no_flag(code: str, key: str,
                                    mutate: Callable[[Tables], None]) -> None:
    scope = {"trial": "by_trial", "operation": "by_operation", "line": "by_line"}
    attr = scope[FLAG_CODES[code].scope]
    t = synthetic_tables()
    assert key in keys_with(getattr(all_flags(t), attr), code)  # flagged when checkable
    mutate(t)
    assert key not in keys_with(getattr(all_flags(t), attr), code)


def test_synthetic_line_without_lab_rows_has_no_lab_flag() -> None:
    assert keys_with(all_flags(synthetic_tables()).by_line, "LAB_NOT_TRIAL_LINKED") == {"M1"}


# --- output -----------------------------------------------------------------------


def test_catalogue_matches_the_flag_functions() -> None:
    assert list(FLAG_CODES) == [
        "THRESHOLDS_INFERRED", "AGGREGATE_LINKS_UNVERIFIED", "RATIONALE_READS_AS_PASS",
        "OPS_OUTSIDE_TRIAL_YEAR", "PLANNED_OPS_PAST_EXTRACT", "COMPLETE_TRIAL_HAS_PLANNED_OPS",
        "OP_LINE_NOT_IN_TRIAL", "LAB_NOT_TRIAL_LINKED"]
    for code, spec in FLAG_CODES.items():
        assert spec.scope in ("trial", "operation", "line")
        assert spec.severity in SEVERITIES and spec.meaning
        assert callable(getattr(checks, code.lower()))


def test_flags_sit_in_their_scope(index: FlagIndex) -> None:
    for attr, scope in [("by_trial", "trial"), ("by_operation", "operation"),
                        ("by_line", "line")]:
        for fs in getattr(index, attr).values():
            assert fs and all(FLAG_CODES[f.code].scope == scope for f in fs)


def test_every_flag_is_json_safe_and_well_formed(index: FlagIndex, tables: Tables) -> None:
    files = {df["_source_file"].iloc[0] for df in tables.values()}
    for f in every_flag(index):
        json.dumps(to_json_safe(f), allow_nan=False)
        assert "np." not in f.message and "nan" not in f.message.lower()
        assert f.severity == FLAG_CODES[f.code].severity and f.severity in SEVERITIES
        assert f.evidence_row_ids
        for ref in f.evidence_row_ids:
            assert parse_evidence_ref(ref)[0] in files


def test_order_is_catalogue_then_deterministic(index: FlagIndex, tables: Tables) -> None:
    rank = {c: i for i, c in enumerate(FLAG_CODES)}
    for scope in (index.by_trial, index.by_operation, index.by_line):
        assert list(scope) == sorted(scope)
        for fs in scope.values():
            assert [rank[f.code] for f in fs] == sorted(rank[f.code] for f in fs)
    again = all_flags(tables)
    assert again == index
    assert [list(s.items()) for s in (again.by_trial, again.by_operation, again.by_line)] == \
           [list(s.items()) for s in (index.by_trial, index.by_operation, index.by_line)]


def test_flag_index_is_frozen(index: FlagIndex) -> None:
    with pytest.raises(AttributeError):
        index.by_trial = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        index.by_trial["x"] = ()  # type: ignore[index]


def test_rules_does_not_import_checks() -> None:
    tree = ast.parse(Path(uc4_mcp.rules.__file__).read_text(encoding="utf-8"))
    names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    names += [f"{n.module}.{a.name}" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
              for a in n.names]
    assert not [n for n in names if "checks" in n]
