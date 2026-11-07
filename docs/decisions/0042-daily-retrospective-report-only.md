# 0042. Daily retrospective, phase 1: report only

- Status: Accepted
- Date: 2026-11-07

## Context

Several Claude Code sessions (an orchestrator and named workers) and Codex
([ADR 0023](0023-codex-writes-code-claude-reviews.md)) work on this repository every day. When
something goes wrong, the fix usually lands in that day's work and the lesson stays in one
session's transcript. Examples from 2026-11-05 to 2026-11-07:

- the git hooks pointed at a removed worktree's `prek` ("prek: not found"), so commits went
  through `uv run git commit`;
- a Codex sandbox left directories with locked ACLs;
- the auto-mode classifier denied a downloaded binary;
- a cron that only lives as long as its session;
- an ADR reason that had gone stale;
- a gendered pronoun in a doc;
- a CI failure only on Linux.

Nobody counts these, so nobody sees which ones repeat.

Andrés asked for a daily retrospective that evaluates how the model, the harness and our
processes work, and proposes improvements, with evidence. Constraints:

- The evidence lives in Claude Code transcripts and Codex session logs on the home PC. They hold
  whole prompts, instructions, tool output and possibly secrets.
- The transcript format is internal to Claude Code and not a public API; it can change with any
  release.
- This repository is public. Working detail about sessions belongs in the private repository
  `piperobot-private`, next to the business plan.
- A process that changes its own rules or permissions without review would undo the guardrails
  in `AGENTS.md`.

## Decision

**Split.**

- The tooling is generic and lives in this repository:
  - the skill `.claude/skills/retro/SKILL.md`;
  - its collector `.claude/skills/retro/retro_collect.py`;
  - tests on synthetic fixtures only.
- Machine values (the transcripts directory, the Codex sessions directory, the private clone)
  come from arguments and environment variables. They are set in the gitignored
  `CLAUDE.local.md`.
- Reports go to `piperobot-private`, never here:
  - `retro/reports/<date>.md`;
  - `retro/metrics/<date>.json`;
  - an improvement log `retro/improvements.md`.

**A deterministic collector, then judgement.** The collector is standard-library Python. For
one local day (or a range), it reads:

- this project's Claude Code transcripts;
- the Codex sessions for this repository (matched by the session's git remote, not its
  directory);
- GitHub through `gh`;
- the Scorecard API.

It writes a JSON of metrics, incidents and correction candidates.

- **Schema**: it reads an allowlist of record types; everything else is counted and skipped
  unread. The format assumptions sit in one documented section of the script, so format drift
  shows up as skipped and malformed counts, not crashes.
- **Redaction**: it drops `<system-reminder>` and instruction-file content, redacts token
  patterns and e-mail addresses, and only then truncates every excerpt to 300 characters. It
  never writes raw transcript text.
- **Judgement**: the session running the skill reads that JSON, the trend against the trailing
  five days, the last five reports and the improvement log. It writes the report: the top three
  problems, each with evidence, a root cause and one proposed fix.
- **What counts as a correction**: human messages, and the orchestrator's peer messages, since
  Andrés's corrections reach workers through it.

**Risk classes for proposed fixes:**

| Class | What it may change |
| --- | --- |
| Low | `docs/knowledge/` and other docs |
| Medium | Skills, hooks, scripts |
| High | `AGENTS.md` rules, permissions, rulesets, `CLAUDE.md`, settings |

High-risk fixes are never applied by an agent.

**Phase 1 applies nothing.** It runs by hand, once a day, for three to four days, and only
reports. Guardrails, written into the skill:

- never touch permissions, settings, `CLAUDE.md` or rulesets;
- never bypass hooks;
- never self-approve a medium- or high-risk change;
- one run per day;
- metrics are diagnostics, not targets: changing what is measured needs Andrés's OK.

Each day's report and metrics go into `piperobot-private` through a pull request merged at once.
The pull request is opened from a fresh branch off an up-to-date `main`, with the personal
account. Andrés's standing authorization covers only these report pull requests.

## Alternatives considered

- **Let the model read the raw transcripts.** Rejected:
  - it is not repeatable;
  - it spends most of the context on noise;
  - it puts secrets and instruction text one step from a committed report.
- **Reports in this repository.** Rejected: they describe working detail and machine setup that
  do not belong in a public repository.
- **A GitHub Actions workflow.** Rejected: the transcripts exist only on the home PC.
- **An off-the-shelf usage-analytics tool.** Rejected: none reads both Claude Code and Codex
  logs and joins them with CI. Each would send transcript data to another service.
- **Apply low-risk fixes automatically from day one.** Deferred: three to four days of reports
  first show whether the findings are right before anything acts on them.

## Consequences

- Each day costs one skill run and one private pull request. The first run covers 2026-11-05 to
  2026-11-07, so it catches the incidents listed above (the acceptance check).
- A Claude Code update can change the transcript format. The collector keeps working, but its
  counts can fall to zero. The report must call out a jump in skipped or malformed records
  before trusting the numbers.
- The metrics JSON holds numbers and short labels only, so the trend is computed, not re-read
  from prose.
- The date window uses a fixed UTC offset (Bogotá, no DST), because Python's `zoneinfo` has no
  time-zone database on Windows without an extra package.
- Phase 2 needs a new ADR. Candidates are a scheduler, and applying low-risk fixes after
  review.
