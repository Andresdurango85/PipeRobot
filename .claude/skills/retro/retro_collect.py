"""Collect redacted retrospective metrics without exporting raw transcripts."""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Never

# CLAUDE CODE FORMAT ASSUMPTIONS
# This format is internal to Claude Code, observed on Claude Code 2.x in 2026-11.
# Format drift appears in skipped/malformed counts. Only these accessors read it.
# Claude Code shell tools whose command output may produce signals.
SIGNAL_TOOLS = {"Bash", "PowerShell"}
ALLOWED = {"user", "assistant", "system", "attachment", "agent-name", "custom-title"}


def claude_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ValueError("invalid text blocks")
    return "\n".join(
        b["text"]
        for b in content
        if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
    )


def claude_record(r: dict[str, Any]) -> dict[str, Any]:
    """Read the internal Claude Code format observed on Claude Code 2.x in 2026-11.

    Drift is reported through skipped and malformed counts by the caller.
    """
    kind = r.get("type", "unknown")
    if kind not in ALLOWED:
        return {"skip": str(kind)}
    if kind in {"agent-name", "custom-title"}:
        name = r["agentName" if kind == "agent-name" else "customTitle"]
        if not isinstance(name, str):
            raise ValueError("invalid session name")
        return {
            "type": kind,
            "id": r["sessionId"],
            "name": name,
        }
    sid, timestamp = r["sessionId"], r["timestamp"]
    if not isinstance(sid, str) or not isinstance(timestamp, str):
        raise ValueError("invalid identity or timestamp")
    result: dict[str, Any] = {"type": kind, "id": sid, "timestamp": timestamp}
    if kind == "system":
        if r.get("subtype") != "compact_boundary":
            return {"skip": "system:" + str(r.get("subtype", "unknown"))}
    elif kind == "attachment":
        a = r["attachment"]
        if a.get("type") != "hook_non_blocking_error":
            return {"skip": "attachment:" + str(a.get("type", "unknown"))}
        result.update(hook=a["hookName"], text=a["stderr"].splitlines()[0] if a["stderr"] else "")
    else:
        content = r["message"]["content"]
        if not isinstance(content, (str, list)) or (
            kind == "assistant" and not isinstance(content, list)
        ):
            raise ValueError("invalid message content")
        blocks = content if isinstance(content, list) else []
        if kind == "assistant":
            result["tools"] = [b["name"] for b in blocks if b.get("type") == "tool_use"]
            result["tool_uses"] = {
                b["id"]: b["name"]
                for b in blocks
                if b.get("type") == "tool_use" and isinstance(b.get("id"), str)
            }
        else:
            result.update(
                text=claude_text(content),
                results=[
                    {
                        "text": claude_text(b.get("content", "")),
                        "error": b.get("is_error") is True,
                        "tool_use_id": b.get("tool_use_id"),
                    }
                    for b in blocks
                    if b.get("type") == "tool_result"
                ],
                origin=r.get("origin", {}).get("kind", r.get("turnOrigin", "")),
                excluded=bool(r.get("isMeta") or r.get("isCompactSummary")),
                denied=bool(
                    r.get("toolDenialKind")
                    or r.get("permissionDecision", {}).get("decision") == "reject",
                ),
            )
    if kind == "user" and (
        not isinstance(result["text"], str)
        or any(not isinstance(b["text"], str) for b in result["results"])
    ):
        raise ValueError("invalid text content")
    if kind == "assistant" and any(not isinstance(t, str) for t in result["tools"]):
        raise ValueError("invalid tool name")
    if kind == "attachment" and not isinstance(result["hook"], str):
        raise ValueError("invalid hook name")
    return result


# END CLAUDE CODE FORMAT ASSUMPTIONS

PATTERNS = [
    (r"github_pat_[A-Za-z0-9_]{20,}", "github"),
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "github"),
    (r"sk-[A-Za-z0-9_-]{16,}", "api"),
    (r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}", "bearer"),
    (r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}", "jwt"),
    (r"AKIA[0-9A-Z]{16}", "aws"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email"),
]


