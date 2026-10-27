@AGENTS.md

## Claude Code specifics

- Start every session by reading `docs/STATUS.md`. End it with the `/handoff` skill
  (`.claude/skills/handoff/`), which updates STATUS, ADRs and knowledge before the PR.
- Machine-specific notes (GitHub accounts, local paths, GPU) live in `CLAUDE.local.md`, which is
  gitignored and loaded automatically. Each machine has its own; never commit it.
- A machine-level memory hub outside the repo, if one exists, only points here. Project know-how
  goes in `docs/`, never only in auto-memory or a hub that the other machine cannot see.
