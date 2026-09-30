"""Task 3: every number in an answer must be in a tool result it cites."""

from typing import Any

from uc4_mcp.bridge import ToolTrace
from uc4_mcp.grounding import Citation, check, numbers_in, quantities, refs_in
from uc4_mcp.models import to_json_safe
from uc4_mcp.store import EvidenceStore

REF = "trial_recommendations_synthetic.csv#620A7637-3BE2-7307-0000-000000000025"


def trace(name: str, result: Any, status: str = "ok") -> ToolTrace:
    return ToolTrace(name, {}, status, {"status": status, "result": result, "message": ""})


SCORE = trace("score_trial", {
    "trial_id": "SYN-TR-0037", "reason": "HOLD: resistant lines 30% < 50% (inferred threshold)",
    "criteria": [{"field": "YIELD_T_HA", "value": 10.79, "threshold": 9.0}],
    "evidence_row_ids": [REF]})
QUERY = trace("query_trials", [{"trial_id": f"SYN-TR-{i:04d}", "verdict": "FAIL"}
                               for i in range(1, 17)])


def test_grounded_answer_passes() -> None:
    g = check(f"SYN-TR-0037 is HOLD: resistant lines 30% < 50% [{REF}].", "Why?", [SCORE])
    assert g.ok and g.citations == (Citation(REF, True),) and g.ungrounded == ()


def test_rounded_value_matches_but_an_integer_must_be_exact() -> None:
    assert check(f"Yield 10.8 t/ha [{REF}].", "", [SCORE]).ok
    assert check(f"Yield 11 t/ha [{REF}].", "", [SCORE]).ungrounded == ("11",)


def test_derived_number_is_ungrounded() -> None:
    g = check(f"It is 20 points short of 50% [{REF}].", "", [SCORE])
    assert not g.ok and g.ungrounded == ("20",)


def test_numbers_need_a_citation() -> None:
    assert check("Resistant lines 30% < 50%.", "", [SCORE]).ungrounded == ("30", "50")


def test_unknown_citation_is_not_found() -> None:
    g = check("See [trial_recommendations_synthetic.csv#NOPE].", "", [SCORE])
    assert g.citations == (Citation("trial_recommendations_synthetic.csv#NOPE", False),)
    assert not g.ok


def test_tool_citation_grounds_counts_from_list_length() -> None:
    assert check("16 trials failed on disease alone [tool:query_trials].", "", [QUERY]).ok


def test_tool_citation_needs_an_ok_result() -> None:
    failed = trace("query_trials", None, status="none")
    g = check("No trials [tool:query_trials].", "", [failed])
    assert g.citations == (Citation("tool:query_trials", False),)


def test_ids_dates_and_rule_names_are_not_quantities() -> None:
    text = f"SYN-TR-0037 and SYN-MZ-00001 on 2026-09-21 12:00 under SYNTH_V1 [{REF}]."
    assert quantities(text) == []
    assert check(text, "", [SCORE]).ok


def test_question_numbers_are_allowed() -> None:
    assert check("None of them is below 50%.", "Which trials are below 50%?", []).ok


def test_citations_are_deduplicated_in_order() -> None:
    g = check(f"A [{REF}]. B [tool:query_trials]. C [{REF}].", "", [SCORE, QUERY])
    assert [c.ref for c in g.citations] == [REF, "tool:query_trials"]


def test_numbers_in_walks_values_strings_and_lengths() -> None:
    assert {30.0, 50.0, 10.79, 9.0, 1.0}.issubset(numbers_in(SCORE.result))
    assert 16.0 in numbers_in(QUERY.result)
    assert 37.0 not in numbers_in(SCORE.result)  # from the ID SYN-TR-0037


def test_real_tool_outputs_carry_refs(store: EvidenceStore) -> None:
    score = to_json_safe(store.score_trial("SYN-TR-0037"))
    ref = score["result"]["evidence_row_ids"][0]
    g = check(f"SYN-TR-0037 is HOLD: resistant lines 30% < 50% (inferred) [{ref}].", "",
              [ToolTrace("score_trial", {"query": "SYN-TR-0037"}, "ok", score)])
    assert g.ok
    view = to_json_safe(store.get_trial("SYN-TR-0037"))
    assert len(refs_in(view)) > 10 and all("#" in r for r in refs_in(view))
