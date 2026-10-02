"""Behavioral tests for bounded synthetic-file ASR input."""

from __future__ import annotations

import json
from pathlib import Path
import wave

import pytest

import benchmark


@pytest.fixture(name="task_root")
def fixture_task_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "task"
    root.mkdir()
    monkeypatch.setattr(benchmark, "TASK_ROOT", root)
    return root


def make_wav(path: Path, *, sample_rate: int = 16_000, channels: int = 1) -> Path:
    """Generate a silent PCM16 fixture without microphone or playback access."""
    with wave.Wave_write(str(path)) as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * channels * sample_rate)
    return path


def test_outside_audio_path_is_rejected(task_root: Path) -> None:
    with pytest.raises(ValueError, match="within this task"):
        benchmark.load_clip(task_root.parent / "outside.wav")


def test_traversal_cannot_escape_task(task_root: Path) -> None:
    with pytest.raises(ValueError, match="within this task"):
        benchmark.contained_path(Path("../outside.wav"))

    assert not (task_root.parent / "outside.wav").exists()


def test_valid_silence_has_duration_and_hash(task_root: Path) -> None:
    clip = benchmark.load_clip(make_wav(task_root / "silence.wav"))

    assert clip.duration_seconds == 1.0
    assert clip.sample_rate == 16_000
    assert len(clip.samples) == 16_000
    assert set(clip.samples) == {0.0}
    assert len(clip.sha256) == 64


def test_wrong_sample_rate_requires_explicit_pipeline(task_root: Path) -> None:
    path = make_wav(task_root / "device-format.wav", sample_rate=48_000)

    with pytest.raises(ValueError, match="16 kHz mono PCM16"):
        benchmark.load_clip(path)


def test_stereo_is_not_silently_flattened(task_root: Path) -> None:
    path = make_wav(task_root / "stereo.wav", channels=2)

    with pytest.raises(ValueError, match="16 kHz mono PCM16"):
        benchmark.load_clip(path)


def test_empty_audio_is_rejected(task_root: Path) -> None:
    path = task_root / "empty.wav"
    with wave.Wave_write(str(path)) as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)

    with pytest.raises(ValueError, match="greater than zero"):
        benchmark.load_clip(path)


def test_numeric_rendering_is_not_silently_normalized() -> None:
    result = benchmark.score_words("seventeen trials", "seventy trials")

    assert result["substitutions"] == 1
    assert result["reference_words"] == 2
    assert result["wer"] == 0.5


def test_silence_hallucination_has_insertions_not_zero_wer() -> None:
    result = benchmark.score_words("", "Thank you")

    assert result["insertions"] == 2
    assert result["reference_words"] == 0
    assert result["wer"] is None


def test_nearest_rank_p95_is_explicit_for_small_samples() -> None:
    assert benchmark.timing_summary([0.1, 0.4, 0.2]) == {
        "count": 3, "p50": 0.2, "p95": 0.4,
    }


def test_missing_timing_is_unavailable_not_zero() -> None:
    assert benchmark.timing_summary([]) == {"count": 0, "p50": None, "p95": None}


@pytest.mark.parametrize("duration", [-1.0, float("nan"), float("inf")])
def test_invalid_timings_cannot_be_reported(duration: float) -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        benchmark.timing_summary([duration])


def test_repetitions_do_not_inflate_accuracy_denominator() -> None:
    first = {
        "mode": "utterance", "status": "ok", "outcome": "question",
        "repetition": 1,
        "word_score": {"reference_words": 2, "substitutions": 1,
                       "deletions": 0, "insertions": 0},
        "measurement": {"text": "seventy trials", "stop_to_final_seconds": 0.4,
                        "realtime_factor": 0.2},
    }
    second = {**first, "repetition": 2}
    failure = {"mode": "utterance", "status": "error"}

    result = benchmark.summarize([first, second, failure], "utterance")

    assert result["reference_words"] == 2
    assert result["word_errors"] == 1
    assert result["synthetic_wer"] == 0.5
    assert result["successful_runs"] == 2
    assert result["failed_runs"] == 1
    assert result["stop_to_final_seconds"] == {"count": 2, "p50": 0.4, "p95": 0.4}


@pytest.mark.parametrize("interval", [0.5, 1.0, 2.0])
def test_documented_update_floor_is_allowlisted(interval: float) -> None:
    assert benchmark.validate_update_interval(interval) == interval


@pytest.mark.parametrize("interval", [0.0, 0.25, -1.0, float("nan")])
def test_unapproved_interval_cannot_enter_comparison(interval: float) -> None:
    with pytest.raises(ValueError, match="Supported comparison intervals"):
        benchmark.validate_update_interval(interval)


def test_final_flush_partials_are_not_live_cadence() -> None:
    result = benchmark.interim_timing({
        "stop_elapsed_seconds": 3.0,
        "events": [
            {"kind": "started", "text": "show", "elapsed_seconds": 0.7},
            {"kind": "partial", "text": "show", "elapsed_seconds": 0.7},
            {"kind": "partial", "text": "show seventeen", "elapsed_seconds": 1.8},
            {"kind": "partial", "text": "not seventy", "elapsed_seconds": 3.2},
            {"kind": "completed", "text": "not seventy", "elapsed_seconds": 3.3},
        ],
    })

    assert result["partial_count"] == 2
    assert result["first_partial_seconds"] == 0.7
    assert result["update_gaps_seconds"] == [1.1]


