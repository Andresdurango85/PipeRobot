from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from piperobot.reports.paired_comment import main, render_paired_comment
from piperobot.stats.paired import PairedCounts, decide_paired

GOLDEN = Path(__file__).parent / "golden"
MARKER = "<!-- piperobot-gate:test -->"
NOTE = (
    "Privileged-state scripted policy: measures the simulated pipeline and regressions, "
    "not a deployable policy (ADR 0034)."
)


@pytest.mark.parametrize(
    ("name", "counts"),
    [
        ("pass", PairedCounts(40, 0, 0, 10)),
        ("block", PairedCounts(30, 10, 0, 10)),
        ("note", PairedCounts(40, 0, 0, 10)),
    ],
)
def test_golden(name: str, counts: PairedCounts) -> None:
    rendered = render_paired_comment(
        decide_paired(counts),
        marker=MARKER,
        title="Policy gate",
        run_url="https://example.com/run/1",
        commit="abcdef123",
        failed_seeds=list(range(40)),
        note=NOTE if name == "note" else None,
    )
    assert rendered == (GOLDEN / f"paired_comment_{name}.md").read_text(encoding="utf-8")


def test_escaping() -> None:
    result = replace(
        decide_paired(PairedCounts(1, 0, 0, 1)),
        reason="<script>*unsafe* | [link](x) &",
    )
    text = render_paired_comment(
        result,
        marker=MARKER,
        title="<b>*title*",
        run_url="https://example.com/)[evil](x)",
        commit="<img>`*",
        failed_seeds=[],
        note="<b>*unsafe* | [link](x) &",
    )
    assert "*&lt;b&gt;\\*unsafe\\* \\| \\[link\\]\\(x\\) &amp;*" in text
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert r"\*unsafe\* \| \[link\]\(x\)" in text
    assert "&lt;img&gt;\\`\\*" in text
    assert "%29%5Bevil%5D%28x%29" in text


@pytest.mark.parametrize(("lost", "expected"), [(0, 0), (4, 0), (10, 1)])
def test_cli(tmp_path: Path, lost: int, expected: int) -> None:
    for name, successes in [("ref", 40), ("cand", 40 - lost)]:
        data = {"episodes": [{"seed": i, "success": i < successes} for i in range(50)]}
        (tmp_path / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "out.md"
    args = [
        "--reference",
        str(tmp_path / "ref.json"),
        "--candidate",
        str(tmp_path / "cand.json"),
        "--marker",
        MARKER,
        "--title",
        "Gate",
        "--note",
        NOTE,
        "--output",
        str(output),
    ]
    assert main(args) == expected
    assert output.read_text(encoding="utf-8").startswith(MARKER + "\n")
    assert "*Privileged\\-state scripted policy:" in output.read_text(encoding="utf-8")
    (tmp_path / "cand.json").write_text("{}", encoding="utf-8")
    assert main(args) == 2


@pytest.mark.parametrize("marker", ["<!-- wrong -->", "<!-- piperobot-gate:x -->\n"])
def test_renderer_rejects_invalid_marker(marker: str) -> None:
    with pytest.raises(ValueError, match="marker"):
        render_paired_comment(
            decide_paired(PairedCounts(1, 0, 0, 1)),
            marker=marker,
            title="Gate",
            run_url=None,
            commit=None,
            failed_seeds=[],
        )


def test_cli_rejects_different_seed_sets(tmp_path: Path) -> None:
    for name, seed in [("ref", 0), ("cand", 1)]:
        (tmp_path / f"{name}.json").write_text(
            json.dumps({"episodes": [{"seed": seed, "success": True}]}), encoding="utf-8"
        )
    output = tmp_path / "comment.md"
    assert (
        main(
            [
                "--reference",
                str(tmp_path / "ref.json"),
                "--candidate",
                str(tmp_path / "cand.json"),
                "--marker",
                MARKER,
                "--title",
                "Gate",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()


@pytest.mark.parametrize("note", ["first\nsecond", "first\rsecond", "first\r\nsecond"])
def test_note_rejects_newline(note: str) -> None:
    with pytest.raises(ValueError, match=r"note.*newline"):
        render_paired_comment(
            decide_paired(PairedCounts(1, 0, 0, 1)),
            marker=MARKER,
            title="Gate",
            run_url=None,
            commit=None,
            failed_seeds=[],
            note=note,
        )


def test_metric_golden_and_escaping() -> None:
    from piperobot.results import MetricSpec
    from piperobot.stats.metric import MetricSummary

    result = decide_paired(PairedCounts(1, 0, 0, 1))
    summary = MetricSummary(2, 2, 2.8, 1)

    def render(spec: MetricSpec | None) -> str:
        return render_paired_comment(
            result,
            marker=MARKER,
            title="Policy gate",
            run_url=None,
            commit=None,
            failed_seeds=[1],
            reference_metric=summary,
            candidate_metric=summary,
            metric_spec=spec,
        )

    assert render(MetricSpec("distance", "cm", 2, "below")) == (
        GOLDEN / "paired_comment_metric.md"
    ).read_text(encoding="utf-8")
    assert "### Metric" in render(None)
    text = render(MetricSpec("<b>*x*|y\nheading", "[m]", 2, "below"))
    assert "<b>" not in text
    assert "&lt;b&gt;" in text
    assert r"\*x\*\|y heading" in text
    assert r"\[m\]" in text


def test_metric_spec_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from piperobot.results import EpisodeResult, EvalResults, MetricSpec, save_results

    a, b, output = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "comment.md"
    episodes = (EpisodeResult(0, True, metric=2),)
    spec = MetricSpec("distance", "cm", 2, "below")
    save_results(EvalResults("a", "e", episodes, spec), a)
    save_results(EvalResults("b", "e", episodes, MetricSpec("other", "cm", 2, "below")), b)
    args = [
        "--reference",
        str(a),
        "--candidate",
        str(b),
        "--marker",
        MARKER,
        "--title",
        "Policy gate",
        "--output",
        str(output),
    ]
    assert main(args) == 2
    assert "metric_spec" in capsys.readouterr().err
    for left, right in [(spec, None), (None, spec), (spec, spec)]:
        save_results(EvalResults("a", "e", episodes, left), a)
        save_results(EvalResults("b", "e", episodes, right), b)
        assert main(args) == 0
        assert "### distance (cm)" in output.read_text(encoding="utf-8")
