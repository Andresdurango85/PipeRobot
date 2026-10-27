# 0015. Keep the generic gate core separate from SO-101-specific code

- Status: Accepted
- Date: 2026-10-27

## Context

Most of the gate is not about the SO-101: the statistics, the verdict, the results contract, the
PR report and the comment posting would work for any robot policy evaluated in episodes. The
environments, the policy, the datasets and the scene variations are specific to this arm and task.
Mixing both would make the generic part impossible to reuse for other robots, tasks or teams.

## Decision

- **Generic core** (no SO-101, LeRobot or Isaac imports): `stats/`, `reports/`,
  `eval/results.py`. It depends only on the results contract and the standard library.
- **Robot / task specific**: `envs/`, `policies/`, `eval/mock_eval.py` (and the future Isaac
  Lab-Arena evaluator), `eval/dataset_stats.py`.
- Specific code may import the core; the core never imports specific code. When adding a module,
  decide which side it belongs to first.
- The folders stay as they are for now; when the core needs to ship on its own, it moves to its
  own package without changes in behaviour.

## Alternatives considered

- One flat package: simpler today, but untangling it later costs far more than keeping the line now.
- Split into two packages now: premature while there is a single robot and task.

## Consequences

- `tests/test_architecture.py` enforces the boundary: core modules may not import specific modules
  or robot libraries (LeRobot, Isaac, torch).
- New evaluators only need to write the results contract to reuse everything else.
