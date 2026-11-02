# 0022. SO-101 hardware deps as a group, no Hub uploads, Developer Mode, manual outcomes

- Status: Accepted
- Date: 2026-11-01

## Context

The [SO-101 bring-up runbook](../knowledge/so101-bringup.md) found four gaps before the arm's
electronics arrive:

- No hardware command runs with the repo's environments: LeRobot 0.6.1 needs its `feetech`,
  `hardware`, `viz` and `training` extras (serial and motor SDKs, `pynput`, Rerun, `accelerate`
  and `wandb`), and neither the `lerobot` extra nor the `sim-pusht` group includes them.
- `lerobot-record`, `lerobot-rollout` (dataset) and `lerobot-train` (policy) push to the Hugging
  Face Hub by default. A recorded dataset holds camera video of the room, and this is a public
  project.
- On Windows `lerobot-train` points `checkpoints\last` at each checkpoint with a symlink, which
  fails with `WinError 1314` without Developer Mode or an elevated shell, hours into a run.
- Nothing in LeRobot 0.6.1 scores an episode on the real arm, yet Phase 0 needs a 20-attempt
  real-arm figure next to the simulation one, and the gate only reads the results contract
  (`piperobot/results.py`), whose episodes need unique integer seeds. A real arm has no seeds.

## Decision

1. **The hardware deps are an `so101` dependency group** in `pyproject.toml`:
   `lerobot[feetech,hardware,viz,training]>=0.6.1,<0.7`, locked in `uv.lock` and installed with
   `uv sync --group so101`. Groups are not published, so no robot-named extra reaches the
   `piperobot` package ([ADR 0019](0019-core-adapters-robots-layout.md)). The lock adds 27 small
   packages and no CUDA wheels; torch stays CPU-only on Linux
   ([ADR 0017](0017-pr-gate-pusht-on-github-runners.md)) and the Pillow override still applies
   ([ADR 0012](0012-dependency-vulnerability-triage.md)).
2. **Nothing recorded on the real arm is uploaded to the Hub.** Every `lerobot-record` and
   `lerobot-rollout` command passes `--dataset.push_to_hub=false`, every `lerobot-train`
   command passes `--policy.push_to_hub=false`, and datasets live outside the git repo. Camera
   (and any audio) data never goes public; publishing one later is a separate, deliberate decision.
3. **Windows Developer Mode is enabled on the training PC**, by Andrés, before the first
   training run, so `lerobot-train` can create its symlinks without an elevated shell.
4. **Real-arm outcomes are recorded by hand and converted by a manual adapter.** The operator
   fills a CSV per run (`attempt`, `success`, optional `failure`, `scene`, `video_url`), and
   `python -m piperobot.adapters.manual.evaluate` turns it into the results contract with
   `evaluator: "manual"`. **The seed of each episode is its attempt number**: on real hardware
   it labels the episode and is not a reproducibility handle. Attempts must be exactly 1..N, so a
   missing or duplicated row fails loudly ([ADR 0009](0009-fail-loudly-on-unusable-data.md))
   instead of silently dropping a failure. The adapter uses only the standard library and names
   no robot, so other robots use it as is.

## Alternatives considered

- An `so101` optional extra: it would be published with the package and put a robot name in it,
  against ADR 0019.
- Folding the hardware extras into the `lerobot` extra: every CI job and every user of the
  package would install serial, keyboard and training tooling it never uses.
- Pushing datasets to a private Hub repo: still uploads room video to a third party, and needs
  tokens on each machine; local datasets are enough for a single-machine Phase 0.
- Running training from an elevated shell instead of Developer Mode: works, but then every
  training run (and anything it launches) runs as administrator.
- Patching LeRobot to copy instead of symlink: a local fork of a pinned dependency, lost on every
  upgrade.
- A null or negative seed for real-arm episodes: needs a contract change, and the core, the
  comment and every evaluator would have to handle a second kind of episode. A synthetic seed
  from a hash of the date and attempt: unique, but meaningless to the operator reading the
  comment.
- Scoring real-arm episodes automatically (a success detector on the camera): a project of its
  own; 20 attempts judged by hand are enough for Phase 0.

## Consequences

- `uv sync` is exact: syncing only `--group so101` removes the `lerobot` extra or the `sim-pusht`
  group if they were installed. Pass every group and extra the machine needs.
- The training venv still needs the CUDA build of torch swapped in after syncing, as
  `gpu-smoke.yml` does; the lock keeps CPU-only torch on Windows.
- Forgetting `push_to_hub=false` on a new command uploads data. The runbook shows it on every
  command; review new commands for it.
- A real-arm baseline does not exist yet. The first real run's results can become one under
  `robots/so101/baselines/`, or a run can be compared with counts (`--candidate 14/20`).
- Hand-judged success is only as consistent as the operator's criteria: write the success rule
  for the task down before the first run, and keep it fixed between runs that are compared.
