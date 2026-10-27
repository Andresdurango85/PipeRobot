# 0013. Git hooks with prek; pre-push mirrors CI in a clean environment

- Status: Accepted
- Date: 2026-10-27

## Context

PR #6 failed in CI because a test imported `numpy` before skipping on a missing `lerobot` extra.
It passed locally, because the laptop has the extra (and numpy) installed. Feedback from CI takes
minutes and a round trip; the same check locally takes seconds. A plain local `pytest` would not
have caught it: the bug only shows in an environment without the extra.

The first attempt used the pre-commit framework (Python's usual equivalent of Husky). The
dependency-review gate blocked it: pre-commit pulls `virtualenv`, whose fixed versions need
`packaging>=26.3`, while LeRobot 0.6.1 caps `packaging<26`.

## Decision

- Use [prek](https://prek.j178.dev/), a Rust reimplementation of pre-commit that reads the standard
  `.pre-commit-config.yaml` and ships as a binary with no Python dependencies, pinned in the uv
  `dev` group. Hooks are `repo: local` and call tools through `uv run --locked`, so versions come
  from `uv.lock`, the same ones CI uses.
- **On commit** (staged files only, ~1 s): `ruff check --fix`, `ruff format`, and `uv lock --check`
  when `pyproject.toml` or `uv.lock` change.
- **On push** (whole repo, ~5 s): the `lint-and-test` CI job: `ruff check .`,
  `ruff format --check .`, and `pytest` under `uv run --isolated --locked`, a throwaway environment
  with only the default dependencies, like CI.
- Each clone installs the hooks once with `uv run prek install` (both hook types, from
  `default_install_hook_types`). Agents never skip them (`--no-verify`).
- CI stays the authoritative gate; hooks are a fast local copy of it.

## Alternatives considered

- pre-commit: the standard, but cannot be locked with secure versions next to LeRobot 0.6.1 (see
  Context). The config file is compatible, so switching back is a dependency swap once LeRobot
  lifts its `packaging` cap.
- pre-commit installed per machine with `uv tool install`: outside `uv.lock`, so unpinned and
  invisible to Dependabot and dependency review.
- Husky / lint-staged: need Node.js in a Python repo.
- Lefthook: also a dependency-free binary, but its own config format.
- Hooks pulling ruff from `astral-sh/ruff-pre-commit`: a second ruff version pinned outside
  `uv.lock` that can drift from CI.
- Plain `pytest` on pre-push: misses the exact class of bug that motivated this ADR.

## Consequences

- The numpy bug is caught before pushing (mutation-checked: plain `pytest` passed, the pre-push
  hook failed with `ModuleNotFoundError`).
- prek is younger (0.x) than pre-commit; if it misbehaves, fall back to pre-commit with the same
  config.
- Pushing costs ~5 s more. Committing reformats files; re-stage and commit again.
- Hooks are not installed by cloning: the home PC setup must run `uv run prek install`.
- When the CI job changes, update the pre-push hooks in the same PR.
