"""Prepare task-local Moonshine assets or measure offline synthetic WAV replay.

Only --prepare downloads assets. Measurement never selects a microphone, runs
an LLM, executes recognized commands or writes UC4 state.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
import wave

from moonshine_voice import ModelArch, Transcriber, TranscriptEventListener
from moonshine_voice.download import get_model_for_language
from moonshine_voice.moonshine_api import MoonshineError

from benchmark import (
    Clip, UPDATE_INTERVALS, contained_path, load_clip, score_words, summarize,
    validate_update_interval,
)
from preflight import TASK_ROOT, write_inventory


def _artifact_info(path: Path) -> dict[str, str | int]:
    with contained_path(path).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path.relative_to(TASK_ROOT)),
            "bytes": path.stat().st_size, "sha256": digest}


def read_corpus() -> tuple[dict[str, Any], list[tuple[dict[str, Any], Clip]]]:
    """Validate the synthetic manifest and load bounded task-local WAVs.

    Returns:
        Manifest and clip records with validated audio and hashes.

    Raises:
        ValueError: If labels are not the allowlisted synthetic corpus.
        OSError: If a task-local fixture is unavailable.
    """
    path = contained_path(Path("corpus/synthetic.json"))
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["evidence_type"] != "synthetic_engineering_smoke_only":
        raise ValueError("Only the approved synthetic corpus is supported")
    records = []
    identifiers: set[str] = set()
    for label in manifest["clips"]:
        identifier = label["id"]
        if not re.fullmatch(r"(question|filter|preference|value|silence)-\d{2}", identifier):
            raise ValueError("Unsupported synthetic clip identifier")
        if identifier in identifiers:
            raise ValueError("Duplicate synthetic clip identifier")
        identifiers.add(identifier)
        audio_path = contained_path(Path(f"corpus/{identifier}.wav"))
        if label["outcome"] == "no_speech" and not audio_path.exists():
            with wave.Wave_write(str(audio_path)) as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16_000)
                audio.writeframes(b"\x00\x00" * (2 * 16_000))
        records.append((label, load_clip(audio_path)))
    return manifest, records


def prepare() -> dict[str, Any]:
    """Download English tiny-streaming assets only into the task's assets tree.

    Returns:
        Runtime version and exact local artifact hashes and sizes.

    Raises:
        ValueError: If the runtime version or any returned model path mismatches.
        OSError: If asset download or hashing fails.
    """
    if metadata.version("moonshine-voice") != "0.1.5":
        raise ValueError("Expected approved moonshine-voice 0.1.5")
    import truststore

    truststore.inject_into_ssl()
    root = contained_path(Path("assets/moonshine"))
    model_path, architecture = get_model_for_language(
        "en", ModelArch.TINY_STREAMING, cache_root=root,
    )
    model = contained_path(Path(model_path))
    if architecture != ModelArch.TINY_STREAMING or not model.is_relative_to(root):
        raise ValueError("Downloaded model does not match approved configuration")
    artifacts = [
        _artifact_info(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    ]
    return {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_type": "local_asset_preparation_not_accuracy_result",
        "runtime": "moonshine-voice", "version": "0.1.5",
        "language": "en", "architecture": architecture.name,
        "model_path": str(model.relative_to(TASK_ROOT)),
        "artifacts": artifacts,
    }


class TraceListener(TranscriptEventListener):
    """Record synthetic transcript events and errors on a monotonic replay clock."""

    def __init__(self, started: float) -> None:
        self.started = started
        self.events: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def _record(self, kind: str, event: Any) -> None:
        self.events.append({
            "sequence": len(self.events) + 1, "kind": kind,
            "elapsed_seconds": time.perf_counter() - self.started,
            "text": event.line.text,
        })

    def on_line_started(self, event: Any) -> None:
        self._record("started", event)

    def on_line_text_changed(self, event: Any) -> None:
        self._record("partial", event)

    def on_line_completed(self, event: Any) -> None:
        self._record("completed", event)

    def on_error(self, event: Any) -> None:
        self.errors.append(str(event))


async def replay(
    transcriber: Transcriber, clip: Clip, update_interval: float = 0.5,
) -> dict[str, Any]:
    """Feed a bounded WAV at real-time cadence, recording updates and lag.

    Args:
        transcriber: Warmed task-local recognizer.
        clip: Validated PCM clip, not a microphone source.
        update_interval: Allowlisted SDK transcription update floor in seconds.

    Returns:
        Transcript, complete event timeline and monotonic timing measurements.
        Last-sound timing is unmeasured; Stop latency is reported separately.
    """
    stream = transcriber.create_stream(
        update_interval=validate_update_interval(update_interval),
    )
    stream.start()
    started = time.perf_counter()
    listener = TraceListener(started)
    stream.add_listener(listener)
    processing = 0.0
    maximum_lag = 0.0
    try:
        for offset in range(0, len(clip.samples), 1600):
            chunk = clip.samples[offset:offset + 1600]
            due = started + (offset + len(chunk)) / clip.sample_rate
            remaining = due - time.perf_counter()
            if remaining > 0:
                await asyncio.sleep(remaining)
            maximum_lag = max(maximum_lag, time.perf_counter() - due)
            processing_started = time.perf_counter()
            stream.add_audio(chunk, clip.sample_rate)
            processing += time.perf_counter() - processing_started
        stopped = time.perf_counter()
        transcript = stream.stop()
        finished = time.perf_counter()
        if transcript is None or listener.errors:
            raise RuntimeError(f"Stream did not finalize cleanly: {listener.errors}")
        processing += finished - stopped
        return {
            "text": " ".join(line.text for line in transcript.lines).strip(),
            "stop_elapsed_seconds": stopped - started,
            "stop_to_final_seconds": finished - stopped,
            "processing_seconds": processing,
            "realtime_factor": processing / clip.duration_seconds,
            "maximum_replay_backlog_seconds": maximum_lag,
            "replay_wall_seconds": finished - started,
            "events": listener.events,
            "first_nonempty_event_from_replay_start_seconds": next(
                (event["elapsed_seconds"] for event in listener.events if event["text"]),
                None,
            ),
        }
    finally:
        stream.close()


def measure(
    runtime_file: Path, repetitions: int, update_interval: float = 0.5,
) -> dict[str, Any]:
    """Run warmed file baselines and native replay on synthetic fixtures only.

    Args:
        runtime_file: Task-local prepared artifact manifest.
        repetitions: One to three timing repetitions, not independent speakers.
        update_interval: Supported SDK update floor for native-streaming replay.

    Returns:
        Full redacted synthetic evidence, preserving unsuccessful trials.

    Raises:
        ValueError: If runtime configuration or artifact hashes mismatch.
    """
    validate_update_interval(update_interval)
    runtime = json.loads(contained_path(runtime_file).read_text(encoding="utf-8"))
    if runtime["version"] != metadata.version("moonshine-voice"):
        raise ValueError("Installed runtime differs from prepared runtime")
    if runtime["architecture"] != "TINY_STREAMING" or runtime["language"] != "en":
        raise ValueError("Expected approved English tiny-streaming assets")
    for artifact in runtime["artifacts"]:
        with contained_path(Path(artifact["path"])).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != artifact["sha256"]:
                raise ValueError("Prepared model artifact hash mismatch")
    manifest, records = read_corpus()
    loading_started = time.perf_counter()
    transcriber = Transcriber(
        model_path=contained_path(Path(runtime["model_path"])),
        model_arch=ModelArch.TINY_STREAMING,
        options={"identify_speakers": "false"},
    )
    load_seconds = time.perf_counter() - loading_started
    runs: list[dict[str, Any]] = []
    try:
        transcriber.transcribe_without_streaming(records[0][1].samples, 16_000)
        for mode in ("utterance", "native_streaming"):
            for repetition in range(1, repetitions + 1):
                for label, clip in records:
                    run = {"clip_id": label["id"], "outcome": label["outcome"],
                           "reference": label["text"], "expected_slots": label.get("expected_slots", {}),
                           "mode": mode, "repetition": repetition, "audio_sha256": clip.sha256,
                           "duration_seconds": clip.duration_seconds}
                    try:
                        if mode == "native_streaming":
                            result = asyncio.run(replay(transcriber, clip, update_interval))
                        else:
                            started = time.perf_counter()
                            transcript = transcriber.transcribe_without_streaming(clip.samples, 16_000)
                            elapsed = time.perf_counter() - started
                            result = {"text": " ".join(line.text for line in transcript.lines).strip(),
                                      "stop_to_final_seconds": elapsed, "processing_seconds": elapsed,
                                      "realtime_factor": elapsed / clip.duration_seconds}
                        run.update(status="ok", measurement=result,
                                   word_score=score_words(label["text"], result["text"]))
                    except (MoonshineError, OSError, RuntimeError, ValueError) as error:
                        run.update(status="error", error=str(error))
                    runs.append(run)
                    print(f"{mode} {repetition} {label['id']}: {run['status']}", flush=True)
    finally:
        transcriber.close()
    return {
        "schema_version": 1, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_type": manifest["evidence_type"], "runtime": runtime,
        "python": sys.version.split()[0], "os": sys.platform,
        "configuration": {
            "update_interval_seconds": update_interval,
            "ingress_chunk_seconds": 0.1,
            "transcriber_options": {"identify_speakers": "false"},
            "thread_count": "not_exposed_by_inspected_public_option_parser",
        },
        "voice": manifest["voice"], "repetitions": repetitions,
        "model_load_seconds_os_cache_uncontrolled": load_seconds,
        "accuracy_denominator": "first repetition only; one synthetic voice; no held-out speakers",
        "unmeasured": ["word_aligned_lag", "speech_onset_and_last_sound_latency", "peak_ram_vram",
                       "browser_render", "domain_slot_accuracy", "breeder_usability", "five_minute_sustainability"],
        "runs": runs, "summary": {mode: summarize(runs, mode) for mode in ("utterance", "native_streaming")},
        "actions_submitted": 0,
    }


def main() -> int:
    """Run approved preparation or offline measurement; return two on failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--runtime", type=Path, default=Path("results/moonshine-runtime.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--update-interval", type=float, choices=UPDATE_INTERVALS, default=0.5)
    args = parser.parse_args()
    target = contained_path(args.output)
    if not target.is_relative_to((TASK_ROOT / "results").resolve()) or target.exists():
        parser.error("Choose a new output file under this task's results directory")
    try:
        result = prepare() if args.prepare else measure(
            args.runtime, args.repetitions, args.update_interval,
        )
        write_inventory(result, target)
    except (MoonshineError, OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"Research run failed: {error}\n")
    print(f"Evidence saved: {target.relative_to(TASK_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())