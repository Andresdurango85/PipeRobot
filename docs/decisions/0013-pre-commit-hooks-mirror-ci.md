# 0013. Git hooks with pre-commit; pre-push mirrors CI in a clean environment

- Status: Accepted
- Date: 2026-10-27

## Context

PR #6 failed in CI because a test imported `numpy` before skipping on a missing `lerobot` extra.
It passed locally, because the laptop has the extra (and numpy) installed. Feedback from CI takes
minutes and a round trip; the same check locally takes seconds. A plain local `pytest` would not
have caught it: the bug only shows in an environment without the extra.

## Decision

- Use the [pre-commit](https://pre-commit.com) framework (Python's equivalent of Husky), pinned in
  the uv `dev` group. Hooks are `repo: local` and call tools through `uv run --locked`, so versions
  come from `uv.lock`, the same ones CI uses; no second list of versions to keep in sync.
- **On commit** (staged files only, ~1 s): `ruff check --fix`, `ruff format`, and `uv lock --check`
  when `pyproject.toml` or `uv.lock` change.
- **On push** (whole repo, ~5 s): the `lint-and-test` CI job: `ruff check .`,
  `ruff format --check .`, and `pytest` under `uv run --isolated --locked`, a throwaway environment
  with only the default dependencies, like CI.
- Each clone installs the hooks once with `uv run pre-commit install` (both hook types, from
  `default_install_hook_types`). Agents never skip them (`--no-verify`).
- CI stays the authoritative gate; hooks are a fast local copy of it.

## Alternatives considered

- Husky / lint-staged: need Node.js in a Python repo.
- Lefthook or prek (a faster pre-commit reimplementation): fine tools, but pre-commit is the
  standard most Python contributors already know; prek reads the same config if speed matters later.
- Hooks pulling ruff from `astral-sh/ruff-pre-commit`: a second ruff version pinned outside
  `uv.lock` that can drift from CI.
- Plain `pytest` on pre-push: misses the exact class of bug that motivated this ADR.

## Consequences

- The numpy bug is caught before pushing (mutation-checked: plain `pytest` passed, the pre-push
  hook failed with `ModuleNotFoundError`).
- Pushing costs ~5 s more. Committing reformats files; re-stage and commit again.
- Hooks are not installed by cloning: the home PC setup must run `uv run pre-commit install`.
- When the CI job changes, update the pre-push hooks in the same PR.
