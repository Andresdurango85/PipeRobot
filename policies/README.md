# policies

Policy checkpoints or, preferably, links to the Hugging Face Hub (weights are not committed to git).

- `mock-policy.json`: stand-in "policy" for the mock evaluator (`eval/mock_eval.py`) until a real
  ACT policy runs in Isaac Lab-Arena ([ADR 0014](../docs/decisions/0014-mock-evaluator-and-pr-gate-workflow.md)).
  Its `success_rate` drives the simulated outcomes: lowering it in a PR simulates a regression,
  which `pr-gate` must block. If a change is a legitimate new baseline, regenerate
  `stats/baseline.json` in the same PR.