def redact(text: str, *, truncate: bool = True) -> str:
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    # Heuristic: a contents block ends at a blank line and an unindented line.
    text = re.sub(
        r"^Contents of [^\n]*(?:CLAUDE|AGENTS|MEMORY)\.md[^\n]*(?:\n|\Z).*?(?=\n\n\S|\Z)",
        "",
        text,
        flags=re.M | re.S,
    )
    for pattern, kind in PATTERNS:
        text = re.sub(pattern, ("Bearer " if kind == "bearer" else "") + f"[REDACTED:{kind}]", text)
    text = re.sub(
        r"(?i)\b(token|secret|password|passwd|api[_-]?key)\b(\s*[=:]\s*)(?!\[REDACTED:)\S+",
        r"\1\2[REDACTED:value]",
        text,
    )
    for home in {str(Path.home()).replace("\\", "/"), str(Path.home()).replace("/", "\\")}:
        text = re.sub(re.escape(home), "~", text, flags=re.I)
    return text[:299] + "…" if truncate and len(text) > 300 else text


def stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp needs offset")
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def minutes(start: str, end: str) -> float:
    return round((stamp(end) - stamp(start)).total_seconds() / 60, 3)


def gh_json(args: list[str]) -> object:
    binary = shutil.which("gh")
    if binary is None:
        raise ValueError("gh not found")
    result = subprocess.run(  # noqa: S603 -- resolved gh, explicit argument list
        [binary, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    decoder = json.JSONDecoder()
    remaining = result.stdout.strip()
    pages = []
    while remaining:
        page, consumed = decoder.raw_decode(remaining)
        pages.append(page)
        remaining = remaining[consumed:].lstrip()
    if not pages:
        raise ValueError("empty GitHub response")
    combined = pages[0]
    for page in pages[1:]:
        if isinstance(combined, list) and isinstance(page, list):
            combined.extend(page)
        elif isinstance(combined, dict) and isinstance(page, dict):
            for key, value in page.items():
                if isinstance(value, list) and isinstance(combined.get(key), list):
                    combined[key].extend(value)
    return combined


def fetch_scorecard(repo: str) -> dict[str, Any]:
    url = f"https://api.scorecard.dev/projects/github.com/{repo}"
    with urllib.request.urlopen(url, timeout=20) as response:
        value = json.load(response)
        if not isinstance(value, dict):
            raise ValueError("expected scorecard object")
        return value


def github(
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
    call: Callable[[list[str]], object],
) -> dict[str, Any]:
    def api(path: str, paginate: bool = False) -> dict[str, Any]:
        value = call(["api", f"repos/{args.repo}/{path}", *(["--paginate"] if paginate else [])])
        if not isinstance(value, dict):
            raise ValueError("expected GitHub object")
        return value

    def api_list(path: str, paginate: bool = False) -> list[dict[str, Any]]:
        value = call(["api", f"repos/{args.repo}/{path}", *(["--paginate"] if paginate else [])])
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError("expected GitHub list of objects")
        return value

    # The newest 100 closed PRs suffice for daily runs; older updated PRs are not scanned.
    prs = []
    for pr in api_list("pulls?state=closed&sort=updated&direction=desc&per_page=100"):
        if not pr.get("merged_at") or not start <= stamp(pr["merged_at"]) < end:
            continue
        commits = api_list(f"pulls/{pr['number']}/commits?per_page=100", True)
        heads = [
            c for c in commits if stamp(c["commit"]["committer"]["date"]) <= stamp(pr["created_at"])
        ]
        failed = False
        if heads:
            checks = api(f"commits/{heads[-1]['sha']}/check-runs?per_page=100", True)
            failed = any(
                (
                    c.get("conclusion") in {"failure", "timed_out", "cancelled", "action_required"}
                    for c in checks["check_runs"]
                ),
            )
        # Approximation: GitHub does not retain the head SHA at PR open time.
        prs.append(
            (
                {k: pr[k] for k in ("number", "title", "created_at", "merged_at")}
                | {
                    "open_to_merge_minutes": minutes(pr["created_at"], pr["merged_at"]),
                    "rework_commits": sum(
                        (
                            stamp(c["commit"]["committer"]["date"]) > stamp(pr["created_at"])
                            for c in commits
                        ),
                    ),
                    "first_head_checks_failed_approx": failed,
                }
            ),
        )
    runs = []
    nightly = []
    history: list[dict[str, Any]] = []
    if args.nightly_workflow:
        try:
            encoded = api("contents/history.json?ref=history")["content"]
            history = json.loads(base64.b64decode(encoded))
        except (ValueError, KeyError, OSError):
            history = []
    data = api(f"actions/runs?created={iso(start)}..{iso(end)}&per_page=100", True)
    for r in data["workflow_runs"]:
        if not start <= stamp(r.get("created_at", r["run_started_at"])) < end:
            continue
        run = {
            k: r.get(k)
            for k in (
                "id",
                "name",
                "path",
                "event",
                "head_sha",
                "conclusion",
                "run_started_at",
                "updated_at",
            )
        }
        run["duration_minutes"] = minutes(r["run_started_at"], r["updated_at"])
        run["url"] = r.get("html_url", "")
        if args.evaluate_workflow and Path(r["path"]).name == Path(args.evaluate_workflow).name:
            for job in api(f"actions/runs/{r['id']}/jobs?per_page=100", True)["jobs"]:
                if (
                    job["name"] == args.evaluate_job
                    and job.get("conclusion") != "skipped"
                    and job.get("started_at")
                    and job.get("completed_at")
                ):
                    run["evaluate_minutes"] = minutes(job["started_at"], job["completed_at"])
                    run["over_budget"] = run["evaluate_minutes"] > args.budget_minutes
        if args.nightly_workflow and Path(r["path"]).name == Path(args.nightly_workflow).name:
            nightly.append(
                {
                    "id": r["id"],
                    "conclusion": r["conclusion"],
                    "verdict": next(
                        (
                            verdict(h.get("verdict"))
                            for h in history
                            if (
                                str(h.get("run_id")) == str(r["id"])
                                and h.get("series") == "nightly"
                            )
                        ),
                        None,
                    ),
                },
            )
        runs.append(run)
    return {
        "merged_prs": prs,
        "runs": runs,
        "failures": sum(r["conclusion"] in {"failure", "timed_out"} for r in runs),
        "nightly": nightly,
    }


# Ordered output signals: one match per tool result, independent of exit status.
OUTPUT_SIGNALS = (
    ("hook_failure", re.compile(r"hooks[/\\][\w.-]+: line \d+: .*not found", re.I), False),
    ("hook_failure", re.compile(r"^- hook id: \S+", re.I | re.M), True),
    (
        "command_not_found",
        re.compile(
            r"command not found|: not found$|is not recognized as "
            r"(?:an internal or external command|the name of a cmdlet)",
            re.I | re.M,
        ),
        False,
    ),
    (
        "fs_permission_denied",
        re.compile(
            r"Permission denied|Access is denied|Access to the path .* is denied|PermissionError",
            re.I,
        ),
        False,
    ),
    ("traceback", re.compile(r"Traceback \(most recent call last\)", re.I), False),
    ("panic", re.compile(r"panicked at", re.I), False),
)


def verdict(value: object) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", value):
        return value.upper()
    return None


COUNTERS = (
    "user_messages",
    "peer_messages",
    "task_notifications",
    "tool_calls",
    "tool_errors",
    "permission_denials",
    "hook_failures",
    "interrupted_turns",
    "compactions",
)


def collect(
    args: argparse.Namespace,
    gh: Callable[[list[str]], object] = gh_json,
    fetch: Callable[[str], dict[str, Any]] = fetch_scorecard,
) -> dict[str, Any]:
    if not args.transcripts.is_dir():
        raise ValueError("transcripts must be a readable directory")
    match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", args.utc_offset)
    if not match or int(match[2]) > 23 or int(match[3]) > 59:
        raise ValueError("invalid UTC offset")
    offset = timezone(
        timedelta(minutes=(int(match[2]) * 60 + int(match[3])) * (-1 if match[1] == "-" else 1)),
    )
    for value in (args.date, args.until or args.date):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("dates must use YYYY-MM-DD")
    first, last = date.fromisoformat(args.date), date.fromisoformat(args.until or args.date)
    if last < first:
        raise ValueError("until precedes date")
    start = datetime.combine(first, datetime.min.time(), offset).astimezone(UTC)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), offset).astimezone(UTC)
    sources: dict[str, Any] = {
        "transcript_files": 0,
        "subagent_files": 0,
        "records": 0,
        "malformed_lines": 0,
        "skipped_types": {},
        "codex_files": 0,
        "codex_malformed_lines": 0,
    }
    signal_tools = {name.strip() for name in args.signal_tools.split(",") if name.strip()}
    sessions: dict[str, dict[str, Any]] = {}
    names: dict[str, dict[str, str]] = {}
    incidents: list[dict[str, Any]] = []
    candidates = []
    counts: Counter[str] = Counter()
    signals: dict[tuple[str, str, str], dict[str, Any]] = {}
    hooks: dict[tuple[str, str, str], dict[str, Any]] = {}

    def incident(sid: str, timestamp: str, kind: str, text: str = "", **extra: object) -> None:
        counts[kind] += 1
        incidents.append(
            {"session": sid, "timestamp": timestamp, "kind": kind, "excerpt": text, **extra},
        )

    files: list[tuple[Path, str | None]] = [
        (p, None) for p in sorted(args.transcripts.glob("*.jsonl"))
    ]
    files += [
        (p, p.parent.parent.name) for p in sorted(args.transcripts.glob("*/subagents/*.jsonl"))
    ]
    # Force a directory read even when no matching files exist.
    next(args.transcripts.iterdir(), None)
    for path, parent in files:
        if not path.resolve().is_relative_to(args.transcripts.resolve()):
            continue
        sources["subagent_files" if parent else "transcript_files"] += 1
        touched: set[str] = set()
        tool_uses: dict[str, str] = {}
        try:
            raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            sources["malformed_lines"] += 1
            continue
        for raw in raw_lines:
            try:
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError("not object")
                r = claude_record(obj)
                if "skip" in r:
                    key = r["skip"]
                    sources["skipped_types"][key] = sources["skipped_types"].get(key, 0) + 1
                    continue
                sid = parent or r["id"]
                if not isinstance(sid, str):
                    raise ValueError("bad session")
                if r["type"] in {"agent-name", "custom-title"}:
                    names.setdefault(sid, {})[r["type"]] = r["name"]
                    continue
                if r["type"] == "assistant":
                    tool_uses.update(r["tool_uses"])
                timestamp = iso(stamp(r["timestamp"]))
                if not start <= stamp(timestamp) < end:
                    continue
            except (ValueError, KeyError, TypeError, AttributeError, IndexError):
                sources["malformed_lines"] += 1
                continue
            sources["records"] += 1
            s = sessions.setdefault(
                sid,
                {
                    "session_id": sid,
                    "first_seen": timestamp,
                    "last_seen": timestamp,
                    "subagent_files": 0,
                    **dict.fromkeys(COUNTERS, 0),
                    "tool_calls_by_name": {},
                    "peer_messages_by_sender": {},
                    "permission_denials_by_kind": {},
                    "output_signals_by_kind": {},
                },
            )
            s["first_seen"] = min(s["first_seen"], timestamp, key=stamp)
            s["last_seen"] = max(s["last_seen"], timestamp, key=stamp)
            if parent and sid not in touched:
                s["subagent_files"] += 1
                touched.add(sid)
            kind = r["type"]
            if kind == "assistant":
                for tool in r["tools"]:
                    s["tool_calls"] += 1
                    s["tool_calls_by_name"][tool] = s["tool_calls_by_name"].get(tool, 0) + 1
            elif kind == "system":
                s["compactions"] += 1
                incident(sid, timestamp, "compaction")
            elif kind == "attachment":
                s["hook_failures"] += 1
                key = (sid, r["hook"], r["text"])
                counts["hook_failure"] += 1
                if key in hooks:
                    h = hooks[key]
                    h["count"] += 1
                    h["first_seen"] = min(h["first_seen"], timestamp, key=stamp)
                    h["last_seen"] = max(h["last_seen"], timestamp, key=stamp)
                    h["timestamp"] = h["first_seen"]
                else:
                    h = {
                        "session": sid,
                        "timestamp": timestamp,
                        "kind": "hook_failure",
                        "excerpt": r["text"],
                        "hook": r["hook"],
                        "count": 1,
                        "first_seen": timestamp,
                        "last_seen": timestamp,
                    }
                    hooks[key] = h
                    incidents.append(h)
            elif kind == "user":
                text, origin = r["text"], r["origin"]
                if origin in {"task-notification", "task_notification"}:
                    s["task_notifications"] += 1
                sender = "unknown"
                if origin == "peer":
                    m = re.search(
                        r'<cross-session-message\b[^>]*\bfrom-name=["\x27]([^"\x27]+)',
                        text,
                    )
                    sender = m[1] if m else "unknown"
                    s["peer_messages"] += 1
                    senders = s["peer_messages_by_sender"]
                    senders[sender] = senders.get(sender, 0) + 1
                human = (
                    origin == "human"
                    and not r["excluded"]
                    and bool(text.strip())
                    and not r["results"]
                )
                s["user_messages"] += int(human)
                if human or origin == "peer":
                    clean = (
                        re.sub(r"</?cross-session-message\b[^>]*>", "", text)
                        .replace(
                            "Another Claude session sent a message:",
                            "",
                        )
                        .strip()
                    )
                    candidates.append(
                        {
                            "session": sid,
                            "timestamp": timestamp,
                            "origin": origin,
                            "from_name": sender if origin == "peer" else None,
                            "text": clean,
                        },
                    )
                if text.startswith("[Request interrupted by user"):
                    s["interrupted_turns"] += 1
                    incident(sid, timestamp, "interrupted", text)
                result_text = "\n".join(b["text"] for b in r["results"])
                if r["denied"]:
                    denial = (
                        "classifier"
                        if "denied by the Claude Code auto mode classifier" in result_text
                        else (
                            "user"
                            if re.search(
                                r"doesn't want to proceed|user rejected|user denied",
                                result_text,
                                re.I,
                            )
                            else "other"
                        )
                    )
                    s["permission_denials"] += 1
                    denials = s["permission_denials_by_kind"]
                    denials[denial] = denials.get(denial, 0) + 1
                    reason = re.search(r"Reason: \[(.*?)\]", result_text, re.S)
                    incident(
                        sid,
                        timestamp,
                        "permission_denial",
                        result_text,
                        reason=reason[1] if reason else None,
                    )
                for b in r["results"]:
                    if b["error"] and not r["denied"]:
                        s["tool_errors"] += 1
                        incident(sid, timestamp, "tool_error", b["text"])
                    tool_id = b["tool_use_id"]
                    if not isinstance(tool_id, str) or tool_uses.get(tool_id) not in signal_tools:
                        continue
                    for signal, pattern, needs_failed in OUTPUT_SIGNALS:
                        match = pattern.search(b["text"])
                        if match is None or (needs_failed and "Failed" not in b["text"]):
                            continue
                        if signal == "hook_failure":
                            s["hook_failures"] += 1
                            incident_kind = "hook_failure"
                        else:
                            by_kind = s["output_signals_by_kind"]
                            by_kind[signal] = by_kind.get(signal, 0) + 1
                            incident_kind = "output_signal"
                        counts[incident_kind] += 1
                        line_start = b["text"].rfind("\n", 0, match.start()) + 1
                        line_end = b["text"].find("\n", match.start())
                        matched_line = b["text"][line_start : line_end if line_end >= 0 else None]
                        key = (sid, signal, matched_line)
                        if key in signals:
                            item = signals[key]
                            item["count"] += 1
                            item["first_seen"] = min(item["first_seen"], timestamp, key=stamp)
                            item["last_seen"] = max(item["last_seen"], timestamp, key=stamp)
                            item["timestamp"] = item["first_seen"]
                        else:
                            redacted_text = redact(b["text"], truncate=False)
                            redacted_match = pattern.search(redacted_text)
                            excerpt_start = (
                                max(0, redacted_match.start() - 100) if redacted_match else 0
                            )
                            item = {
                                "session": sid,
                                "timestamp": timestamp,
                                "kind": incident_kind,
                                "signal": signal,
                                "excerpt": redact(redacted_text[excerpt_start:]),
                                "count": 1,
                                "first_seen": timestamp,
                                "last_seen": timestamp,
                            }
                            signals[key] = item
                            incidents.append(item)
                        break
    for sid, s in sessions.items():
        labels = names.get(sid, {})
        s["name"] = labels.get("agent-name", labels.get("custom-title", sid[:8]))
    codex = collect_codex(args, start, end, sources, incident)
    git = None
    if not args.no_github:
        try:
            git = github(args, start, end, gh)
            for run in git["runs"]:
                excerpt = f"{run['name']} {run['conclusion']} {run['url']}"
                if run["conclusion"] in {"failure", "timed_out"}:
                    incident("github", run["run_started_at"], "ci_failure", excerpt)
                if run.get("over_budget"):
                    incident("github", run["run_started_at"], "budget_exceeded", excerpt)
        except (OSError, ValueError, subprocess.SubprocessError, KeyError, TypeError) as error:
            git = {"error": str(error)}
    score = None
    if not args.no_scorecard:
        try:
            value = fetch(args.repo)
            score = {
                "score": value["score"],
                "date": value["date"],
                "repo": {"commit": value["repo"]["commit"]},
                "checks": {c["name"]: c["score"] for c in value["checks"]},
            }
        except Exception as error:  # external service failures must not fail collection
            score = {"error": str(error)[:200]}
    kept = []
    used: Counter[str] = Counter()
    for item in sorted(incidents, key=lambda i: (stamp(i["timestamp"]), i["kind"], i["session"])):
        item["session"] = sessions.get(item["session"], {}).get("name", item["session"])
        if used[item["kind"]] < 40:
            kept.append(item)
            used[item["kind"]] += 1
    for candidate in candidates:
        candidate["session"] = sessions[candidate["session"]]["name"]
    return {
        "schema": 1,
        "generated_by": "retro_collect.py",
        "date": args.date,
        "until": last.isoformat(),
        "utc_offset": args.utc_offset,
        "window_utc": [iso(start), iso(end)],
        "sources": sources,
        "sessions": sorted(
            sessions.values(), key=lambda s: (stamp(s["first_seen"]), s["session_id"])
        ),
        "totals": (
            {k: sum(s[k] for s in sessions.values()) for k in COUNTERS}
            | {
                k: dict(sum((Counter(s[k]) for s in sessions.values()), Counter()))
                for k in (
                    "tool_calls_by_name",
                    "peer_messages_by_sender",
                    "permission_denials_by_kind",
                    "output_signals_by_kind",
                )
            }
        ),
        "codex": codex,
        "github": git,
        "scorecard": score,
        "incident_counts": dict(counts),
        "incidents": kept,
        "correction_candidates": sorted(
            candidates,
            key=lambda c: (stamp(c["timestamp"]), c["session"]),
        ),
    }


