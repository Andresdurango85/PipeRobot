---
name: retro
description: Daily retrospective for PipeRobot (report only). Collects the complete days since the last report (through yesterday) of Claude Code, Codex, GitHub and Scorecard evidence with retro_collect.py, writes a redacted report and metrics to the private repo through a pull request, and proposes fixes without applying any. Use when asked for the retro, retrospective, "retro del día", or "/retro [date]".
---

# Daily retrospective (report only)

Goal: once a day, find the three problems that cost the most in how the model, the harness and our
processes worked, with evidence. For each one, propose one fix and its risk. Do not apply any
fix. Decision and reasons: [ADR 0042](../../../docs/decisions/0042-daily-retrospective-report-only.md).

## Guardrails (read first, never relax)

- The retro applies **no** fix (ADR 0042; ADR 0045 keeps that). You write a report, a metrics
  file and the improvement log, in the private repository, and nothing else.
- Never touch permissions, `settings*.json`, `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`,
  rulesets or repository settings. Never bypass hooks (`--no-verify`, `core.hooksPath`).
- Never approve your own medium- or high-risk proposal; they go to Andrés.
- Metrics are diagnostics, not targets. Do not change what is measured, or how, without
  Andrés's OK.
- One run per day. If `retro/reports/<date>.md` already exists in the private repo, stop and say
  so.
- Only redacted collector output goes into the report: never paste raw transcript text, tool
  output or secrets. Quote incidents by their excerpt and reference (session, timestamp).
- Public/private split: nothing from the report goes into the public PipeRobot repo.

## Inputs

These come from the machine's `CLAUDE.local.md` or the environment; never hard-code them here:

| Variable | What |
| --- | --- |
| `PIPEROBOT_RETRO_TRANSCRIPTS` | This project's Claude Code transcripts directory (`~/.claude/projects/<slug>`). Never another project's. |
| `PIPEROBOT_RETRO_CODEX` | Codex sessions directory (`~/.codex/sessions`), optional |
| `PIPEROBOT_RETRO_REPORTS` | Local clone of `Andresdurango85/piperobot-private` |

The window is complete local days, never today
([ADR 0045](../../../docs/decisions/0045-daily-retrospective-phase-2-window-and-watchdog.md)).
By default it runs from the day after the latest `retro/reports/<date>.md` through yesterday, in
America/Bogota: `--date` is the first day, `--until` is yesterday, and `<date>` in every file
name is the window's last day. A Monday run therefore covers Saturday and Sunday, and a missed
day is caught up by the next run. The caller may give a day (`/retro 2026-11-07`) or a range
(`2026-11-05..2026-11-07`) instead. If the window would be empty (yesterday already reported),
stop and say so. `gh` runs with the personal account's token (`GH_TOKEN`, see
`CLAUDE.local.md`), never the employer's.

## Steps

1. **Collect.** From the PipeRobot clone, write the output to a scratch directory outside both
   repositories:

   ```
   uv run python .claude/skills/retro/retro_collect.py collect \
     --date <date> [--until <date>] \
     --transcripts "$PIPEROBOT_RETRO_TRANSCRIPTS" \
     --codex-dir "$PIPEROBOT_RETRO_CODEX" --codex-repo Andresdurango85/PipeRobot \
     --repo Andresdurango85/PipeRobot \
     --evaluate-workflow so101-gate.yml --evaluate-job evaluate --budget-minutes 30 \
     --nightly-workflow nightly.yml \
     --output <scratch>/retro-<date>.json --metrics-output <scratch>/<date>.json
   ```

   Check `sources` first. If `malformed_lines` or a skipped type jumped compared with earlier
   runs, or a count you expect (`user_messages`, `tool_calls`) is zero, the transcript format
   may have changed. Say so at the top of the report and trust the numbers less.

   The incidents are leads, not verdicts:
   - `output_signal` and text-detected `hook_failure` incidents come from pattern matches on
     shell output. A command that greps logs or transcripts (including an earlier retro's)
     matches too: check the excerpt before you count it.
   - `hook_non_blocking_error` incidents are deduplicated with a `count`.
   - A session without an `agent-name` shows as its id prefix.

2. **Read the history.** Run `git -C "$PIPEROBOT_RETRO_REPORTS" switch main` and
   `git -C "$PIPEROBOT_RETRO_REPORTS" pull --ff-only`. Then:
   - read the last 5 files in `retro/reports/` and all of `retro/improvements.md`;
   - run `retro_collect.py trend --current <scratch>/<date>.json --history
     "$PIPEROBOT_RETRO_REPORTS/retro/metrics" --window 5 --output <scratch>/trend-<date>.json`.

3. **Write `retro/reports/<date>.md`** in the private clone, in English, with these sections:
   - **Metrics vs trailing average**: a table from the trend output; only metrics that moved, or
     that matter, with current, mean, n and delta. Include Scorecard and the SO-101 evaluate time
     against the 30-minute budget.
   - **Top 3 problems**, ranked by cost (time lost, rework, risk). For each:
     - the evidence: incident references `session @ timestamp (kind)`, with redacted excerpts;
     - the root cause: why it happened, not what happened;
     - one proposed fix, classified:
       - **low**: `docs/knowledge/`, other docs;
       - **medium**: skills, hooks, scripts;
       - **high**: `AGENTS.md` rules, permissions, rulesets, `CLAUDE.md`, settings (never applied
         by an agent).
   - **Corrections**: what `correction_candidates` show the maintainer or the orchestrator had to
     correct. You judge which candidates are corrections; most messages are not.
   - **Earlier improvements**: for each open entry in `retro/improvements.md`, whether its metric
     moved, and its new status.
   - **Data quality**: the collector's skipped, malformed and capped counts.

4. **Update the log.** Append each new proposal to `retro/improvements.md` as a table row:
   `id` (`R-<date>-<n>`), date, problem, change, risk, hypothesis, metric, status (`proposed`;
   later `approved`, `applied`, `kept`, `reverted` or `dropped`). Update the status of earlier rows
   from step 3. Copy `<scratch>/<date>.json` to `retro/metrics/<date>.json` (numbers only; never
   the full output).

5. **Publish the report.**
   - In the private clone, create a fresh branch `retro/<date>` from the up-to-date `main`. Never
     commit to its `main` directly.
   - Commit only `retro/` (`Co-Authored-By` trailer as usual) and push the branch.
   - Open a pull request in `Andresdurango85/piperobot-private` with the personal account and
     merge it. Andrés's standing authorization covers these report pull requests only.
   - Never push anything to the public PipeRobot repository in this skill.

6. **Tell Andrés**, in Spanish, in at most 5 lines:
   - the date;
   - the 3 problems, one line each, with the risk class of each fix;
   - anything that needs a decision;
   - the report PR link.
