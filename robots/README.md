# robots

One folder per robot whose files are public: data and configuration, little code
([ADR 0019](../docs/decisions/0019-core-adapters-robots-layout.md)). Policy specs point to
checkpoints on the Hugging Face Hub; weights are not committed to git. Baselines are counts plus
provenance, loaded by `piperobot/stats/baseline.py` and always passed explicitly with `--baseline-file`.

## mock

A test fixture, not gated ([ADR 0014](../docs/decisions/0014-mock-evaluator-and-pr-gate-workflow.md)).

- `policy.json`: stand-in "policy" for the mock evaluator (`piperobot/adapters/mock/evaluate.py`), for local demos.
  Its `success_rate` drives the simulated outcomes. `pr-gate` no longer evaluates it.
- `baseline.json`: the mock policy's baseline.

## pusht

The PushT simulator, the task `pr-gate` evaluates
([ADR 0016](../docs/decisions/0016-real-evaluator-lerobot-pusht.md),
[ADR 0017](../docs/decisions/0017-pr-gate-pusht-on-github-runners.md)).

- `policies/vqbet.json`: the first real policy, `lerobot/vqbet_pusht` pinned to a commit SHA. Run
  it with `uv sync --extra lerobot --group sim-pusht` and
  `uv run python -m piperobot.adapters.lerobot.evaluate --policy robots/pusht/policies/vqbet.json --output out/results.json`
  (~5 min on CPU). `config_overrides` changes config values without retraining (e.g.
  `bet_softmax_temperature`).
- `baselines/vqbet.json`: its baseline, measured with `baseline.yml` on the runner type `pr-gate`
  uses (500 episodes, ~43 min on the laptop CPU). If a policy change is a legitimate new baseline,
  re-measure it with `baseline.yml` and commit the counts by PR.

## so101

The SO-101 tube-to-rack task. `envs/` will hold the Isaac Lab 3.0 environment configuration
([ADR 0021](../docs/decisions/0021-isaac-lab-3-on-windows-without-arena.md)). `tools/` holds
developer tools that are not part of the gate: `dataset_stats.py` (Hub dataset metadata) and
`isaac_seed_check.py` (does Isaac Lab reproduce an episode from its seed; runs in the Isaac Lab
env).

The object-free asset check uses `so101/tools/demo_extract.py` (pinned parquet extraction without
videos), `so101/tools/isaac_demo_replay.py` (Isaac Lab 3.0, substeps 2 and 4) and
`so101/tools/demo_replay_report.py` (bare-Python GO / BASE_OFFSET / NO_GO report). Scene data,
unit mapping and fixed analysis rules live in `so101/envs/`.

- `so101/envs/course_assets.json`: pinned course asset manifest and provenance.
- `so101/tools/fetch_course_assets.py`: verified external-cache fetch and offline check.
- `so101/envs/vials_to_rack_success.py`: pure per-episode placement and success tracker.

- `so101/envs/vials_to_rack_scene.py`: nominal Isaac Lab scene without cameras or randomization.
- `so101/envs/vials_to_rack_layout.py`: pure deterministic reconstructed-demo layouts.
- `so101/tools/isaac_mount_compare.py`: verified course/native asset mount comparison.
- `so101/tools/isaac_success_check.py`: registered static sensing checks and demo diagnostics.
- `so101/tools/success_variants.py`: replays dumped tracker inputs under 2/5 N x slot-depth on/off (diagnostic).

- `so101/envs/vials_to_rack_episodes.py`: reusable Isaac reconstructed-episode runtime.
- `so101/envs/repeatability.py`: registered stdlib repeatability and decision rules.
- `so101/tools/isaac_repeatability.py`: one-process Isaac study.
- `so101/tools/repeatability_driver.py`: isolated episode subprocess driver.
- `so101/tools/repeatability_report.py`: portable JSON and Markdown study report.

- `so101/envs/vials_to_rack_task.py`: policy-driven episode task and observation/action contract.
- `so101/envs/vials_to_rack_task.json`: reconstructed-demo evaluation spec.
- `so101/envs/vials_to_rack_randomization.py`: independent seeded scene layouts.
- `so101/policies/demo_replay.py`: open-loop replay policy indexed by demo seed.
- `so101/policies/demo_replay.json`: pinned offline policy inputs and preparation command.
