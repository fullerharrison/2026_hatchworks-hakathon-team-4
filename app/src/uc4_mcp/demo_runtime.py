"""Loopback-only, explicitly isolated runtime for browser checks and rehearsals."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import socket
import threading
import time
from urllib.request import ProxyHandler, build_opener

import uvicorn

from uc4_mcp.candidate_api import create_candidate_app
from uc4_mcp.candidate_history import CandidateHistory
from uc4_mcp.llm import LLMError


def no_model():
    raise LLMError("Model is not configured for this test")


@dataclass(frozen=True)
class DemoRuntime:
    url: str
    history: CandidateHistory
    startup_seconds: float


@contextmanager
def candidate_demo_server(storage: Path, model_factory=no_model, archive: Path | None = None):
    """Own the bound socket and server thread; never use the active DB/log defaults."""
    started = time.monotonic()
    storage = Path(storage)
    history = CandidateHistory(path=storage / "history.sqlite3", archive=archive,
                               legacy_log=storage / "legacy.jsonl")
    app = create_candidate_app(model_factory, get_history=lambda: history)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", log_level="warning",
                                         timeout_graceful_shutdown=5))
    failures = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}/"

        def serve():
            try:
                server.run(sockets=[listener])
            except BaseException as exc:
                failures.append(exc)

        worker = threading.Thread(target=serve, name="uc4-demo-server", daemon=True)
        worker.start()
        # Ignore proxy configuration only for this loopback readiness request.
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 30
        last_error = None
        try:
            while time.monotonic() < deadline:
                if failures or not worker.is_alive():
                    raise RuntimeError(f"Demo server exited before readiness: {failures!r}")
                try:
                    with opener.open(url + "health", timeout=1) as response:
                        health = json.load(response)
                    if health.get("status") == "ok" and health.get("snapshot_id") == history.snapshot_id:
                        break
                except (OSError, ValueError) as exc:
                    last_error = exc
                time.sleep(.05)
            else:
                raise RuntimeError(f"Demo server HTTP readiness failed: {last_error}")
            yield DemoRuntime(url, history, round(time.monotonic() - started, 3))
        finally:
            server.should_exit = True
            worker.join(10)
            if worker.is_alive():
                server.force_exit = True
                worker.join(5)
            if worker.is_alive():
                raise RuntimeError("Isolated demo server did not stop")
