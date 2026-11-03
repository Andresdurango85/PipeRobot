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
- **`gpu-smoke.yml`**: on pushes to this repo's branches that touch `piperobot/`,
  `robots/pusht/`, `pyproject.toml`, `uv.lock` or the workflow (not `dependabot/**`), and by hand,
  on the self-hosted GPU runner: `nvidia-smi`, torch sees CUDA, 50 PushT episodes on CUDA, count
  and time in the job summary. Not required and not a gate
  ([ADR 0020](../decisions/0020-self-hosted-gpu-runner.md)); never on pull requests since
  2026-11-02 ([ADR 0027](../decisions/0027-self-hosted-runner-push-only-and-pinned-actions.md)).
  First run 3 min 3 s (CUDA torch downloaded), warm re-run 2 min 5 s: install 16 s, evaluation
  83 s. _(verified 2026-11-01, run 41345428882, attempts 1 and 2)_
- **`isaac-render.yml`**: on push to `ci/isaac-render` or by hand (never on pull requests), on
  the self-hosted GPU runner: installs Isaac Lab at the pinned commit into the runner's tool cache,
  then runs `robots/so101/tools/isaac_render_check.py` as an empty stage and as one RTX camera
  frame, cold and warm, with VRAM samples and Kit's GPU log lines in the artifact
  ([isaac.md](isaac.md)). _(added 2026-11-01, run 41369455668)_
- **`zizmor.yml`**: zizmor (GitHub Actions security linter, from `uv.lock`) on every PR and push
  to `main`, with `GH_TOKEN` so its online audits run (known-vulnerable actions, impostor
  commits); findings show as annotations and fail the job. Not a required check until added to
  the ruleset. zizmor 1.32's default policy already demands SHA pins for every action, so there
  is no `zizmor.yml` config file. Starting point on `main` before ADR 0027: 20 `unpinned-uses`,
  7 `artipacked` (checkout without `persist-credentials: false`), 2 `dependabot-cooldown`; all
  fixed, none ignored. _(verified 2026-11-02, zizmor 1.32.0 offline)_
- **`scorecard.yml`**: OpenSSF Scorecard weekly (Monday) and on push to `main`; SARIF to code
  scanning, results published for the README badge. Publishing imposes rules on the workflow: no
  top-level `env`/`defaults`, no workflow-level writes, `id-token: write` only on the Scorecard
  job, an Ubuntu hosted runner, and only checkout, upload-artifact, codeql upload-sarif,
  scorecard-action and harden-runner as steps. Only `push` and `schedule` are supported triggers;
  `workflow_dispatch` and `pull_request` are experimental. Not a gate.
  _(verified 2026-11-02, scorecard-action v2.5.0 README)_
- **`mutation.yml`**: mutmut on `piperobot/stats` on `ubuntu-latest`, weekly, by hand, and on
  PRs that touch the stats code or its tests; score and survivors in the job summary and log. Not
  a gate ([testing.md](testing.md)). _(verified 2026-11-02, mutmut 3.8.1)_
- **`history.yml`**: on push to `main` touching `piperobot/`, `robots/pusht/`, `uv.lock` or itself,
  and by hand: evaluates PushT (`contents: read`), appends one record to `history.json` on the
  append-only `history` branch through `.github/scripts/append_history.sh` (the only job with
  `contents: write`; fetch–append–push with retries, explicit `refs/heads/history` refspec), and
  deploys the rendered page to Pages (`pages: write`, `id-token: write`, `github-pages`
  environment). `append` and `deploy` run only on `refs/heads/main`
  ([ADR 0026](../decisions/0026-success-rate-history-data-branch-and-pages.md)). Needs Pages from
  GitHub Actions, the `history` branch and its ruleset first. Since ADR 0030 an `attest` job
  (`id-token: write`, `attestations: write`, our stdlib module only) signs each point between
  `evaluate` and `append`; `append` commits the signed record plus `results/<run>.<attempt>.json`
  and `bundles/<run>.<attempt>.jsonl`, and the page links them. First run: 41579899042 on the merge
  of #39, all three jobs green, one record (29/50, PASS) at
  <https://andresdurango85.github.io/PipeRobot/>. _(verified 2026-11-03)_
- **The history's repo settings were applied on 2026-11-03** through the REST API by the
  orchestrator session, with Andrés's explicit OK: Pages `build_type=workflow`; the orphan
  `history` branch seeded with `[]`; the ruleset "history (append-only)" (id 26424151, deletion +
  non-fast-forward, no bypass actors); the `github-pages` environment deploys from `main` only
  (set by enabling Pages). Re-check with `gh api repos/<owner>/<repo>/rulesets/26424151` and
  `.../environments/github-pages/deployment-branch-policies`. _(verified 2026-11-03)_
