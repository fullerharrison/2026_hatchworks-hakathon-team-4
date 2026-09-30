"""Evidence checks for the novice and expert reading paths in the UC4 report."""

import pandas as pd

from lifecycle import chronology_checks, stage_counts
from load import find_zip, load_tables
from report import meeting_briefing


def test_briefing_reports_v2_counts_and_qualifies_inference() -> None:
    sources = load_tables(find_zip())
    tables: dict[str, pd.DataFrame] = {
        "trial_level": sources["recommendations"],
        "chronology_checks": chronology_checks(sources),
    }

    briefing = meeting_briefing(tables, stage_counts(sources))

    assert 'id="overview"' in briefing and 'id="expert"' in briefing
    assert "7 PASS, 35 HOLD or 30 FAIL" in briefing
    assert "SYN-TR-0037 is HOLD" in briefing
    assert "this share does not reconcile to the linked lines" in briefing
    assert "72/72 supplied trial verdicts" in briefing
    assert "62/72" in briefing and "131/216" in briefing
    assert "144/216 operations" in briefing
    assert "inferred from the outcomes" in briefing
    assert "not a verified join" in briefing