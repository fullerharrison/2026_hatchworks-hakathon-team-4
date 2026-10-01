"""The question set against the real model (spends tokens): pytest -m live app/tests."""

import os

import anyio
import pytest

from uc4_mcp.agent import load_agent_settings
from uc4_mcp.bridge import open_bridge
from uc4_mcp.evals import CaseResult, load_cases, run_cases
from uc4_mcp.llm import PortkeyChat, load_settings
from uc4_mcp.candidate_server import create_candidate_server

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(not os.environ.get("PORTKEY_API_KEY"),
                                 reason="PORTKEY_API_KEY not set")]


def test_every_supported_question_passes() -> None:
    async def main() -> list[CaseResult]:
        async with open_bridge(create_candidate_server()) as bridge:
            return await run_cases(load_cases(), PortkeyChat(load_settings()), bridge,
                                   load_agent_settings())
    failed = {r.case_id: r.failures for r in anyio.run(main) if not r.passed}
    assert not failed, failed
