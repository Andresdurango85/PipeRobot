"""Daily seed planning and workflow input validation."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from piperobot.seeds import main, rotating_first_seed


def test_known_ranges() -> None:
    assert rotating_first_seed(date(2026, 1, 1), 500) == 100000
    assert rotating_first_seed(date(2026, 11, 3), 500) == 100000 + 500 * 306
    assert rotating_first_seed(date(2026, 1, 2), 7, base=20) == 27


@pytest.mark.parametrize("episodes", [1, 50, 500, 1000])
def test_consecutive_days_do_not_overlap(episodes: int) -> None:
    day = date(2026, 1, 1)
    for offset in range(365):
        current = day + timedelta(days=offset)
        first = rotating_first_seed(current, episodes)
        following = rotating_first_seed(current + timedelta(days=1), episodes)
        assert first + episodes == following


@pytest.mark.parametrize("episodes", [0, -1])
def test_invalid_episode_count(episodes: int) -> None:
    with pytest.raises(ValueError, match="episodes"):
        rotating_first_seed(date(2026, 1, 1), episodes)


def test_before_epoch() -> None:
    with pytest.raises(ValueError, match="epoch"):
        rotating_first_seed(date(2025, 12, 31), 500)


@pytest.mark.parametrize(
    ("episodes", "seed"),
    [("0", ""), ("1001", ""), ("1.5", ""), ("-1", ""), ("5", "-2"), ("5", "x")],
)
def test_invalid_cli_inputs(monkeypatch: pytest.MonkeyPatch, episodes: str, seed: str) -> None:
    monkeypatch.setenv("EPISODES", episodes)
    monkeypatch.setenv("FIRST_SEED", seed)
    assert main() == 2


def test_explicit_cli_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("EPISODES", "3")
    monkeypatch.setenv("FIRST_SEED", "0")
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main() == 0
    assert "episodes=3\nseed=0\n" in capsys.readouterr().out
    assert "seeds 0-2" in summary.read_text()
