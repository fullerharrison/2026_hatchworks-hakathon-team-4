"""Evidence checks for the novice and expert reading paths in the UC4 report."""

import pandas as pd

from lifecycle import chronology_checks, stage_counts
from load import V2_ZIP_NAME, align, find_zip, link_rates, load_tables
from report import meeting_briefing
from rules import decision_by_verdict
from versions import version_diff


def test_briefing_reports_v3_counts_and_qualifies_inference() -> None:
    supplied = load_tables(find_zip())
    sources = align(supplied)
    tables: dict[str, pd.DataFrame] = {
        "trial_level": sources["recommendations"],
        "chronology_checks": chronology_checks(sources),
        "link_rates": link_rates(supplied),
        "version_diff": version_diff(load_tables(find_zip(name=V2_ZIP_NAME)), supplied),
        "decision_by_verdict": decision_by_verdict(sources),
    }

    briefing = meeting_briefing(tables, stage_counts(sources))

    assert 'id="overview"' in briefing and 'id="expert"' in briefing
    assert "7 PASS, 35 HOLD or 30 FAIL" in briefing
    assert "720 plot values" in briefing
    assert "(genomics and recommendations) were resent unchanged" in briefing
    assert "SYN-TR-0037 is HOLD" in briefing
    assert "72/72 supplied trial verdicts" in briefing
    assert "11/14 recorded links resolve fully" in briefing
    assert "genomics lines resolve\n  0/150" in briefing
    assert "354/360 trial × trait pairs" in briefing
    assert "71/72 trials" in briefing
    assert "47/72 trials with a verdict are not COMPLETE" in briefing
    assert "is positional and not a verified join" in briefing
    assert "inferred from the outcomes" in briefing
