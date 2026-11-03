# SO-101 baselines

- `scripted-pick-place.json` and `scripted-pick-place-episodes.json`: the gate's baseline, the
  scripted policy on seeds 100000-100099, measured by `so101-gate.yml` in baseline mode on the
  self-hosted runner ([ADR 0036](../../../docs/decisions/0036-so101-gate-scripted-policy-on-100-fixed-seeds.md)):
  78/100 (run 41707984345). All 22 failures are `not_placed`, 16 with wrist_flex at its joint
  limit: the scripted policy's known failure mode, not a gate defect.
- `demo-replay.json` and `demo-replay-episodes.json`: the replay on seeds 0-74 (6/75), the gate's
  baseline until ADR 0036. Kept as the evaluator's acceptance reference and the fallback policy's
  baseline; the gate no longer reads them.