def collect_codex(
    args: argparse.Namespace,
    start: datetime,
    end: datetime,
    sources: dict[str, Any],
    incident: Callable[..., None],
) -> dict[str, Any]:
    sessions = []
    if args.codex_dir:
        day = start.date() - timedelta(days=1)
        while day <= end.date() + timedelta(days=1):
            for path in sorted((args.codex_dir / day.strftime("%Y/%m/%d")).glob("*.jsonl")):
                sources["codex_files"] += 1
                meta = None
                events = []
                try:
                    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    sources["codex_malformed_lines"] += 1
                    continue
                for line in raw_lines:
                    try:
                        r = json.loads(line)
                        t = iso(stamp(r["timestamp"]))
                        p = r["payload"]
                        if not isinstance(p, dict):
                            raise ValueError("payload")
                        if r["type"] == "session_meta":
                            meta = (
                                p.get("id", p.get("session_id")),
                                iso(stamp(p["timestamp"])),
                                p.get("git", {}).get("repository_url", ""),
                            )
                        events.append((t, r["type"], p.get("type")))
                    except (ValueError, KeyError, TypeError, AttributeError):
                        sources["codex_malformed_lines"] += 1
                if not meta:
                    continue
                sid, began, repo = meta
                if not isinstance(repo, str):
                    sources["codex_malformed_lines"] += 1
                    continue
                normalized = repo.lower().removeprefix("https://github.com/").removesuffix(".git")
                if (
                    not isinstance(sid, str)
                    or normalized != args.codex_repo.lower()
                    or not start <= stamp(began) < end
                ):
                    continue
                ended = max([began, *(e[0] for e in events)], key=stamp)
                errors = Counter(
                    (
                        e[2]
                        for e in events
                        if (
                            e[1] == "event_msg"
                            and e[2] in {"error", "stream_error", "turn_aborted"}
                        )
                    ),
                )
                complete = any(e[1:] == ("event_msg", "task_complete") for e in events)
                sessions.append(
                    {
                        "session_id": sid,
                        "started": began,
                        "ended": ended,
                        "wall_minutes": minutes(began, ended),
                        "completed": complete,
                        "tool_calls": sum(
                            (
                                (
                                    e[1] == "response_item"
                                    and e[2] in {"custom_tool_call", "function_call"}
                                )
                                for e in events
                            ),
                        ),
                        "error_events": dict(errors),
                    },
                )
                if not complete:
                    incident("codex:" + sid[:8], ended, "codex_incomplete")
                for t, typ, event in events:
                    if typ == "event_msg" and event in errors:
                        incident("codex:" + sid[:8], t, "codex_error", event)
            day += timedelta(days=1)
    return {
        "sessions": sorted(sessions, key=lambda s: (stamp(s["started"]), s["session_id"])),
        "briefs": len(sessions),
        "completed": sum(s["completed"] for s in sessions),
        "incomplete": sum(not s["completed"] for s in sessions),
        "tool_calls": sum(s["tool_calls"] for s in sessions),
        "error_events": sum(sum(s["error_events"].values()) for s in sessions),
    }


