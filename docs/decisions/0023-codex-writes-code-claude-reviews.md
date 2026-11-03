# 0023. Codex writes the code; Claude sessions orchestrate and review

- Status: Accepted
- Date: 2026-11-02

## Context

Phase 0 runs several agent sessions at once on the home PC: one orchestrator session that Andrés
talks to, and worker sessions that each own one branch in their own git worktree. Until
2026-11-01 the Claude sessions also wrote the code they reviewed, so the author and the reviewer
were the same model with the same blind spots. Andrés asked for a split: Codex CLI writes the
code, and the Claude sessions brief it and review its diff, like a developer and a QA reviewer.

Codex CLI 0.166 runs on Windows in an elevated sandbox, as separate `CodexSandbox*` users. That
sandbox cannot run `uv`, write git metadata in a worktree, or use the GPU runtime that Isaac Sim
needs ([ci.md](../knowledge/ci.md)).

## Decision

1. **Codex writes the code.** A Claude session writes a brief (goal, files, constraints, tests to
   add, commands to run) into a file and runs
   `codex exec -C <worktree> --sandbox workspace-write -o <report.md> - < <brief.md>`.
2. **Claude sessions review and run what the sandbox cannot**: `uv sync`, the hooks, git, Isaac
   and GPU runs. They read the whole diff, check it against the ADRs and the brief, and either
   send Codex a follow-up brief or make a small fix themselves (a lint error, a path, a missing
   type guard). Larger rework goes back to Codex.
3. **One orchestrator, several workers.** Andrés talks only to the orchestrator session. It
   assigns each worker a branch and a worktree, keeps their files from overlapping, relays
   approval needs to Andrés and reviews each PR before merge. Workers report back to it.
4. **The rules do not change with the author.** Commits, PRs and merges still follow `AGENTS.md`:
   the personal account only, no hook bypass, memory changes in the same PR as the code.

## Alternatives considered

- Claude sessions write and review their own code: faster per change, but the review shares the
  author's assumptions.
- Codex reviews Claude's code: the opposite split. It is possible, but Andrés chose this one, and
  Codex's sandbox cannot run the hooks or the GPU checks that a review needs.
- One session for everything: simpler, but one context fills up quickly on Isaac work and blocks
  parallel branches.

## Consequences

- Every change gets a second model's review before the PR.
- A brief must be written before any code, which costs time on one-line changes. Small fixes by
  the reviewer are allowed for that reason.
- The sandbox recipe in [ci.md](../knowledge/ci.md) (the venv's `home`, `UV_LINK_MODE=copy`,
  pytest's `--basetemp`, cleanup from inside the sandbox) must stay current with Codex releases.
- Session names and who is working on what are per machine and change often; they live in
  `docs/STATUS.md`, not in this ADR.
