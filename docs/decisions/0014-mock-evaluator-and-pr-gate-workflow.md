# 0014. Mock evaluator and the pr-gate workflow, before the simulation exists

- Status: Accepted
- Date: 2026-10-27

## Context

The statistics (`stats/gate.py`) and the PR comment (`reports/pr_comment.py`) existed, but nothing
connected them to a pull request, and the Isaac Lab-Arena simulation needs the home PC's GPU,
which is not available yet. Waiting would leave the riskiest integration (workflow permissions,
sticky comment, exit codes, artifacts) untested until late.

## Decision

- **Results contract** (`eval/results.py`): every evaluator writes one JSON file with `policy`,
  `evaluator` and `episodes` (`seed`, `success`, optional `scene`, `failure`, `video_url`). Seeds
  are unique; empty results are an error. The gate and the report only read this contract.
- **Mock evaluator** (`eval/mock_eval.py`): a stand-in policy (`policies/mock-policy.json`, a
  `success_rate`) "runs" 50 episodes whose outcomes derive from each seed only: deterministic, and
  lowering the rate only adds failures, like a real regression.
- **Stored baseline** (`stats/baseline.json`): counts plus provenance, loaded by
  `stats/baseline.py`. `stats.gate` and `reports.pr_comment` accept `--results` and
  `--baseline-file` besides raw counts; invalid input files exit 2 ([0009](0009-fail-loudly-on-unusable-data.md)).
- **`pr-gate.yml`** on every PR: evaluate → render report (also to the job summary) → create or
  update the sticky comment (`reports/sticky_comment.py`, matched by marker and bot author) → run
  the gate, failing the job on BLOCK → upload results and report as an artifact.
- Security: only this job gets `pull-requests: write`; PR data reaches shell steps through
  environment variables, never `${{ }}` interpolation inside `run:`. Fork PRs get a read-only
  token, so they skip the comment and keep the report in the job summary.

## Alternatives considered

- Wait for Isaac Lab-Arena: integration bugs would surface late, mixed with simulation problems.
- `pull_request_target` to comment on fork PRs: runs with a write token next to untrusted code; a
  well-known injection risk. A `workflow_run` follow-up workflow is the safe pattern if fork PRs
  ever need comments.
- Posting with `gh` in shell: fewer lines, but untestable; the Python module is unit-tested
  against a fake GitHub (create, update, pagination, never editing a human's comment).
- Evaluating the base branch on every PR instead of a stored baseline: doubles the cost of each
  run ([0003](0003-statistical-gate-wilson-newcombe.md) chose a stored baseline).

## Consequences

- The full loop runs in CI today; Phase 0's "a worse PR is blocked" criterion is demonstrated with
  the mock and covered by `tests/test_mock_eval.py`.
- Replacing the mock means replacing one workflow step; the job moves to the self-hosted GPU
  runner ([0005](0005-two-machine-setup.md)).
- `stats/baseline.json` must be regenerated when the policy legitimately changes; later a nightly
  job should own it.
- The mock proves the plumbing, not the robot: no videos yet, and its numbers mean nothing about
  real policies.
- Unit tests never read `policies/` or `stats/baseline.json`: judging the committed policy is
  pr-gate's job alone. (A first version did, and the pre-push hook rejected a sabotaged policy
  before pr-gate could, so the gate itself was never exercised.)