def metrics(full: dict[str, Any]) -> dict[str, Any]:
    git = full["github"] or {}
    prs, runs = git.get("merged_prs", []), git.get("runs", [])
    sources = full["sources"]
    return {
        "schema": 1,
        **{k: full[k] for k in ("date", "until", "utc_offset", "incident_counts")},
        "totals": {k: full["totals"][k] for k in (*COUNTERS, "output_signals_by_kind")},
        "codex": {
            k: full["codex"][k]
            for k in ("briefs", "completed", "incomplete", "tool_calls", "error_events")
        },
        "github": {
            "merged_prs": len(prs),
            "rework_commits": sum(p["rework_commits"] for p in prs),
            "first_head_checks_failed_approx": sum(
                (p["first_head_checks_failed_approx"] for p in prs),
            ),
            "runs": len(runs),
            "run_failures": git.get("failures", 0),
            "evaluate_over_budget": sum(bool(r.get("over_budget")) for r in runs),
            "evaluate_max_minutes": max(
                (r.get("evaluate_minutes", 0) for r in runs),
                default=0,
            ),
            "nightly_verdicts": dict(
                Counter(
                    (
                        verdict(r["verdict"])
                        for r in git.get("nightly", [])
                        if verdict(r["verdict"]) is not None
                    ),
                ),
            ),
        },
        "scorecard": {"score": (full["scorecard"] or {}).get("score")},
        "sources": {
            "files": sum(sources[k] for k in ("transcript_files", "subagent_files", "codex_files")),
            "malformed_lines": sources["malformed_lines"] + sources["codex_malformed_lines"],
            "skipped_records": sum(full["sources"]["skipped_types"].values()),
        },
    }


