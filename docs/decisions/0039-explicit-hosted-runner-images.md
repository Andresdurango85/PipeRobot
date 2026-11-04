# 0039. No job runs on `ubuntu-latest`; hosted images move explicitly

- Status: Accepted
- Date: 2026-11-04

## Context

GitHub moves `ubuntu-latest` from Ubuntu 24.04 to 26.04 in a rollout that ends on 2026-11-19
(actions/runner-images#14748). Seven of our jobs still used the moving label: `ci.yml`'s
`lint-and-test`, `clean-install` and `type-check`, `dependency-review`, `mutation`, `scorecard`
and `zizmor`. None of them computes a number we compare across runs.

The PushT jobs do: `pr-gate`, `baseline.yml`, `nightly.yml`, `history.yml`'s `evaluate` and
`readme.yml`'s `linux` job are already pinned to `ubuntu-24.04`, enforced by `PINNED_IMAGE` in
`tests/test_workflows.py`. A new OS brings a new glibc/libm (2.39 on 24.04, 2.43 on 26.04) and,
on 26.04, a uv-managed Python 3.12 instead of the system 3.12.3, so near-miss episodes can flip.
The image effect cannot be read from runs on different VMs: two 24.04 runners that both reported
an "AMD EPYC 9V74" disagreed in 10 of 500 episodes ([lerobot.md](../knowledge/lerobot.md)), so
the host confounds the image.

The 2026-11-03 probe ran the non-numeric jobs on both images with the same results: 1073 passed
and 2 skipped on each, the same mutation survivors, `pwsh` on both
([ci.md](../knowledge/ci.md)). Neither image ships `ffmpeg`. Scorecard's publishing check accepts
any `ubuntu-NN.NN` label from 22.04 up (`ossf/scorecard-infra`,
`api/app/server/verify_workflow.go`).

## Decision

- **No job runs on `ubuntu-latest`.** Every hosted job names its image (`ubuntu-NN.NN` or
  `windows-NNNN`); self-hosted jobs use the `[self-hosted, Windows, gpu]` set; reusable-workflow
  callers have no `runs-on`. `test_no_job_runs_on_a_moving_label` checks every workflow.
- **Non-numeric jobs move with green CI.** The seven jobs above move to `ubuntu-26.04` now
  (`test_non_numeric_hosted_jobs_run_on_ubuntu_26_04`). Scorecard can only run on `main`, so its
  first push run after the merge is the check; if it rejects 26.04, only that job goes back.
- **Numeric jobs need a registered comparison.** They stay on `ubuntu-24.04` until a comparison
  designed and registered before it runs, with the host controlled or recorded (CPU flags, not
  only the model name), shows the move does not change the outcomes beyond a pre-set bound.
  Andrés decides whether and when to run it. If outcomes differ, the baseline is refreshed on
  the new image in the same PR as the switch (the procedure in [ci.md](../knowledge/ci.md)).
- **Already-pinned non-numeric jobs move with their own validating run**, not in a batch:
  `certify.yml` (its `append` and `deploy` jobs run only on `main`, so the first `history.yml`
  run after the merge validates it, and the rollback is a revert), and the hosted jobs of
  `so101-gate.yml` (any edit to that file runs the self-hosted evaluation, so they move with the
  next gate-relevant SO-101 change).

## Alternatives considered

- **Keep `ubuntu-latest` for non-numeric jobs**: every image change would land unannounced, in
  the middle of unrelated PRs.
- **Pin everything to `ubuntu-24.04`**: postpones the same work to 24.04's deprecation and keeps
  the non-numeric jobs off the image the probe already validated.
- **Move every hosted job to 26.04 in one PR**: the numeric jobs would shift the baseline without
  a comparison, the `so101-gate.yml` edit would run the home PC for ~40 min, and `certify.yml`
  cannot be validated from a branch.
- **A `runs-on: ${{ inputs.image }}` input** to switch images by dispatch: the label stops being
  reviewable in the file, and the numeric pin test could no longer check it.

## Consequences

- An image change is always a diff that a reviewer sees and CI tests.
- Two hosted images are in use for a while (24.04 for numeric, certify and SO-101 hosted jobs;
  26.04 for the rest). `ci.md` lists which job is where.
- When GitHub ships the next image, the non-numeric jobs move by a one-line PR per job set; the
  numeric jobs wait for a registered comparison.
- CodeQL (default setup) and Dependabot pick their own runners; they are outside this rule.