- **Scorecard's first score: 6.3/10** (Scorecard v5.6.0 on `7779d43`). 10/10: Pinned-Dependencies,
  Token-Permissions, Dangerous-Workflow, SAST, CI-Tests, Security-Policy,
  Dependency-Update-Tool, Binary-Artifacts, License. Low, and why: Code-Review 0 (no approving
  reviews, [ADR 0018](../decisions/0018-no-required-review-for-the-owner.md)), Maintained 0 (repo
  younger than 90 days), CII-Best-Practices 0 (no OpenSSF badge), Fuzzing 0 (Hypothesis is not
  detected as fuzzing), Contributors 0 (one person), Branch-Protection 3, Vulnerabilities 5 (the
  advisories accepted in [ADR 0012](../decisions/0012-dependency-vulnerability-triage.md)).
  Packaging and Signed-Releases do not apply (no releases). Results:
  `curl https://api.scorecard.dev/projects/github.com/Andresdurango85/PipeRobot`.
  _(verified 2026-11-03)_
- ~~Known issue: Dependabot's `uv` update job fails on `torch` and `torchvision`; likely the
  CPU-index source for torch on Linux.~~ _(2026-11-03; the guess about the cause was wrong)_
- **Dependabot's `uv` job failed because it tried to widen our torch pins past LeRobot's cap.**
  Both runs (41445044081, 41574159723) ended with `dependency_file_not_resolvable` for exactly
  `torch` (to 2.14.1/2.15.0) and `torchvision` (to 0.29.x): the `lerobot` extra pins
  `torch>=2.11,<2.12` and `torchvision>=0.26,<0.27` to match LeRobot 0.6.1's
  `torch>=2.7,<2.12`, so the resolver proved it unsatisfiable. The CPU index and the Pillow
  override were not involved; the other uv updates still opened PRs (#36). Fix: an `ignore`
  rule in `dependabot.yml` for minor and major updates of both (patches still come), guarded by
  a test that pyproject still caps them at a minor. A Dependabot PR for lerobot 0.7 will likely
  fail against this rule: that is the signal to raise the pins, the extra and the rule together,
  by hand, in one PR. `update-types` was chosen over a `versions` range because GitHub's options
  reference shows no pip/uv range example. Dependabot runs only on the default branch and has no
  API to start a run; a change to `dependabot.yml` on `main` starts one right away (the UI's
  "Check for updates" is the fallback). _(verified 2026-11-03)_
- **Fixed**: the first `uv` run after the rule merged (#43) succeeded with no resolver errors,
  logging "All updates for torch were ignored" and the same for torchvision (run 41584487086).
  The rule does **not** hold back security updates: GitHub's docs say `update-types` "only
  affects version updates, not security updates" (an `ignore` by name or `versions` would). A
  torch security fix outside 2.11.x would still be unresolvable against LeRobot's cap, so its
  alert needs manual triage ([ADR 0012](../decisions/0012-dependency-vulnerability-triage.md)).
  _(verified 2026-11-03, GitHub docs "Controlling which dependencies are updated")_
- **The 7-day cooldown works**: the log shows "Filtered out N versions due to cooldown", and the
  first SHA-pinned update was setup-uv 7.6.0 → 10.3.2, not 10.3.3, released 6 days earlier.
  _(verified 2026-11-03)_
- `tests/test_workflows.py` checks the workflow invariants of ADR 0027 (self-hosted triggers,
  `gpu` label, hook allowlist, SHA pins, `persist-credentials`) and runs the job-started hook
  with PowerShell when one is installed (`pwsh` is preinstalled on `ubuntu-latest`).
- `nightly.yml` (larger baseline) does not exist yet; see [`../STATUS.md`](../STATUS.md).

## Local hooks

- **Git hooks mirror CI** ([ADR 0013](../decisions/0013-pre-commit-hooks-mirror-ci.md)), run by
  prek from `.pre-commit-config.yaml`: ruff on commit; on push, ruff on the whole repo plus
  `pytest` under `uv run --isolated --locked` (fresh env without the `lerobot` extra, like CI),
  ~5 s. Install once per clone with `uv run prek install`.
  _(verified 2026-10-27, prek 0.5.7, uv, Windows laptop)_
- **Git worktrees share one `.git/hooks`**, and `prek install` writes the absolute path of the
  current checkout's `prek.exe` into it. Installed from a worktree, every other worktree's
  commits break (`exec: prek: not found`) once that worktree's venv is removed. Install from the
  main checkout: `C:\Users\nuevo\PipeRobot\.venv\Scripts\prek.exe install`.
  _(verified 2026-11-03, prek 0.5.7)_
- **zizmor runs offline in the hooks** (on commit when `.github/` or the hook config changes,
  and on push always), because hooks must work without a token; CI adds the online audits.
  _(2026-11-02, ADR 0027)_
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
  pass, and Claude Code's auto mode allows it. ~~"Require review from Code Owners" is still on in
  the ruleset and does not block it.~~ _(verified 2026-10-28, PR #17)_
- **"Require review from Code Owners" blocked Dependabot's PRs** (the owner's own PRs were
  unaffected), so Andrés turned it off in the `main` ruleset, in line with
  [ADR 0018](../decisions/0018-no-required-review-for-the-owner.md). _(2026-11-03, PRs #36, #37)_
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
- **Job-started hook**: the runner runs the script named in `ACTIONS_RUNNER_HOOK_JOB_STARTED`
  (set in the OS environment or in `.env` in the runner folder; a change needs a runner restart)
  after a job is assigned and before it starts. The docs say a non-zero exit means the job does
  not run; `continue-on-error` does not apply. `.ps1` runs with `pwsh`, falling back to
  `powershell`. It sees the default `GITHUB_*` variables, has no timeout, and its output shows
  under "Set up runner". Ours is `.github/runner/job-started.ps1`
  ([ADR 0027](../decisions/0027-self-hosted-runner-push-only-and-pinned-actions.md)).
  _(verified 2026-11-02, GitHub docs "Running scripts before or after a job", runner 2.338.2)_
- **A refused job still runs its `if: always()` steps.** With the hook exiting 1, "Set up
  runner" fails and normal steps are skipped, but `always()` steps execute on the runner: a
  refused `gpu-smoke` ran `actions/upload-artifact` and uploaded a 529-byte file a previous run
  had left in `out/` (run 41573497209). The job's actions are downloaded before the hook runs.
  On this runner the hook is invoked as `powershell -command ". '<script>'"`, so Windows
  PowerShell 5.1 under the machine's execution policy runs it; an allowed job prints
  "Allowed job: …" (run 41573361134). _(verified 2026-11-03, runner 2.338.2, throwaway PR #35)_
- **Fixed by ending the worker** ([ADR 0029](../decisions/0029-refused-jobs-end-their-worker-and-workspaces-are-wiped.md)):
  the hook runs as a direct child of the job's `Runner.Worker.exe`
  (`RunnerService → Runner.Listener → Runner.Worker → powershell`), and on refusal it stops that
  process. Then no step runs, `always()` ones included, and no artifact is uploaded; the run
  fails in about 20 s, and the Listener logs "worker encounter an unhandled exception or app
  crash", marks the job Failed and keeps listening (runs 41580283257, 41580287237). The cost: a
  refused job has **no log on GitHub** (log API 404, `BlobNotFound`); look in
  `C:\actions-runner\_diag\Runner_*.log`. The Listener's `ERR BrokerServer … TaskCanceledException`
  lines at each job end are normal: the same pattern shows on ordinary jobs.
  _(verified 2026-11-03, runner 2.338.2)_
- **The job-completed hook wipes the workspace** after every allowed job: "Wiped job workspace:
  C:\actions-runner\_work\PipeRobot\PipeRobot (21 entries)" under "Complete runner", ~13 s for
  `gpu-smoke`. A cold workspace costs no measurable time: `gpu-smoke` ran in 2 min 30 s cold
  (install 17 s, evaluation 94 s, run 41580744632) against 2 min 25 s–2 min 43 s warm, since the
  uv cache lives in the tool cache and the Hugging Face cache in `gh-runner`'s profile. Another
  session's GPU study was running at the same time. _(verified 2026-11-03)_
- **A killed (refused) job does not run the job-completed hook**, so the wipe after the previous
  allowed job is what keeps its workspace empty. _(verified 2026-11-03)_
- ~~`C:\actions-runner` inherits from `C:\`: "Authenticated Users" have Modify and "Users" read,
  including `.credentials_rsaparams` (the runner's key), so every local account, the Codex
  sandbox users included, could rewrite or read the runner.~~ _(verified 2026-11-02, ACL)_
- **`C:\actions-runner` no longer inherits** (ADR 0027): SYSTEM and Administrators full,
  `gh-runner` Modify (the service runs as `.\gh-runner`; self-update needs Modify), the
  `GITHUB_ActionsRunner_*` group `config.cmd` created full, and `nuevo` read on `_diag` only.
  `nuevo` can no longer read `_work` or the runner's config: debug runs through the Actions logs
  or `_diag`, and anything else needs an elevated shell. `.env` is read-only for `gh-runner`
  (Modify on the folder lacks delete-child). The hook's live copy is
  `C:\ProgramData\piperobot-runner\job-started.ps1` (no inheritance; `gh-runner` and `nuevo`
  read only). ACL backup for rollback: `C:\ProgramData\actions-runner-acl-backup.txt`, restored
  with `icacls C:\ /restore <file>` (paths are stored relative to the parent folder).
  Changing the tree's ACL takes minutes: `icacls` walks every file, and the Isaac tool cache
  alone is ~17 GB (the `/save` backup is 202 MB). Closing the elevated window mid-run leaves the
  tree half-changed and the service stopped; the steps are idempotent, so re-run them.
  _(applied by Andrés, elevated, 2026-11-03; verified: `nuevo` denied on `.credentials_rsaparams`,
  `_work`, the Isaac venv and `bin`; live hook's sha256 equals the tracked file; runner online)_
- **Runner groups limited to selected workflows exist only for organizations**, so a personal
  repo cannot tie its runner to specific workflow files; the job-started hook does that job here.
  _(2026-11-02)_
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
- **setup-uv publishes no floating major tags after v7** (`v7` → v7.6.0, then only `v8.0.0` …
  `v10.3.3`), which is why Dependabot never moved `@v7` past v7. With SHA pins and a
  `# vX.Y.Z` comment it follows full versions. _(verified 2026-11-02, tags via the API)_
- **Actions pinned by SHA** ([ADR 0027](../decisions/0027-self-hosted-runner-push-only-and-pinned-actions.md)):
  checkout v7.0.1, setup-uv v7.6.0, cache v6.1.0, upload-artifact v7.0.2, dependency-review
  v5.0.0, scorecard-action v2.5.0, codeql-action/upload-sarif v4.39.1, each at the commit its tag
  pointed to. `gh api repos/<o>/<r>/commits/<tag> --jq .sha` dereferences annotated tags (same
  result as `git ls-remote <url> 'refs/tags/<tag>^{}'`). _(verified 2026-11-02)_
- **Repo Actions permissions before ADR 0027**: `allowed_actions: all`,
  `sha_pinning_required: false`, default workflow token read-only, fork approval
  `all_external_contributors`. _(verified 2026-11-02, API)_
- **Repo Actions permissions since ADR 0027**: `allowed_actions: selected` with
  `github_owned_allowed: true` (`actions/*`, `github/*`), `verified_allowed: false`,
  `patterns_allowed: [astral-sh/setup-uv@*, ossf/scorecard-action@*]`, and
  `sha_pinning_required: true`. A new third-party action must be added to the patterns first.
  Applied by the orchestrator session with Andrés's explicit OK; a worker session's auto mode
  refuses the `PUT` ("Modify Shared Resources"). Read back with
  `gh api repos/<o>/<r>/actions/permissions` and `…/permissions/selected-actions`.
  _(verified 2026-11-03, API)_
- **Secret scanning's non-provider patterns and validity checks stay disabled** on this repo:
  the API returns 200 to the request but nothing changes, likely because they need GitHub Secret
  Protection, which a personal public repo does not have. Do not retry. _(verified 2026-11-02)_
- ~~`ubuntu-latest` moves to Ubuntu 26 from 2026-10-19. No impact today because uv pins Python
  3.12 itself.~~ _(2026-10-26; wrong about the impact, see below)_
- **`ubuntu-latest` becomes Ubuntu 26.04.1 (kernel 7.0) in a rollout from 2026-10-19 to
  2026-11-19** (actions/runner-images#14748). uv pins Python, but torch's CPU wheels still load
  the OS's glibc/libm, which can flip near-miss PushT episodes like a CPU change does. So the jobs
  whose results are compared across runs pin `ubuntu-24.04`: `pr-gate`, `baseline.yml`
  and `history.yml`'s `evaluate` job (`tests/test_workflows.py` checks it). The
  others (`ci`, `zizmor`, `scorecard`, `mutation`, `dependency-review`) stay on `ubuntu-latest`.
  Until then every run of ours had landed on 24.04.5 (image versions 20261012, 20261025).
  _(verified 2026-11-03)_
- **Moving the pinned jobs to a new image is a deliberate step**: dispatch `baseline.yml` on the
  new image and compare it episode by episode with `robots/pusht/baselines/vqbet-episodes.json`
  (`python -m piperobot.stats.paired`). Identical: switch every pinned label in one PR. Not
  identical: refresh the baseline in the same PR as the switch. _(2026-11-03)_
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
