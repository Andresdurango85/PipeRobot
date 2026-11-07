---
name: handoff
description: End-of-session ritual for PipeRobot. Updates docs/STATUS.md, writes ADRs for new decisions and dated knowledge entries for verified facts, runs the docs checks, and proposes the commit. Use when the user says handoff, wrap up, end of session, "cerrar sesión", or before opening a PR.
---

# Hand-off

Goal: the next session, on either machine and with any agent, can continue cold from the repo
alone. Follow the memory protocol in `AGENTS.md` (ADR 0001).

1. **Collect what happened.** Review this session's conversation and `git diff main...HEAD`
   plus uncommitted changes. List: work done, decisions made, facts verified, open questions.
2. **Decisions → ADRs.** For each non-trivial decision not yet recorded, copy the template from
   `docs/decisions/README.md` into the next free `NNNN-kebab-title.md`, fill every section, and
   add it to the index table. Never edit an accepted ADR: supersede it with a new one.
3. **Facts → knowledge.** For each non-obvious fact or verified command, add a bullet to the
   right `docs/knowledge/<topic>.md` with `_(verified YYYY-MM-DD, <tool/version>, <source>)_`.
   New topic → new file and a row in `docs/knowledge/README.md`.
4. **Rewrite `docs/STATUS.md`.** Update "Last updated" (date and machine), the Phase 0 table,
   "Done recently" (keep the last ~5), "Next" (ordered, each item actionable cold), and "Open
   questions". Keep it under ~60 lines.
5. **Machine-only notes** (accounts, paths, local GPU) go to `CLAUDE.local.md`, never to `docs/`.
6. **Check.** Run `uv run pytest tests/test_docs.py` and `uv run ruff check .`; fix failures.
   Scan the diff for secrets or employer-related content. Then check that the git hooks still
   point at an existing `prek`. Worktrees share one `.git/hooks`, and a `prek install` run from a
   removed worktree breaks every commit with `prek: not found`:

   ```bash
   hook="$(git rev-parse --git-common-dir)/hooks/pre-push"
   prek="$(sed -n 's/^PREK="\(.*\)"$/\1/p' "$hook")"
   test -x "$prek" || echo "hooks point at a missing prek ($prek)"
   ```

   If it prints anything, do not commit around it (`uv run git` or `--no-verify`). Tell the
   orchestrator or Andrés: the fix is `prek install` from the main checkout, never from a
   worktree ([ci.md](../../../docs/knowledge/ci.md)).
7. **Propose, don't push.** Show Andrés a summary (in Spanish) of the memory changes and the
   suggested commit message. Commit or push only if he asks; memory changes go in the same PR as
   the code.
8. If a machine-level memory hub exists (see `CLAUDE.local.md`), add one log line there pointing
   to the PR or branch, nothing more.
