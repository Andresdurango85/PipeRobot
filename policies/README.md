# policies

Policy checkpoints or, preferably, links to the Hugging Face Hub (weights are not committed to git).

- `mock-policy.json`: stand-in "policy" for the mock evaluator (`eval/mock_eval.py`) until a real
  ACT policy runs in Isaac Lab-Arena ([ADR 0014](../docs/decisions/0014-mock-evaluator-and-pr-gate-workflow.md)).
  Its `success_rate` drives the simulated outcomes: lowering it in a PR simulates a regression,
  which `pr-gate` must block. If a change is a legitimate new baseline, regenerate
  `stats/baseline.json` in the same PR.
- `pusht-vqbet.json`: the first real policy, `lerobot/vqbet_pusht` pinned to a commit SHA, for
  the PushT simulator ([ADR 0016](../docs/decisions/0016-real-evaluator-lerobot-pusht.md)). Run it
  with `uv sync --extra lerobot --extra sim-pusht` and
  `uv run python -m eval.lerobot_eval --policy policies/pusht-vqbet.json --output out/results.json`
  (~5 min on CPU). Its baseline is `stats/baselines/vqbet-pusht.json`, measured over 500 episodes
  (`--episodes 500`, ~43 min).
