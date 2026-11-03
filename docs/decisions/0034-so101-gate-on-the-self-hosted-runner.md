# 0034. The SO-101 gate on the self-hosted runner: paired on a same-runner baseline, reported by a hosted job

- Status: Accepted
- Date: 2026-11-03

## Context

Phase 0's target is a gate on the SO-101 tube-to-rack task. The Isaac Lab evaluator runs every
seed in a fresh Isaac process ([0033](0033-so101-isaac-evaluator-one-process-per-seed.md)),
about 20 s per seed, and needs the RTX GPU of the self-hosted runner on the owner's PC
([0020](0020-self-hosted-gpu-runner.md)). That runner may only run trusted code: self-hosted
workflows are triggered by push, dispatch or schedule, behind a job-started hook that ends any
other job ([0027](0027-self-hosted-runner-push-only-and-pinned-actions.md),
[0029](0029-refused-jobs-end-their-worker-and-workspaces-are-wiped.md)). A gate also has to
post a PR comment, which needs a token that can write to pull requests, and no write token may
reach the home PC.

## Decision

### Gate policy and power

- The gate evaluates `robots/so101/policies/demo_replay.json` for now: open-loop replay of the
  course's 75 demos on the reconstructed layout, one Isaac process per seed (0033). It is a
  pipeline test, not a policy with power. Its reference rate is 6/75 (8%): the dataset has no
  object poses and the reconstruction guesses the grasp point.
- What that means for the gate, computed with `piperobot.stats`:
  - Unpaired ([0003](0003-statistical-gate-wilson-newcombe.md)) can never block it: 0/50
    against 6/75 is PASS (Newcombe [-0.164, +0.003]).
  - Paired over all 75 seeds blocks only a total collapse: losing all 6 successes gives exact
    McNemar p = 1/64 → BLOCK, while losing 3 of 6 gives p = 1/8 → PASS.
  - Hence 75 seeds (~25 min with one worker), not 50.
- The registered demo regression is the weak-grip spec (`demo_replay_weak_grip.json`, gripper
  command floored at 25). Expected 0/75 → BLOCK, registered in `weak_grip_expectation.json`
  before any run (PR #56).
- The gate's target policy is a scripted privileged-state pick-and-place on the seeded
  randomized layout (separate spike, registered go/no-go ≥ 30/50 on seeds 210000–210049, tuned
  only on 200000–200099). If it passes, it replaces the replay in the gate and this section is
  superseded.

### Baseline

- Measured by the workflow's baseline mode on the runner, as `gh-runner`, with the tool-cache
  Isaac venv and `prepare_caches.py`-verified inputs: the exact conditions of a gate run. It is
  never measured interactively. Physics device, process model and machine all move outcomes
  (0033: CPU vs GPU changed 23/75, in-process vs one process per seed 20/75).
- Files: `robots/so101/baselines/demo-replay.json` (counts, seeds 0–74, commit, platform: GPU,
  driver, Isaac Lab, torch, actuators, physics device) and `demo-replay-episodes.json`
  (per-episode results), committed by PR as in PushT.
- Cross-check on the first baseline run: its trajectory fingerprints should equal the
  interactive acceptance run R1 (0033), which ran as another user with another Kit cache. A
  difference is reported, not ignored.
- A PR that changes the scene (`robots/so101/envs/**`) or the evaluator must re-measure the
  baseline before merging. The gate itself never re-measures.

### Paired, not unpaired

- The gate compares the PR's per-seed outcomes with the baseline's on the SAME seeds (exact
  McNemar, `piperobot.stats.paired`, [0032](0032-nightly-paired-run-on-rotating-seeds.md)).
  That is sound here because one runner, one configuration and one process per seed make each
  seed's outcome a deterministic function of policy and scene (0033: 2 × 75 seeds
  bit-identical).
- The PR's seeds must be a subset of the baseline's; disjoint seeds rule out pairing.
- Unpaired comparison stays available for policies whose baseline uses disjoint seeds.

### Workflow: evidence on the runner, verdict and comment from a hosted job

