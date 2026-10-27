# 0001. Project memory lives in the repo

- Status: Accepted
- Date: 2026-10-26

## Context

Work happens on two machines (see [0005](0005-two-machine-setup.md)) and, soon, with several
agents (Claude Code sessions, subagents, CI agents, possibly Codex). Before this ADR the know-how
was split across a memory hub that exists only on the laptop (and mixes employer work), Claude
Code's per-folder auto-memory (per machine, Claude only), and a `CLAUDE.md` that mixed rules,
context and state. None of it reached the home PC, and only Claude could read most of it.

## Decision

The repo is the single source of truth for project knowledge, split by kind and lifetime:

- `AGENTS.md`: rules and project context for any agent; `CLAUDE.md` imports it.
- `docs/STATUS.md`: current state, next steps and hand-off; rewritten every session.
- `docs/decisions/`: ADRs, immutable, superseded by new ADRs.
- `docs/knowledge/`: verified facts and gotchas, each dated with version and source.
- `CLAUDE.local.md` (gitignored): machine-specific notes.

Memory changes ship in the same PR as the code they describe. Agents propose memory changes
through PRs and never write them straight to `main`. Raw outputs (eval JSON, logs, videos) go to
CI artifacts or the Hugging Face Hub, never to memory. `tests/test_docs.py` checks links and the
ADR format.

## Alternatives considered

- Keep the laptop memory hub: it is not synced, mixes employer data, and cannot go to a personal PC.
- Claude auto-memory only: per machine, Claude-specific, and unreviewed.
- A wiki or Notion: outside the PR flow, so it drifts from the code and agents cannot review it in
  context.
- One big `CLAUDE.md`: grows without bound, mixes stable rules with daily state, and only Claude
  reads it.

## Consequences

- Both machines and every agent read the same knowledge after `git pull`.
- Memory is versioned and reviewed like code; a wrong "fact" needs an approved PR to land.
- The repo is public: nothing secret or employer-related may be written to memory.
- It costs discipline at the end of each session; the `/handoff` skill and the PR template make
  that step cheap and visible.
