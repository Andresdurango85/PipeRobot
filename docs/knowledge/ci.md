# CI (GitHub Actions)

## Current workflows

- **`ci.yml`**: ruff + pytest on `ubuntu-latest`, no GPU, no LeRobot; ~7 s per run.
  _(verified 2026-10-26, run 40439823769)_
- **`dependency-review.yml`**: fails a PR that adds a dependency with a high or critical
  advisory. **CodeQL** runs as GitHub's default setup (no workflow file; Settings → Code security).
  Both are merge gates ([ADR 0011](../decisions/0011-free-security-gates.md)).
- **`pr-gate.yml`**: PushT evaluation on CPU (50 fixed-seed episodes) → report (also in the job
  summary) → sticky comment → gate verdict (fails on BLOCK) → artifact `pr-gate-<PR>` with
  results, report and the videos of the first 10 episodes
  ([ADR 0014](../decisions/0014-mock-evaluator-and-pr-gate-workflow.md),
  [ADR 0017](../decisions/0017-pr-gate-pusht-on-github-runners.md)). Runs on `ubuntu-latest` with
  CPU-only torch until the evaluator needs the GPU runner. Fork PRs get no comment (read-only
  token); the report is still in the job summary.
- **`baseline.yml`**: manual (`workflow_dispatch`) run of N episodes on the same runner type, to
  measure a baseline where the gate runs; its counts are committed to `robots/<robot>/baselines/` by PR.
- **`gpu-smoke.yml`**: on every same-repo PR (and by hand), on the self-hosted GPU runner:
  `nvidia-smi`, torch sees CUDA, 50 PushT episodes on CUDA, count and time in the job summary.
  Not required and not a gate ([ADR 0020](../decisions/0020-self-hosted-gpu-runner.md)).
  First run 3 min 3 s (CUDA torch downloaded), warm re-run 2 min 5 s: install 16 s, evaluation
  83 s. _(verified 2026-11-01, run 41345428882, attempts 1 and 2)_
- **`isaac-render.yml`**: on push to `ci/isaac-render` or by hand (never on pull requests), on
  the self-hosted GPU runner: installs Isaac Lab at the pinned commit into the runner's tool cache,
  then runs `robots/so101/tools/isaac_render_check.py` as an empty stage and as one RTX camera
  frame, cold and warm, with VRAM samples and Kit's GPU log lines in the artifact
  ([isaac.md](isaac.md)). _(added 2026-11-01, run 41369455668)_
- `nightly.yml` (larger baseline) does not exist yet; see [`../STATUS.md`](../STATUS.md).

## Local hooks

- **Git hooks mirror CI** ([ADR 0013](../decisions/0013-pre-commit-hooks-mirror-ci.md)), run by
  prek from `.pre-commit-config.yaml`: ruff on commit; on push, ruff on the whole repo plus
  `pytest` under `uv run --isolated --locked` (fresh env without the `lerobot` extra, like CI),
  ~5 s. Install once per clone with `uv run prek install`.
  _(verified 2026-10-27, prek 0.5.7, uv, Windows laptop)_
