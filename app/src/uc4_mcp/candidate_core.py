"""Shared candidate reconstruction and provisional policy; no report dependencies."""
from __future__ import annotations
import re
import zipfile
from pathlib import Path
import pandas as pd

ZIP_PATH = Path(__file__).resolve().parents[3] / "get_started" / "candidate_recommendations_synthetic.zip"
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


def load_current(path: Path = ZIP_PATH, *, strict_counts: bool = True) -> dict[str, pd.DataFrame]:
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
            if missing or (strict_counts and len(df) != expected):
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
    means["TRIAL_YIELD_VS_CHECK_PCT"] = 100 * means.YIELD_T_HA / means.CHECK_YIELD_T_HA.where(means.CHECK_YIELD_T_HA > 0)
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
    agg["REBUILT_YIELD_VS_CHECK_PCT"] = 100 * agg.YIELD_T_HA / agg.CHECK_YIELD_T_HA.where(agg.CHECK_YIELD_T_HA > 0)
    agg["REBUILT_N_TRIALS"] = counts
    rec = t["recommendations"].merge(agg, on="MATERIAL_GUID", how="left", validate="one_to_one")
    for col in ["REBUILT_N_TRIALS", "REBUILT_N_TRIALS_USED"]:
        rec[col] = (rec.MATERIAL_GUID.map(counts) if col == "REBUILT_N_TRIALS" else rec[col]).fillna(0).astype(int)
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
             & rec.MARKER_DISEASE_RESISTANCE.isin(["RESISTANT", "INTERMEDIATE"]) & (rec.N_TRIALS_USED >= 2))
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
