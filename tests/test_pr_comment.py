from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest

from piperobot.reports.pr_comment import COMMENT_MARKER, MAX_FAILED_LISTED, main, render_comment
from piperobot.results import EpisodeResult
from piperobot.stats.gate import SuccessCount, decide

GOLDEN_DIR = Path(__file__).parent / "golden"
RUN_URL = "https://github.com/Andresdurango85/PipeRobot/actions/runs/1"
COMMIT = "d70f397abcdef0123456789"


def _failed(count: int) -> list[EpisodeResult]:
    # Reverse order on purpose: the comment must sort them by seed.
    return [
        EpisodeResult(
            seed=seed,
            success=False,
            scene=f"rack_{seed % 3}",
            failure="tube dropped",
            video_url=f"https://example.org/episode_{seed}.mp4",
        )
        for seed in reversed(range(count))
    ]


def test_comment_starts_with_marker_for_sticky_updates() -> None:
    comment = render_comment(decide(SuccessCount(45, 50), SuccessCount(45, 50)))

    assert comment.splitlines()[0] == COMMENT_MARKER


@pytest.mark.parametrize(
    ("candidate", "heading"),
    [
        (SuccessCount(45, 50), "## ✅ PipeRobot gate: PASS"),
        (SuccessCount(38, 50), "## ⚠️ PipeRobot gate: WARN"),
        (SuccessCount(25, 50), "## ❌ PipeRobot gate: BLOCK"),
    ],
)
def test_heading_shows_verdict(candidate: SuccessCount, heading: str) -> None:
    comment = render_comment(decide(candidate, SuccessCount(45, 50)))

    assert heading in comment.splitlines()


def test_results_table_shows_counts_rates_and_short_commit() -> None:
    comment = render_comment(decide(SuccessCount(38, 50), SuccessCount(45, 50)), commit=COMMIT)

    assert "| Candidate (`d70f397`) | 38/50 | 76.0% |" in comment
    assert "| Baseline | 45/50 | 90.0% |" in comment
    assert "**-14.0 pp**" in comment


def test_failed_episodes_are_sorted_and_capped() -> None:
    result = decide(SuccessCount(25, 50), SuccessCount(45, 50))

    comment = render_comment(result, _failed(25), run_url=RUN_URL)
    rows = [line for line in comment.splitlines() if "[▶ video]" in line]

    assert "### Failed episodes (25)" in comment
    assert len(rows) == MAX_FAILED_LISTED
    assert rows[0].startswith("| 0 |")
    assert rows[-1].startswith("| 9 |")
    assert f"_…and 15 more in the [workflow run]({RUN_URL})._" in comment


def test_no_failed_section_when_every_episode_passed() -> None:
    comment = render_comment(decide(SuccessCount(50, 50), SuccessCount(45, 50)))

    assert "Failed episodes" not in comment


def test_failed_section_without_details() -> None:
    comment = render_comment(decide(SuccessCount(40, 50), SuccessCount(45, 50)))

    assert "### Failed episodes (10)" in comment
    assert "_No per-episode details were provided._" in comment


def test_table_cells_are_escaped() -> None:
    episode = EpisodeResult(seed=1, success=False, scene="rack | dim\nlight")

    comment = render_comment(decide(SuccessCount(49, 50), SuccessCount(45, 50)), [episode])

    assert "| 1 | rack \\| dim light | — | — |" in comment


def test_more_failed_episodes_than_failures_is_an_error() -> None:
    with pytest.raises(ValueError, match="only failed 1"):
        render_comment(decide(SuccessCount(49, 50), SuccessCount(45, 50)), _failed(2))


def test_explanation_uses_configured_tolerance() -> None:
    result = decide(SuccessCount(45, 50), SuccessCount(45, 50), tolerance=0.15)

    assert "dropped more than 15 pp" in render_comment(result)


def test_explanation_preserves_fractional_tolerance() -> None:
    result = decide(SuccessCount(45, 50), SuccessCount(45, 50), tolerance=0.125)

    assert "dropped more than 12.5 pp" in render_comment(result)


def test_comment_preserves_fractional_confidence() -> None:
    result = decide(SuccessCount(45, 50), SuccessCount(45, 50), confidence=0.975)

    comment = render_comment(result)

    assert "| 97.5% CI |" in comment
    assert "The 97.5% interval" in comment


