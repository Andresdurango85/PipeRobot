# 0045. Daily retrospective, phase 2: complete-day windows, a watchdog, then a schedule

- Status: Accepted
- Date: 2026-11-10

## Context

Phase 1 of the daily retrospective ([ADR 0042](0042-daily-retrospective-report-only.md)) ran by
hand twice:

- on 2026-11-07 for 2026-11-05..2026-11-07;
- on 2026-11-10 as a catch-up for 2026-11-08..2026-11-09.

Two failures showed up, and neither is about the collector:

1. **A day was skipped.** Nothing fired Monday 2026-11-09's run. Phase 1 is triggered from memory,
   and the only scheduler available to a session (a session cron) dies with its session, which
   ADR 0042 already listed as a weakness. The miss was found only when Andrés asked what had
   happened.
2. **A same-day run loses the evening.** The 2026-11-07 run covered "today" and was committed at
   13:21 local. That evening's incidents were never reported, including the weekend's costliest
   one, a GPU idle for about 1 h 41 min with work queued. Any run at 17:45 for "today" drops
   17:45 to 24:00 by design.

ADR 0042 named two candidates for phase 2: a scheduler, and applying low-risk fixes after review.

What a scheduler can use (Claude Code docs, verified 2026-11-10, see
[harness.md](../knowledge/harness.md)):

- The transcripts exist only on the home PC, so cloud routines (`/schedule`) and GitHub Actions
  cannot run the collector.
- `claude -p "/retro"` runs a project skill headless.
- `--permission-mode dontAsk` denies anything not pre-approved and never waits for input.
- `bypassPermissions` is documented for isolated containers and VMs only.
- How Windows Task Scheduler interacts with the user's PATH and login credentials is not
  documented.

## Decision

Phase 2 has three parts. The first two apply now; the third waits for Andrés.

1. **Windows are complete local days, never today.** By default a run covers the day after the
   latest report through yesterday, and its files are named by the window's last day. So a
   Monday run covers Saturday and Sunday, and a missed day is caught up by the next run. "One run
   per day" stays: a run with an empty window stops. This replaces ADR 0042's "today" default;
   its other decisions stand. Implemented in the retro skill's text.
2. **A watchdog that does not depend on the machine it watches.** A scheduled GitHub Actions
   workflow in `piperobot-private` runs every weekday at about 10:00 Bogotá. If the newest
   `retro/reports/<date>.md` on `main` is older than yesterday, it opens or updates one
   `retro-missing` issue, which notifies Andrés. It needs only `contents: read` and
   `issues: write`. It works even when the PC is off, which was Monday's failure mode. A missing
   report is a signal for Andrés or the orchestrator, not something the watchdog fixes.
3. **A local schedule, set up by Andrés.** Windows Task Scheduler runs `claude -p "/retro"` on
   weekday mornings in the PipeRobot clone, with:
   - `--permission-mode dontAsk`, never `bypassPermissions`;
   - an explicit allow list for the commands the skill runs: `uv run python
     .claude/skills/retro/...`, `git` in the private clone, and `gh pr create`/`gh pr merge` on
     `piperobot-private`;
   - `--add-dir` for the transcripts directory and the private clone;
   - stdout and stderr logged to a file.

   Creating the task, its allow list and its authentication is a settings and permissions
   change, which is high risk under ADR 0042, so Andrés does it. Agents only document the
   commands, in [harness.md](../knowledge/harness.md). The first scheduled run is checked by
   hand: the report, its window and any `permission_denials`.

**Out of scope:** applying low-risk fixes automatically stays deferred. Andrés approves each
proposal, as he did on 2026-11-10 for R-2026-11-09-1..6. That has worked, and it is cheap.

## Alternatives considered

- **Keep running by hand.** That is what failed on Monday.
- **A session cron in the orchestrator.** It dies with the session; useful only as a reminder
  while one is open.
- **Run for "today" at night, for example at 23:30.** It still misses whatever happens after the
  run, and it depends on the PC being on late. Covering yesterday each morning has no gap.
- **Cloud routines or a GitHub Actions run of the retro itself.** Neither can read the
  transcripts, which never leave the home PC (ADR 0042).
- **Claude desktop scheduled tasks.** They run on the computer and may be simpler than Task
  Scheduler, but their behaviour for an unattended Windows run is not verified. This is a
  candidate if Task Scheduler's authentication or PATH turns out to be a problem.
- **`bypassPermissions` for the scheduled run.** It is simpler, but the docs limit it to isolated
  machines, and this PC holds the employer's credentials and Andrés's apps.

## Consequences

- Reports describe complete days, and consecutive windows meet with no gap. The first run under
  the new default is 2026-11-11, for 2026-11-10.
- A Monday report covers three days, and the previous file can cover a different number of days.
  So `retro_collect.py trend` normalizes per day (retro proposal R-2026-11-09-6).
- The watchdog is a second workflow in the private repository. A false alarm can come from a
  holiday or an intentional skip; the issue is then closed with a reason.
- Until Andrés sets up the schedule, the orchestrator runs the retro each weekday morning, or
  Andrés asks for it, and the watchdog catches a miss either way.
- Watch: the scheduled run's permission denials. A denied `gh` or `git` call leaves a report
  unpublished, and the watchdog reports it the next morning.
