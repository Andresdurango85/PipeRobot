# Agent harness: transcripts, session logs and the retro collector

Facts about the Claude Code and Codex files that the daily retrospective reads
([ADR 0042](../decisions/0042-daily-retrospective-report-only.md)). Both formats are internal to
their tools, not public APIs. Re-check them when a tool updates and the collector's skipped or
malformed counts jump.

- **Claude Code keeps one JSONL transcript per session** in
  `~/.claude/projects/<slug>/<sessionId>.jsonl`. The slug is the start directory with
  separators turned into `-`, e.g. `c--Users-<user>-PipeRobot`.
  - Subagents write `<sessionId>/subagents/agent-<id>.jsonl` next to it.
  - Sessions started in the main clone keep this slug when they work in other worktrees, so one
    directory holds the project.
  - Every line is an object with a `type`; about 20 types were seen. Only `user`, `assistant`,
    `system`, `attachment`, `agent-name` and `custom-title` are needed for the retro.
  - Several types hold whole prompts, instructions or file contents and must never be copied:
    `api-request`, `api-request-blob`, `last-prompt`, `file-history-*`, and `attachment`s such
    as `instructions` and `prompt_snapshot`.

  _(verified 2026-11-07, Claude Code 2.1.294, Windows)_
- **The fields that classify a turn**:
  - `user.origin.kind` is `human`, `peer` (a cross-session message; its text carries
    `<cross-session-message from="..." from-name="...">`) or `task-notification`. Some records
    only have `turnOrigin`.
  - `user.toolDenialKind` (e.g. `automode-blocked`) and `user.permissionDecision.decision ==
    "reject"` mark denials.
  - `tool_result` blocks carry `is_error`.
  - `system` records with `subtype: compact_boundary` mark compactions.
  - `agent-name` records carry the session's display name.
  - A hook that fails without blocking leaves an `attachment` of type
    `hook_non_blocking_error`, with `hookName`, `command`, `exitCode` and `stderr`.

  _(verified 2026-11-07, Claude Code 2.1.294)_
- **Codex keeps one JSONL per session** in `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`, for
  every project together. Lines are `{timestamp, type, payload}`.
  - `session_meta.payload.git.repository_url` names the repository, so filter on that: the
    `cwd` of a worktree or of a sibling clone looks alike.
  - `event_msg` with `payload.type == "task_complete"` marks a finished `codex exec`.
  - `session_meta.payload.base_instructions` and the `response_item` messages hold full prompts:
    never copy them.

  _(verified 2026-11-07, codex-cli 0.166.0)_
- **The collector's date window uses a fixed UTC offset**, `--utc-offset`, default `-05:00`.
  Python's `zoneinfo` has no time-zone database on Windows unless the `tzdata` package is
  installed: `ZoneInfo("America/Bogota")` raises `ZoneInfoNotFoundError` in this repository's
  venv. Bogotá: no DST since 1993; revisit if the scheduler ever runs elsewhere.
  _(verified 2026-11-07, CPython 3.12.12, Windows)_
- **Headless runs for a scheduled retro** ([ADR 0045](../decisions/0045-daily-retrospective-phase-2-window-and-watchdog.md)):
  - `claude -p "/retro 2026-11-09"` expands a project skill from `.claude/skills/` and passes the
    rest of the line as arguments. Do not add `--bare`: it skips skill discovery and OAuth.
  - `--permission-mode dontAsk`: reads in the working and `--add-dir` directories, plus whatever
    `--allowedTools` or `permissions.allow` pre-approve, run; everything else is denied, and the
    run goes on without waiting. `bypassPermissions` is documented for isolated containers and VMs
    only. Bash rules match by prefix: `Bash(git diff *)`, where the space before `*` matters.
  - Since v2.1.302, `-p` with no mode starts in Manual (`default`) mode; denied calls continue.
    `--output-format stream-json --verbose` reports denials as `permission_denied` events and
    in the result's `permission_denials`.
  - Exit code 0 on success, non-zero on failure; a failure inside the run, such as missing
    authentication, prints as the result on stdout. `-p` stops background work after 10 minutes
    idle (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`).
  - Authentication: `ANTHROPIC_API_KEY`, when set, wins over `CLAUDE_CODE_OAUTH_TOKEN`
    (`claude setup-token`, one year) and `/login`, so an API key in the task's environment bills
    the API, not the subscription.
  - Not documented: how compound commands (`&&`, `|`) match allow rules, the exit code when
    `--max-turns` ends a run, and whether a Task Scheduler task inherits the user's PATH and
    can read `%USERPROFILE%\.claude\.credentials.json`. Use the absolute path to `claude.exe`,
    and check the first scheduled run by hand.

  _(verified 2026-11-10, code.claude.com/docs/en: headless, permission-modes, cli-reference,
  skills, authentication)_
