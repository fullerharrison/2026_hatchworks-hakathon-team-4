"""Current UC4 candidate analysis. Reads only the replacement ZIP, without repairs.

Legacy v3 helpers remain in load.py/rules.py for historical regression tests.
Run: python analysis/uc4_eda/uc4_eda.py
"""
from __future__ import annotations

import base64
import hashlib
import html
import re
import zipfile
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

from style import apply_style

HERE = Path(__file__).resolve().parent
ZIP_PATH = HERE.parents[1] / "get_started" / "candidate_recommendations_synthetic.zip"
FILES = {
    "recommendations": ("candidate_recommendations_synthetic", 150),
    "germplasm": ("germplasm_pedigree_synthetic", 152),
    "genomics": ("genomics_synthetic", 152),
    "lab": ("lab_observations_synthetic", 456),
    "observation": ("observation_synthetic", 5184),
    "operations": ("operations_field_updates_synthetic", 360),
    "dictionary": ("trait_dictionary_synthetic", 6),
    "bridge": ("trial_germplasm_bridge_synthetic", 1728),
}
KEYS = {"recommendations": "MATERIAL_GUID", "germplasm": "MATERIAL_GUID",
        "genomics": "MATERIAL_GUID", "lab": "ROWGUID", "observation": "OBSERVATION_UUID",
        "operations": "ID", "dictionary": "TRAIT_GUID", "bridge": "TRIAL_ENTRY_GUID"}
REQUIRED = {
    "recommendations": "MATERIAL_GUID MATERIAL_ID N_TRIALS N_TRIALS_USED YIELD_VS_CHECK_PCT DISEASE_SCORE_MEAN MOISTURE_PCT_MEAN GERMINATION_PCT FUMONISIN_PPM MARKER_DISEASE_RESISTANCE GENOMIC_BREEDING_VALUE SYSTEM_RAG SYSTEM_REASON CAVEATS BREEDER_DECISION BREEDER_COMMENT",
    "germplasm": "MATERIAL_GUID MATERIAL_ID LINE_GUID HIGHNAME",
    "genomics": "MATERIAL_GUID MATERIAL_ID GENOMIC_BREEDING_VALUE MARKER_DISEASE_RESISTANCE QC_STATUS_LID",
    "lab": "ROWGUID MATERIAL_GUID TRAIT_GUID NUMBER_VALUE OBSERVATION_DATE",
    "observation": "OBSERVATION_UUID TRIAL_ENTRY_RELATIONSHIP_GUID ATTACHED_TO_FIELD_ENTITY_ID FIELD_ID GID REPLICATION_NO TRAIT_GUID TRAIT_CODE NUMBER_VALUE",
    "operations": "ID ATTACHED_TO_FIELD_ENTITY_ID OPERATION_TYPE_LID STATUS_LID PLANNED_DATE ACTUAL_DATE DELAY_DAYS SEEDSDL_UPDATE_DATE",
    "dictionary": "TRAIT_GUID TRAIT_CODE TRAIT_NAME SOURCE_TABLE UNIT",
    "bridge": "TRIAL_ENTRY_GUID TRIAL_GUID TRIAL_ID FIELD_ENTITY_ID MATERIAL_GUID MATERIAL_ID LINE_GUID REPLICATION_NO PLOT_NO ENTRY_ROLE_LID",
}


def load_current(path: Path = ZIP_PATH) -> dict[str, pd.DataFrame]:
    """Exact archive selection; reject ambiguous members, missing/duplicate primary keys."""
    tables = {}
    with zipfile.ZipFile(path) as z:
        for key, (stem, expected) in FILES.items():
            names = [n for n in z.namelist() if n.lower().endswith(".csv")
                     and re.sub(r" \d+$", "", Path(n).stem) == stem]
            if len(names) != 1:
                raise ValueError(f"{stem}: expected one member, found {len(names)}")
            name = names[0]
            df = pd.read_csv(z.open(name), encoding="utf-8-sig")
            missing = set(REQUIRED[key].split()) - set(df.columns)
            if missing or len(df) != expected:
                raise ValueError(f"{name}: missing columns {sorted(missing)}; rows {len(df)}, expected {expected}")
            pk = KEYS[key]
            if df[pk].isna().any() or df[pk].duplicated().any():
                raise ValueError(f"{name}: null or duplicate primary key {pk}")
            df["_source_file"] = name
            df["_line_no"] = range(2, len(df) + 2)
            tables[key] = df
    return tables


