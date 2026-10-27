# CI (GitHub Actions)

## Current workflows

- **`ci.yml`**: ruff + pytest on `ubuntu-latest`, no GPU, no LeRobot; ~7 s per run.
  _(verified 2026-10-26, run 40439823769)_
- **`dependency-review.yml`**: fails a PR that adds a dependency with a high or critical
  advisory. **CodeQL** runs as GitHub's default setup (no workflow file; Settings → Code security).
  Both are merge gates ([ADR 0011](../decisions/0011-free-security-gates.md)).
- `pr-gate.yml` (GPU, self-hosted runner on the home PC) and `nightly.yml` (larger baseline) do
  not exist yet; see [`../STATUS.md`](../STATUS.md).

## Local hooks

- **`pre-commit` hooks mirror CI** ([ADR 0013](../decisions/0013-pre-commit-hooks-mirror-ci.md)):
  ruff on commit; on push, ruff on the whole repo plus `pytest` under `uv run --isolated --locked`
  (fresh env without the `lerobot` extra, like CI), ~5 s. Install once per clone with
  `uv run pre-commit install`. _(verified 2026-10-27, pre-commit 4.7, uv, Windows laptop)_
- **`uv run --isolated --locked` is the cheap way to reproduce the CI environment**: it builds a
  throwaway env from `uv.lock` (default deps only, from uv's cache) in ~4 s.
  _(verified 2026-10-27)_
- **Use `uv add --dev <pkg> --no-sync` on a machine with extras installed**, then
  `uv sync --extra lerobot`; a plain sync installs only the default deps.
  _(verified 2026-10-27)_

## Repository rules

- **`main` is protected by the ruleset `main`** ([ADR 0010](../decisions/0010-main-branch-ruleset.md)).
  Required check names are the job names (`lint-and-test`, `dependency-review`): renaming a job
  requires updating the ruleset. Inspect it with `gh api repos/Andresdurango85/PipeRobot/rulesets`.
- **The owner cannot approve his own PRs**, including those opened by agents with his account;
  merge them with the admin bypass (`gh pr merge <n> --admin`). _(GitHub behaviour, 2026-10-27)_

## Gotchas

- **A machine with the `lerobot` extra hides missing-import bugs in the lint/test job.** A test
  that imported `numpy` before `pytest.importorskip("lerobot...")` passed locally and failed in CI
  (no numpy there). Reproduce the CI environment in a throwaway venv before pushing tests that
  touch optional dependencies:
  `UV_PROJECT_ENVIRONMENT=<tmp-dir> uv sync --locked && UV_PROJECT_ENVIRONMENT=<tmp-dir> uv run --no-sync pytest`.
  _(verified 2026-10-27, PR #6)_

- **Stacked PRs: merge the second only after GitHub retargets it to `main`.** PR #2 was based on
  PR #1's branch; merging #2 seconds after #1 merged it into #1's branch, not `main`, and it had to
  be re-landed as #3. GitHub retargets the second PR when the first PR's branch is deleted, which
  now happens automatically (`delete_branch_on_merge`). Prefer a single PR when practical.
  _(verified 2026-10-27, PRs #1–#3)_

- **`astral-sh/setup-uv@v6` runs on Node 20, which GitHub has deprecated**; it is forced onto
  Node 24 with an annotation. Latest release is v10.3.2 (2026-10-22); bump in its own PR and check
  whether inputs such as `enable-cache` changed. _(verified 2026-10-26, run annotations, GitHub releases)_
- **`ubuntu-latest` moves to Ubuntu 26 from 2026-10-19.** No impact today because uv pins Python
  3.12 itself. _(verified 2026-10-26, run annotations)_
- **The golden-file test needs LF endings everywhere**, enforced by `.gitattributes`
  ([ADR 0007](../decisions/0007-lf-line-endings.md)). _(verified 2026-10-26)_
- **Editing the sticky PR comment needs `pull-requests: write`** in the workflow permissions
  ([ADR 0008](../decisions/0008-sticky-pr-comment-and-golden-file.md)). Not yet exercised.
