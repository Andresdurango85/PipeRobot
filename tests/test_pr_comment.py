from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from reports.pr_comment import (
    COMMENT_MARKER,
    MAX_FAILED_LISTED,
    FailedEpisode,
    main,
    render_comment,
)
from stats.gate import SuccessCount, decide

GOLDEN_DIR = Path(__file__).parent / "golden"
RUN_URL = "https://github.com/Andresdurango85/PipeRobot/actions/runs/1"
COMMIT = "d70f397abcdef0123456789"


def _failed(count: int) -> list[FailedEpisode]:
    # Reverse order on purpose: the comment must sort them by seed.
    return [
        FailedEpisode(
            seed=seed,
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
    episode = FailedEpisode(seed=1, scene="rack | dim\nlight", failure=None, video_url=None)

    comment = render_comment(decide(SuccessCount(49, 50), SuccessCount(45, 50)), [episode])

    assert "| 1 | rack \\| dim light | — | — |" in comment


def test_more_failed_episodes_than_failures_is_an_error() -> None:
    with pytest.raises(ValueError, match="only failed 1"):
        render_comment(decide(SuccessCount(49, 50), SuccessCount(45, 50)), _failed(2))


def test_failed_episode_requires_seed() -> None:
    with pytest.raises(ValueError, match="seed"):
        FailedEpisode.from_dict({"scene": "rack_0"})


def test_explanation_uses_configured_tolerance() -> None:
    result = decide(SuccessCount(45, 50), SuccessCount(45, 50), tolerance=0.15)

    assert "dropped more than 15 pp" in render_comment(result)


def test_full_block_comment_matches_golden_file() -> None:
    # Review the golden file like a snapshot. Regenerate with: UPDATE_GOLDEN=1 uv run pytest
    result = decide(SuccessCount(25, 50), SuccessCount(45, 50))
    comment = render_comment(result, _failed(12), run_url=RUN_URL, commit=COMMIT)
    golden = GOLDEN_DIR / "pr_comment_block.md"

    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(exist_ok=True)
        golden.write_text(comment, encoding="utf-8", newline="\n")
    assert comment == golden.read_text(encoding="utf-8")


def test_main_writes_comment_and_succeeds_even_on_block(tmp_path: Path) -> None:
    failed_json = tmp_path / "failed.json"
    failed_json.write_text(json.dumps([{"seed": 7, "failure": "timeout"}]), encoding="utf-8")
    output = tmp_path / "comment.md"

    exit_code = main(
        [
            "--candidate", "25/50",
            "--baseline", "45/50",
            "--failed-episodes", str(failed_json),
            "--output", str(output),
        ]
    )  # fmt: skip

    assert exit_code == 0
    comment = output.read_text(encoding="utf-8")
    assert "## ❌ PipeRobot gate: BLOCK" in comment
    assert "| 7 | — | timeout | — |" in comment
