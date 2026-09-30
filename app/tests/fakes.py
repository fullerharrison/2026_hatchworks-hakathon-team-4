"""Scripted stand-ins for the model, and a helper that runs ``ask`` over the session store."""

import copy
import itertools
from collections.abc import Sequence
from typing import Any

import anyio

from uc4_mcp.agent import AgentSettings, Answer, ask
from uc4_mcp.bridge import open_bridge
from uc4_mcp.llm import Completion, ToolRequest, Usage
from uc4_mcp.server import create_server
from uc4_mcp.store import EvidenceStore

REF_0037 = "trial_recommendations_synthetic.csv#620A7637-3BE2-7307-0000-000000000025"
_ids = itertools.count(1)


def call(name: str, **arguments: Any) -> Completion:
    """A completion that asks for one tool call."""
    return Completion(None, (ToolRequest(f"call_{next(_ids)}", name, arguments),), Usage(10, 5))


def say(text: str) -> Completion:
    """A completion with a final answer."""
    return Completion(text, (), Usage(10, 5))


class FakeChat:
    """Returns the scripted completions in order; an Exception entry is raised instead."""

    model = "fake-model"

    def __init__(self, script: Sequence[Completion | Exception]) -> None:
        self.script = list(script)
        self.seen: list[list[dict[str, Any]]] = []
        self.tools: list[list[dict[str, Any]]] = []

    async def complete(self, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]]) -> Completion:
        self.seen.append(copy.deepcopy(messages))
        self.tools.append(tools)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def run_ask(store: EvidenceStore, chat: FakeChat, question: str,
            history: Sequence[dict[str, str]] = (),
            settings: AgentSettings = AgentSettings()) -> Answer:
    async def main() -> Answer:
        async with open_bridge(create_server(lambda: store)) as bridge:
            return await ask(question, model=chat, bridge=bridge, history=history,
                             settings=settings)
    return anyio.run(main)