- `.github/workflows/so101-gate.yml` is triggered only by `push` (this repo's branches except
  `dependabot/**`, on the SO-101 policy, scene, baseline and cache files, the Isaac adapter, the
  paired statistics and comment code, and the workflow itself) and `workflow_dispatch` (with
  `mode: gate | baseline`). Never by `pull_request`, `pull_request_target` or `workflow_run`.
- Job `evaluate` runs on `[self-hosted, Windows, gpu]` with `contents: read` only. It reuses the
  Isaac Lab install that `isaac-render.yml` keeps in the runner's tool cache (built as
  `gh-runner` at the pinned commit; the owner's EULA acceptance is recorded in the workflow,
  [0021](0021-isaac-lab-3-on-windows-without-arena.md)), verifies the course assets and
  episodes by sha256 into a tool-cache `PIPEROBOT_CACHE`, fails fast when less than 3.5 GB of
  GPU memory is free (the owner's desktop uses ~10 GB of 16), runs the evaluator, and uploads the
  evidence as the `so101-gate` artifact. It fails only on an evaluator error (exit 2), never on
  a verdict.
- Job `report` runs on `ubuntu-24.04` and is the only job with a write permission
  (`pull-requests: write`). It decides paired against the committed per-episode baseline,
  renders the comment with `piperobot.reports.paired_comment`, posts it as a sticky comment with
  its own marker (`<!-- piperobot-gate:so101 -->`, next to PushT's) on the open PRs whose head
  is the evaluated commit, and fails on BLOCK. The artifact is treated as untrusted data
  (validated by the results contract, escaped in the comment).
- **No `workflow_run`.** Because the workflow is push-only, only collaborators can trigger it,
  so a second job in the same workflow can hold the write token while the token never reaches
  the home PC. A `workflow_run` reporter would add a trigger that zizmor flags as dangerous,
  cross-run artifact access and a run lookup, for no gain in trust. This reasoning holds only
  while the workflow stays push-only: `tests/test_workflows.py` fails if `so101-gate.yml` gets
  any other trigger, and if any job with a write permission anywhere runs on a self-hosted
  runner.
- The hook's allowlist gains `so101-gate.yml`; the owner redeploys the live copy (elevated, a
  copy and a hash check, no restart).
- **Concurrency**: one group per workflow and branch, `cancel-in-progress: true`, so a newer push
  supersedes an older run of the same branch. No group shared across the GPU workflows: GitHub
  keeps one pending run per group and cancels older pending ones, so a shared group would
  silently drop one branch's queued run when two branches push. The single runner already runs
  one job at a time.
- **Budget**: the evaluator step times out at 32 minutes and the job at 40 (240 in baseline
  mode); the job summary flags a run above the 30-minute Phase 0 budget.
- **Not a required check**: the runner is a PC that can be off, and a required check would then
  block every merge touching these paths.

## Alternatives considered

- **Unpaired against the counts, as pr-gate does**: cannot block this policy at all (above).
- **50 seeds**: about 4 baseline successes; losing all of them gives p = 1/16, so even a total
  collapse would pass.
- **A `pull_request` trigger with the comment posted from the runner**: a fork controls a
  `pull_request` workflow's YAML, and a write token would sit on the home PC.
- **A `workflow_run` reporter**: see above.
- **A shared concurrency group for the GPU**: drops queued runs.
- **Measuring the baseline interactively**: another user, another Kit cache and another session
  can move outcomes; the gate's own conditions are the only valid reference.

## Consequences

- With one worker a gate run takes ~25 min of evaluation plus setup, at the edge of the 30-minute
  budget; two parallel workers, with a registered repeatability test, are the next step.
- A runner that is off leaves the check pending; merges do not wait for it.
- The comment and the check exist only for pushes to this repo's branches; a fork PR gets
  neither until a collaborator pushes its commits to a branch here.
- The gate detects only a total collapse of the replay policy until the scripted policy replaces
  it; the comment states the counts, so a reader can see how little evidence 6 successes carry.
