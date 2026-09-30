"""``uc4-ask``: the question agent from the terminal, its HTTP server and its evaluation.

    uc4-ask ask "Why is SYN-TR-0037 amber?" [--json]
    uc4-ask chat                              follow-up questions keep the conversation
    uc4-ask serve [--host 127.0.0.1] [--port 8766]   POST /ask, GET /health
    uc4-ask eval [--cases PATH] [--out DIR]   run the supported questions
    uc4-ask ping                           check the Portkey route supports tool calls
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import anyio
import uvicorn
from anyio import to_thread
from mcp.server.mcpserver import MCPServer

from uc4_mcp.agent import AGENT_LOG, Answer, ask, load_agent_settings
from uc4_mcp.api import create_app
from uc4_mcp.bridge import open_bridge
from uc4_mcp.evals import (CASES_PATH, RESULTS_DIR, CaseResult, load_cases, report,
                           result_stem, run_cases)
from uc4_mcp.llm import ChatModel, LLMError, PortkeyChat, load_settings, ping
from uc4_mcp.models import to_json_safe
from uc4_mcp.server import configure_logging

MAX_HISTORY = 10  # messages kept in chat (5 questions and answers)
server: MCPServer | None = None  # None: the uc4 server over the zip; tests set their own


def make_model() -> ChatModel:
    """The configured Portkey model (tests replace this function)."""
    return PortkeyChat(load_settings())


def quiet_sdk_logging() -> None:
    """The MCP SDK logs rejected tool calls at INFO to the console; the agent logs them."""
    for name in ("mcp", "openai", "httpx2", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)


def configure_cli_logging() -> None:
    configure_logging()  # tool calls -> app/logs/uc4_mcp.log, as for MCP clients
    configure_logging(AGENT_LOG, name="uc4_agent")
    quiet_sdk_logging()


def render(answer: Answer) -> str:
    """Answer text with citations numbered [1], [2]…, a Sources list and the disclaimer."""
    text = answer.text
    for i, c in enumerate(answer.citations, 1):
        text = text.replace(f"[{c.ref}]", f"[{i}]")
    lines = [text]
    if answer.citations:
        lines += ["", "Sources:"]
        lines += [f"  [{i}] {c.ref}" + ("" if c.found else "  (not in the tool results)")
                  for i, c in enumerate(answer.citations, 1)]
    if answer.status == "unverified":
        lines += ["", "Warning: " + "; ".join(answer.problems)]
    return "\n".join([*lines, "", answer.disclaimer])


async def _ask(question: str, history: list[dict[str, str]], model: ChatModel) -> Answer:
    async with open_bridge(server) as bridge:
        return await ask(question, model=model, bridge=bridge, history=history,
                         settings=load_agent_settings())


def _exit_code(answer: Answer) -> int:
    return 0 if answer.status in ("answered", "clarify") else 1


def cmd_ask(args: argparse.Namespace) -> int:
    answer = anyio.run(_ask, args.question, [], make_model())
    print(json.dumps(to_json_safe(answer), indent=2) if args.json else render(answer))
    return _exit_code(answer)


async def _chat(model: ChatModel) -> None:
    history: list[dict[str, Any]] = []
    async with open_bridge(server) as bridge:
        while True:
            try:
                question = (await to_thread.run_sync(input, "uc4> ")).strip()
            except EOFError:
                return
            if question.lower() in ("", "quit", "exit"):
                return
            answer = await ask(question, model=model, bridge=bridge, history=history,
                               settings=load_agent_settings())
            print(render(answer), end="\n\n")
            history += [{"role": "user", "content": question},
                        {"role": "assistant", "content": answer.text}]
            del history[:-MAX_HISTORY]


def cmd_chat(args: argparse.Namespace) -> int:
    anyio.run(_chat, make_model())
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    uvicorn.run(create_app(make_model, server, load_agent_settings()),
                host=args.host, port=args.port, log_level="warning")
    return 0


async def _eval(cases_path: Path, model: ChatModel) -> list[CaseResult]:
    async with open_bridge(server) as bridge:
        return await run_cases(load_cases(cases_path), model, bridge, load_agent_settings())


def cmd_eval(args: argparse.Namespace) -> int:
    model = make_model()
    results = anyio.run(_eval, args.cases, model)
    today = date.today()
    name = result_stem(model.model, today)
    md, js = args.out / f"{name}.md", args.out / f"{name}.json"
    args.out.mkdir(parents=True, exist_ok=True)
    md.write_text(report(results, model.model, today), encoding="utf-8")
    js.write_text(json.dumps(to_json_safe(results), indent=2), encoding="utf-8")
    passed = sum(r.passed for r in results)
    print(f"passed {passed} of {len(results)}; report {md}")
    return 0 if passed == len(results) else 1


def cmd_ping(args: argparse.Namespace) -> int:
    report = anyio.run(ping, make_model())
    print(report)
    return 0 if "tool_call=yes" in report else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uc4-ask", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ask", help="answer one question")
    p.add_argument("question")
    p.add_argument("--json", action="store_true", help="print the full Answer as JSON")
    p.set_defaults(func=cmd_ask)
    sub.add_parser("chat", help="interactive; empty line or EOF quits"
                   ).set_defaults(func=cmd_chat)
    p = sub.add_parser("serve", help="HTTP API: POST /ask, GET /health")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    p.set_defaults(func=cmd_serve)
    p = sub.add_parser("eval", help="run the supported questions against the model")
    p.add_argument("--cases", type=Path, default=CASES_PATH)
    p.add_argument("--out", type=Path, default=RESULTS_DIR)
    p.set_defaults(func=cmd_eval)
    sub.add_parser("ping", help="one tool-call round trip").set_defaults(func=cmd_ping)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run one ``uc4-ask`` command; exit 2 with a readable message if the model is not set up."""
    args = build_parser().parse_args(argv)
    configure_cli_logging()
    try:
        code = args.func(args)
    except LLMError as e:
        sys.stderr.write(f"{e}\n")
        code = 2
    except KeyboardInterrupt:
        code = 130
    raise SystemExit(code)