def test_full_block_comment_matches_golden_file() -> None:
    # Review the golden file like a snapshot. Regenerate with: UPDATE_GOLDEN=1 uv run pytest
    result = decide(SuccessCount(25, 50), SuccessCount(45, 50))
    comment = render_comment(result, _failed(12), run_url=RUN_URL, commit=COMMIT)
    golden = GOLDEN_DIR / "pr_comment_block.md"

    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(exist_ok=True)
        golden.write_text(comment, encoding="utf-8", newline="\n")
    assert comment == golden.read_text(encoding="utf-8")


def test_main_renders_from_results_file_and_succeeds_even_on_block(tmp_path: Path) -> None:
    episodes = [{"seed": 7, "success": False, "failure": "timeout"}]
    episodes += [{"seed": seed, "success": seed % 2 == 0} for seed in range(8, 57)]
    results = tmp_path / "results.json"
    results.write_text(json.dumps({"policy": "p", "episodes": episodes}), encoding="utf-8")
    output = tmp_path / "out" / "comment.md"

    exit_code = main(["--results", str(results), "--baseline", "45/50", "--output", str(output)])

    assert exit_code == 0
    comment = output.read_text(encoding="utf-8")
    assert "## ❌ PipeRobot gate: BLOCK" in comment
    assert "| 7 | — | timeout | — |" in comment


def test_main_returns_2_on_invalid_results(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text('{"episodes": []}', encoding="utf-8")

    assert main(["--results", str(results), "--baseline", "45/50"]) == 2


def test_main_stdout_is_utf8_on_cp1252_console(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = tmp_path / "results.json"
    results.write_text(
        json.dumps({"policy": "p", "episodes": [{"seed": 1, "success": False}]}),
        encoding="utf-8",
    )
    output = tmp_path / "comment.md"
    args = ["--results", str(results), "--baseline", "15/20"]
    assert main([*args, "--output", str(output)]) == 0
    buffer = io.BytesIO()
    stdout = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stdout)

    assert main(args) == 0

    comment = buffer.getvalue().decode("utf-8")
    assert comment == output.read_text(encoding="utf-8")
    assert "⚠️" in comment


def test_main_stdout_without_buffer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text(
        json.dumps({"policy": "p", "episodes": [{"seed": 1, "success": True}]}),
        encoding="utf-8",
    )
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    assert main(["--results", str(results), "--baseline", "15/20"]) == 0

    assert stdout.getvalue() == render_comment(decide(SuccessCount(1, 1), SuccessCount(15, 20)))


def test_metric_golden_and_escaping() -> None:
    from piperobot.results import MetricSpec
    from piperobot.stats.metric import MetricSummary

    result = decide(SuccessCount(1, 2), SuccessCount(1, 2))
    summary = MetricSummary(2, 2, 2.8, 1)
    spec = MetricSpec("distance", "cm", 2, "below")
    comment = render_comment(result, metric_summary=summary, metric_spec=spec)
    assert comment == (GOLDEN_DIR / "pr_comment_metric.md").read_text(encoding="utf-8")
    assert "### Metric" in render_comment(result, metric_summary=summary)
    empty_unit = render_comment(
        result, metric_summary=summary, metric_spec=MetricSpec("distance", "", 20, "above")
    )
    assert "### distance\n" in empty_unit
    assert "Success when distance is above 20." in empty_unit
    assert "Warning" not in empty_unit
    escaped = render_comment(
        result, metric_summary=summary, metric_spec=MetricSpec("x|y\nheading", "m|s", 2, "below")
    )
    assert "### x\\|y heading (m\\|s)" in escaped


def test_metric_from_results_cli(tmp_path: Path) -> None:
    from piperobot.results import EpisodeResult, EvalResults, MetricSpec, save_results

    path, output = tmp_path / "results.json", tmp_path / "comment.md"
    save_results(
        EvalResults(
            "p",
            "e",
            (EpisodeResult(0, True, metric=1.5),),
            MetricSpec("distance", "cm", 1.5, "below"),
        ),
        path,
    )
    assert main(["--results", str(path), "--baseline", "1/1", "--output", str(output)]) == 0
    text = output.read_text(encoding="utf-8")
    assert "| Candidate | 1.5 | 1.5 | 0 |" in text
    assert "Success when distance is below 1.5 cm." in text
    assert "Warning" in text
