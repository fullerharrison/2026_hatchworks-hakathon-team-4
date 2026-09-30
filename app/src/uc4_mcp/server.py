"""MCP server for the UC4 evidence layer: 8 read-only tools and 2 resources over EvidenceStore.

Tools are thin wrappers: each calls one store method and returns its envelope through
``to_json_safe``. Descriptions are the Phase 2 agent's instructions. Never print to stdout:
it carries the stdio protocol; logging goes to ``app/logs/uc4_mcp.log``.
"""

from __future__ import annotations

import argparse
import functools
import json
import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from uc4_mcp.models import to_json_safe
from uc4_mcp.store import MISSED_FIELDS, QUERY_FLAGS, EvidenceStore

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "uc4_mcp.log"
logger = logging.getLogger("uc4_mcp")
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True)

LIST_SOURCES = (
    "List the seven v2 source files (grain: one entry per file): zip member, row count, row "
    "key, grain (what one row is), a synthetic-data marker and what each file lacks, plus the "
    "date the extract was taken. All data is synthetic hackathon mock data. "
    "Example: list_sources()")
FIND_TRIAL = (
    "Find a trial by TRIAL_ID, GUID or ID fragment (case-insensitive). Returns status ok with "
    "{id, guid, label}, many with up to 20 candidates (ask the user which one; never guess), "
    "or none. Verdicts are per trial. Example: find_trial(query=\"SYN-TR-0037\") or "
    "find_trial(query=\"0037\")")
FIND_LINE = (
    "Find a breeding line (material) by MATERIAL_ID, GUID or ID fragment (case-insensitive). "
    "Returns status ok with {id, guid, label}, many with up to 20 candidates (ask the user "
    "which one; never guess), or none. Example: find_line(query=\"SYN-MZ-00001\")")
GET_TRIAL = (
    "Everything the files say about one trial (grain: per trial): start year, status and "
    "location; trial-level values with units (yield t/ha, moisture %, disease score, plant "
    "height cm, flowering days, GBV mean, resistant lines %, genomics QC pass %); the "
    "SYNTH_V1 (inferred) verdict with each criterion; the 10 lines the observation file links "
    "to it, each with its GBV and disease-resistance marker; the supplied GBV mean and "
    "resistant % beside those recomputed over the linked lines; its 3 operations by date; "
    "and consistency flags. Every value cites source_file and row_id. Ambiguous input returns "
    "candidates. Example: get_trial(query=\"SYN-TR-0037\")")
GET_LINE = (
    "Everything the files say about one breeding line: identity, genomics (GBV, 4 markers, "
    "QC), lab results (traits are unnamed and the lab file has no trial key), the 4-5 trials "
    "it appears in with each trial's verdict, its operations and flags. Note: verdicts are "
    "per trial; a line has no verdict of its own and the trial verdicts are not combined. "
    "Every value cites source_file and row_id. Example: get_line(query=\"SYN-MZ-00001\")")
SCORE_TRIAL = (
    "Score one trial with SYNTH_V1 (inferred): verdict PASS/HOLD/FAIL (per trial), a colour "
    "proposal, each of the 7 criteria with value, threshold and the bracket the data allows, "
    "triggered knockouts, a one-line reason, the supplied verdict and rationale, what the "
    "rationale omits, and trial-scope flags. Thresholds are inferred from the supplied "
    "verdicts, not a supplied Syngenta rule; flags never change the verdict. "
    "Example: score_trial(query=\"SYN-TR-0001\")")
QUERY_TRIALS = (
    "List trials (per trial: trial_id, verdict, reason) matching every given filter (AND), "
    "sorted by trial_id. verdict: PASS, HOLD or FAIL (SYNTH_V1 (inferred), equal to the "
    "supplied verdicts). knockout: yield, disease or both (FAIL knockouts triggered). "
    f"missed: a PASS criterion the trial does not meet, one of {', '.join(MISSED_FIELDS)}. "
    "only: with missed, it is the sole unmet PASS criterion; with knockout, no other knockout "
    f"triggered. flag: one of {', '.join(QUERY_FLAGS)}; an operation flag counts its trial "
    "once. LAB_NOT_TRIAL_LINKED is a line flag and is not accepted here. No match gives status "
    "ok with an empty list; an unknown value gives status none listing the valid values. "
    "Example: query_trials(knockout=\"disease\", only=true)")
BASELINE_CHECK = (
    "Re-score all 72 trials with SYNTH_V1 (inferred) and compare with the supplied verdicts "
    "(per trial): {checked, matched, mismatches}; expect 72, 72 and none. "
    "Example: baseline_check()")