def test_historical_trace_without_stop_is_unavailable() -> None:
    assert benchmark.interim_timing({"events": []}) == {
        "partial_count": 0, "first_partial_seconds": None,
        "update_gaps_seconds": [], "available": False,
    }


@pytest.fixture(name="fidelity_rubric")
def fixture_fidelity_rubric() -> dict[str, dict[str, list[str]]]:
    path = Path(__file__).parent / "corpus" / "fidelity-rubric.json"
    return json.loads(path.read_text(encoding="utf-8"))["clips"]


def test_digit_rendering_can_pass_fidelity_without_rewriting_transcript(
    fidelity_rubric: dict[str, dict[str, list[str]]],
) -> None:
    hypothesis = "Enter cold test 87.5 percent"

    result = benchmark.assess_fidelity(hypothesis, fidelity_rubric["value-01"])

    assert result == {"numeric": True, "unit": True, "domain_term": True}
    assert hypothesis == "Enter cold test 87.5 percent"
    assert benchmark.score_words("Enter cold test eighty seven point five percent", hypothesis)["wer"] == 0.5


def test_fumonisin_error_remains_a_domain_failure_with_correct_value_and_unit(
    fidelity_rubric: dict[str, dict[str, list[str]]],
) -> None:
    result = benchmark.assess_fidelity(
        "Enter few minutes and 0.8 ppm.", fidelity_rubric["value-02"],
    )

    assert result == {"numeric": True, "unit": True, "domain_term": False}


def test_changed_rejected_value_fails_numeric_and_negation_checks(
    fidelity_rubric: dict[str, dict[str, list[str]]],
) -> None:
    result = benchmark.assess_fidelity(
        "Show at least seventeen trials. Not seventeen.", fidelity_rubric["filter-03"],
    )

    assert result == {"numeric": False, "unit": True, "domain_term": True, "negation": False}


def test_reversed_negation_does_not_pass_just_because_both_numbers_exist(
    fidelity_rubric: dict[str, dict[str, list[str]]],
) -> None:
    result = benchmark.assess_fidelity(
        "Show at least seventy trials, not seventeen.", fidelity_rubric["filter-03"],
    )

    assert result["numeric"] is True
    assert result["negation"] is False


def test_correct_negation_passes_declared_digit_equivalence(
    fidelity_rubric: dict[str, dict[str, list[str]]],
) -> None:
    result = benchmark.assess_fidelity(
        "Show at least 17 trials, not 70.", fidelity_rubric["filter-03"],
    )

    assert result == {"numeric": True, "unit": True, "domain_term": True, "negation": True}


def test_numeric_substring_does_not_match_a_wrong_decimal(
    fidelity_rubric: dict[str, dict[str, list[str]]],
) -> None:
    result = benchmark.assess_fidelity("Enter fumonisin 0.88 ppm.", fidelity_rubric["value-02"])

    assert result["numeric"] is False


def test_missing_diagnostic_patterns_are_not_vacuously_passing() -> None:
    with pytest.raises(ValueError, match="nonempty"):
        benchmark.assess_fidelity("anything", {"numeric": []})


def test_corrected_value_does_not_match_decimal_continuation(
    fidelity_rubric: dict[str, dict[str, list[str]]],
) -> None:
    result = benchmark.assess_fidelity("Change 85 to 90.5 percent.", fidelity_rubric["value-03"])

    assert result["numeric"] is False


def test_negated_decimal_is_not_accepted_as_the_reference_integer(
    fidelity_rubric: dict[str, dict[str, list[str]]],
) -> None:
    result = benchmark.assess_fidelity("Show at least 17 trials, not 70.5.", fidelity_rubric["filter-03"])

    assert result["negation"] is False


def test_failed_first_trial_remains_in_fidelity_denominator() -> None:
    from compare_moonshine import fidelity_for_result

    result = fidelity_for_result({"runs": [
        {"mode": "utterance", "repetition": 1, "outcome": "value_entry",
         "clip_id": "value-01", "reference": "eighty seven point five", "status": "error"},
        {"mode": "utterance", "repetition": 2, "outcome": "value_entry",
         "clip_id": "value-01", "reference": "eighty seven point five", "status": "ok",
         "measurement": {"text": "87.5"}},
    ]}, {"clips": {"value-01": {"numeric": ["87\\.5"]}}})

    assert result["utterance"]["components"]["numeric"] == {"passed": 0, "total": 1}
    assert result["utterance"]["cases"][0]["hypothesis"] is None


def test_missing_fidelity_rubric_is_a_blocker_not_a_silent_skip() -> None:
    from compare_moonshine import fidelity_for_result

    with pytest.raises(ValueError, match="Missing fidelity rubric"):
        fidelity_for_result({"runs": [
            {"mode": "utterance", "repetition": 1, "outcome": "question",
             "clip_id": "unknown", "status": "error"},
        ]}, {"clips": {}})