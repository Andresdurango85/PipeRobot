# policies

Policy checkpoints or, preferably, links to the Hugging Face Hub (weights are not committed to git).

- `mock-policy.json`: stand-in "policy" for the mock evaluator (`eval/mock_eval.py`), used by the
  tests and for local demos ([ADR 0014](../docs/decisions/0014-mock-evaluator-and-pr-gate-workflow.md)).
  Its `success_rate` drives the simulated outcomes. `pr-gate` no longer evaluates it.
- `pusht-vqbet.json`: the first real policy, `lerobot/vqbet_pusht` pinned to a commit SHA, for
  the PushT simulator ([ADR 0016](../docs/decisions/0016-real-evaluator-lerobot-pusht.md)). Run it
  with `uv sync --extra lerobot --extra sim-pusht` and
  `uv run python -m eval.lerobot_eval --policy policies/pusht-vqbet.json --output out/results.json`
  (~5 min on CPU). Its baseline is `stats/baselines/vqbet-pusht.json`, measured over 500 episodes
  (`--episodes 500`, ~43 min on the laptop CPU). It is the policy `pr-gate` evaluates
  ([ADR 0017](../docs/decisions/0017-pr-gate-pusht-on-github-runners.md)). `config_overrides`
  changes config values without retraining (e.g. `bet_softmax_temperature`); if a change is a
  legitimate new baseline, re-measure `stats/baselines/vqbet-pusht.json` with `baseline.yml`.
