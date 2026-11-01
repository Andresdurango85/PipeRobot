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

The SO-101 tube-to-rack task. `envs/` will hold the Isaac Lab / Isaac Lab-Arena environment
configuration.