def audit_links(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    relationships = [
        ("recommendations", "MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
        ("genomics", "MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
        ("lab", "MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
        ("bridge", "MATERIAL_GUID", "germplasm", "MATERIAL_GUID"),
        ("bridge", "LINE_GUID", "germplasm", "LINE_GUID"),
        ("observation", "TRIAL_ENTRY_RELATIONSHIP_GUID", "bridge", "TRIAL_ENTRY_GUID"),
        ("observation", "GID", "germplasm", "MATERIAL_GUID"),
        ("observation", "ATTACHED_TO_FIELD_ENTITY_ID", "bridge", "FIELD_ENTITY_ID"),
        ("observation", "FIELD_ID", "bridge", "TRIAL_GUID"),
        ("operations", "ATTACHED_TO_FIELD_ENTITY_ID", "bridge", "FIELD_ENTITY_ID"),
        ("observation", "TRAIT_GUID", "dictionary", "TRAIT_GUID"),
        ("lab", "TRAIT_GUID", "dictionary", "TRAIT_GUID"),
    ]
    rows = []
    for src, col, dst, target in relationships:
        values = t[src][col].dropna().unique()
        resolved = set(values) & set(t[dst][target].dropna())
        rows.append(dict(source=f"{src}.{col}", target=f"{dst}.{target}",
                         distinct=len(values), resolved=len(resolved),
                         missing_rows=int(t[src][col].isna().sum()),
                         unresolved="; ".join(sorted(set(values) - resolved))))
    return pd.DataFrame(rows)


def consistency(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Cross-check repeated identities and chronology, never silently remap them."""
    rows = []
    def add(check, bad, total):
        rows.append(dict(check=check, violations=int(bad), checked=int(total)))
    germ = t["germplasm"]
    for source in ["recommendations", "genomics", "bridge"]:
        x = t[source].merge(germ[["MATERIAL_GUID", "MATERIAL_ID", "LINE_GUID"]],
                            on="MATERIAL_GUID", how="left", suffixes=("", "_master"),
                            validate="many_to_one")
        add(f"{source}: material GUID agrees with material ID",
            (x.MATERIAL_ID != x.MATERIAL_ID_master).sum(), len(x))
        if source == "bridge":
            add("bridge: material GUID agrees with line GUID",
                (x.LINE_GUID != x.LINE_GUID_master).sum(), len(x))
    b = t["bridge"]
    for source, target in [("TRIAL_GUID", "TRIAL_ID"), ("TRIAL_GUID", "FIELD_ENTITY_ID"),
                           ("FIELD_ENTITY_ID", "TRIAL_GUID")]:
        n = b.groupby(source)[target].nunique()
        add(f"bridge: one {target} per {source}", (n != 1).sum(), len(n))
    x = t["observation"].merge(b, left_on="TRIAL_ENTRY_RELATIONSHIP_GUID",
                               right_on="TRIAL_ENTRY_GUID", suffixes=("_obs", "_bridge"),
                               how="left", validate="many_to_one")
    for a, c in [("GID", "MATERIAL_GUID"), ("FIELD_ID", "TRIAL_GUID"),
                 ("ATTACHED_TO_FIELD_ENTITY_ID", "FIELD_ENTITY_ID"),
                 ("REPLICATION_NO_obs", "REPLICATION_NO_bridge")]:
        add(f"observation: {a} agrees with bridge {c}", (x[a] != x[c]).sum(), len(x))
    x = t["observation"].merge(t["dictionary"][["TRAIT_GUID", "TRAIT_CODE"]],
                               on="TRAIT_GUID", how="left", suffixes=("", "_dict"),
                               validate="many_to_one")
    add("observation: trait GUID agrees with trait code", (x.TRAIT_CODE != x.TRAIT_CODE_dict).sum(), len(x))
    natural = ["TRIAL_ENTRY_RELATIONSHIP_GUID", "TRAIT_GUID"]
    add("observation: unique trait per entry", t["observation"].duplicated(natural).sum(), len(x))
    n = t["observation"].groupby("TRIAL_ENTRY_RELATIONSHIP_GUID").TRAIT_CODE.nunique()
    add("observation: three traits per bridge entry", (n != 3).sum(), len(b))
    add("bridge: unique trial/plot/replication", b.duplicated(["TRIAL_GUID", "PLOT_NO", "REPLICATION_NO"]).sum(), len(b))
    ops = t["operations"]
    planned = pd.to_datetime(ops.PLANNED_DATE)
    actual = pd.to_datetime(ops.ACTUAL_DATE)
    updated = pd.to_datetime(ops.SEEDSDL_UPDATE_DATE)
    delta = (actual - planned).dt.days
    add("operations: supplied delay equals actual minus planned", ((delta != ops.DELAY_DAYS) & actual.notna()).sum(), actual.notna().sum())
    add("operations: update precedes actual date", (updated < actual).sum(), actual.notna().sum())
    add("operations: missed operation has actual date", ((ops.STATUS_LID == "MISSED") & actual.notna()).sum(), (ops.STATUS_LID == "MISSED").sum())
    add("operations: completed/delayed operation lacks actual date", ((ops.STATUS_LID != "MISSED") & actual.isna()).sum(), (ops.STATUS_LID != "MISSED").sum())
    add("operations: completed operation has nonzero delay", ((ops.STATUS_LID == "COMPLETED") & (delta != 0)).sum(), (ops.STATUS_LID == "COMPLETED").sum())
    add("operations: delayed operation lacks positive delay", ((ops.STATUS_LID == "DELAYED") & ~(delta > 0)).sum(), (ops.STATUS_LID == "DELAYED").sum())
    add("lab: unique material/trait", t["lab"].duplicated(["MATERIAL_GUID", "TRAIT_GUID"]).sum(), len(t["lab"]))
    return pd.DataFrame(rows)


def reconstruct(t: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Replicate means, then equal trial means; ratio of mean yields, not mean ratios."""
    b, ops = t["bridge"], t["operations"]
    entries = b[["TRIAL_ENTRY_GUID", "TRIAL_GUID", "TRIAL_ID", "FIELD_ENTITY_ID",
                 "MATERIAL_GUID", "MATERIAL_ID", "ENTRY_ROLE_LID", "REPLICATION_NO",
                 "_source_file", "_line_no"]].rename(
                     columns={"_source_file": "_bridge_source_file", "_line_no": "_bridge_line_no"})
    obs = t["observation"].merge(entries, left_on="TRIAL_ENTRY_RELATIONSHIP_GUID",
                                right_on="TRIAL_ENTRY_GUID", how="left", validate="many_to_one")
    means = obs.pivot_table(index=["TRIAL_GUID", "TRIAL_ID", "MATERIAL_GUID", "MATERIAL_ID", "ENTRY_ROLE_LID"],
                            columns="TRAIT_CODE", values="NUMBER_VALUE", aggfunc="mean").reset_index()
    provenance = obs.groupby(["TRIAL_GUID", "MATERIAL_GUID"]).agg(
        OBSERVATION_SOURCE_FILE=("_source_file", "first"),
        OBSERVATION_SOURCE_LINES=("_line_no", lambda s: ";".join(map(str, sorted(s.unique())))),
        BRIDGE_SOURCE_FILE=("_bridge_source_file", "first"),
        BRIDGE_SOURCE_LINES=("_bridge_line_no", lambda s: ";".join(map(str, sorted(s.unique())))))
    means = means.merge(provenance, on=["TRIAL_GUID", "MATERIAL_GUID"], validate="one_to_one")
    checks = means[means.ENTRY_ROLE_LID == "CHECK"].groupby("TRIAL_GUID").YIELD_T_HA.mean()
    means["CHECK_YIELD_T_HA"] = means.TRIAL_GUID.map(checks)
    means["TRIAL_YIELD_VS_CHECK_PCT"] = 100 * means.YIELD_T_HA / means.CHECK_YIELD_T_HA
    missed = set(ops.loc[(ops.OPERATION_TYPE_LID == "IRRIGATION") & (ops.STATUS_LID == "MISSED"), "ATTACHED_TO_FIELD_ENTITY_ID"])
    excluded = set(b.loc[b.FIELD_ENTITY_ID.isin(missed), "TRIAL_GUID"])
    means["EXCLUDED_IRRIGATION_MISSED"] = means.TRIAL_GUID.isin(excluded)
    candidates = means[means.ENTRY_ROLE_LID == "TRIAL_ENTRY"]
    used = candidates[~candidates.EXCLUDED_IRRIGATION_MISSED]
    counts = candidates.groupby("MATERIAL_GUID").TRIAL_GUID.nunique()
    agg = used.groupby("MATERIAL_GUID").agg(
        REBUILT_N_TRIALS_USED=("TRIAL_GUID", "nunique"),
        YIELD_T_HA=("YIELD_T_HA", "mean"), CHECK_YIELD_T_HA=("CHECK_YIELD_T_HA", "mean"),
        REBUILT_DISEASE_SCORE_MEAN=("DISEASE_SCORE", "mean"),
        REBUILT_MOISTURE_PCT_MEAN=("MOISTURE_PCT", "mean"),
        MEAN_TRIAL_RATIOS=("TRIAL_YIELD_VS_CHECK_PCT", "mean"))
    agg["REBUILT_YIELD_VS_CHECK_PCT"] = 100 * agg.YIELD_T_HA / agg.CHECK_YIELD_T_HA
    agg["REBUILT_N_TRIALS"] = counts
    rec = t["recommendations"].merge(agg, on="MATERIAL_GUID", how="left", validate="one_to_one")
    for col in ["REBUILT_N_TRIALS", "REBUILT_N_TRIALS_USED"]:
        rec[col] = rec[col].fillna(0).astype(int)
    lab = t["lab"].merge(t["dictionary"][["TRAIT_GUID", "TRAIT_CODE", "UNIT"]],
                         on="TRAIT_GUID", validate="many_to_one")
    lab_values = lab.pivot(index="MATERIAL_GUID", columns="TRAIT_CODE", values="NUMBER_VALUE").add_prefix("REBUILT_")
    rec = rec.merge(lab_values, on="MATERIAL_GUID", how="left", validate="one_to_one")
    lab_refs = lab.pivot(index="MATERIAL_GUID", columns="TRAIT_CODE", values="_line_no").add_suffix("_LAB_SOURCE_LINE")
    rec = rec.merge(lab_refs, on="MATERIAL_GUID", how="left", validate="one_to_one")
    rec["LAB_SOURCE_FILE"] = t["lab"]._source_file.iloc[0]
    gen = t["genomics"][["MATERIAL_GUID", "GENOMIC_BREEDING_VALUE", "MARKER_DISEASE_RESISTANCE"]].rename(
        columns={c: f"REBUILT_{c}" for c in ["GENOMIC_BREEDING_VALUE", "MARKER_DISEASE_RESISTANCE"]})
    rec = rec.merge(gen, on="MATERIAL_GUID", how="left", validate="one_to_one")
    gen_refs = t["genomics"][["MATERIAL_GUID", "_source_file", "_line_no"]].rename(
        columns={"_source_file": "GENOMICS_SOURCE_FILE", "_line_no": "GENOMICS_SOURCE_LINE"})
    rec = rec.merge(gen_refs, on="MATERIAL_GUID", how="left", validate="one_to_one")
    rec["REBUILT_EXCLUDED_TRIALS"] = rec.REBUILT_N_TRIALS - rec.REBUILT_N_TRIALS_USED
    rec["SUPPLIED_EXCLUDED_TRIALS"] = rec.CAVEATS.fillna("").str.extract(r"^(\d+) trial\(s\) excluded: irrigation missed")[0].fillna(0).astype(int)
    rows = []
    specs = [("N_TRIALS", 0), ("N_TRIALS_USED", 0), ("YIELD_VS_CHECK_PCT", .05),
             ("DISEASE_SCORE_MEAN", .005), ("MOISTURE_PCT_MEAN", .05),
             ("GERMINATION_PCT", .05), ("FUMONISIN_PPM", .005), ("GENOMIC_BREEDING_VALUE", 0)]
    for col, tolerance in specs:
        available = rec[col].notna() & rec[f"REBUILT_{col}"].notna()
        delta = (rec[col] - rec[f"REBUILT_{col}"]).abs()
        match = available & (delta <= tolerance + 1e-9)
        rec[f"{col}_MATCH"] = match | (rec[col].isna() & rec[f"REBUILT_{col}"].isna())
        rows.append(dict(metric=col, tolerance=tolerance, compared=int(available.sum()),
                         matches=int(match.sum()), both_missing=int((rec[col].isna() & rec[f"REBUILT_{col}"].isna()).sum()),
                         missing_disagreement=int((rec[col].isna() ^ rec[f"REBUILT_{col}"].isna()).sum()), max_abs_delta=delta.max()))
    marker_match = rec.MARKER_DISEASE_RESISTANCE == rec.REBUILT_MARKER_DISEASE_RESISTANCE
    rec["MARKER_MATCH"] = marker_match
    rows.append(dict(metric="MARKER_DISEASE_RESISTANCE", tolerance=0, compared=len(rec), matches=int(marker_match.sum()), both_missing=0, missing_disagreement=0, max_abs_delta=0))
    rec["CAVEAT_MATCH"] = rec.REBUILT_EXCLUDED_TRIALS == rec.SUPPLIED_EXCLUDED_TRIALS
    rows.append(dict(metric="EXCLUDED_TRIAL_CAVEAT", tolerance=0, compared=len(rec), matches=int(rec.CAVEAT_MATCH.sum()), both_missing=0, missing_disagreement=0, max_abs_delta=0))
    return rec, means, pd.DataFrame(rows)


def candidate_rule(rec: pd.DataFrame) -> pd.Series:
    """Outcome-compatible rule. Precedence and complete GREEN conjunction are inferred."""
    red = (rec.YIELD_VS_CHECK_PCT < 95) | (rec.DISEASE_SCORE_MEAN > 6) | (rec.FUMONISIN_PPM > 4)
    green = ((rec.YIELD_VS_CHECK_PCT >= 103) & (rec.DISEASE_SCORE_MEAN <= 4)
             & (rec.MOISTURE_PCT_MEAN <= 23) & (rec.GERMINATION_PCT >= 90)
             & (rec.FUMONISIN_PPM <= 4) & rec.MARKER_DISEASE_RESISTANCE.notna()
             & (rec.MARKER_DISEASE_RESISTANCE != "SUSCEPTIBLE") & (rec.N_TRIALS_USED >= 2))
    result = pd.Series("AMBER", index=rec.index, name="INFERRED_RAG")
    result.loc[green] = "GREEN"
    result.loc[red & (rec.N_TRIALS_USED > 0)] = "RED"
    result.loc[rec.N_TRIALS_USED == 0] = "AMBER"
    return result


def thresholds() -> pd.DataFrame:
    return pd.DataFrame([
        ("Yield vs checks", "RED <95%; GREEN >=103%", "95 and 103 stated in reasons; inequality/precedence inferred"),
        ("Disease", "RED >6; GREEN <=4", "6 and 4 stated in reasons; boundary precision unresolved"),
        ("Moisture", "GREEN <=23%; >23% AMBER, including >25%", "23 and 25 stated; >25 is not a RED knockout in supplied outcomes"),
        ("Germination", "GREEN >=90%; <90% AMBER, including <85%", "90 and 85 stated; <85 is not a RED knockout in supplied outcomes"),
        ("Fumonisin", "RED >4 ppm", "4 stated in reasons; strict inequality inferred"),
        ("Disease marker", "SUSCEPTIBLE prevents GREEN", "Marker warning stated; GREEN gating inferred"),
        ("Usable trials", "0 -> AMBER; GREEN needs >=2", "No-data/one-trial warnings stated; precedence inferred"),
        ("Genomic value / cold test", "No gate needed to reproduce outcomes", "Absence of an observed effect does not prove these are unused in the intended rule"),
    ], columns=["criterion", "compatible_behavior", "evidence_status"])


def reason_precision_audit(rec: pd.DataFrame) -> pd.DataFrame:
    """Check numeric warnings against both displayed and reconstructed precision.

    Reasons round disease to one decimal, while the candidate file uses two.
    Only audit warnings actually present; RED reasons need not list AMBER gates.
    """
    labels = {"yield vs checks": "YIELD_VS_CHECK_PCT", "disease score": "DISEASE_SCORE_MEAN",
              "harvest moisture": "MOISTURE_PCT_MEAN", "germination": "GERMINATION_PCT",
              "fumonisin": "FUMONISIN_PPM"}
    pattern = re.compile(r"(yield vs checks|disease score|harvest moisture|germination|fumonisin) "
                         r"([\d.]+)%? \((above|below) (?:target|limit|minimum) ([\d.]+)%?\)")
    rows = []
    for _, r in rec.iterrows():
        for match in pattern.finditer(r.SYSTEM_REASON):
            label, printed, direction, threshold = match.groups()
            col, threshold = labels[label], float(threshold)
            supplied, rebuilt = r[col], r[f"REBUILT_{col}"]
            def agrees(value):
                return bool(pd.notna(value) and (value > threshold if direction == "above" else value < threshold))
            rows.append(dict(MATERIAL_ID=r.MATERIAL_ID, metric=col, reason_fragment=match.group(),
                             reason_printed_value=float(printed), supplied_value=supplied, rebuilt_value=rebuilt,
                             threshold=threshold, direction=direction,
                             printed_warning_agrees=agrees(float(printed)),
                             supplied_warning_agrees=agrees(supplied), rebuilt_warning_agrees=agrees(rebuilt),
                             _source_file=r._source_file, _line_no=r._line_no))
    return pd.DataFrame(rows)


def distribution_tables(t: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Numeric and categorical profiles, retaining the different measurement grains."""
    numeric, categorical = [], []
    def describe(source, metric, unit, s):
        summary = s.describe()
        numeric.append(dict(source=source, metric=metric, unit=unit,
                            missing=int(s.isna().sum()), **summary.to_dict()))
    rec = t["recommendations"]
    units = {"N_TRIALS": "trials", "N_TRIALS_USED": "trials", "YIELD_VS_CHECK_PCT": "% of checks",
             "DISEASE_SCORE_MEAN": "score", "MOISTURE_PCT_MEAN": "%", "GERMINATION_PCT": "%",
             "FUMONISIN_PPM": "ppm", "GENOMIC_BREEDING_VALUE": "index"}
    for col, unit in units.items():
        describe("candidate summary", col, unit, rec[col])
    dictionary = t["dictionary"].set_index("TRAIT_GUID")
    for source in ["observation", "lab"]:
        for guid, df in t[source].groupby("TRAIT_GUID"):
            if guid in dictionary.index:
                describe(source, dictionary.loc[guid, "TRAIT_CODE"], dictionary.loc[guid, "UNIT"], df.NUMBER_VALUE)
    for col in ["GENOMIC_BREEDING_VALUE", "QC_CALL_RATE_PCT"]:
        describe("genomics", col, "%" if col == "QC_CALL_RATE_PCT" else "index", t["genomics"][col])
    describe("operation updates", "DELAY_DAYS", "days", t["operations"].DELAY_DAYS)
    for source, cols in {"recommendations": ["SYSTEM_RAG", "MARKER_DISEASE_RESISTANCE"],
                         "genomics": ["QC_STATUS_LID", "MARKER_DISEASE_RESISTANCE", "MARKER_DROUGHT_TOLERANCE", "MARKER_YIELD_POTENTIAL"],
                         "operations": ["OPERATION_TYPE_LID", "STATUS_LID", "RECORDED_VIA"],
                         "bridge": ["ENTRY_ROLE_LID"]}.items():
        for col in cols:
            for value, count in t[source][col].fillna("(missing)").value_counts().items():
                categorical.append(dict(source=source, column=col, level=value, count=int(count), share=count/len(t[source])))
    return pd.DataFrame(numeric), pd.DataFrame(categorical)


def create_figures(rec, means, ops, reconciliation, out: Path) -> list[Path]:
    apply_style()
    out.mkdir(exist_ok=True)
    paths = []
    colors = {"GREEN": "#1baf7a", "AMBER": "#eda100", "RED": "#eb6834"}
    def save(fig, name):
        p = out / f"{name}.png"
        fig.savefig(p, dpi=160, bbox_inches="tight")
        plt.close(fig)
        paths.append(p)
    fig, ax = plt.subplots(figsize=(8, 3))
    counts = rec.SYSTEM_RAG.value_counts().reindex(colors, fill_value=0)
    ax.barh(counts.index, counts.values, color=list(colors.values()))
    for i, n in enumerate(counts): ax.text(n + .7, i, str(n), va="center")
    ax.set(title="150 candidate recommendations", xlabel="Candidates", xlim=(0, 75))
    save(fig, "candidate_verdicts")
    fig, axes = plt.subplots(2, 3, figsize=(12, 6))
    for ax, col, boundary in zip(axes.flat, ["YIELD_VS_CHECK_PCT", "DISEASE_SCORE_MEAN", "MOISTURE_PCT_MEAN", "GERMINATION_PCT", "FUMONISIN_PPM", "N_TRIALS_USED"], [95, 6, 23, 90, 4, 2]):
        for label, color in colors.items():
            ax.hist(rec.loc[rec.SYSTEM_RAG == label, col].dropna(), bins=12, alpha=.5, label=label, color=color)
        ax.axvline(boundary, color="#52514e", linestyle="--")
        ax.set_title(col.replace("_", " "))
    axes.flat[0].legend()
    fig.suptitle("Candidate metrics; dashed lines show selected compatible cut-points")
    fig.tight_layout()
    save(fig, "candidate_metrics")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
    rec.N_TRIALS_USED.value_counts().sort_index().plot.bar(ax=axes[0], color="#2a78d6", rot=0)
    axes[0].set(title="Usable trials per candidate", xlabel="Usable trials", ylabel="Candidates")
    ops.groupby(["OPERATION_TYPE_LID", "STATUS_LID"]).size().unstack(fill_value=0).plot.barh(stacked=True, ax=axes[1])
    axes[1].set(title="Recorded operation status", ylabel="", xlabel="Operation updates")
    fig.tight_layout()
    save(fig, "candidate_coverage_operations")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
    for ax, col, rebuilt in [(axes[0], "YIELD_VS_CHECK_PCT", "REBUILT_YIELD_VS_CHECK_PCT"), (axes[1], "YIELD_VS_CHECK_PCT", "MEAN_TRIAL_RATIOS")]:
        x = rec[[col, rebuilt]].dropna()
        ax.scatter(x[col], x[rebuilt] - x[col], s=14, color="#2a78d6")
        ax.axhline(.05, ls="--", color="#eda100"); ax.axhline(-.05, ls="--", color="#eda100")
        ax.set(xlabel="Supplied yield vs checks (%)", ylabel="Rebuilt minus supplied (percentage points)")
    axes[0].set_title("Ratio of mean yields: source-compatible")
    axes[1].set_title("Mean trial ratios: different calculation")
    fig.tight_layout()
    save(fig, "candidate_yield_reconciliation")
    return paths


def report_text(t, rec, means, tables, figures, digest) -> str:
    def table(df): return df.to_html(index=False, escape=True, border=0)
    def figure(p):
        data = base64.b64encode(p.read_bytes()).decode()
        return f'<img alt="{html.escape(p.stem.replace("_", " "))}" src="data:image/png;base64,{data}">'
    samples = pd.concat([rec[rec.SYSTEM_RAG == c].head(1) for c in ["GREEN", "AMBER", "RED"]]
                        + [rec[rec.N_TRIALS_USED == 0].head(1)])
    samples = samples[["MATERIAL_ID", "SYSTEM_RAG", "SYSTEM_REASON", "CAVEATS", "_source_file", "_line_no"]]
    ops = t["operations"]
    rounded_disagree = rec[rec.SOURCE_RAG != rec.SYSTEM_RAG]
    mismatches = rec[rec.INFERRED_RAG != rec.SYSTEM_RAG]
    warnings = tables["reason_precision_audit"]
    precision_cases = warnings[~warnings.printed_warning_agrees | ~warnings.supplied_warning_agrees | ~warnings.rebuilt_warning_agrees]
    excluded = means.loc[means.EXCLUDED_IRRIGATION_MISSED, "TRIAL_GUID"].nunique()
    linked = int((tables["link_rates"].resolved == tables["link_rates"].distinct).sum())
    violations = int(tables["consistency_checks"].violations.sum())
    links = ''.join(f'<li><a href="tables/{name}.csv">{name.replace("_", " ")}</a></li>' for name in tables)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>UC4 replacement candidate analysis</title><style>
body{{font:16px/1.55 system-ui,sans-serif;color:#202820;background:#fcfcfb;max-width:1200px;margin:auto;padding:28px}}
h1,h2{{line-height:1.2}}a{{color:#175a97}}table{{border-collapse:collapse;font-size:13px;display:block;overflow:auto;margin:20px 0;max-height:650px}}
th,td{{padding:8px;border-bottom:1px solid #deded7;text-align:left}}th{{background:#eef1e9;position:sticky;top:0}}img{{max-width:100%;height:auto}}
.brief{{background:#edf4eb;border-left:5px solid #1baf7a;padding:18px}}code{{overflow-wrap:anywhere}}section{{margin:35px 0}}
</style></head><body><h1>UC4: evidence behind candidate recommendations</h1>
<p>Replacement delivery received 1 October 2026; fourth local delivery (source remarks say “integrated V2 (fixed)”). All data are synthetic.</p>
<nav><a href="#overview">Overview</a> · <a href="#sources">Sources and joins</a> · <a href="#reconcile">Reconstruction</a> · <a href="#rules">Scoring audit</a> · <a href="#operations">Operations</a> · <a href="#limits">Limits and questions</a> · <a href="#downloads">Audit tables</a></nav>
<section id="overview"><h2>What changed for the breeder</h2><div class="brief">
<p>The recommendation now belongs to a <strong>candidate line</strong>, rather than a trial. There are 150 recommendations: <strong>32 GREEN, 53 AMBER and 65 RED</strong>. GREEN indicates a candidate meeting the compatible field/lab criteria; AMBER needs review; RED fails a must-pass criterion. These remain system recommendations; all breeder decision/comment fields are blank.</p>
<p>The replacement supplies check varieties, a recorded trial-to-line bridge, named lab traits with units, and field measurements. Yield is compared with checks, replacing the old fixed absolute-yield rule. Two candidates have no field data and remain AMBER. The previous SYNTH_V1 rule and trial examples are historical.</p></div>
{figure(figures[0])}<h3>Examples with source citations</h3>{table(samples)}</section>
<section id="sources"><h2>Eight files, explicit recorded joins</h2>{table(tables['source_manifest'])}
<p>The 152 germplasm/genomics records cover 150 candidates plus two check varieties. The bridge has 1,296 TRIAL_ENTRY rows and 432 CHECK rows across 72 trials: three replicates, with six candidate entries and two checks per trial. Only 148 candidates appear in field trials. Each bridge entry has three trait measurements.</p>
<p>All {linked}/{len(tables['link_rates'])} audited key relationships resolve; {violations} violations across the identity and chronology checks. Membership resolution alone does not prove biological correctness. No positional GUID repairs or old-source metadata are used.</p>
{table(tables['link_rates'])}{table(tables['consistency_checks'])}
<p><strong>No trial master file is supplied.</strong> Trial IDs and GUIDs come from the bridge; field entity IDs are a separate key namespace. Location, trial year/status and exclusion policy are not supplied as trial attributes. Operation dates do not establish a trial's official status.</p></section>
<section id="reconcile"><h2>Do recommendations reproduce from the measurements?</h2>
<p>For each trial/material, average the three replicate observations. For checks, average the two check-variety yields within each trial. Exclude a trial if its recorded irrigation operation is MISSED. Average each candidate's remaining trial means with equal trial weight. Yield vs checks = 100 × mean candidate yield / mean corresponding check yield. Averaging the per-trial ratios gives a different answer.</p>
<p>This ratio-of-means calculation reproduces all 148 available yield comparisons within ±0.05 percentage points. Disease uses ±0.005 score units and moisture ±0.05 percentage points, reflecting the precision of the supplied candidate file. Lab germination and fumonisin join through the trait dictionary; genomic values and markers join directly by material GUID. Missing field values for the two untested lines are retained.</p>
{table(tables['metric_reconciliation'])}{figure(figures[3])}
<p>These methods are <strong>inferred from reproducibility</strong>, not a confirmed analysis protocol. Full unrounded reconstructed values, alternative mean-ratio results, original values and provenance are downloadable below.</p></section>
<section id="distributions"><h2>Trait distributions and completeness</h2>
<p>Summaries retain the source grain: candidate summaries, individual field measurements, material-level lab tests and genomic samples. They include cold-test vigour and genomic QC even though neither needs a gate to reproduce this snapshot's RAG.</p>
{table(tables['numeric_summary'])}{table(tables['categorical_summary'])}</section>
<section id="rules"><h2>Candidate scoring replaces SYNTH_V1</h2>
<p>A compatible rule reproduces {len(rec)-len(mismatches)}/150 supplied RAG values using the rounded candidate summary: RED for yield below 95%, disease above 6, or fumonisin above 4 ppm. Otherwise GREEN requires yield ≥103%, disease ≤4, moisture ≤23%, germination ≥90%, a non-susceptible disease marker and at least two usable trials; otherwise AMBER. No field data yields AMBER.</p>
<p>Supplied reasons state numeric targets/limits. The complete GREEN conjunction, precedence, equality behavior and no-data priority remain inferred. Moisture above 25% and germination below 85% are warnings rather than RED knockouts in the observed outcomes. Genomic breeding value and cold-test vigour require no gate to reproduce this snapshot; this does not establish their intended role.</p>
{table(tables['threshold_evidence'])}{figure(figures[1])}
<h3>Rounding audit</h3><p>Applying the same rule to reconstructed source precision differs from the supplied RAG for {len(rounded_disagree)} candidates. This is audited separately from matching the supplied rounded summary; equality at a displayed threshold can hide an underlying value on the other side.</p>
{table(rounded_disagree[['MATERIAL_ID','SYSTEM_RAG','INFERRED_RAG','SOURCE_RAG','DISEASE_SCORE_MEAN','REBUILT_DISEASE_SCORE_MEAN','MOISTURE_PCT_MEAN','REBUILT_MOISTURE_PCT_MEAN']])}
<p>Warning-level precision is audited separately: {len(precision_cases)} warnings have a printed, summary or reconstructed value that does not satisfy the stated comparison. Reasons can print a disease value of 6.0 as “above 6.0” because the reason uses one decimal while the candidate summary retains two. Such formatting is not a RAG mismatch; use the cited numeric record.</p>
{table(precision_cases)}
<h3>Supplied-summary rule mismatches</h3>{table(mismatches[['MATERIAL_ID','SYSTEM_RAG','INFERRED_RAG','SYSTEM_REASON']])}</section>
<section id="operations"><h2>Operational evidence changes usable coverage</h2>
<p>{excluded} trials have missed irrigation, accounting for the exclusion caveats on 30 candidates. There are 344 COMPLETED, 11 DELAYED and five MISSED operation updates. Delays affect fungicide spray and harvest; excluding these as well is not needed to reconstruct the supplied candidate summary. Record updates are evidence of what was reported, not independent proof that work occurred.</p>
{figure(figures[2])}{table(tables['excluded_trials'])}
<p>Lab dates and operational planned/actual/update dates are available. Plot observation dates, trial start/status/location metadata, pedigree and breeding stage are absent or unfilled; no breeding-cycle improvement can be measured.</p></section>
<section id="limits"><h2>Open questions and app migration impacts</h2><ol>
<li>Confirm the ratio-of-means calculation, equal trial weighting and exclusion of all candidates/check comparisons from a trial with missed irrigation.</li>
<li>Confirm the complete RAG rule, threshold equality and rounding policy, including moisture >25%, germination <85%, and no-field-data precedence.</li>
<li>Confirm whether genomic breeding value or cold-test vigour should affect RAG and whether the missing pedigree/stage/trial metadata is intentional.</li>
<li>Confirm use of the maize-like synthetic data for the vegetable-seed challenge.</li></ol>
<p>The running app remains a <strong>historical v2 demo</strong>. Its trial-scoring tools, PASS/HOLD/FAIL contracts, source loader, evidence joins, trial screen, grounding rules, evaluations and decision storage need a coordinated candidate-level migration. Setting UC4_ZIP to this archive does not migrate those interfaces. Existing decisions must retain the original snapshot and recommendation context. This refresh changes analysis/documentation only.</p>
<p>Earlier analyses are superseded: <a href="v1/report_v1.html">v1</a>, <a href="v2/report_v2.html">v2</a>, <a href="v3/report_v3.html">v3</a>. Previous ZIPs are retained as historical evidence and for the app dependency; none supplies evidence to this report.</p></section>
<section id="downloads"><h2>Reproducibility and downloadable evidence</h2>
<p>Source: <code>{ZIP_PATH.name}</code><br>SHA-256: <code>{digest}</code><br>Regenerate: <code>python analysis/uc4_eda/uc4_eda.py</code> (pandas and matplotlib required). Audit CSVs include source member names and CSV row numbers (header is line 1).</p><ul>{links}</ul>
</section></body></html>'''


def main() -> None:
    t = load_current()
    links, checks = audit_links(t), consistency(t)
    rec, means, reconciliation = reconstruct(t)
    numeric, categorical = distribution_tables(t)
    rec["INFERRED_RAG"] = candidate_rule(rec)
    source = rec.copy()
    for col in ["YIELD_VS_CHECK_PCT", "DISEASE_SCORE_MEAN", "MOISTURE_PCT_MEAN", "GERMINATION_PCT", "FUMONISIN_PPM", "GENOMIC_BREEDING_VALUE", "MARKER_DISEASE_RESISTANCE", "N_TRIALS_USED"]:
        source[col] = rec[f"REBUILT_{col}"]
    rec["SOURCE_RAG"] = candidate_rule(source)
    digest = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    manifest = pd.DataFrame([dict(table=k, member=v._source_file.iloc[0], rows=len(v),
                                   columns=len(v.columns)-2, primary_key=KEYS[k], archive=ZIP_PATH.name,
                                   archive_sha256=digest) for k, v in t.items()])
    excluded = means.loc[means.EXCLUDED_IRRIGATION_MISSED, ["TRIAL_GUID", "TRIAL_ID"]].drop_duplicates()
    op_sources = t["operations"].loc[(t["operations"].OPERATION_TYPE_LID == "IRRIGATION") & (t["operations"].STATUS_LID == "MISSED")]
    trial_map = t["bridge"][["TRIAL_GUID", "FIELD_ENTITY_ID"]].drop_duplicates()
    excluded = excluded.merge(trial_map, on="TRIAL_GUID", validate="one_to_one").merge(
        op_sources, left_on="FIELD_ENTITY_ID", right_on="ATTACHED_TO_FIELD_ENTITY_ID", validate="one_to_one")
    provenance = []
    for k, df in t.items():
        refs = df[[KEYS[k], "_source_file", "_line_no"]].rename(columns={KEYS[k]: "source_key"}).assign(table=k)
        provenance.append(refs)
    tables = {"source_manifest": manifest, "link_rates": links, "consistency_checks": checks,
              "candidate_level": rec, "trial_material_means": means, "metric_reconciliation": reconciliation,
              "threshold_evidence": thresholds(), "excluded_trials": excluded,
              "reason_precision_audit": reason_precision_audit(rec),
              "source_provenance": pd.concat(provenance, ignore_index=True),
              "operation_updates": t["operations"], "trait_dictionary": t["dictionary"],
              "numeric_summary": numeric, "categorical_summary": categorical,
              "column_quality": pd.DataFrame([dict(table=k, column=c, missing=int(df[c].isna().sum()), distinct=int(df[c].nunique()))
                                               for k, df in t.items() for c in df.columns if not c.startswith("_")])}
    # v3 was archived before this generator was activated. Remove stale generated
    # files only in these two resolved output directories; never touch source ZIPs.
    for directory in [HERE / "tables", HERE / "figures"]:
        directory.mkdir(exist_ok=True)
        assert directory.resolve().parent == HERE
        for p in directory.iterdir():
            if p.is_file() and p.suffix in {".csv", ".png"}:
                p.unlink()
    for name, df in tables.items():
        df.to_csv(HERE / "tables" / f"{name}.csv", index=False)
    figures = create_figures(rec, means, t["operations"], reconciliation, HERE / "figures")
    out = HERE / "report.html"
    out.write_text(report_text(t, rec, means, tables, figures, digest), encoding="utf-8")
    print(f"{len(figures)} figures, {len(tables)} tables -> {out}")
    print(f"RAG summary rule matches: {(rec.INFERRED_RAG == rec.SYSTEM_RAG).sum()}/150; source-precision matches: {(rec.SOURCE_RAG == rec.SYSTEM_RAG).sum()}/150")


if __name__ == "__main__":
    main()