- **pre-commit (the Python tool) cannot live in our lock with secure versions**: it needs
  `virtualenv>=21.14.9` (four high advisories below that), which needs `packaging>=26.3`, while
  LeRobot 0.6.1 caps `packaging<26`. prek is a Rust binary with no Python dependencies, so it
  avoids the conflict. _(verified 2026-10-27, dependency-review on PR #7)_
- **`uv run --isolated --locked` is the cheap way to reproduce the CI environment**: it builds a
  throwaway env from `uv.lock` (default deps only, from uv's cache) in ~4 s.
  _(verified 2026-10-27)_
- **Use `uv add --dev <pkg> --no-sync` on a machine with extras installed**, then
  `uv sync --extra lerobot`; a plain sync installs only the default deps.
  _(verified 2026-10-27)_

## Repository rules

- **`main` is protected by the ruleset `main`** ([ADR 0010](../decisions/0010-main-branch-ruleset.md),
  [ADR 0018](../decisions/0018-no-required-review-for-the-owner.md): PR and green checks required,
  no approving review).
  Required check names are the job names (`lint-and-test`, `dependency-review`, `pr-gate`):
  renaming a job requires updating the ruleset. Inspect it with
  `gh api repos/Andresdurango85/PipeRobot/rulesets`. _(pr-gate added 2026-10-27)_
- **The owner cannot approve his own PRs**, including those opened by agents with his account.
  With a required review that meant merging through the admin bypass (`gh pr merge <n> --admin`),
  hence ADR 0018. _(GitHub behaviour, 2026-10-27)_
- **With 0 required approvals, PRs merge with a plain `gh pr merge <n> --merge`** once the checks
  pass, and Claude Code's auto mode allows it. "Require review from Code Owners" is still on in the
  ruleset and does not block it. _(verified 2026-10-28, PR #17)_
- **Claude Code's auto mode refuses admin-bypass merges** ("Merge Without Review") even when the
  owner asked in chat and even with a `Bash(gh pr merge:*)` allow rule in
  `.claude/settings.local.json`. It also refuses editing the ruleset through the API ("CI Bypass"):
  Andrés changes rulesets in the GitHub UI.
  _(verified 2026-10-27 on PRs #4 and #8; 2026-10-28 on PRs #11–#13 and the ruleset)_

## Self-hosted runners

- **GitHub says self-hosted runners "should almost never be used for public repositories"**:
  any user can open a PR and compromise the machine, and `--ephemeral` (de-register after one
  job) is only a partial mitigation. Our rules are in
  [ADR 0020](../decisions/0020-self-hosted-gpu-runner.md).
  _(verified 2026-10-28, GitHub docs "Secure use reference")_
- **A fork PR's `pull_request` workflow runs the PR's own workflow files**, so it can target any
  runner label; only the repo's fork approval setting stops it. The options are approval for
  first-time contributors new to GitHub, for first-time contributors, or for all external
  contributors; the first two skip anyone with a merged PR or commit. `pull_request_target` runs
  regardless of the setting. Check it with
  `gh api repos/<owner>/<repo>/actions/permissions/fork-pr-contributor-approval`.
  _(verified 2026-10-28, GitHub docs "Managing GitHub Actions settings for a repository")_
- ~~This repo's fork approval is `first_time_contributors`.~~ _(verified 2026-10-28, API)_
- **This repo's fork approval is `all_external_contributors`**, set by the owner in the UI for
  the GPU runner. _(verified 2026-11-01, API)_
- **The runner app needs only outbound HTTPS on 443** to GitHub's domains, auto-updates by
  default, and stops receiving jobs if not updated within 30 days. A job with no matching online
  runner waits in the queue up to 24 h. Windows 10/11 64-bit and Windows Server are supported.
  _(verified 2026-10-28, GitHub docs "Self-hosted runners reference")_

- **Registering a Windows runner as a service**: `config.cmd --unattended --runasservice
  --windowslogonaccount <PC>\<user> --windowslogonpassword <pw>`. `config.cmd` is a batch file,
  so a password with cmd metacharacters (`& ^ % ! < > |`) arrives altered and the runner reports
  "Invalid windows credentials entered"; an alphanumeric password works. An empty password
  fails with "Invalid configuration provided for windowslogonpassword". Both failures happen
  after the runner is registered, leaving it offline with no service: delete `.runner`,
  `.credentials` and `.credentials_rsaparams` and run `config.cmd` again with `--replace`.
  A 404 from `actions/runner-registration` means the registration token expired (1 h) or is
  not this repo's. _(verified 2026-11-01, runner 2.338.2, Windows 11)_
- **`shell: powershell` on a self-hosted Windows runner is Windows PowerShell 5.1** when `pwsh`
  is not installed: `>>` and `Tee-Object` write UTF-16, so `GITHUB_ENV` and
  `GITHUB_STEP_SUMMARY` are written with `Out-File -Append -Encoding utf8`. The service user has
  no Developer Mode, so `huggingface_hub` warns that it cannot symlink and copies cache files
  instead (harmless). _(verified 2026-11-01, run 41345428882)_

## Gotchas

- **Two sessions must not share one working directory.** A parallel session switched this
  checkout to its own branch mid-task. Each extra session works in its own worktree:
  `git worktree add ../so101-wt-<topic> <branch>`, and `git worktree remove` it afterwards.
  _(verified 2026-10-27)_

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

## Packaging the `piperobot` distribution

- **A flat layout needs `[tool.uv.build-backend] module-root = ""`**; `uv_build` expects `src/`
  by default. With `module-name = "piperobot"`, `uv build --wheel` ships only `piperobot/`
  (README files inside the package included) plus `.dist-info`; `robots/`, `tests/` and `docs/`
  stay out. _(verified 2026-11-01, uv 0.10.8, `uv_build>=0.10.8,<0.11`)_
- **`clean-install` in `ci.yml`** installs only the wheel in a fresh venv and imports every
  module with `python -I` from outside the checkout, so an eager `import lerobot` or a file
  missing from the wheel fails CI. Locally on Windows: 14 modules import with no extras.
  _(verified 2026-11-01)_
- **Codex's Windows sandbox** (CLI 0.166, `windows.sandbox = "elevated"`) runs as separate
  `CodexSandbox*` users: it cannot follow uv's minor-version junction
  (`cpython-3.12-windows-x86_64-none`), so point the venv's `pyvenv.cfg` `home` at the real
  `cpython-3.12.12-...` folder; and folders that Python creates with mode 0o700 (pytest's temp
  dirs) are private to whichever user created them, so run pytest with
  `-p no:cacheprovider --basetemp=.venv\pytest-tmp`. It cannot run `uv` (no cache access) or
  write git metadata in a worktree. _(verified 2026-11-01)_
- **Create a Codex worktree's venv with `UV_LINK_MODE=copy`**, or the sandbox cannot read it
  (`PermissionError` importing `ruff` or `pytest`). By default uv hardlinks venv files to its
  cache under `%LOCALAPPDATA%\uv\cache`, whose files keep a protected ACL without the
  `CodexSandboxUsers` group; copied files inherit the worktree's ACL instead. Recipe:

  ```powershell
  $env:UV_LINK_MODE = "copy"
  uv sync                      # or `uv sync --reinstall` to fix an existing venv
  # then point .venv\pyvenv.cfg `home` at the real cpython-3.12.12-... folder (above)
  codex exec -C <worktree> --sandbox workspace-write -o <report.md> - < <brief.md>
  ```

  Feed the brief on stdin from a file, or `codex exec` waits for input.
  _(verified 2026-11-01, Codex CLI 0.166, uv 0.10.8)_
- **Delete sandbox-owned folders from inside the sandbox.** `.venv\pytest-tmp` and other folders
  that Codex's Python created are private to the sandbox user, so `Remove-Item` and
  `git worktree remove` fail on them for your own user. No admin rights are needed; run the delete
  as the sandbox user first, then remove the worktree:

  ```powershell
  codex sandbox -c 'sandbox_mode="workspace-write"' -- `
    C:\Users\<you>\AppData\Roaming\uv\python\cpython-3.12.12-windows-x86_64-none\python.exe `
    -c "import shutil; shutil.rmtree(r'.venv\pytest-tmp')"
  ```

  _(verified 2026-11-02, Codex CLI 0.166)_
