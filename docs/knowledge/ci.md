# CI (GitHub Actions)

## Current workflows

- **`ci.yml`**: ruff + pytest on `ubuntu-26.04`, no GPU, no LeRobot; ~7 s per run.
  _(verified 2026-10-26, run 40439823769)_
- **`dependency-review.yml`**: fails a PR that adds a dependency with a high or critical
  advisory. **CodeQL** runs as GitHub's default setup (no workflow file; Settings → Code security).
  Both are merge gates ([ADR 0011](../decisions/0011-free-security-gates.md)).
- **`pr-gate.yml`**: PushT evaluation on CPU (50 fixed-seed episodes) → report (also in the job
  summary) → sticky comment → gate verdict (fails on BLOCK) → artifact `pr-gate-<PR>` with
  results, report and the videos of the first 10 episodes
  ([ADR 0014](../decisions/0014-mock-evaluator-and-pr-gate-workflow.md),
  [ADR 0017](../decisions/0017-pr-gate-pusht-on-github-runners.md)). Runs on `ubuntu-26.04`
  (pinned, [ADR 0039](../decisions/0039-explicit-hosted-runner-images.md)) with CPU-only torch until the evaluator needs the GPU runner. Fork PRs get no comment (read-only
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
- **A push that only touches a doc under `robots/pusht/` still runs `gpu-smoke`** on the home
  PC: the path filter has no file-type exclusion. Pushing the comparison design file to a branch
  ran it once (run 41959014289, 3 min). Expect it, or keep such pushes local until the PR.
  _(verified 2026-11-04)_
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
- **`mutation.yml`**: mutmut on `piperobot/stats` on `ubuntu-26.04`, weekly, by hand, and on
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
- **`certify.yml`** ([ADR 0031](../decisions/0031-history-schema-2-and-certify-trusted-builder.md)):
  a reusable workflow (`on: workflow_call`, inputs `series` and `artifact`), the only signer of
  v2 certificates. `history.yml`'s `attest`, `append` and `deploy` jobs moved into it unchanged
  in substance; `history.yml` keeps `evaluate` and calls it with `series: main`. Its jobs write the
  schema-2 record from the caller's artifact (main: `results.json`; nightly: `candidate.json` and
  `reference.json`), sign it, append it with its evidence (`results/<run>.<attempt>.json`,
  `.reference.json` for nightly, `bundles/<run>.<attempt>.jsonl`) and deploy the page. Every job
  runs only on `refs/heads/main`, on `ubuntu-26.04` since 2026-11-05 (`ubuntu-24.04` before);
  top-level `permissions: {}`, the caller grants the union and each job narrows it.
  _(2026-11-03; image updated 2026-11-05)_
