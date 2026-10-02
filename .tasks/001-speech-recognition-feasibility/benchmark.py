"""Task-contained WAV input and provenance for synthetic ASR engineering tests."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import hashlib
from importlib import import_module
import math
from pathlib import Path
import re
import sys
from typing import Any
import wave

from preflight import TASK_ROOT


UPDATE_INTERVALS = (0.5, 1.0, 2.0)


def validate_update_interval(interval: float) -> float:
    """Return an allowlisted SDK interval, rejecting unsupported experiments.

    Args:
        interval: Streaming update floor in seconds for this bounded slice.

    Returns:
        The unchanged interval when it belongs to the approved comparison set.

    Raises:
        ValueError: If the interval is not 0.5, 1.0 or 2.0 seconds.
    """
    if interval not in UPDATE_INTERVALS:
        raise ValueError("Supported comparison intervals are 0.5, 1.0 and 2.0 s")
    return interval


@dataclass(frozen=True)
class Clip:
    """Validated PCM audio, its duration and exact source-file hash."""

    samples: list[float]
    sample_rate: int
    duration_seconds: float
    sha256: str


def contained_path(path: Path) -> Path:
    """Resolve an existing or future path without allowing task escape.

    Args:
        path: Absolute path or path relative to this task directory.

    Returns:
        Resolved task-local path, including symlink resolution.

    Raises:
        ValueError: If the path resolves outside the task.
    """
    root = TASK_ROOT.resolve()
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Benchmark paths must stay within this task")
    return resolved


def load_clip(path: Path) -> Clip:
    """Load a bounded, task-local 16 kHz mono PCM16 WAV without resampling.

    Args:
        path: Synthetic WAV path inside this task; no microphone access.

    Returns:
        Float samples, duration and SHA-256 provenance.

    Raises:
        ValueError: If containment, format or the 30-second size cap fails.
        OSError: If the file cannot be read.
        wave.Error: If the file is not a valid WAV.
    """
    source = contained_path(path)
    if source.stat().st_size > 1_000_000:
        raise ValueError("WAV file exceeds engineering smoke-test size cap")
    with wave.open(str(source), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (
            1, 2, 16_000,
        ) or audio.getcomptype() != "NONE":
            raise ValueError("Expected 16 kHz mono PCM16 WAV")
        frames = audio.getnframes()
        if not 0 < frames <= 30 * 16_000:
            raise ValueError("WAV duration must be greater than zero and <= 30 s")
        data = audio.readframes(frames)
    if len(data) != frames * 2:
        raise ValueError("WAV contains truncated sample data")
    integers = array("h", data)
    if sys.byteorder != "little":
        integers.byteswap()
    return Clip(
        samples=[sample / 32768.0 for sample in integers],
        sample_rate=16_000,
        duration_seconds=frames / 16_000,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )


def score_words(reference: str, hypothesis: str) -> dict[str, int | float | None]:
    """Score raw spoken-reference labels with jiwer, without numeric conversion.

    Args:
        reference: Synthetic spoken text, not canonical numeric slot labels.
        hypothesis: Recognizer output to compare.

    Returns:
        Word edit counts and WER, with None WER for an empty reference.
        Normalization lowercases and removes punctuation/extra whitespace only.

    Raises:
        ImportError: If the pinned research dependencies are not installed.
    """
    jiwer = import_module("jiwer")
    normalize = jiwer.Compose([
        jiwer.ToLowerCase(), jiwer.RemovePunctuation(),
        jiwer.RemoveMultipleSpaces(), jiwer.Strip(),
        jiwer.ReduceToListOfListOfWords(),
    ])
    result = jiwer.process_words(
        reference, hypothesis, reference_transform=normalize,
        hypothesis_transform=normalize,
    )
    words = result.hits + result.substitutions + result.deletions
    return {
        "reference_words": words,
        "substitutions": result.substitutions,
        "deletions": result.deletions,
        "insertions": result.insertions,
        "wer": result.wer if words else None,
    }


def timing_summary(values: list[float]) -> dict[str, int | float | None]:
    """Return nearest-rank timing percentiles with explicit sample counts.

    Args:
        values: Finite nonnegative durations in seconds.

    Returns:
        Count, p50 and p95; percentiles are None for no observations.

    Raises:
        ValueError: If durations are negative or nonfinite.
    """
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("Timings must be finite and nonnegative")
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "p50": None, "p95": None}
    return {
        "count": len(ordered),
        "p50": ordered[math.ceil(0.5 * len(ordered)) - 1],
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def summarize(runs: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    """Aggregate timings while counting first-repetition accuracy only.

    Args:
        runs: Synthetic per-clip results, including explicit failures.
        mode: Whole-utterance or native-streaming measurement name.

    Returns:
        Counts, pooled word errors and timings; failed clips stay visible.
    """
    measured = [run for run in runs if run["mode"] == mode and run["status"] == "ok"]
    speech = [run for run in measured if run["outcome"] != "no_speech"]
    first = [run for run in speech if run["repetition"] == 1]
    words = sum(run["word_score"]["reference_words"] for run in first)
    errors = sum(
        run["word_score"][key] for run in first
        for key in ("substitutions", "deletions", "insertions")
    )
    summary = {
        "successful_runs": len(measured),
        "failed_runs": sum(run["mode"] == mode and run["status"] == "error" for run in runs),
        "first_repetition_speech_clips": len(first),
        "reference_words": words, "word_errors": errors,
        "synthetic_wer": errors / words if words else None,
        "stop_to_final_seconds": timing_summary([
            run["measurement"]["stop_to_final_seconds"] for run in speech
        ]),
        "realtime_factor": timing_summary([
            run["measurement"]["realtime_factor"] for run in speech
        ]),
        "silence_runs": sum(run["outcome"] == "no_speech" for run in measured),
        "nonempty_silence_runs": sum(
            run["outcome"] == "no_speech" and bool(run["measurement"]["text"])
            for run in measured
        ),
    }
    if mode == "native_streaming":
        interim = [interim_timing(run["measurement"]) for run in speech]
        summary["live_interim"] = {
            "speech_runs": len(speech),
            "runs_without_live_partial": sum(not item["partial_count"] for item in interim),
            "first_partial_from_replay_start_seconds": timing_summary([
                item["first_partial_seconds"] for item in interim
                if item["first_partial_seconds"] is not None
            ]),
            "update_gaps_seconds": timing_summary([
                gap for item in interim for gap in item["update_gaps_seconds"]
            ]),
            "maximum_backlog_seconds": timing_summary([
                run["measurement"]["maximum_replay_backlog_seconds"] for run in speech
            ]),
        }
    return summary


def interim_timing(measurement: dict[str, Any]) -> dict[str, Any]:
    """Measure only nonempty partial updates emitted before explicit Stop.

    Args:
        measurement: A native replay result with event and Stop timestamps.

    Returns:
        Live partial count, first replay-relative time and consecutive gaps.
        Historical records without a Stop timestamp are marked unavailable.
    """
    stop = measurement.get("stop_elapsed_seconds")
    if stop is None:
        return {"partial_count": 0, "first_partial_seconds": None,
                "update_gaps_seconds": [], "available": False}
    times = [
        event["elapsed_seconds"] for event in measurement.get("events", [])
        if event["kind"] == "partial" and event["text"].strip()
        and event["elapsed_seconds"] < stop
    ]
    return {
        "partial_count": len(times),
        "first_partial_seconds": times[0] if times else None,
        "update_gaps_seconds": [later - earlier for earlier, later in zip(times, times[1:])],
        "available": True,
    }


def assess_fidelity(text: str, checks: dict[str, list[str]]) -> dict[str, bool]:
    """Check an explicitly authored fixture rubric without altering ASR text.

    Args:
        text: Original recognizer hypothesis, including errors.
        checks: Named diagnostic components and required literal/regex patterns.

    Returns:
        Component pass flags; all declared patterns must match for a pass.
        This is not a general semantic parser or confidence estimate.

    Raises:
        ValueError: If a component lacks meaningful checks.
        re.error: If an authored rubric pattern is invalid.
    """
    if any(not patterns or any(not pattern for pattern in patterns)
           for patterns in checks.values()):
        raise ValueError("Fidelity components must have nonempty checks")
    return {
        component: all(re.search(pattern, text, re.IGNORECASE) is not None
                       for pattern in patterns)
        for component, patterns in checks.items()
    }