def numeric(value: object, prefix: str = "") -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    if isinstance(value, dict):
        for k, v in sorted(value.items()):
            result.update(numeric(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result[prefix] = value
    return result


def trend(current: Path, history: Path, window: int) -> dict[str, Any]:
    now = json.loads(current.read_text(encoding="utf-8"))
    records = []
    skipped = []
    for path in sorted(history.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            date.fromisoformat(record["date"])
            if record["date"] < now["date"]:
                records.append((record["date"], path.name, numeric(record)))
        except (OSError, ValueError, KeyError, TypeError):
            skipped.append(path.name)
    chosen = sorted(records)[-window:]
    result = {}
    for key, value in numeric(now).items():
        values = [r[2][key] for r in chosen if key in r[2]]
        mean = sum(values) / len(values) if values else None
        result[key] = {
            "current": value,
            "mean": round(mean, 3) if mean is not None else None,
            "n": len(values),
            "delta": round(value - mean, 3) if mean is not None else None,
        }
    return {"metrics": result, "skipped": skipped}


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError(message)


def write(path: Path, value: object) -> None:
    def clean(v: object) -> object:
        if isinstance(v, str):
            return redact(v)
        if isinstance(v, dict):
            return {redact(str(k)): clean(x) for k, x in v.items()}
        if isinstance(v, list):
            return [clean(x) for x in v]
        return v

    serialized = json.dumps(
        clean(value), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False
    )
    # Reparse after the final serialized pass to guarantee valid JSON.
    serialized = redact(serialized, truncate=False)
    json.loads(serialized)
    path.write_text(serialized + "\n", encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = Parser(description=__doc__)
        commands = parser.add_subparsers(dest="command", required=True)
        c = commands.add_parser("collect")
        for flag in (
            "date",
            "until",
            "codex-repo",
            "repo",
            "evaluate-workflow",
            "evaluate-job",
            "nightly-workflow",
        ):
            c.add_argument("--" + flag, required=flag == "date")
        for flag in ("transcripts", "codex-dir", "metrics-output"):
            c.add_argument("--" + flag, type=Path, required=flag == "transcripts")
        c.add_argument("--signal-tools", default=",".join(sorted(SIGNAL_TOOLS)))
        c.add_argument("--utc-offset", default="-05:00")
        c.add_argument("--budget-minutes", type=float, default=30)
        c.add_argument("--no-github", action="store_true")
        c.add_argument("--no-scorecard", action="store_true")
        t = commands.add_parser("trend")
        t.add_argument("--current", type=Path, required=True)
        t.add_argument("--history", type=Path, required=True)
        t.add_argument("--window", type=int, default=5)
        for p in (c, t):
            p.add_argument("--output", type=Path, required=True)
        # argparse treats negative offsets as options unless attached with '='.
        arguments = list(sys.argv[1:] if argv is None else argv)
        if "--utc-offset" in arguments:
            i = arguments.index("--utc-offset")
            if i + 1 < len(arguments):
                arguments[i : i + 2] = ["--utc-offset=" + arguments[i + 1]]
        args = parser.parse_args(arguments)
        if args.command == "collect":
            if args.codex_dir and not args.codex_repo:
                raise ValueError("--codex-dir requires --codex-repo")
            if (not args.no_github or not args.no_scorecard) and not args.repo:
                raise ValueError("--repo required for external sources")
            if args.evaluate_workflow and not args.evaluate_job:
                raise ValueError("--evaluate-workflow requires --evaluate-job")
            if args.budget_minutes <= 0:
                raise ValueError("budget must be positive")
            full = collect(args)
            write(args.output, full)
            if args.metrics_output:
                write(args.metrics_output, metrics(full))
        else:
            if args.window < 1:
                raise ValueError("window must be positive")
            write(args.output, trend(args.current, args.history, args.window))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print("ERROR: " + redact(" ".join(str(error).splitlines())), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