- **`certify.yml` image moves cannot be tested on a branch**: every job has
  `if: github.ref == 'refs/heads/main'`, so PR CI skips them all. The 26.04 move is validated by
  the first run on `main` after the merge: `history.yml` on the merge push (`certify.yml` is in
  its `paths`), checked end to end with `certificate verify` on the new record. Rollback is a
  revert. First run on 26.04: `history.yml` 42072603337 on `61d70b9` (merge of #81), all four
  jobs green on `ubuntu-26.04`; record 29/50 PASS, EPYC 7763, `runner_image` `ubuntu26
  20261101.186.1` (the caller's evaluate host, not certify's). `certificate verify` on the raw
  `results/42072603337.1.json` gave VERIFIED with `--bundle` and no `gh` login and through the
  API (signer `certify.yml@refs/heads/main`); one flipped episode gave NOT CERTIFIED. The first
  26.04 `history.yml` record overall was run 42049206277 (`2b31943`, merge of #79), before
  certify moved. _(verified 2026-11-05)_
- **Call `certify.yml` as `uses: $/.github/workflows/certify.yml`**, not `./`. zizmor 1.32's
  `self-repository` audit flags `./` reusable-workflow calls; `$/` is GitHub's newer same-repo
  syntax and, like `./`, runs the workflow file from the caller's own commit, so a branch still
  cannot pick another `certify.yml`. ADR 0031 writes `./`; the guarantee is the same.
  `tests/test_workflows.py` requires exactly `$/...` and exempts `./` and `$/` from SHA pins.
  _(verified 2026-11-03, zizmor 1.32.0)_
- **First v2 certificate**: `history.yml` run 41770900924 on `3c42236` (merge of #71), schema-2
  record 29/50 PASS. Its Fulcio certificate has `buildSignerURI`
  `.../.github/workflows/certify.yml@refs/heads/main` and `buildConfigURI`
  `.../.github/workflows/history.yml@refs/heads/main`: the reusable workflow is the signer
  (`job_workflow_ref`), the caller is the config (`workflow_ref`), as the verifier assumes.
  `certificate verify` gave VERIFIED with `--bundle` and no `gh` login and through the API, and
  NOT CERTIFIED for an altered copy. Read the raw fields with `gh attestation verify ... --bundle
  ... --predicate-type <gate-verdict-v2 URL> --format json`; without `--predicate-type`, gh looks
  for SLSA provenance and finds none in the verdict bundle. _(verified 2026-11-04, gh 2.88.1)_
- **First nightly certificate**: `nightly.yml` dispatch run 41779993747 on `011536d` (merge of
  #73), every job green. Fulcio certificate: `buildSignerURI` `certify.yml@refs/heads/main`,
  `buildConfigURI` `nightly.yml@refs/heads/main`, `github-hosted`. `certificate verify
  <run>.json --reference <run>.reference.json` gave VERIFIED (259/500 PASS) through the API and
  with `--bundle` and no `gh` login; an altered candidate gave NOT CERTIFIED and an altered file
  passed as `--reference` gave MISMATCH. When the two arms agree on every seed, `candidate.json`
  and `reference.json` are byte-identical (the files carry no commit), so the subject list holds
  one digest twice; the reference commit rests only on the signed record. _(verified 2026-11-04)_
- **Verify byte-exact files: `core.autocrlf` breaks certificates.** On Windows with a global
  `core.autocrlf=true`, `git clone -b history` rewrites `results/*.json` with CRLF, the sha256
  changes and a genuine file gives NOT CERTIFIED. Download the raw files
  (`https://raw.githubusercontent.com/<owner>/<repo>/history/results/...` or the Pages copies), or
  clone with `git -c core.autocrlf=false clone ...`. The verifier never normalizes line endings
  (the digest must stay exact); it adds a CRLF hint to NOT CERTIFIED instead. `save_results`
  writes LF on every OS too: before, a results file written on Windows (the SO-101 runner, a
  local run) had CRLF and different bytes from the same results on Linux. _(verified 2026-11-04)_
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
  younger than 90 days), CII-Best-Practices 0 (no OpenSSF badge), Fuzzing 0 (for Python,
  Scorecard counts only `import atheris` or a ClusterFuzzLite Dockerfile, not Hypothesis: see the
  fuzzing entry below), Contributors 0 (one person), Branch-Protection 3, Vulnerabilities 5 (the
  advisories accepted in [ADR 0012](../decisions/0012-dependency-vulnerability-triage.md)).
  Packaging and Signed-Releases do not apply (no releases). Results:
  `curl https://api.scorecard.dev/projects/github.com/Andresdurango85/PipeRobot`.
  _(verified 2026-11-03)_
- **Scorecard's Vulnerabilities check honours `osv-scanner.toml`.** Scorecard v5.6.0
  (`clients/osv.go`, pinned through scorecard-action v2.5.0) runs OSV-Scanner v2.5.1's
  `osvscanner.DoScan` recursively over the downloaded repo, with no config override, so
  OSV-Scanner's own rules apply (`internal/config/manager.go`, `pkg/osvscanner/filter.go`):
  - It uses the `osv-scanner.toml` in the scanned lockfile's own directory (repo root, next to
    `uv.lock`); child directories do not inherit it.
  - An `[[IgnoredVulns]]` id hides its whole alias group, so a GHSA id also hides its PYSEC and
    CVE aliases.
  - `ignoreUntil` and `reason` are optional; without `ignoreUntil` the ignore never expires.
  - A file with an unknown key is rejected and silently replaced with the empty default.
  - Dependabot dismissals do not count.

  An OSV `querybatch` over `uv.lock`'s 124 registry packages on 2026-11-05 found exactly ADR
  0012's five advisories (each GHSA with its PYSEC alias; torch both as `2.11.0` and
  `2.11.0+cpu`), Scorecard's "5 existing vulnerabilities". `osv-scanner.toml` ignores them with
  a reason linking ADR 0012 and `ignoreUntil = 2027-05-05`; `tests/test_osv_scanner_config.py`
  keeps its ids equal to the ADR's and its keys valid. Update the file with every LeRobot
  upgrade (ADR 0012, Decision 3) and when the date passes: re-query OSV, re-check reachability,
  then move the date or drop the entry. OSV-Scanner itself was not run locally; Scorecard
  rescores only on push to `main`. Confirmed after the merge: `scorecard.yml` run 42089231563 on
  `c0bcccb` published Vulnerabilities 10 ("0 existing vulnerabilities detected"), overall 6.7.
  _(verified 2026-11-05 from source and the API)_
- **The two setuptools advisories stay unreachable, but not because "we build no packages".**
  [ADR 0012](../decisions/0012-dependency-vulnerability-triage.md) gave that reason
  (`package = false`) on 2026-10-26; since `3fe8eae` (2026-11-01) `uv sync` builds and installs
  `piperobot` itself, editable (`uv.lock`: `source = { editable = "." }`). The ADR stays as
  written; the accurate reason is where setuptools code runs:
  - `piperobot` is built by `uv_build` (`[build-system]` in `pyproject.toml`), which has no
    dependencies (`requires_dist` is empty on PyPI for `uv-build` 0.10.8 and 0.13.7), so no
    setuptools.
  - setuptools 81.0.0 is in `uv.lock` only as a dependency of torch 2.11 (both platform
    markers), held under 82 by LeRobot's cap. The fixes (83.0.0 for GHSA-h35f-9h28-mq5c, 84.1.0
    for GHSA-xmj3-9gf7-h52w) are both past the cap.
  - Two locked packages have no wheels: `evdev` 2.0.0 (via pynput, Linux only) and
    `feetech-servo-sdk` 1.0.0 (LeRobot's `feetech` extra, through our `so101` group). uv builds
    them with setuptools in an isolated build environment. Neither uses `setup_requires`.
  - GHSA-h35f-9h28-mq5c is in setuptools' `sdist` command (MANIFEST.in exclusions on macOS
    filesystems); building a wheel from an sdist does not run it, and releases are
    `git archive` tarballs ([ADR 0041](../decisions/0041-signed-source-releases.md)).
    GHSA-xmj3-9gf7-h52w is in `Wheel.install_as_egg` (legacy egg installs on Windows); uv
    installs every wheel itself.

  `osv-scanner.toml`'s two setuptools reasons now say this. _(verified 2026-11-07 from
  `uv.lock`, PyPI metadata, the two sdists' build files and the GitHub advisories)_
