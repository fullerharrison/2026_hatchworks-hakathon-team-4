"""``uc4-ask``: the question agent from the terminal, its HTTP server and its evaluation.

    uc4-ask ping                              check the Portkey route supports tool calls
"""

from __future__ import annotations

import argparse
import sys

import anyio

from uc4_mcp.llm import ChatModel, LLMError, PortkeyChat, load_settings, ping


def make_model() -> ChatModel:
    """The configured Portkey model (tests replace this function)."""
    return PortkeyChat(load_settings())


def cmd_ping(args: argparse.Namespace) -> int:
    report = anyio.run(ping, make_model())
    print(report)
    return 0 if "tool_call=yes" in report else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uc4-ask", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ping", help="one tool-call round trip").set_defaults(func=cmd_ping)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run one ``uc4-ask`` command; exit 2 with a readable message if the model is not set up."""
    args = build_parser().parse_args(argv)
    try:
        code = args.func(args)
    except LLMError as e:
        sys.stderr.write(f"{e}\n")
        code = 2
    raise SystemExit(code)