def _call(name: str, args: dict[str, Any], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run one store call, log it, and return its envelope as plain JSON types."""
    try:
        envelope = to_json_safe(fn())
    except Exception:
        logger.exception("%s %s failed", name, json.dumps(args))
        raise
    logger.info("%s %s -> %s", name, json.dumps(args), envelope["status"])
    return envelope


def _json(obj: Any) -> str:
    return json.dumps(to_json_safe(obj), allow_nan=False)


def create_server(get_store: Callable[[], EvidenceStore]) -> MCPServer:
    """Build the MCP server over a store supplier (called on each request, so it may be lazy).

    Args:
        get_store: Returns the ``EvidenceStore``; tests pass their session store.

    Returns:
        An ``MCPServer`` with the 8 tools and 2 resources.
    """
    server = MCPServer("uc4-mcp")

    @server.tool(description=LIST_SOURCES, annotations=READ_ONLY)
    def list_sources() -> dict[str, Any]:
        return _call("list_sources", {}, lambda: get_store().list_sources())

    @server.tool(description=FIND_TRIAL, annotations=READ_ONLY)
    def find_trial(query: str) -> dict[str, Any]:
        return _call("find_trial", {"query": query}, lambda: get_store().find_trial(query))

    @server.tool(description=FIND_LINE, annotations=READ_ONLY)
    def find_line(query: str) -> dict[str, Any]:
        return _call("find_line", {"query": query}, lambda: get_store().find_line(query))

    @server.tool(description=GET_TRIAL, annotations=READ_ONLY)
    def get_trial(query: str) -> dict[str, Any]:
        return _call("get_trial", {"query": query}, lambda: get_store().get_trial(query))

    @server.tool(description=GET_LINE, annotations=READ_ONLY)
    def get_line(query: str) -> dict[str, Any]:
        return _call("get_line", {"query": query}, lambda: get_store().get_line(query))

    @server.tool(description=SCORE_TRIAL, annotations=READ_ONLY)
    def score_trial(query: str) -> dict[str, Any]:
        return _call("score_trial", {"query": query}, lambda: get_store().score_trial(query))

    @server.tool(description=QUERY_TRIALS, annotations=READ_ONLY)
    def query_trials(verdict: str | None = None, knockout: str | None = None,
                     missed: str | None = None, only: bool = False,
                     flag: str | None = None) -> dict[str, Any]:
        args = {k: v for k, v in [("verdict", verdict), ("knockout", knockout),
                                  ("missed", missed), ("only", only), ("flag", flag)]
                if v not in (None, False)}
        return _call("query_trials", args, lambda: get_store().query_trials(
            verdict=verdict, knockout=knockout, missed=missed, only=only, flag=flag))

    @server.tool(description=BASELINE_CHECK, annotations=READ_ONLY)
    def baseline_check() -> dict[str, Any]:
        return _call("baseline_check", {}, lambda: get_store().baseline_check())

    @server.resource("uc4://sources", name="sources", mime_type="application/json",
                     description="The seven source files and the extract date (as list_sources).")
    def sources_resource() -> str:
        return _json(get_store().list_sources()["result"])

    @server.resource("uc4://rule/SYNTH_V1", name="rule-SYNTH_V1", mime_type="application/json",
                     description="SYNTH_V1 (inferred): criteria, thresholds, brackets, flag codes.")
    def rule_resource() -> str:
        return _json(get_store().rule())

    return server


@functools.cache
def _default_store() -> EvidenceStore:
    return EvidenceStore.from_zip()


server = create_server(_default_store)


def configure_logging(path: Path = LOG_PATH) -> logging.Handler:
    """Send the ``uc4_mcp`` logger to a file (never stdout); returns the handler added."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return handler


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """``--transport stdio`` (default) or ``http`` with ``--host`` and ``--port``."""
    parser = argparse.ArgumentParser(prog="uc4-mcp", description=__doc__)
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1",
                        help="HTTP only; 0.0.0.0 for clients in Docker (no authentication)")
    parser.add_argument("--port", type=int, default=8765, help="HTTP only; serves /mcp")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the server, loading the zip first so a missing archive fails at once."""
    args = parse_args(argv)
    configure_logging()
    try:
        _default_store()
    except FileNotFoundError as e:
        logger.error("Cannot start: %s", e)
        sys.stderr.write(f"{e}\n")
        raise SystemExit(1) from e
    logger.info("uc4-mcp starting over %s", args.transport)
    if args.transport == "http":
        server.run("streamable-http", host=args.host, port=args.port)
    else:
        server.run("stdio")