- **Scorecard's Fuzzing check is binary, with two triggers** (v5.6.0, `checks/raw/fuzzing.go`):
  - a `.clusterfuzzlite/Dockerfile` with a non-comment line;
  - the literal regex `import atheris` in a `*.py` file of a prominent language (lines of code
    at least a quarter of the per-language average; ours is Python, 705k lines, against HTML's
    23k).

  `from atheris import ...` and Hypothesis do not count.
  [ADR 0040](../decisions/0040-fuzz-untrusted-parsers-with-atheris.md) picks atheris on hosted
  runners: OSS-Fuzz's `base-builder` (which ClusterFuzzLite uses) compiles Python 3.11.13, and
  we require 3.12. The workflow is `fuzz.yml`:
  - It runs on `pull_request` (parser paths), weekly on Tuesdays at 04:23 UTC, and by hand.
  - It uses `ubuntu-26.04` with one matrix job per `fuzz/fuzz_*.py`: 60 s each on a PR, 600 s on
    the schedule.
  - It needs `uv sync --locked --group fuzz`. atheris 3.1.0 has only manylinux x86_64 wheels, so
    the group carries a Linux x86_64 marker.
  - A crash uploads `fuzz-crashes-<target>-<attempt>`.

  Scorecard reads the score from the files, not from runs. Confirmed after the merge of #85:
  `scorecard.yml` run 42114724255 on `a3e4150` published Fuzzing 10, overall 7.3 (the API's
  `date` 2026-11-05T21:40:25Z). The merge push changed `uv.lock`, so it also ran `history.yml`
  (42114724291) and `so101-gate.yml` (42114724349, evaluate ~40 min); both green.
  _(verified 2026-11-05 from source; score and runs verified 2026-11-06)_
- **Scorecard's Signed-Releases check reads asset names only** (v5.6.0,
  `probes/releasesAreSigned`, `probes/releasesHaveProvenance`,
  `checks/evaluation/signed_releases.go`):
  - It inspects the 5 most recent releases and skips those without uploaded assets. GitHub's
    automatic "Source code" archives are not assets.
  - No release with assets gives -1 (inconclusive, not counted).
  - Per release: 10 for an asset ending in `.intoto.jsonl`, else 8 for `.asc`, `.minisig`,
    `.sig`, `.sign`, `.sigstore` or `.sigstore.json`, else 0. The check's score is the floor of
    the mean.

  So one unsigned release would cost the overall score about half a point.
  `actions/attest` v4.2.2 writes its Sigstore bundle (DSSE envelope plus certificate and
  transparency-log entry) to `bundle-path`. `gh release create` with assets creates a draft,
  uploads the assets, then publishes. _(verified 2026-11-06 from source: scorecard v5.6.0,
  actions/attest v4.2.2, cli/cli `pkg/cmd/release/create`)_
- **`release.yml`** ([ADR 0041](../decisions/0041-signed-source-releases.md)): on an annotated
  `v*` tag push, or `workflow_dispatch` with a `tag`, it publishes a GitHub Release with three
  assets. They are a `git archive` tarball, its Sigstore bundle (`.sigstore.json`) and the
  bundle's DSSE envelope (`.intoto.jsonl`).
  - Jobs: `build` (`release_preflight.py check-tag` fails closed), `attest`, `publish` (the only
    `contents: write`) and `verify` (bundle and attestation API).
  - Hosted `ubuntu-26.04`, no caches. Notes come from `docs/releases/<tag>.md`.
  - A failed run publishes nothing. `workflow_dispatch` re-runs it with `release.yml` from
    `main`, but the preflight script and notes come from the tag, so a bug there needs a new
    tag. _(2026-11-06)_
