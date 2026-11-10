"""Synthetic-only regression tests for the private retrospective collector."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

SPEC = importlib.util.spec_from_file_location(
    "retro_collect",
    Path(__file__).resolve().parents[1] / ".claude/skills/retro/retro_collect.py",
)
assert SPEC is not None
assert SPEC.loader is not None
retro = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(retro)
T = "2026-11-07T12:00:00Z"


def user(text: str = "hello", /, **extra: object) -> dict[str, Any]:
    return {
        "type": "user",
        "sessionId": "abcdefghijk",
        "timestamp": T,
        "origin": {"kind": "human"},
        "message": {"content": text},
        **extra,
    }


def result(text: str, **extra: object) -> dict[str, Any]:
    return user(
        message={
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "x",
                    "content": text,
                    "is_error": True,
                },
            ],
        },
        **extra,
    )


def tool_use(name: str = "Bash", tool_id: object = "x") -> dict[str, Any]:
    return {
        "type": "assistant",
        "sessionId": "abcdefghijk",
        "timestamp": T,
        "message": {"content": [{"type": "tool_use", "name": name, "id": tool_id}]},
    }


def lines(path: Path, records: Sequence[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def options(tmp_path: Path, **extra: object) -> argparse.Namespace:
    root = tmp_path / "transcripts"
    root.mkdir(exist_ok=True)
    return argparse.Namespace(
        signal_tools="Bash,PowerShell",
        transcripts=root,
        date="2026-11-07",
        until=None,
        utc_offset="-05:00",
        codex_dir=None,
        codex_repo=None,
        repo="owner/repo",
        no_github=True,
        no_scorecard=True,
        evaluate_workflow=None,
        evaluate_job=None,
        budget_minutes=30,
        nightly_workflow=None,
        **extra,
    )


@pytest.mark.parametrize(
    ("until", "offset", "expected"),
    [(None, "-05:00", 1), ("2026-11-08", "-05:00", 2), (None, "+00:00", 0)],
)
def test_window(tmp_path: Path, until: str | None, offset: str, expected: int) -> None:
    args = options(tmp_path)
    args.until, args.utc_offset = until, offset
    lines(
        args.transcripts / "s.jsonl",
        [user(timestamp="2026-11-08T04:59:00Z"), user(timestamp="2026-11-08T05:00:00Z")],
    )
    assert retro.collect(args)["totals"]["user_messages"] == expected


def test_malformed_and_allowlist(tmp_path: Path) -> None:
    args = options(tmp_path)
    missing = user()
    del missing["sessionId"]
    path = args.transcripts / "s.jsonl"
    lines(
        path,
        [
            [],
            missing,
            {"type": "api-request", "message": "UNIQUE_PRIVATE"},
            {
                "type": "attachment",
                "sessionId": "s",
                "timestamp": T,
                "attachment": {"type": "instructions", "text": "UNIQUE_PRIVATE"},
            },
        ],
    )
    with path.open("a", encoding="utf-8") as stream:
        stream.write("{broken\n")
    full = retro.collect(args)
    assert full["sources"]["malformed_lines"] == 3
    assert sum(full["sources"]["skipped_types"].values()) == 2
    output = tmp_path / "out.json"
    retro.write(output, full)
    assert "UNIQUE_PRIVATE" not in output.read_text(encoding="utf-8")


def test_sessions_and_events(tmp_path: Path) -> None:
    args = options(tmp_path)
    records = [
        user(),
        user("meta", isMeta=True),
        user("summary", isCompactSummary=True),
        user(
            "Another Claude session sent a message: "
            '<cross-session-message from="id" from-name="Alice">fix it</cross-session-message>',
            origin={"kind": "peer"},
        ),
        user("done", turnOrigin="task_notification", origin={}),
        user("[Request interrupted by user]"),
        {
            "type": "assistant",
            "sessionId": "abcdefghijk",
            "timestamp": T,
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "id": "x"},
                    {"type": "thinking", "text": "PRIVATE"},
                ],
            },
        },
        result("C:/x/.git/hooks/pre-commit: line 13: exec: prek: not found"),
        result(
            "denied by the Claude Code auto mode classifier Reason: [unsafe]",
            toolDenialKind="automode-blocked",
            permissionDecision={"decision": "reject"},
        ),
        result("USER DENIED", permissionDecision={"decision": "reject"}),
        result("blocked", toolDenialKind="x"),
        {
            "type": "system",
            "subtype": "compact_boundary",
            "sessionId": "abcdefghijk",
            "timestamp": T,
        },
        {"type": "custom-title", "sessionId": "abcdefghijk", "customTitle": "Title"},
        {"type": "agent-name", "sessionId": "abcdefghijk", "agentName": "Agent"},
    ]
    records += [
        {
            "type": "attachment",
            "sessionId": "abcdefghijk",
            "timestamp": T,
            "attachment": {
                "type": "hook_non_blocking_error",
                "hookName": "stop",
                "stderr": "failed\nPRIVATE",
            },
        },
    ] * 3
    lines(args.transcripts / "s.jsonl", records)
    lines(args.transcripts / "abcdefghijk/subagents/a.jsonl", [user(sessionId="child")])
    lines(
        args.transcripts / "title.jsonl",
        [
            user(sessionId="title"),
            {"type": "custom-title", "sessionId": "title", "customTitle": "Only title"},
        ],
    )
    lines(args.transcripts / "fallback.jsonl", [user(sessionId="fallback123")])
    full = retro.collect(args)
    session = next(s for s in full["sessions"] if s["name"] == "Agent")
    assert session["user_messages"] == 3
    assert session["subagent_files"] == 1
    assert session["peer_messages_by_sender"] == {"Alice": 1}
    assert session["task_notifications"] == 1
    assert session["tool_calls_by_name"] == {"Bash": 1}
    assert session["permission_denials_by_kind"] == {"classifier": 1, "user": 1, "other": 1}
    assert session["hook_failures"] == 4
    assert session["compactions"] == session["interrupted_turns"] == 1
    assert {s["name"] for s in full["sessions"]} == {"Agent", "Only title", "fallback"}
    assert any(i.get("count") == 3 for i in full["incidents"])
    assert any(i.get("reason") == "unsafe" for i in full["incidents"])
    assert any(c["text"] == "fix it" for c in full["correction_candidates"])


SECRETS = [
    "github_pat_" + "A" * 24,
    "ghp_" + "a" * 24,
    "sk-ant-" + "b" * 24,
    "Bearer " + "c" * 24,
    "eyJabcdef.abcdefgh.ijklmnop",
    "AKIA" + "A" * 16,
    "person@example.com",
    "password=hidden",
]


@pytest.mark.parametrize("secret", SECRETS)
def test_redaction(secret: str) -> None:
    assert secret not in retro.redact("x" * 290 + secret)
    assert secret not in retro.redact(secret)


def test_redaction_blocks_and_home() -> None:
    hidden = "before<system-reminder>PRIVATE\nPRIVATE</system-reminder>after"
    assert "PRIVATE" not in retro.redact(hidden)
    assert "PRIVATE" not in retro.redact("Contents of C:/x/CLAUDE.md:\nPRIVATE\n\nVisible")
    assert retro.redact(str(Path.home()) + "/file") == "~/file"


@pytest.mark.parametrize("secret", SECRETS)
def test_all_free_text_and_metrics(tmp_path: Path, secret: str) -> None:
    args = options(tmp_path)
    lines(
        args.transcripts / "s.jsonl",
        [
            user(secret),
            result(secret),
            {"type": "agent-name", "sessionId": "abcdefghijk", "agentName": secret},
            user(
                f'<cross-session-message from-name="{secret}">{secret}</cross-session-message>',
                origin={"kind": "peer"},
            ),
            result(
                "denied by the Claude Code auto mode classifier Reason: [" + secret + "]",
                toolDenialKind="automode-blocked",
            ),
            {
                "type": "assistant",
                "sessionId": "abcdefghijk",
                "timestamp": T,
                "message": {"content": [{"type": "tool_use", "name": secret}]},
            },
            {
                "type": "attachment",
                "sessionId": "abcdefghijk",
                "timestamp": T,
                "attachment": {
                    "type": "hook_non_blocking_error",
                    "hookName": secret,
                    "stderr": secret,
                },
            },
        ],
    )
    full = retro.collect(args)
    output = tmp_path / "output.json"
    retro.write(output, full)
    text = output.read_text(encoding="utf-8")
    json.loads(text)
    for pattern, _ in retro.PATTERNS:
        assert not retro.re.search(pattern, text)
    small = retro.metrics(full)

    def check(value: object) -> None:
        if isinstance(value, dict):
            forbidden = {"excerpt", "text", "correction_candidates", "title", "name", "session"}
            assert not forbidden & value.keys()
            for k, v in value.items():
                check(k)
                check(v)
        elif isinstance(value, list):
            for v in value:
                check(v)
        elif isinstance(value, str):
            assert len(value) <= 40

    check(small)


def test_cap(tmp_path: Path) -> None:
    args = options(tmp_path)
    lines(args.transcripts / "s.jsonl", [result("failure")] * 45)
    full = retro.collect(args)
    assert full["incident_counts"]["tool_error"] == 45
    assert len(full["incidents"]) == 40


def test_codex(tmp_path: Path) -> None:
    args = options(tmp_path)
    args.codex_dir, args.codex_repo = tmp_path / "codex", "owner/repo"

    def record(typ: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"timestamp": T, "type": typ, "payload": payload}

    def session(sid: str, repo: str) -> dict[str, Any]:
        return record("session_meta", {"id": sid, "timestamp": T, "git": {"repository_url": repo}})

    root = args.codex_dir / "2026/11/07"
    lines(
        root / "a.jsonl",
        [
            session("a", "https://github.com/OWNER/REPO.git"),
            record("event_msg", {"type": "task_complete"}),
            record("response_item", {"type": "function_call"}),
        ],
    )
    lines(
        root / "b.jsonl",
        [
            session("b", "owner/repo"),
            record("event_msg", {"type": "stream_error", "message": "PRIVATE"}),
            [],
        ],
    )
    lines(root / "c.jsonl", [session("c", "other/repo")])
    full = retro.collect(args)
    assert full["codex"]["briefs"] == 2
    assert full["codex"]["completed"] == full["codex"]["incomplete"] == 1
    assert full["codex"]["tool_calls"] == full["codex"]["error_events"] == 1
    assert full["sources"]["codex_malformed_lines"] == 1


def test_github_scorecard(tmp_path: Path) -> None:
    args = options(tmp_path)
    args.no_github = args.no_scorecard = False
    args.evaluate_workflow = args.nightly_workflow = "night.yml"
    args.evaluate_job = "evaluate"
    before, after = "2026-11-07T11:00:00Z", "2026-11-07T13:00:00Z"
    prefix = "repos/owner/repo/"
    run_query = "actions/runs?created=2026-11-07T05:00:00Z..2026-11-08T05:00:00Z&per_page=100"
    history = [{"run_id": 2, "series": "nightly", "verdict": "pass"}]
    responses = {
        ("api", prefix + "pulls?state=closed&sort=updated&direction=desc&per_page=100"): [
            {"number": 1, "title": "PR", "created_at": T, "merged_at": after}
        ],
        ("api", prefix + "pulls/1/commits?per_page=100", "--paginate"): [
            {"sha": "first", "commit": {"committer": {"date": before}}},
            {"sha": "last", "commit": {"committer": {"date": after}}},
        ],
        ("api", prefix + "commits/first/check-runs?per_page=100", "--paginate"): {
            "check_runs": [{"conclusion": "failure"}]
        },
        ("api", prefix + "contents/history.json?ref=history"): {
            "content": base64.b64encode(json.dumps(history).encode()).decode()
        },
        ("api", prefix + run_query, "--paginate"): {
            "workflow_runs": [
                {
                    "id": 2,
                    "name": "Night",
                    "path": ".github/workflows/night.yml",
                    "event": "schedule",
                    "head_sha": "abc",
                    "conclusion": "failure",
                    "run_started_at": T,
                    "updated_at": after,
                    "html_url": "https://github.com/run/2",
                }
            ]
        },
        ("api", prefix + "actions/runs/2/jobs?per_page=100", "--paginate"): {
            "jobs": [
                {
                    "name": "evaluate",
                    "conclusion": "success",
                    "started_at": T,
                    "completed_at": after,
                }
            ]
        },
    }

    def gh(arguments: list[str]) -> object:
        assert tuple(arguments) in responses, arguments
        return responses.pop(tuple(arguments))

    def fetch(repo: str) -> dict[str, Any]:
        assert repo == "owner/repo"
        return {
            "score": 8,
            "date": "2026-11-07",
            "repo": {"commit": "abc"},
            "checks": [{"name": "Review", "score": 9}],
        }

    full = retro.collect(args, gh, fetch)
    assert not responses
    pr = full["github"]["merged_prs"][0]
    assert pr["open_to_merge_minutes"] == 60
    assert pr["rework_commits"] == 1
    assert pr["first_head_checks_failed_approx"] is True
    assert full["github"]["nightly"][0]["verdict"] == "PASS"
    assert retro.metrics(full)["github"]["nightly_verdicts"] == {"PASS": 1}
    assert full["incident_counts"]["ci_failure"] == full["incident_counts"]["budget_exceeded"] == 1
    assert full["scorecard"]["checks"] == {"Review": 9}
    args.no_github = True

    def failed(repo: str) -> dict[str, Any]:
        raise OSError("offline")

    assert retro.collect(args, fetch=failed)["scorecard"] == {"error": "offline"}


def test_trend(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    for day, value in [(1, 1), (2, 3), (3, 5), (9, 99)]:
        (history / f"{day}.json").write_text(
            json.dumps({"date": f"2026-11-{day:02d}", "totals": {"calls": value}}),
            encoding="utf-8",
        )
    (history / "bad.json").write_text("{", encoding="utf-8")
    current = tmp_path / "current.json"
    current.write_text(
        json.dumps({"date": "2026-11-07", "totals": {"calls": 8, "new": 1}}),
        encoding="utf-8",
    )
    output = tmp_path / "trend.json"
    args = [
        "trend",
        "--current",
        str(current),
        "--history",
        str(history),
        "--window",
        "2",
        "--output",
        str(output),
    ]
    assert retro.main(args) == 0
    first = output.read_bytes()
    assert retro.main(args) == 0
    assert output.read_bytes() == first
    data = json.loads(first)
    assert data["normalization"] == "per_day"
    assert data["gauges"] == ["github.evaluate_max_minutes", "schema", "scorecard.score"]
    assert data["current"] == {"file": "current.json", "date": "2026-11-07", "days": 1}
    assert data["history"] == [
        {"file": "2.json", "date": "2026-11-02", "days": 1},
        {"file": "3.json", "date": "2026-11-03", "days": 1},
    ]
    assert data["metrics"]["totals.calls"] == {
        "basis": "per_day",
        "current": 8,
        "current_total": 8,
        "mean": 4,
        "n": 2,
        "delta": 4,
    }
    assert data["metrics"]["totals.new"] == {
        "basis": "per_day",
        "current": 1,
        "current_total": 1,
        "mean": None,
        "n": 0,
        "delta": None,
    }
    assert data["skipped"] == ["bad.json"]


def test_trend_mixed_windows(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    for day, until, total in [(1, 1, 2), (2, 3, 10), (4, 6, 24)]:
        retro.write(
            history / f"{day}.json",
            {
                "date": f"2026-11-{day:02d}",
                "until": f"2026-11-{until:02d}",
                "calls": total,
                **({"sparse": 9} if day == 4 else {}),
            },
        )
    current = tmp_path / "current.json"
    retro.write(current, {"date": "2026-11-07", "until": "2026-11-09", "calls": 24, "sparse": 12})
    data = retro.trend(current, history, 3)
    assert data["current"]["days"] == 3
    assert [r["days"] for r in data["history"]] == [1, 2, 3]
    # 36 / 6 = 6, whereas the mean of daily means would be (2 + 5 + 8) / 3 = 5.
    assert data["metrics"]["calls"] == {
        "basis": "per_day",
        "current": 8,
        "current_total": 24,
        "mean": 6,
        "n": 3,
        "delta": 2,
    }
    assert data["metrics"]["sparse"] == {
        "basis": "per_day",
        "current": 4,
        "current_total": 12,
        "mean": 3,
        "n": 1,
        "delta": 1,
    }


def test_trend_gauges(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    for day, until, value in [(1, 1, 2), (2, 3, 6)]:
        retro.write(
            history / f"{day}.json",
            {
                "date": f"2026-11-{day:02d}",
                "until": f"2026-11-{until:02d}",
                "schema": value,
                "scorecard": {"score": value},
                "github": {"evaluate_max_minutes": value},
            },
        )
    current = tmp_path / "current.json"
    retro.write(
        current,
        {
            "date": "2026-11-07",
            "until": "2026-11-09",
            "schema": 8,
            "scorecard": {"score": 8},
            "github": {"evaluate_max_minutes": 8},
        },
    )
    data = retro.trend(current, history, 2)
    for key in retro.GAUGES:
        assert data["metrics"][key] == {
            "basis": "raw",
            "current": 8,
            "mean": 4,
            "n": 2,
            "delta": 4,
        }


def test_trend_legacy_windows(tmp_path: Path) -> None:
    history = tmp_path / "history"
    history.mkdir()
    retro.write(history / "missing.json", {"date": "2026-11-01", "calls": 2})
    retro.write(history / "null.json", {"date": "2026-11-02", "until": None, "calls": 4})
    current = tmp_path / "current.json"
    retro.write(current, {"date": "2026-11-07", "until": None, "calls": 5})
    data = retro.trend(current, history, 2)
    assert [r["days"] for r in data["history"]] == [1, 1]
    assert data["current"]["days"] == 1
    assert data["metrics"]["calls"]["mean"] == 3
    assert data["metrics"]["calls"]["n"] == 2


@pytest.mark.parametrize("until", ["2026-10-31", "invalid", 42])
def test_trend_invalid_history_window(tmp_path: Path, until: object) -> None:
    history = tmp_path / "history"
    history.mkdir()
    retro.write(history / "bad.json", {"date": "2026-11-01", "until": until, "calls": 2})
    current = tmp_path / "current.json"
    retro.write(current, {"date": "2026-11-07", "calls": 5})
    data = retro.trend(current, history, 2)
    assert data["skipped"] == ["bad.json"]
    assert data["history"] == []
    assert data["metrics"]["calls"]["n"] == 0


@pytest.mark.parametrize("until", ["2026-11-06", "invalid", 42])
def test_trend_invalid_current_window(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    until: object,
) -> None:
    current = tmp_path / "current.json"
    retro.write(current, {"date": "2026-11-07", "until": until})
    with pytest.raises(ValueError, match=r"until|Invalid isoformat"):
        retro.trend(current, tmp_path, 2)
    assert (
        retro.main(
            [
                "trend",
                "--current",
                str(current),
                "--history",
                str(tmp_path),
                "--output",
                str(tmp_path / "out.json"),
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR: ")
    assert len(captured.err.splitlines()) == 1


@pytest.mark.parametrize("case", ["missing", "codex", "arguments", "output"])
def test_cli_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str) -> None:
    root = tmp_path / "transcripts"
    if case != "missing":
        root.mkdir()
    args = [
        "collect",
        "--date",
        "2026-11-07",
        "--transcripts",
        str(root),
        "--no-github",
        "--no-scorecard",
        "--output",
        str(tmp_path if case == "output" else tmp_path / "out.json"),
    ]
    if case == "codex":
        args += ["--codex-dir", str(tmp_path / "codex")]
    assert retro.main([] if case == "arguments" else args) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR: ")
    assert len(captured.err.splitlines()) == 1


def test_cli_success(tmp_path: Path) -> None:
    args = options(tmp_path)
    lines(args.transcripts / "s.jsonl", [user()])
    output, small = tmp_path / "out.json", tmp_path / "metrics.json"
    assert (
        retro.main(
            [
                "collect",
                "--date",
                args.date,
                "--utc-offset",
                "-05:00",
                "--transcripts",
                str(args.transcripts),
                "--no-github",
                "--no-scorecard",
                "--output",
                str(output),
                "--metrics-output",
                str(small),
            ],
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["totals"]["user_messages"] == 1
    assert json.loads(small.read_text(encoding="utf-8"))["schema"] == 1
    assert b"\r\n" not in output.read_bytes()


@pytest.mark.parametrize(
    ("text", "signal"),
    [
        (".git/hooks/pre-push: line 13: exec: prek: not found", "hook_failure"),
        ("zizmor (offline)....Failed\n- hook id: zizmor\n- exit code: 1", "hook_failure"),
        ("x" * 400 + "\nrm: cannot remove 'x': Permission denied", "fs_permission_denied"),
        ("Traceback (most recent call last):\nPermission denied", "fs_permission_denied"),
        ("command not found", "command_not_found"),
        ("thing: not found", "command_not_found"),
        ("is not recognized as the name of a cmdlet", "command_not_found"),
        ("Traceback (most recent call last):", "traceback"),
        ("thread 'main' panicked at crates", "panic"),
        ("everything succeeded", None),
    ],
)
def test_output_signals(tmp_path: Path, text: str, signal: str | None) -> None:
    args = options(tmp_path)
    record = result(text)
    record["message"]["content"][0]["is_error"] = False
    lines(args.transcripts / "s.jsonl", [tool_use(), record] * 3)
    full = retro.collect(args)
    assert full["totals"]["tool_errors"] == 0
    if signal is None:
        assert full["incidents"] == []
        assert full["totals"]["output_signals_by_kind"] == {}
        return
    assert len(full["incidents"]) == 1
    item = full["incidents"][0]
    assert item["signal"] == signal
    assert item["count"] == 3
    assert item["first_seen"] == item["last_seen"] == T
    if signal == "hook_failure":
        assert item["kind"] == "hook_failure"
        assert full["totals"]["hook_failures"] == 3
    else:
        assert item["kind"] == "output_signal"
        assert full["sessions"][0]["output_signals_by_kind"] == {signal: 3}
        assert retro.metrics(full)["totals"]["output_signals_by_kind"] == {signal: 3}
    if signal == "fs_permission_denied":
        assert "Permission denied" in item["excerpt"]


@pytest.mark.parametrize("token_length", [36, 120])
def test_output_signal_redacts_before_slicing(tmp_path: Path, token_length: int) -> None:
    args = options(tmp_path)
    token = "ghp_" + "Q" * (token_length - 4)
    text = "x" * 450 + " " + token + " " * 20 + "Permission denied" + "z" * 400
    record = result(text)
    record["message"]["content"][0]["is_error"] = False
    lines(args.transcripts / "s.jsonl", [tool_use("Bash"), record])

    excerpt = retro.collect(args)["incidents"][0]["excerpt"]
    assert "[REDACTED:github]" in excerpt
    assert "Q" not in excerpt
    assert "Permission denied" in excerpt
    assert len(excerpt) == 300
    assert excerpt.endswith("…")


@pytest.mark.parametrize("signal_inside_reminder", [False, True])
def test_output_signal_removes_whole_reminder(tmp_path: Path, signal_inside_reminder: bool) -> None:
    args = options(tmp_path)
    reminder = "R" * 150
    signal = "Permission denied"
    text = (
        "safe start "
        + "x" * 450
        + "<system-reminder>"
        + reminder
        + (signal if signal_inside_reminder else "")
        + "</system-reminder>"
        + ("" if signal_inside_reminder else signal)
    )
    record = result(text)
    record["message"]["content"][0]["is_error"] = False
    lines(args.transcripts / "s.jsonl", [tool_use("Bash"), record])

    excerpt = retro.collect(args)["incidents"][0]["excerpt"]
    assert "R" not in excerpt
    assert "system-reminder" not in excerpt
    if signal_inside_reminder:
        assert excerpt.startswith("safe start ")
        assert signal not in excerpt
    else:
        assert signal in excerpt


def test_denial_is_not_tool_error(tmp_path: Path) -> None:
    args = options(tmp_path)
    lines(
        args.transcripts / "s.jsonl",
        [result("denied by the Claude Code auto mode classifier", toolDenialKind="classifier")],
    )
    full = retro.collect(args)
    assert full["totals"]["permission_denials"] == 1
    assert full["totals"]["tool_errors"] == 0
    assert [item["kind"] for item in full["incidents"]] == ["permission_denial"]


def test_error_and_signal_both_count(tmp_path: Path) -> None:
    args = options(tmp_path)
    lines(args.transcripts / "s.jsonl", [tool_use(), result("Permission denied")])
    full = retro.collect(args)
    assert full["totals"]["tool_errors"] == 1
    assert full["totals"]["output_signals_by_kind"] == {"fs_permission_denied": 1}
    assert {item["kind"] for item in full["incidents"]} == {"tool_error", "output_signal"}


@pytest.mark.parametrize("name", ["Read", "Grep", "Bash", "PowerShell"])
@pytest.mark.parametrize(
    "text", ["Permission denied", ".git/hooks/pre-push: line 13: exec: prek: not found"]
)
def test_signal_tool_filter(tmp_path: Path, name: str, text: str) -> None:
    args = options(tmp_path)
    lines(args.transcripts / "s.jsonl", [tool_use(name), result(text)])
    full = retro.collect(args)
    assert full["totals"]["tool_errors"] == 1
    assert full["incident_counts"].get("output_signal", 0) + full["totals"]["hook_failures"] == (
        1 if name in {"Bash", "PowerShell"} else 0
    )


@pytest.mark.parametrize("tool_id", [None, 42, "unknown"])
def test_unmapped_tool_id(tmp_path: Path, tool_id: object) -> None:
    args = options(tmp_path)
    record = result("Permission denied")
    record["message"]["content"][0]["tool_use_id"] = tool_id
    lines(args.transcripts / "s.jsonl", [tool_use(), record])
    full = retro.collect(args)
    assert full["totals"]["output_signals_by_kind"] == {}
    assert full["totals"]["tool_errors"] == 1


@pytest.mark.parametrize("tool_id", [None, 42, ["x"]])
def test_non_string_tool_use_id(tmp_path: Path, tool_id: object) -> None:
    args = options(tmp_path)
    lines(args.transcripts / "s.jsonl", [tool_use(tool_id=tool_id), result("Permission denied")])
    full = retro.collect(args)
    assert full["sources"]["malformed_lines"] == 0
    assert full["totals"]["tool_calls"] == 1
    assert full["totals"]["output_signals_by_kind"] == {}


def test_tool_ids_are_per_file(tmp_path: Path) -> None:
    args = options(tmp_path)
    lines(args.transcripts / "a.jsonl", [tool_use()])
    lines(args.transcripts / "b.jsonl", [result("Permission denied")])
    assert retro.collect(args)["totals"]["output_signals_by_kind"] == {}


def test_cli_signal_tools(tmp_path: Path) -> None:
    args = options(tmp_path)
    lines(args.transcripts / "s.jsonl", [tool_use("Read"), result("Permission denied")])
    output = tmp_path / "out.json"
    assert (
        retro.main(
            [
                "collect",
                "--date",
                args.date,
                "--transcripts",
                str(args.transcripts),
                "--no-github",
                "--no-scorecard",
                "--signal-tools",
                "Read",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["totals"]["output_signals_by_kind"] == {
        "fs_permission_denied": 1,
    }
