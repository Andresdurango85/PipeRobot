# 0027. Self-hosted jobs run on push only, behind a runner-side hook; actions pinned by SHA

- Status: Accepted
- Date: 2026-11-02

## Context

[0020](0020-self-hosted-gpu-runner.md) put a self-hosted GPU runner on the home PC and let
`gpu-smoke` run on `pull_request`, guarded by a job-level `if:` that skips fork and Dependabot PRs.
A `pull_request` workflow runs the YAML of the PR head, so a fork can delete that `if:`. Moving our
workflow to `push` does not close the path either: a fork PR can **add** its own workflow with
`on: pull_request` and `runs-on: [self-hosted, Windows, gpu]`. Until now the only barrier was the
repo setting "require approval for all external contributors".

The hard fix GitHub offers, a runner group limited to selected workflows, exists only for
organizations; this repo belongs to a personal account. The runner application does offer
job-started hooks: the script named in `ACTIONS_RUNNER_HOOK_JOB_STARTED` runs before every job,
and if it exits non-zero the job fails and none of its steps run. The script lives on the runner
machine, out of reach of any workflow file.

Separately, every action was referenced by a movable tag (`@v7`). A moved or hijacked tag would
run new code on the home PC and in every job with a token. Dependabot's github-actions ecosystem
updates SHA pins that carry a `# vX.Y.Z` comment. It had also stalled on `astral-sh/setup-uv@v7`:
setup-uv stopped publishing floating major tags after v7 (only `v8.0.0` … `v10.3.3`), so there was
no `v8`/`v10` tag for Dependabot to move to.

## Decision

1. **Self-hosted workflows are triggered only by `push`, `workflow_dispatch` or `schedule`.**
   `gpu-smoke` moves from `pull_request` to `push` on this repo's branches (except
   `dependabot/**`, and only when the code it exercises changes: `piperobot/`, `robots/pusht/`,
   `pyproject.toml`, `uv.lock`, the workflow itself), plus `workflow_dispatch`. Forks cannot push
   here. Its job keeps a repository guard and the Dependabot actor guard. The check still shows on
   the PR, because it runs on the PR's head commit. This replaces 0020's rule "GPU workflows use
   `pull_request` and `workflow_dispatch`"; the rest of 0020 stands.
2. **A job-started hook on the runner refuses everything else.**
   `.github/runner/job-started.ps1` allows a job only if the repository is
   `Andresdurango85/PipeRobot`, the event is `push`, `workflow_dispatch` or `schedule`, and
   `GITHUB_WORKFLOW_REF` names one of the allowlisted self-hosted workflow files on a
   `refs/heads/*` ref. The tracked file is the reviewed source; the live copy is installed by hand
   on the runner machine in a folder the runner's user can only read, and named in the runner's
   `.env` ([ci.md](../knowledge/ci.md)). Adding a self-hosted workflow means updating the
   allowlist and redeploying the live copy. The approval setting for external contributors stays
   on as a second layer.
   The runner folder `C:\actions-runner` stops inheriting from `C:\`, where "Authenticated Users"
   had Modify and "Users" had read: every local account, the Codex sandbox users included, could
   rewrite the runner's binaries and `.env` and read its credentials. Only SYSTEM,
   Administrators, the runner's user (`gh-runner`, Modify, needed for self-update and `_work`) and
   the service group that `config.cmd` created keep access; the owner reads `_diag` only. `.env`
   is read-only for `gh-runner`.
3. **Every action is pinned by full commit SHA** with a `# vX.Y.Z` comment, at the commit its
   floating tag pointed to (no behaviour change). Dependabot proposes updates; a new release
   waits 7 days (`cooldown`) before it is proposed. After this merges, the repo's Actions
   settings allow only GitHub-owned actions plus the listed third-party ones, and require SHA
   pinning.
4. **zizmor** (a static security linter for GitHub Actions workflows) runs in CI on every PR and
   push to `main` with its online audits, and in the git hooks offline
   ([0013](0013-pre-commit-hooks-mirror-ci.md)). It is a dev dependency in `uv.lock`
   ([0002](0002-python-tooling-and-pinning.md)). A finding is fixed, or ignored inline with the
   reason.
5. **OpenSSF Scorecard** runs weekly and on push to `main`, uploads SARIF to code scanning and
   publishes its score (badge in the README). It is a posture report, not a gate.
6. `tests/test_workflows.py` checks the invariants on our own workflows: self-hosted jobs only on
   the allowed triggers and the `gpu` label, the hook's allowlist equals the set of self-hosted
   workflows, every `uses:` is SHA-pinned with a version comment, every checkout sets
   `persist-credentials: false`, and the hook's allow/refuse decisions.

## Alternatives considered

- Keep `pull_request` with the `if:` guard: the guard lives in the file a fork controls.
- A runner group restricted to selected workflows: the real fix, but only for organizations.
  Moving the repo into a free organization is possible later, if outside contributors appear.
- `--ephemeral` or just-in-time runners in a container: still the path if the runner must ever
  serve untrusted code (0020); not available for Isaac's rendering on Windows.
- Only the approval setting: one click by the owner on a fork PR would run its workflows on the
  home PC.
- Pin by tag and rely on immutable releases: not every action we use publishes immutable
  releases, and a tag can still be repointed where they are not.

## Consequences

- A fork PR cannot run a step on the home PC even if the owner approves its workflows: the hook
  fails the job first. A collaborator with push access can still run code there, by design.
- The hook only protects if its live copy is installed, current, and not writable by the
  runner's user. The rest of `C:\actions-runner` stays writable by that user, so a job that
  passes the hook could change the runner itself. Accepted: only trusted jobs get past the hook.
- Re-running `config.cmd` or editing the runner's files now needs an elevated shell.
- `gpu-smoke` now runs on every qualifying push, PR or not, and no longer runs on doc-only
  changes. It tests the head commit, not the PR's merge commit.
- Dependabot will now propose setup-uv v10 and other majors as SHA bumps; each one is reviewed as
  a code change, and lands at least 7 days after its release.
- Required checks are set in the ruleset by hand; `zizmor` is not required until Andrés adds it.