- **First release, `v0.1.0`**:
  <https://github.com/Andresdurango85/PipeRobot/releases/tag/v0.1.0>.
  - The annotated tag `0aecdef` points to `60f7d44` (the merge of #88).
  - `release.yml` run 42389421459 (push): `build`, `attest`, `publish` and `verify` all green.
  - Tarball sha256: `bad6ce9183113c3caaa242ae2858eed497c2648e09d4810bea1e3d8e65927496`.

  Verified locally on Windows from `gh release download v0.1.0`, all with exit code 0 and with
  `--signer-workflow Andresdurango85/PipeRobot/.github/workflows/release.yml`:
  - `gh attestation verify` against the attached `.sigstore.json` bundle, and again through the
    attestation API;
  - `release_preflight.py check-envelope` on the downloaded pair.

  The certificate names `refs/tags/v0.1.0`, commit `60f7d44`, run 42389421459 attempt 1, and a
  Rekor entry at 2026-11-07T16:04:37Z. `git archive --format=tar --prefix=piperobot-v0.1.0/
  refs/tags/v0.1.0 | gzip -n -9`, run locally with git 2.53.0.windows.3 and gzip 1.14, gives
  the same sha256, so the tarball is reproducible across these tool versions.

  Signed-Releases was still -1 after the release's own merge push: the `scorecard.yml` run
  scored `60f7d44` at 16:03:50Z, a minute before the release existed. The next push rescored:
  run 42390508012 on `9caac15` gave Signed-Releases 10 ("1 out of the last 1 releases have a
  total of 2 signed artifacts"), Token-Permissions 10, overall 7.5 (API date
  2026-11-07T16:17:13Z). _(verified 2026-11-07)_
- **Release tags are protected by two rulesets on `refs/tags/v*`** (created by the orchestrator
  session with Andrés's OK):
  - 26762784, "release tags (immutable)": deletion, update and non-fast-forward, no bypass
    actors;
  - 26762786, "release tags (maintainer creates)": creation, bypassed only by the repository
    admin role (`RepositoryRole` 5).

  So only the maintainer can create a `v*` tag, and nobody can move or delete one. GitHub's
  immutable releases stay off (`gh api repos/<owner>/<repo>/immutable-releases` gives
  `"enabled": false`): Andrés declined them for now. Re-check with
  `gh api repos/<owner>/<repo>/rulesets/<id>`. _(verified 2026-11-07)_
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
- **`so101-gate.yml`** ([ADR 0035](../decisions/0035-so101-gate-on-the-self-hosted-runner.md)):
  the SO-101 gate. Runs on every branch push (and by hand, with `mode: gate | baseline`; a
  baseline run is never cancelled; on a branch a newer push cancels the older run, on `main`
  runs queue, but GitHub keeps only one pending run per concurrency group: with three quick
  merges to `main`, the middle one's pending run is replaced by the third and never evaluated on
  `main`). Job `changes` (hosted, ~10 s) decides whether the push is
  gate-relevant: the whole branch against its merge-base with `main` (`before..sha` on `main`),
  matched against `PATHS` in `.github/scripts/so101_gate.py` (the SO-101 policy, scene,
  baselines and cache script, `piperobot/`, `pyproject.toml`, `uv.lock`, the workflow and that
  script). Job `so101-gate-verdict` (hosted, `if: always()`) is the one check to require
  ([ADR 0037](../decisions/0037-so101-gate-verdict-is-a-required-check.md)): green when nothing
  relevant changed or `evaluate` and `report` both succeeded; red on a BLOCK, a skipped,
  cancelled or failed run, or Dependabot touching relevant files (the runner never runs
  Dependabot's code: review it and push a commit to the branch, or bypass). Job `evaluate` runs
  only on a relevant, non-Dependabot push, on the self-hosted GPU runner (`contents: read`):
  reuses `isaac-render`'s tool-cache Isaac Lab, verifies inputs with `prepare_caches.py` into
  `$RUNNER_TOOL_CACHE\piperobot-cache`, picks 2 Isaac workers when the free VRAM allows
  (`VRAM_PER_WORKER_MB` each), else 1 with a warning (same seeds), evaluates the scripted
  policy on seeds 100000-100099 ([ADR 0036](../decisions/0036-so101-gate-scripted-policy-on-100-fixed-seeds.md))
  and uploads the `so101-gate` artifact. Job `report` on `ubuntu-26.04` (the only job with
  `pull-requests: write`): paired verdict against `$BASELINE-episodes.json`
  (`robots/so101/baselines/scripted-pick-place`),
  sticky comment `<!-- piperobot-gate:so101 -->` on the open PRs whose head is the commit,
  failure on BLOCK; with no baseline on the branch it only writes a summary while `main` has none
  either, and fails once `main` has one. A push before the hook allowed it was refused on the runner, as intended (run
  41607023801). Live results: baseline dispatch 41659300745 on main; baseline PR #59 PASS
  (run 41664424596, b = c = 0); demo PR #60 with the registered weak grip BLOCK (run
  41669493827: 0/75, b = 6, c = 0, p = 1/64). Each run is ~26 min, and a merge that touches the
  watched paths also queues a gate run on main, so a follow-up PR can wait ~25 min for the
  runner. Those results are the replay era (demo_replay, seeds 0-74). **A baseline measured on
  a branch** (dispatch `mode=baseline` with `--ref` the branch) is valid only if the branch is
  up to date with main at dispatch time: the platform guard does not see code drift, so a
  gate-relevant merge on main before the branch merges means update and measure again.
  Scripted-era timing (baseline run 41707984345, 78/100, one worker): 52 min of evaluation; a
  failed seed costs ~2x a success (full 600-step horizon), so a regressing PR runs longer, up to
  ~95 min on one worker if every seed fails. Two workers take ~27 min at the baseline rate. The
  evaluate step times out at 120 min and the job at 130 so a timeout never replaces a verdict; a
  failed `evaluate` skips `report` (red check, no verdict). _(verified 2026-11-03)_
  Scripted-era live results: swap PR #63 PASS (run 41721012732, 78/100 vs 78/100, b = c = 0);
  registered demo PR #65 with gripper_closed 12 BLOCK (run 41728156209: 20/100, b = 59, c = 1,
  p = 5.3e-17), two workers, 36 min of evaluation although 80 seeds ran the full horizon.
  _(verified 2026-11-03)_
- **`readme.yml`**: runs the README's 30-minute path as written, on `ubuntu-26.04` and
  `windows-2025`, from a fresh checkout with an empty `UV_CACHE_DIR` and `HF_HOME` (the first
  policy download counts), timing each command; the Linux job fails above 30 minutes. A fenced
  block preceded by `<!-- readme-test -->` is executed, one command per line, from the
  repository root; `<!-- readme-test: exit N -->` expects exit code N and allows a single
  command. Lines may not end in `\` (continuations differ between bash and PowerShell).
  `.github/scripts/readme_commands.py extract README.md` lists the steps. Runs on PRs that touch
  the README or its tooling, weekly (drift from code and dependencies) and by hand. Not a
  required check. `robots/pusht/policies/demo-degraded.json` exists only for the README's BLOCK
  step; a test keeps every workflow and `piperobot/` from referencing it. _(2026-11-03)_
- **First README run** (41597539505, cold `UV_CACHE_DIR` and `HF_HOME`): `ubuntu-24.04` 254 s,
  `windows-2025` 299 s from the first command to the last. Per step on Linux (Windows): `uv sync`
  1 s (2 s), `pytest` 43 s (40 s), the `lerobot` + `sim-pusht` sync 4 s (7 s) including a torch
  download of 182 MiB (109 MiB), the PASS evaluation with the first policy download 108 s
  (130 s), the demo evaluation 98 s (117 s). PASS 27/50 on both; the demo BLOCK 5/50 on Linux,
  4/50 on Windows (one near-miss episode). A home connection adds the ~300 MB of downloads.
  _(verified 2026-11-03)_
- **`${{ runner.temp }}` is invalid in a workflow- or job-level `env:`**: the `runner` context
  exists only inside steps, and GitHub rejects the whole file ("This run likely failed because
  of a workflow file issue", zero jobs). zizmor and PyYAML do not notice; a test in
  `tests/test_workflows.py` now does. Use `$RUNNER_TEMP` inside the step. _(verified 2026-11-03,
  run 41597215145)_
- `tests/test_workflows.py` checks the workflow invariants of ADR 0027 (self-hosted triggers,
  `gpu` label, hook allowlist, SHA pins, `persist-credentials`) and runs the job-started hook
  with PowerShell (`pwsh` is preinstalled on `ubuntu-24.04` and `ubuntu-26.04`). A missing
  `pwsh`/`powershell` or `git` skips those tests locally but fails them when `CI=true`
  (`tests/binaries.py`), so a runner image change cannot drop them silently.
- **`nightly.yml`** ([ADR 0032](../decisions/0032-nightly-paired-run-on-rotating-seeds.md)):
  daily at 03:17 UTC and by hand, on `ubuntu-26.04` (`ubuntu-24.04` until 2026-11-05). One job
  evaluates the reference (`vqbet.json`'s `commit`, its own lock) and then `main` on the same
  500 fresh seeds (`python -m piperobot.seeds`: first seed
  `100000 + episodes × days since 2026-01-01`) and uploads `nightly-evaluation` (both results,
  both commits, platform, UTC time, raw CPU flags line, runner image). A second job, without torch, runs `piperobot.stats.paired` and the unpaired gate for the
  summary and fails on a paired BLOCK. `workflow_dispatch` only works once a workflow is on the
  default branch, so the pre-merge measurement used a temporary `push` trigger on the PR branch.
  A third job, `certify`, calls `certify.yml` with series `nightly` on `main` only. It needs
  `evaluate`, not `verdict`, so a BLOCK night is signed too and the alert never waits on Sigstore.
  A dispatch from `main` is signed like a scheduled night; one from a branch skips it. _(2026-11-04)_
- **First nightly measurement** (run 41592248166, seeds 253000–253499, `ubuntu-24.04`, AMD EPYC
  9V45): evaluate job 22 min (reference 620 s, candidate 681 s for 500 episodes each), verdict
  job 7 s. Paired: 309/500 both, 0 discordant, PASS. Unpaired: 309/500 = 61.8% on fresh seeds
  against the committed 265/500 = 53.0% on 1000–1499, +8.8 pp with the interval [0.027, 0.148]
  above zero: the gate's fixed seeds may be harder than average. One night only; the series will
  tell.
  _(verified 2026-11-03)_
- **Second night** (dispatch run 41779993747 on `011536d`, the 03:17 UTC cron of 2026-11-04 never
  fired; seeds 253500–253999, AMD EPYC 7763, 4 CPUs): evaluate job 43.5 min (reference 1325 s,
  candidate 1262 s), twice night 1's 22 min on an EPYC 9V45, against a 90-min timeout. Watch it;
  no change for now. Paired: 259 both, 0 discordant, PASS. Unpaired: 259/500 = 51.8% against the
  committed 53.0%, interval [-0.074, 0.050]: night 1's +8.8 pp did not repeat.
  _(verified 2026-11-04)_
- **The 03:17 UTC cron starts about 7 h 41 min late**: the scheduled runs of 2026-11-04
  (41817751006) and 2026-11-05 (42015111937) were both created at 10:58 UTC. GitHub delays
  scheduled workflows under load; a night's result arrives late morning UTC, not overnight.
  _(verified 2026-11-05)_
- **First night on `ubuntu-26.04`**: scheduled run 42206404058 on `a3e4150`, created 10:55:59 UTC
  on 2026-11-06; all five jobs (`evaluate`, `verdict`, `certify` `attest`/`append`/`deploy`) green
  on `ubuntu-26.04`. Seeds 254500–254999, AMD EPYC 7763; evaluate job 43 min (reference 1286 s,
  candidate 1271 s), like night 2 on the same CPU. Paired against reference `34eabdd`: 285 both, 0
  discordant, p=1, PASS. Unpaired: 285/500 = 57.0% against the committed 53.0%, interval
  [-0.022, 0.101]. Its schema-2 record in the `nightly` series carries `runner_image` `ubuntu26
  20261101.186.1`. _(verified 2026-11-06)_
- **Triage of a nightly BLOCK**: an alert, never a merge block. Do not rerun the same seeds: CPU
  PushT is deterministic within a runner, so a rerun only reproduces it. Look at the discordant
  seeds in the two results files, then wait for the next nights' fresh seeds or dispatch more
  episodes. If `main` really differs from the reference (a refactor, a dependency bump), a
  neutral difference still raises a false BLOCK about once in 40 nights, until a baseline
  refresh moves the reference forward.

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
  _(verified 2026-11-03, prek 0.5.7)_ It happened again on 2026-11-06/07: the hooks pointed at
  a removed `PipeRobot-anita-videos` worktree, so commits and pushes failed with
  `prek: not found` until sessions ran `uv run git ...` instead (that puts the venv's `prek` on
  PATH, so the hooks still run). Reinstalled from the main checkout on 2026-11-07. Worker
  sessions must never run `prek install` in a worktree; check with
  `grep '^PREK=' .git/hooks/pre-push`. _(verified 2026-11-07)_
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
  Required check names are the job names (`lint-and-test`, `dependency-review`, `pr-gate`, and
  `so101-gate-verdict` since 2026-11-04, ADR 0037):
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
- **PowerShell parses `"$env:NAME:"` inside a string as a drive-qualified variable**: the
  so101-gate fallback warning `"... for $env:MAX_WORKERS: ~50 min"` printed `for  ~50 min`.
  Write `$($env:NAME)` when a colon follows. _(verified 2026-11-04, Windows PowerShell 5.1,
  tests/test_workflows.py runs the preflight)_
- **ffmpeg is not preinstalled on `ubuntu-24.04`**: so101-gate's `video-report` falls back to
  `apt-get install ffmpeg` (6.1.1-3ubuntu5, about 20 s), as the step summary shows. Not verified:
  what `needs.video.result` reads when a job with job-level `continue-on-error` fails; the video
  comment's renderer handles `success` and `failure` alike. _(verified 2026-11-04, run
  41896631821)_ Not yet exercised on `ubuntu-26.04` (the `so101-gate.yml` move, #82): the ffmpeg
  steps run only when `seed_list` is not empty, and no gate run since has lost an episode (#85's
  run 42103743678 lost none; push runs skip the video jobs). The first run with a lost episode
  verifies the apt install on 26.04. _(2026-11-06)_

## Gotchas

- **One GitHub 500 used to turn a correct PASS red.** Run 41736214611 (#67) evaluated a
  PASS, then the report job's POST to `/issues/67/comments` got HTTP 500 and the job failed;
  re-running only `report` went green. `sticky_comment.py` now retries 5xx and network errors
  (3 attempts, 2 s and 5 s) and re-lists before each retry, so a timed-out POST is edited, not
  posted twice. The list endpoint can lag a just-created comment; the backoff only mitigates it.
  _(verified 2026-11-03)_

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
  whose results are compared across runs pin `ubuntu-24.04`: `pr-gate`, `baseline.yml`,
  `nightly.yml` and `history.yml`'s `evaluate` job (`tests/test_workflows.py` checks it). The
  others (`ci`, `zizmor`, `scorecard`, `mutation`, `dependency-review`) stayed on `ubuntu-latest`
  until ADR 0039 (below).
  Until then every run of ours had landed on 24.04.5 (image versions 20261012, 20261025).
  _(verified 2026-11-03)_
- **Moving the pinned jobs to a new image is a deliberate step**: dispatch `baseline.yml` on the
  new image and compare it episode by episode with `robots/pusht/baselines/vqbet-episodes.json`
  (`python -m piperobot.stats.paired`). Identical: switch every pinned label in one PR. Not
  identical: refresh the baseline in the same PR as the switch. _(2026-11-03)_
- **Ubuntu 26.04 probe, before the flip** (2026-11-03). Probes ran on branches only and were
  then closed: draft PR #64 and a push-triggered copy of `baseline.yml`, run 41726981138.
  Images: 24.04.5 `20261026.354.1` and 26.04.1 `20261026.180.1`, both on kernel
  `7.0.0-1017-azure`.
  - **Unpinned jobs are ready**. `ci` was green on both images, and `lint-and-test` gave
    1073 passed and 2 skipped on each, the same two skips (no `lerobot`, Windows junctions).
    `pwsh` 7.6.9 is on both. `mutation` on 26.04 left the same survivors as 24.04 (run
    41721070938).
  - **The images differ**. glibc is 2.39 on 24.04 and 2.43 on 26.04. The system `python3` is
    3.12.3 on 24.04, which uv uses, and 3.14.4 on 26.04, so there uv downloads a managed
    3.12.16. "uv pins Python" means the minor version only.
  - **PushT 500 episodes (seeds 1000-1499), for information only**. 24.04 on an AMD EPYC 9V74
    gave 267/500. That is exactly the known 9V74 result
    ([lerobot.md](lerobot.md)): the same 10 seeds differ from the committed baseline.
  - 26.04 drew an Intel Xeon Platinum 8370C and gave 263/500. Against the committed baseline
    it lost 1013, 1044, 1122, 1250 and 1338 and gained 1366, 1380 and 1455. Against the 24.04
    run, 4 episodes differ.
  - The OS change and the CPU change come together here, so the 26.04 effect cannot be
    isolated. It is within the 6-10 near-miss episodes that any two platforms differ by. The
    pinned jobs stay on `ubuntu-24.04`; moving them is a separate decision (procedure above).
    _(verified 2026-11-03; decided by the registered comparison below)_
- **Which hosted image each job uses** ([ADR 0039](../decisions/0039-explicit-hosted-runner-images.md)):
  no job uses `ubuntu-latest` (`test_no_job_runs_on_a_moving_label`). `ubuntu-26.04`: `ci`
  (three jobs), `dependency-review`, `mutation`, `scorecard`, `zizmor`, and since 2026-11-05 the
  numeric jobs (`pr-gate`, `baseline`, `nightly`, `history` `evaluate`, `readme` `linux`;
  `PINNED_IMAGE`), which move only after a registered comparison, and `certify.yml` (validated
  on `main`, above), and since 2026-11-05 the five hosted jobs of `so101-gate.yml` (moved with
  their own gate run, below). No job runs on `ubuntu-24.04` any more. `windows-2025`: `readme`
  `windows`. Neither Ubuntu image ships `ffmpeg` (the SO-101
  `video-report` job installs it with apt). Scorecard's publishing check accepts `ubuntu-NN.NN`
  from 22.04 up (`ossf/scorecard-infra`, `api/app/server/verify_workflow.go`); the first push run
  on `ubuntu-26.04` (42044757417) published 6.3 for `dc9ab2d`. _(2026-11-04; verified 2026-11-05)_
- **Registered 24.04 → 26.04 comparison for the numeric jobs: no effect, baseline kept**
  ([design and result](../../robots/pusht/baselines/ubuntu-2604-comparison.md), run
  41959796057, 2026-11-05). On the same VM, a 24.04 and a 26.04 container gave the same 500
  PushT outcomes as the runner itself on four VMs (EPYC 7763, 9V74 twice, 9V45), and three
  native 26.04 runs matched `vqbet-episodes.json` exactly, so the pins moved and `vqbet.json`
  stayed. What the run also showed:
  - The 18 evaluations produced two outcome vectors, split by host, never by image: the EPYC
    7763 (no `avx512*` flags) gives the committed 265/500, the 9V74 and 9V45 (AVX-512) give
    267/500, 10 discordant. Hypothesis from one run (N = 18 evaluations, 2 vectors), AMD hosts
    only: the probe's Intel Xeon 8370C, also AVX-512, gave a third vector (263/500).
  - Consequence for the unpaired comparisons with the committed vector: on an AVX-512 AMD host
    an unchanged policy sits 10 of 500 episodes away (seeds 1000-1499) and still PASSes; on
    `pr-gate`'s 50 seeds (1000-1049) it loses 1013 and 1044, 27/50 instead of 29/50. That is
    the 0-10 floor already known ([lerobot.md](lerobot.md)), now with a likely cause; it is not
    a regression.
  - The flags digest over-splits hosts: the 9V74 (`60bd6102`) and 9V45 (`3a6ca04c`) digests
    differ (the 9V45 adds `avx512_vp2intersect`, `avx_vnni`, `x2apic`) but their outcomes are
    identical; the 7763 is `9c39b836`. Group by the AVX-512 flags, not by the digest alone.
  - Those are `cpu_flags_digest` values (`piperobot.reports.history`), the same hash as
    `cpu_flags_sha256` in `history.json`. `image-compare.yml` hashed the raw `/proc/cpuinfo`
    line instead (`9e641570` / `c8543a3b` / `4aece38d` in the run's logs). Future comparisons
    must use `cpu_flags_digest`. _(verified 2026-11-05)_
  - The run's artifacts expire on 2026-12-05; the design file keeps the per-job table.
  _(verified 2026-11-05)_
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
- **Codex can turn a non-ASCII character in code into `?`.** A brief asked for a ` · `
  separator in `piperobot/reports/history.py`; the code came back with ` ? ` and the page
  showed "CPU A ? ubuntu24". The brief reached Codex intact (the PowerShell pipe sent UTF-8,
  checked byte by byte), and a `ǁ` (U+01C1) that Codex wrote into a data file the same day
  survived, so where it is lost is not known. In briefs, give non-ASCII characters as escapes
  (`\u00b7`) or name them, and grep a Codex diff for `?` where a symbol was intended; a
  screenshot of rendered output catches it too. _(observed 2026-11-03, Codex CLI 0.166)_
- **Codex leaves sandbox-owned folders besides `pytest-tmp`** (`.venv\pytest-focused`,
  `.venv\pytest-*`), which `git worktree remove` cannot delete; remove them all from inside the
  sandbox (`glob.glob(r'.venv\pytest-*')`) before removing a worktree, and tell Codex in the brief
  to use only `--basetemp=.venv\pytest-tmp`. _(observed 2026-11-03, Codex CLI 0.166)_
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
- **Sandbox-owned folders also land at the worktree root**, when a brief does not say where temp
  files go. Codex's own test runs left `.test-release-*` (2026-11-06) and `.pytest-cache-29c`,
  `.pytest-tmp-29c`, `.pytest-tmp-29c-full` (2026-11-07) there. Your own user cannot open them,
  and whole-repo tools then break:
  - `ruff format --check .` panics ("Expected a ruff source file");
  - zizmor's directory walk fails;
  - git warns "could not open directory".

  The sandbox-run delete above removes them too. Test git repos inside them hold read-only
  object files, so clear the read-only bit on error:

  ```powershell
  codex sandbox -c 'sandbox_mode="workspace-write"' -- <python.exe> -c "import glob, os, shutil, stat; h = lambda f, p, e: (os.chmod(p, stat.S_IWRITE), f(p)); [shutil.rmtree(p, onexc=h) for p in glob.glob('.pytest-*') + glob.glob(r'.venv\pytest-*')]"
  ```

  It cleaned all three worktrees involved, including a `.venv\pytest-focused` left on
  2026-11-03, with no admin rights. _(verified 2026-11-07, Codex CLI 0.166)_
- **Every Codex brief says where temp files go and cleans them at the end** (retro proposal
  R-2026-11-07-2). Put these lines in the brief:
  - run pytest only as `pytest -p no:cacheprovider --basetemp=.venv\pytest-tmp`;
  - create no files or folders at the worktree root other than the ones the brief asks for;
  - as the last step, delete `.venv\pytest-tmp` and any other temp folder you created, from
    inside the sandbox.

  Before `git worktree remove`, run the sandbox delete above for anything left over; never
  remove a worktree that still holds sandbox-owned folders. _(2026-11-07)_
